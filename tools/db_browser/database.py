# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Database access layer for the browser.

Provides read operations for browsing and limited write operations
for favorite/trash actions. Uses the same SQLite database as Variety's
Smart Selection Engine.
"""

import sqlite3
import threading
import time
import os
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager

from .models import (
    ImageResponse,
    SourceResponse,
    TagResponse,
    PaletteResponse,
)


class DatabaseBrowser:
    """Read-focused database access for the web browser.

    Thread-safe via RLock. Supports both read-only and read-write modes.
    """

    EXPECTED_SCHEMA_VERSION = 6

    def __init__(self, db_path: str, readonly: bool = False):
        """Initialize database connection.

        Args:
            db_path: Path to the SQLite database file.
            readonly: If True, open in read-only mode (safer for browsing).
        """
        self.db_path = db_path
        self.readonly = readonly
        self._lock = threading.RLock()

        # Build connection URI
        if readonly:
            uri = f"file:{db_path}?mode=ro"
        else:
            uri = f"file:{db_path}?mode=rw"

        self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrent access
        if not readonly:
            self.conn.execute("PRAGMA journal_mode=WAL")

        # Verify schema version
        self._check_schema_version()

    def _check_schema_version(self) -> None:
        """Verify database schema version is compatible."""
        try:
            cursor = self.conn.execute(
                "SELECT version FROM schema_info LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                version = row["version"]
                if version > self.EXPECTED_SCHEMA_VERSION:
                    import warnings
                    warnings.warn(
                        f"Database schema version {version} is newer than "
                        f"expected {self.EXPECTED_SCHEMA_VERSION}. "
                        "Some features may not work correctly."
                    )
        except sqlite3.OperationalError:
            # Table doesn't exist - old schema or empty DB
            pass

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # --- Read Operations ---

    def get_image_count(self) -> int:
        """Get total number of images."""
        with self._lock:
            cursor = self.conn.execute("SELECT COUNT(*) FROM images")
            return cursor.fetchone()[0]

    def get_source_count(self) -> int:
        """Get total number of sources."""
        with self._lock:
            cursor = self.conn.execute("SELECT COUNT(*) FROM sources")
            return cursor.fetchone()[0]

    def get_images(
        self,
        page: int = 1,
        page_size: int = 24,
        source_id: Optional[str] = None,
        tag_name: Optional[str] = None,
        purity: Optional[str] = None,
        favorites_only: bool = False,
        search: Optional[str] = None,
        sort_by: str = "last_indexed_at",
        sort_desc: bool = True,
    ) -> Tuple[List[ImageResponse], int]:
        """Get paginated list of images with optional filters.

        Returns:
            Tuple of (images, total_count)
        """
        with self._lock:
            # Build query
            base_query = """
                SELECT DISTINCT
                    i.filepath, i.filename, i.source_id,
                    i.width, i.height, i.aspect_ratio, i.file_size,
                    i.is_favorite, i.times_shown, i.last_shown_at,
                    i.palette_status,
                    m.category, m.purity, m.source_url, m.uploader, m.views
                FROM images i
                LEFT JOIN image_metadata m ON i.filepath = m.filepath
            """
            count_query = """
                SELECT COUNT(DISTINCT i.filepath)
                FROM images i
                LEFT JOIN image_metadata m ON i.filepath = m.filepath
            """

            conditions = []
            params: List[Any] = []

            # Tag filter requires join
            if tag_name:
                base_query += """
                    JOIN image_tags it ON i.filepath = it.filepath
                    JOIN tags t ON it.tag_id = t.tag_id
                """
                count_query += """
                    JOIN image_tags it ON i.filepath = it.filepath
                    JOIN tags t ON it.tag_id = t.tag_id
                """
                conditions.append("t.name = ?")
                params.append(tag_name)

            # Other filters
            if source_id:
                conditions.append("i.source_id = ?")
                params.append(source_id)

            if purity:
                conditions.append("m.purity = ?")
                params.append(purity)

            if favorites_only:
                conditions.append("i.is_favorite = 1")

            if search:
                conditions.append("(i.filename LIKE ? OR i.filepath LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])

            # Apply conditions
            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)
                base_query += where_clause
                count_query += where_clause

            # Get total count
            cursor = self.conn.execute(count_query, params)
            total = cursor.fetchone()[0]

            # Apply sorting
            valid_sort_columns = {
                "last_indexed_at": "i.first_indexed_at",
                "filename": "i.filename",
                "times_shown": "i.times_shown",
                "last_shown_at": "i.last_shown_at",
                "file_size": "i.file_size",
            }
            sort_col = valid_sort_columns.get(sort_by, "i.first_indexed_at")
            sort_order = "DESC" if sort_desc else "ASC"
            base_query += f" ORDER BY {sort_col} {sort_order}"

            # Apply pagination
            offset = (page - 1) * page_size
            base_query += " LIMIT ? OFFSET ?"
            params.extend([page_size, offset])

            # Execute
            cursor = self.conn.execute(base_query, params)
            rows = cursor.fetchall()

            images = [self._row_to_image(row) for row in rows]
            return images, total

    def get_image(self, filepath: str) -> Optional[ImageResponse]:
        """Get a single image by filepath."""
        with self._lock:
            cursor = self.conn.execute(
                """
                SELECT
                    i.filepath, i.filename, i.source_id,
                    i.width, i.height, i.aspect_ratio, i.file_size,
                    i.is_favorite, i.times_shown, i.last_shown_at,
                    i.palette_status,
                    m.category, m.purity, m.source_url, m.uploader, m.views
                FROM images i
                LEFT JOIN image_metadata m ON i.filepath = m.filepath
                WHERE i.filepath = ?
                """,
                (filepath,),
            )
            row = cursor.fetchone()
            return self._row_to_image(row) if row else None

    def image_exists(self, filepath: str) -> bool:
        """Check if an image exists in the database."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT 1 FROM images WHERE filepath = ?", (filepath,)
            )
            return cursor.fetchone() is not None

    def get_sources(self) -> List[SourceResponse]:
        """Get all sources with image counts."""
        with self._lock:
            cursor = self.conn.execute(
                """
                SELECT
                    s.source_id, s.source_type, s.times_shown,
                    COUNT(i.filepath) as image_count
                FROM sources s
                LEFT JOIN images i ON s.source_id = i.source_id
                GROUP BY s.source_id
                ORDER BY image_count DESC
                """
            )
            return [
                SourceResponse(
                    source_id=row["source_id"],
                    source_type=row["source_type"],
                    times_shown=row["times_shown"] or 0,
                    image_count=row["image_count"],
                )
                for row in cursor.fetchall()
            ]

    def get_tags(self, limit: int = 100) -> List[TagResponse]:
        """Get tags with usage counts, ordered by popularity."""
        with self._lock:
            cursor = self.conn.execute(
                """
                SELECT t.tag_id, t.name, t.category, COUNT(it.filepath) as count
                FROM tags t
                JOIN image_tags it ON t.tag_id = it.tag_id
                GROUP BY t.tag_id
                ORDER BY count DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [
                TagResponse(
                    tag_id=row["tag_id"],
                    name=row["name"],
                    category=row["category"],
                    count=row["count"],
                )
                for row in cursor.fetchall()
            ]

    def get_palette(self, filepath: str) -> Optional[PaletteResponse]:
        """Get color palette for an image."""
        with self._lock:
            cursor = self.conn.execute(
                """
                SELECT * FROM palettes WHERE filepath = ?
                """,
                (filepath,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            colors = [
                row[f"color{i}"]
                for i in range(16)
                if row[f"color{i}"]
            ]

            return PaletteResponse(
                filepath=row["filepath"],
                colors=colors,
                background=row["background"],
                foreground=row["foreground"],
                avg_hue=row["avg_hue"],
                avg_saturation=row["avg_saturation"],
                avg_lightness=row["avg_lightness"],
                color_temperature=row["color_temperature"],
            )

    def get_tags_for_image(self, filepath: str) -> List[TagResponse]:
        """Get all tags for a specific image."""
        with self._lock:
            cursor = self.conn.execute(
                """
                SELECT t.tag_id, t.name, t.category
                FROM tags t
                JOIN image_tags it ON t.tag_id = it.tag_id
                WHERE it.filepath = ?
                ORDER BY t.name
                """,
                (filepath,),
            )
            return [
                TagResponse(
                    tag_id=row["tag_id"],
                    name=row["name"],
                    category=row["category"],
                    count=0,  # Not computed in this context
                )
                for row in cursor.fetchall()
            ]

    # --- Write Operations ---

    def set_favorite(self, filepath: str, is_favorite: bool) -> bool:
        """Set or clear favorite status for an image.

        Args:
            filepath: Image filepath.
            is_favorite: True to favorite, False to unfavorite.

        Returns:
            True if successful, False if image not found or readonly mode.
        """
        if self.readonly:
            return False

        with self._lock:
            cursor = self.conn.execute(
                "UPDATE images SET is_favorite = ? WHERE filepath = ?",
                (1 if is_favorite else 0, filepath),
            )
            if cursor.rowcount == 0:
                return False

            # Record user action
            action = "favorite" if is_favorite else "unfavorite"
            self.conn.execute(
                """
                INSERT INTO user_actions (filepath, action, action_at)
                VALUES (?, ?, ?)
                """,
                (filepath, action, int(time.time())),
            )
            self.conn.commit()
            return True

    def record_trash(self, filepath: str) -> bool:
        """Record a trash action for an image.

        Note: This does not delete the image from the database or disk.
        It only records the user action for analytics.

        Returns:
            True if successful, False if readonly mode.
        """
        if self.readonly:
            return False

        with self._lock:
            # Clear favorite status if set
            self.conn.execute(
                "UPDATE images SET is_favorite = 0 WHERE filepath = ?",
                (filepath,),
            )

            # Record user action
            self.conn.execute(
                """
                INSERT INTO user_actions (filepath, action, action_at)
                VALUES (?, ?, ?)
                """,
                (filepath, "trash", int(time.time())),
            )
            self.conn.commit()
            return True

    # --- Helper Methods ---

    def _row_to_image(self, row: sqlite3.Row) -> ImageResponse:
        """Convert a database row to ImageResponse."""
        return ImageResponse(
            filepath=row["filepath"],
            filename=row["filename"],
            source_id=row["source_id"],
            width=row["width"],
            height=row["height"],
            aspect_ratio=row["aspect_ratio"],
            file_size=row["file_size"],
            is_favorite=bool(row["is_favorite"]),
            times_shown=row["times_shown"] or 0,
            last_shown_at=row["last_shown_at"],
            palette_status=row["palette_status"],
            category=row["category"],
            purity=row["purity"],
            source_url=row["source_url"],
            uploader=row["uploader"],
            views=row["views"],
        )
