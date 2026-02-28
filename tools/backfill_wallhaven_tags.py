#!/usr/bin/env python3
"""Backfill Wallhaven tag data for images missing tags in the database.

This script fetches tag metadata from the Wallhaven API for images that
don't have tags stored in the smart_selection database.

Usage:
    python tools/backfill_wallhaven_tags.py                    # Process all
    python tools/backfill_wallhaven_tags.py --limit 50         # Process 50 images
    python tools/backfill_wallhaven_tags.py --dry-run          # Show what would be done
    python tools/backfill_wallhaven_tags.py --rate 20          # 20 requests/minute
"""

import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Wallhaven API endpoint for wallpaper info
WALLPAPER_INFO_URL = "https://wallhaven.cc/api/v1/w/{}"

# Regex to extract wallhaven ID from filename
# Matches: wallhaven-XXXXXX.jpg, wallhaven-XXXXXX_1.jpg, etc.
WALLHAVEN_ID_PATTERN = re.compile(r"wallhaven-([a-z0-9]+)(?:_\d+)?\.", re.IGNORECASE)


class WallhavenBackfiller:
    """Backfills Wallhaven tag data for images in the database."""

    def __init__(
        self,
        db_path: str,
        api_key: Optional[str] = None,
        rate_limit: int = 10,
        dry_run: bool = False,
    ):
        self.db_path = db_path
        self.api_key = api_key
        self.rate_limit = rate_limit
        self.delay = 60.0 / rate_limit  # seconds between requests
        self.dry_run = dry_run
        self.conn = None
        self.session = requests.Session()

        # Stats
        self.stats = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "tags_added": 0,
        }

    def connect(self):
        """Connect to the database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_images_without_tags(self, limit: Optional[int] = None) -> List[Dict]:
        """Find Wallhaven images that don't have tags in the database."""
        query = """
            SELECT i.filepath, i.filename, i.source_id
            FROM images i
            WHERE i.source_id LIKE 'wallhaven_%'
            AND NOT EXISTS (
                SELECT 1 FROM image_tags it WHERE it.filepath = i.filepath
            )
            ORDER BY i.filepath
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor = self.conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def extract_wallhaven_id(self, filename: str) -> Optional[str]:
        """Extract the Wallhaven ID from a filename."""
        match = WALLHAVEN_ID_PATTERN.search(filename)
        return match.group(1) if match else None

    def fetch_wallpaper_info(self, wallhaven_id: str) -> Optional[Dict]:
        """Fetch wallpaper info from the Wallhaven API."""
        url = WALLPAPER_INFO_URL.format(wallhaven_id)

        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"    Not found: {wallhaven_id}")
            elif e.response.status_code == 401:
                print(f"    Unauthorized (bad API key or NSFW content): {wallhaven_id}")
            elif e.response.status_code == 429:
                print(f"    Rate limited! Waiting 60 seconds...")
                time.sleep(60)
                return self.fetch_wallpaper_info(wallhaven_id)  # Retry
            else:
                print(f"    HTTP error {e.response.status_code}: {wallhaven_id}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"    Request error: {e}")
            return None

    def upsert_tags(self, tags: List[Dict]) -> List[int]:
        """Insert or update tags in the database."""
        if not tags:
            return []

        cursor = self.conn.cursor()
        cursor.executemany(
            """
            INSERT INTO tags (tag_id, name, alias, category, purity)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tag_id) DO UPDATE SET
                name = excluded.name,
                alias = COALESCE(excluded.alias, alias),
                category = COALESCE(excluded.category, category),
                purity = COALESCE(excluded.purity, purity)
            """,
            [
                (t["id"], t["name"], t.get("alias"), t.get("category"), t.get("purity"))
                for t in tags
            ],
        )
        self.conn.commit()
        return [t["id"] for t in tags]

    def link_image_tags(self, filepath: str, tag_ids: List[int]):
        """Link an image to tags."""
        if not tag_ids:
            return

        cursor = self.conn.cursor()
        # Remove existing links (shouldn't be any, but just in case)
        cursor.execute("DELETE FROM image_tags WHERE filepath = ?", (filepath,))
        # Add new links
        cursor.executemany(
            "INSERT OR IGNORE INTO image_tags (filepath, tag_id) VALUES (?, ?)",
            [(filepath, tag_id) for tag_id in tag_ids],
        )
        self.conn.commit()

    def update_image_metadata(self, filepath: str, data: Dict):
        """Update image_metadata table with additional info."""
        cursor = self.conn.cursor()

        # Parse created_at to Unix timestamp
        uploaded_at = None
        created_at = data.get("created_at")
        if created_at:
            try:
                from datetime import datetime
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                uploaded_at = int(dt.timestamp())
            except (ValueError, TypeError):
                pass

        uploader = data.get("uploader", {})

        cursor.execute(
            """
            INSERT INTO image_metadata (filepath, category, purity, uploader, views, favorites, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(filepath) DO UPDATE SET
                category = COALESCE(excluded.category, category),
                purity = COALESCE(excluded.purity, purity),
                uploader = COALESCE(excluded.uploader, uploader),
                views = COALESCE(excluded.views, views),
                favorites = COALESCE(excluded.favorites, favorites),
                uploaded_at = COALESCE(excluded.uploaded_at, uploaded_at)
            """,
            (
                filepath,
                data.get("category"),
                data.get("purity"),
                uploader.get("username") if uploader else None,
                data.get("views"),
                data.get("favorites"),
                uploaded_at,
            ),
        )
        self.conn.commit()

    def process_image(self, image: Dict) -> bool:
        """Process a single image - fetch and store tag data."""
        filepath = image["filepath"]
        filename = image["filename"]

        # Extract Wallhaven ID
        wallhaven_id = self.extract_wallhaven_id(filename)
        if not wallhaven_id:
            print(f"  Skipping (no ID): {filename}")
            self.stats["skipped"] += 1
            return False

        print(f"  Fetching: {wallhaven_id} ({filename})")

        if self.dry_run:
            self.stats["success"] += 1
            return True

        # Fetch from API
        result = self.fetch_wallpaper_info(wallhaven_id)
        if not result or "data" not in result:
            self.stats["failed"] += 1
            return False

        data = result["data"]
        tags = data.get("tags", [])

        if tags:
            # Upsert tags
            tag_ids = self.upsert_tags(tags)
            # Link to image
            self.link_image_tags(filepath, tag_ids)
            self.stats["tags_added"] += len(tags)
            print(f"    Added {len(tags)} tags")
        else:
            print(f"    No tags found")

        # Update metadata
        self.update_image_metadata(filepath, data)

        self.stats["success"] += 1
        return True

    def run(self, limit: Optional[int] = None):
        """Run the backfill process."""
        print("=" * 60)
        print("Wallhaven Tag Backfill")
        print("=" * 60)
        print(f"Database: {self.db_path}")
        print(f"Rate limit: {self.rate_limit} requests/minute")
        print(f"Delay between requests: {self.delay:.1f} seconds")
        if self.api_key:
            print(f"API key: ***{self.api_key[-4:]}")
        else:
            print("API key: None (NSFW images will fail)")
        if self.dry_run:
            print("Mode: DRY RUN")
        print()

        self.connect()

        try:
            # Find images without tags
            images = self.get_images_without_tags(limit)
            total = len(images)
            print(f"Found {total} images without tags")

            if total == 0:
                print("Nothing to do!")
                return

            # Estimate time
            estimated_minutes = (total * self.delay) / 60
            print(f"Estimated time: {estimated_minutes:.1f} minutes")
            print()

            # Process each image
            for i, image in enumerate(images, 1):
                self.stats["processed"] += 1
                print(f"[{i}/{total}] Processing...")

                self.process_image(image)

                # Rate limiting (except for last item)
                if i < total and not self.dry_run:
                    time.sleep(self.delay)

            print()
            print("=" * 60)
            print("Summary")
            print("=" * 60)
            for key, value in self.stats.items():
                print(f"  {key}: {value}")

        finally:
            self.close()


def get_api_key_from_config() -> Optional[str]:
    """Try to read Wallhaven API key from Variety config."""
    config_path = os.path.expanduser("~/.config/variety/variety.conf")
    try:
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith("wallhaven_api_key"):
                    value = line.split("=", 1)[1].strip()
                    if value and value != '""' and value != "''":
                        return value.strip('"\'')
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Wallhaven tag data for images in the database"
    )
    parser.add_argument(
        "--db",
        default=os.path.expanduser("~/.config/variety/smart_selection.db"),
        help="Path to smart_selection database",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Wallhaven API key (reads from variety.conf if not provided)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=10,
        help="API requests per minute (default: 10)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of images to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or get_api_key_from_config()

    backfiller = WallhavenBackfiller(
        db_path=args.db,
        api_key=api_key,
        rate_limit=args.rate,
        dry_run=args.dry_run,
    )

    try:
        backfiller.run(limit=args.limit)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print(f"Processed: {backfiller.stats['processed']}")
        print(f"Success: {backfiller.stats['success']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
