#!/usr/bin/env python3
"""Database healing tool for smart_selection database.

This tool detects and fixes discrepancies between the filesystem and database
without requiring a full reindex. It handles:

1. Folder consolidation - merge folders with exclusion terms into clean folders
2. Source ID updates - update image source_ids to match new folder names
3. Orphan cleanup - remove database entries for files that no longer exist
4. Source merging - combine stats from duplicate sources

Usage:
    python tools/heal_database.py --dry-run  # Show what would be done
    python tools/heal_database.py            # Actually perform changes
"""

import argparse
import os
import re
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def load_exclusions_from_config() -> List[str]:
    """Load exclusion terms from Variety config file."""
    config_path = os.path.expanduser("~/.config/variety/variety.conf")
    exclusions = []
    try:
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith("wallhaven_exclusions"):
                    # Parse format: "True|term1;True|term2;..."
                    value = line.split("=", 1)[1].strip()
                    for item in value.split(";"):
                        if "|" in item:
                            parts = item.split("|", 1)
                            if parts[0].strip().lower() == "true" and len(parts) > 1:
                                exclusions.append(parts[1].strip())
                    break
    except Exception:
        pass
    return exclusions


def build_exclusion_pattern(exclusions: List[str]) -> re.Pattern:
    """Build a regex pattern to match exclusion suffixes in folder names.

    Exclusions like "anime girls" become folder suffix "_anime_girls"
    (spaces converted to underscores by Util.convert_to_filename).

    Also handles partial remnants from incorrectly parsed multi-word exclusions,
    e.g., "anime girls" that became "_girls" when only "-anime" was stripped.
    """
    if not exclusions:
        # Fallback to common patterns if no config found
        return re.compile(r"(__anime__sexy__nsfw__furry(__anime_girls)?|_girls)$")

    # Build pattern from exclusion terms
    patterns = []
    for term in exclusions:
        # Convert to filename format (spaces to underscores, lowercased)
        folder_suffix = "_" + term.lower().replace(" ", "_")
        patterns.append(re.escape(folder_suffix))

        # For multi-word exclusions like "anime girls", also add each word
        # as a separate pattern to catch remnants like "_girls"
        words = term.lower().split()
        if len(words) > 1:
            for word in words:
                patterns.append(re.escape("_" + word))

    # Remove duplicates while preserving order
    seen = set()
    unique_patterns = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique_patterns.append(p)

    # Match any combination of these suffixes at the end
    # Use non-capturing group for efficiency
    pattern_str = "(?:" + "|".join(unique_patterns) + ")+$"
    return re.compile(pattern_str)


class DatabaseHealer:
    """Heals discrepancies between filesystem and database."""

    def __init__(self, db_path: str, download_dir: str, dry_run: bool = True):
        self.db_path = db_path
        self.download_dir = download_dir
        self.dry_run = dry_run
        self.conn = None
        self.stats = {
            "folders_renamed": 0,
            "images_moved": 0,
            "source_ids_updated": 0,
            "orphans_removed": 0,
            "sources_merged": 0,
        }
        # Load exclusion pattern from config
        self.exclusions = load_exclusions_from_config()
        self.exclusion_pattern = build_exclusion_pattern(self.exclusions)
        if self.exclusions:
            print(f"Loaded {len(self.exclusions)} exclusion terms from config")
            print(f"  Pattern: {self.exclusion_pattern.pattern}")

    def connect(self):
        """Connect to the database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_clean_source_id(self, source_id: str) -> str:
        """Strip exclusion terms from source_id to get the clean version."""
        clean = self.exclusion_pattern.sub("", source_id)
        return clean

    def find_dirty_folders(self) -> List[Tuple[str, str]]:
        """Find folders with exclusion terms and their clean counterparts.

        Returns:
            List of (dirty_path, clean_path) tuples
        """
        dirty_folders = []
        download_path = Path(self.download_dir)

        if not download_path.exists():
            print(f"Download directory not found: {self.download_dir}")
            return dirty_folders

        for folder in download_path.iterdir():
            if not folder.is_dir():
                continue

            folder_name = folder.name
            clean_name = self.exclusion_pattern.sub("", folder_name)

            if clean_name != folder_name:
                clean_path = folder.parent / clean_name
                dirty_folders.append((str(folder), str(clean_path)))

        return dirty_folders

    def consolidate_folders(self, dirty_path: str, clean_path: str) -> List[Tuple[str, str]]:
        """Move images from dirty folder to clean folder.

        Returns:
            List of (old_filepath, new_filepath) for moved files
        """
        moved_files = []
        dirty = Path(dirty_path)
        clean = Path(clean_path)

        if not dirty.exists():
            return moved_files

        # Create clean folder if it doesn't exist
        if not clean.exists():
            if self.dry_run:
                print(f"  Would create: {clean}")
            else:
                clean.mkdir(parents=True)
                print(f"  Created: {clean}")

        # Move all image files
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        for file in dirty.iterdir():
            if file.suffix.lower() in image_extensions:
                new_path = clean / file.name

                # Handle name conflicts
                if new_path.exists():
                    base = file.stem
                    suffix = file.suffix
                    counter = 1
                    while new_path.exists():
                        new_path = clean / f"{base}_{counter}{suffix}"
                        counter += 1

                if self.dry_run:
                    print(f"  Would move: {file.name} -> {new_path}")
                else:
                    shutil.move(str(file), str(new_path))
                    print(f"  Moved: {file.name}")

                moved_files.append((str(file), str(new_path)))
                self.stats["images_moved"] += 1

        # Also move state.json if present
        state_file = dirty / "state.json"
        if state_file.exists():
            target_state = clean / "state.json"
            if not target_state.exists():
                if self.dry_run:
                    print(f"  Would move: state.json -> {target_state}")
                else:
                    shutil.move(str(state_file), str(target_state))

        # Remove the now-empty dirty folder
        if not self.dry_run:
            try:
                # Check if folder is empty or only has state.json left
                remaining = list(dirty.iterdir())
                # If only state.json remains and we didn't move it (because target had one), delete it
                if len(remaining) == 1 and remaining[0].name == "state.json":
                    remaining[0].unlink()
                    print(f"  Removed orphaned state.json from: {dirty.name}")
                    remaining = []
                if not remaining:
                    dirty.rmdir()
                    print(f"  Removed empty folder: {dirty}")
            except Exception as e:
                print(f"  Warning: Could not remove folder {dirty}: {e}")

        return moved_files

    def update_image_paths(self, moved_files: List[Tuple[str, str]]):
        """Update image filepaths in database after moving files."""
        if not moved_files:
            return

        for old_path, new_path in moved_files:
            new_source_id = Path(new_path).parent.name

            if self.dry_run:
                print(f"  Would update DB: {old_path} -> {new_path}, source_id={new_source_id}")
            else:
                # Check if new_path already exists in DB (duplicate)
                existing = self.conn.execute(
                    "SELECT filepath FROM images WHERE filepath = ?",
                    (new_path,)
                ).fetchone()

                if existing:
                    # New path already exists - delete the old entry instead of updating
                    # The file was already moved, so just clean up the old DB record
                    self.conn.execute("DELETE FROM images WHERE filepath = ?", (old_path,))
                    self.conn.execute("DELETE FROM image_metadata WHERE filepath = ?", (old_path,))
                    self.conn.execute("DELETE FROM palettes WHERE filepath = ?", (old_path,))
                    self.conn.execute("DELETE FROM image_tags WHERE filepath = ?", (old_path,))
                    self.conn.execute("DELETE FROM user_actions WHERE filepath = ?", (old_path,))
                    print(f"    Removed duplicate DB entry: {Path(old_path).name}")
                else:
                    cursor = self.conn.execute(
                        """
                        UPDATE images
                        SET filepath = ?, filename = ?, source_id = ?
                        WHERE filepath = ?
                        """,
                        (new_path, Path(new_path).name, new_source_id, old_path)
                    )

                    # Also update related tables
                    self.conn.execute(
                        "UPDATE image_metadata SET filepath = ? WHERE filepath = ?",
                        (new_path, old_path)
                    )
                    self.conn.execute(
                        "UPDATE palettes SET filepath = ? WHERE filepath = ?",
                        (new_path, old_path)
                    )
                    self.conn.execute(
                        "UPDATE image_tags SET filepath = ? WHERE filepath = ?",
                        (new_path, old_path)
                    )
                    self.conn.execute(
                        "UPDATE user_actions SET filepath = ? WHERE filepath = ?",
                        (new_path, old_path)
                    )

                    if cursor.rowcount > 0:
                        self.stats["source_ids_updated"] += 1

        if not self.dry_run:
            self.conn.commit()

    def update_source_ids_in_place(self):
        """Update source_ids for images that haven't been moved but have dirty source_ids."""
        cursor = self.conn.execute("SELECT DISTINCT source_id FROM images")
        dirty_source_ids = []

        for row in cursor:
            source_id = row["source_id"]
            clean_id = self.get_clean_source_id(source_id)
            if clean_id != source_id:
                dirty_source_ids.append((source_id, clean_id))

        for dirty_id, clean_id in dirty_source_ids:
            # Get count of affected images
            cursor = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM images WHERE source_id = ?",
                (dirty_id,)
            )
            count = cursor.fetchone()["cnt"]

            if self.dry_run:
                print(f"  Would update {count} images: source_id '{dirty_id}' -> '{clean_id}'")
            else:
                self.conn.execute(
                    "UPDATE images SET source_id = ? WHERE source_id = ?",
                    (clean_id, dirty_id)
                )
                self.stats["source_ids_updated"] += count
                print(f"  Updated {count} images: source_id '{dirty_id}' -> '{clean_id}'")

        if not self.dry_run:
            self.conn.commit()

    def merge_sources(self):
        """Merge duplicate sources (dirty and clean versions) into one."""
        # Find sources that should be merged
        cursor = self.conn.execute("SELECT source_id, source_type, times_shown FROM sources")
        sources = {}
        for row in cursor:
            source_id = row["source_id"]
            clean_id = self.get_clean_source_id(source_id)

            if clean_id not in sources:
                sources[clean_id] = []
            sources[clean_id].append({
                "source_id": source_id,
                "source_type": row["source_type"],
                "times_shown": row["times_shown"] or 0,
            })

        for clean_id, variants in sources.items():
            if len(variants) <= 1:
                continue

            # Sum times_shown from all variants
            total_times_shown = sum(v["times_shown"] for v in variants)
            source_type = variants[0]["source_type"]

            dirty_ids = [v["source_id"] for v in variants if v["source_id"] != clean_id]

            if self.dry_run:
                print(f"  Would merge sources: {dirty_ids} -> '{clean_id}' (total times_shown: {total_times_shown})")
            else:
                # Delete dirty source entries
                for dirty_id in dirty_ids:
                    self.conn.execute("DELETE FROM sources WHERE source_id = ?", (dirty_id,))
                    self.stats["sources_merged"] += 1

                # Upsert clean source with combined stats
                self.conn.execute(
                    """
                    INSERT INTO sources (source_id, source_type, times_shown)
                    VALUES (?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        times_shown = times_shown + excluded.times_shown
                    """,
                    (clean_id, source_type, total_times_shown)
                )
                print(f"  Merged sources: {dirty_ids} -> '{clean_id}'")

        if not self.dry_run:
            self.conn.commit()

    def remove_orphaned_images(self):
        """Remove database entries for images that no longer exist on disk."""
        cursor = self.conn.execute("SELECT filepath FROM images")
        orphans = []

        for row in cursor:
            filepath = row["filepath"]
            if not os.path.exists(filepath):
                orphans.append(filepath)

        if not orphans:
            print("  No orphaned images found")
            return

        print(f"  Found {len(orphans)} orphaned images")

        for filepath in orphans[:10]:  # Show first 10
            print(f"    - {filepath}")
        if len(orphans) > 10:
            print(f"    ... and {len(orphans) - 10} more")

        if self.dry_run:
            print(f"  Would remove {len(orphans)} orphaned images from database")
        else:
            for filepath in orphans:
                self.conn.execute("DELETE FROM images WHERE filepath = ?", (filepath,))
                self.conn.execute("DELETE FROM image_metadata WHERE filepath = ?", (filepath,))
                self.conn.execute("DELETE FROM palettes WHERE filepath = ?", (filepath,))
                self.conn.execute("DELETE FROM image_tags WHERE filepath = ?", (filepath,))
                self.conn.execute("DELETE FROM user_actions WHERE filepath = ?", (filepath,))
                self.stats["orphans_removed"] += 1

            self.conn.commit()
            print(f"  Removed {len(orphans)} orphaned images from database")

    def remove_orphaned_sources(self):
        """Remove sources that have no images."""
        if self.dry_run:
            cursor = self.conn.execute(
                """
                SELECT s.source_id
                FROM sources s
                LEFT JOIN images i ON s.source_id = i.source_id
                WHERE i.filepath IS NULL
                """
            )
            orphans = [row["source_id"] for row in cursor]
            if orphans:
                print(f"  Would remove {len(orphans)} orphaned sources: {orphans[:5]}")
        else:
            self.conn.execute(
                """
                DELETE FROM sources
                WHERE source_id NOT IN (SELECT DISTINCT source_id FROM images WHERE source_id IS NOT NULL)
                """
            )
            self.conn.commit()

    def heal(self):
        """Run the full healing process."""
        print(f"\n{'='*60}")
        print(f"Database Healing {'(DRY RUN)' if self.dry_run else ''}")
        print(f"{'='*60}")
        print(f"Database: {self.db_path}")
        print(f"Download dir: {self.download_dir}")
        print()

        self.connect()

        try:
            # Step 1: Find and consolidate dirty folders
            print("Step 1: Finding folders with exclusion terms...")
            dirty_folders = self.find_dirty_folders()

            if dirty_folders:
                print(f"  Found {len(dirty_folders)} folders to consolidate")
                for dirty_path, clean_path in dirty_folders:
                    dirty_name = Path(dirty_path).name
                    clean_name = Path(clean_path).name
                    print(f"\n  Processing: {dirty_name} -> {clean_name}")

                    moved_files = self.consolidate_folders(dirty_path, clean_path)
                    self.update_image_paths(moved_files)
                    self.stats["folders_renamed"] += 1
            else:
                print("  No dirty folders found")

            # Step 2: Update remaining source_ids in database
            print("\nStep 2: Updating source_ids in database...")
            self.update_source_ids_in_place()

            # Step 3: Merge duplicate sources
            print("\nStep 3: Merging duplicate sources...")
            self.merge_sources()

            # Step 4: Remove orphaned images
            print("\nStep 4: Removing orphaned images...")
            self.remove_orphaned_images()

            # Step 5: Remove orphaned sources
            print("\nStep 5: Removing orphaned sources...")
            self.remove_orphaned_sources()

            # Summary
            print(f"\n{'='*60}")
            print("Summary")
            print(f"{'='*60}")
            for key, value in self.stats.items():
                print(f"  {key}: {value}")

            if self.dry_run:
                print("\n  *** This was a dry run. No changes were made. ***")
                print("  Run without --dry-run to apply changes.")

        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(
        description="Heal discrepancies between filesystem and smart_selection database"
    )
    parser.add_argument(
        "--db",
        default=os.path.expanduser("~/.config/variety/smart_selection.db"),
        help="Path to smart_selection database"
    )
    parser.add_argument(
        "--download-dir",
        default=os.path.expanduser("~/Pictures/Wallpapers/Downloaded by Variety"),
        help="Path to Variety download directory"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    healer = DatabaseHealer(
        db_path=args.db,
        download_dir=args.download_dir,
        dry_run=args.dry_run,
    )
    healer.heal()


if __name__ == "__main__":
    main()
