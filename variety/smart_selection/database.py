# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""SQLite database operations for the Smart Selection Engine.

Provides persistent storage for image metadata, source tracking,
and color palettes using SQLite.
"""

import sqlite3
import threading
import time
from typing import Optional, List

from variety.smart_selection.models import (
    ImageRecord,
    SourceRecord,
    PaletteRecord,
)


class ImageDatabase:
    """SQLite database for image indexing and selection tracking.

    Thread-safety: Uses RLock to serialize all database operations.
    This ensures safe multi-threaded access without data corruption.
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        """Initialize database connection and create schema if needed.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for crash resilience and better concurrent performance
        self.conn.execute("PRAGMA journal_mode=WAL")

        self._create_schema()

    def _create_schema(self):
        """Create database tables if they don't exist."""
        with self._lock:
            cursor = self.conn.cursor()

            # Images table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    filepath TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    source_id TEXT,
                    width INTEGER,
                    height INTEGER,
                    aspect_ratio REAL,
                    file_size INTEGER,
                    file_mtime INTEGER,
                    is_favorite INTEGER DEFAULT 0,
                    first_indexed_at INTEGER,
                    last_indexed_at INTEGER,
                    last_shown_at INTEGER,
                    times_shown INTEGER DEFAULT 0
                )
            ''')

            # Sources table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT,
                    last_shown_at INTEGER,
                    times_shown INTEGER DEFAULT 0
                )
            ''')

            # Palettes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS palettes (
                    filepath TEXT PRIMARY KEY,
                    color0 TEXT, color1 TEXT, color2 TEXT, color3 TEXT,
                    color4 TEXT, color5 TEXT, color6 TEXT, color7 TEXT,
                    color8 TEXT, color9 TEXT, color10 TEXT, color11 TEXT,
                    color12 TEXT, color13 TEXT, color14 TEXT, color15 TEXT,
                    background TEXT,
                    foreground TEXT,
                    avg_hue REAL,
                    avg_saturation REAL,
                    avg_lightness REAL,
                    color_temperature REAL,
                    indexed_at INTEGER,
                    FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE
                )
            ''')

            # Create indexes for common queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_source ON images(source_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_last_shown ON images(last_shown_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(is_favorite)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_palettes_lightness ON palettes(avg_lightness)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_palettes_temperature ON palettes(color_temperature)')

            self.conn.commit()

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    # =========================================================================
    # Image CRUD Operations
    # =========================================================================

    def insert_image(self, record: ImageRecord):
        """Insert a new image record into the database.

        Args:
            record: ImageRecord to insert.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO images (
                    filepath, filename, source_id, width, height, aspect_ratio,
                    file_size, file_mtime, is_favorite, first_indexed_at,
                    last_indexed_at, last_shown_at, times_shown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.filepath,
                record.filename,
                record.source_id,
                record.width,
                record.height,
                record.aspect_ratio,
                record.file_size,
                record.file_mtime,
                1 if record.is_favorite else 0,
                record.first_indexed_at,
                record.last_indexed_at,
                record.last_shown_at,
                record.times_shown,
            ))
            self.conn.commit()

    def get_image(self, filepath: str) -> Optional[ImageRecord]:
        """Get an image record by filepath.

        Args:
            filepath: Path to the image.

        Returns:
            ImageRecord if found, None otherwise.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM images WHERE filepath = ?', (filepath,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_image_record(row)

    def update_image(self, record: ImageRecord):
        """Update an existing image record.

        Args:
            record: ImageRecord with updated values.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE images SET
                    filename = ?,
                    source_id = ?,
                    width = ?,
                    height = ?,
                    aspect_ratio = ?,
                    file_size = ?,
                    file_mtime = ?,
                    is_favorite = ?,
                    first_indexed_at = ?,
                    last_indexed_at = ?,
                    last_shown_at = ?,
                    times_shown = ?
                WHERE filepath = ?
            ''', (
                record.filename,
                record.source_id,
                record.width,
                record.height,
                record.aspect_ratio,
                record.file_size,
                record.file_mtime,
                1 if record.is_favorite else 0,
                record.first_indexed_at,
                record.last_indexed_at,
                record.last_shown_at,
                record.times_shown,
                record.filepath,
            ))
            self.conn.commit()

    def upsert_image(self, record: ImageRecord):
        """Insert or update an image record.

        Args:
            record: ImageRecord to upsert.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO images (
                    filepath, filename, source_id, width, height, aspect_ratio,
                    file_size, file_mtime, is_favorite, first_indexed_at,
                    last_indexed_at, last_shown_at, times_shown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filepath) DO UPDATE SET
                    filename = excluded.filename,
                    source_id = excluded.source_id,
                    width = excluded.width,
                    height = excluded.height,
                    aspect_ratio = excluded.aspect_ratio,
                    file_size = excluded.file_size,
                    file_mtime = excluded.file_mtime,
                    is_favorite = excluded.is_favorite,
                    last_indexed_at = excluded.last_indexed_at,
                    last_shown_at = excluded.last_shown_at,
                    times_shown = excluded.times_shown
            ''', (
                record.filepath,
                record.filename,
                record.source_id,
                record.width,
                record.height,
                record.aspect_ratio,
                record.file_size,
                record.file_mtime,
                1 if record.is_favorite else 0,
                record.first_indexed_at,
                record.last_indexed_at,
                record.last_shown_at,
                record.times_shown,
            ))
            self.conn.commit()

    def delete_image(self, filepath: str):
        """Delete an image record by filepath.

        Args:
            filepath: Path to the image to delete.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM images WHERE filepath = ?', (filepath,))
            self.conn.commit()

    def get_all_images(self) -> List[ImageRecord]:
        """Get all image records.

        Returns:
            List of all ImageRecords in the database.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM images')
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_images_by_source(self, source_id: str) -> List[ImageRecord]:
        """Get all images from a specific source.

        Args:
            source_id: Source identifier to filter by.

        Returns:
            List of ImageRecords from the specified source.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM images WHERE source_id = ?', (source_id,))
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_favorite_images(self) -> List[ImageRecord]:
        """Get all favorite images.

        Returns:
            List of ImageRecords marked as favorites.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM images WHERE is_favorite = 1')
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def record_image_shown(self, filepath: str):
        """Record that an image was shown.

        Updates last_shown_at to current time and increments times_shown.

        Args:
            filepath: Path to the image that was shown.
        """
        with self._lock:
            cursor = self.conn.cursor()
            now = int(time.time())
            cursor.execute('''
                UPDATE images SET
                    last_shown_at = ?,
                    times_shown = times_shown + 1
                WHERE filepath = ?
            ''', (now, filepath))
            self.conn.commit()

    def _row_to_image_record(self, row: sqlite3.Row) -> ImageRecord:
        """Convert a database row to an ImageRecord.

        Args:
            row: SQLite row object.

        Returns:
            ImageRecord instance.
        """
        return ImageRecord(
            filepath=row['filepath'],
            filename=row['filename'],
            source_id=row['source_id'],
            width=row['width'],
            height=row['height'],
            aspect_ratio=row['aspect_ratio'],
            file_size=row['file_size'],
            file_mtime=row['file_mtime'],
            is_favorite=bool(row['is_favorite']),
            first_indexed_at=row['first_indexed_at'],
            last_indexed_at=row['last_indexed_at'],
            last_shown_at=row['last_shown_at'],
            times_shown=row['times_shown'],
        )

    # =========================================================================
    # Source CRUD Operations
    # =========================================================================

    def upsert_source(self, record: SourceRecord):
        """Insert or update a source record.

        Args:
            record: SourceRecord to upsert.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO sources (source_id, source_type, last_shown_at, times_shown)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_type = excluded.source_type,
                    last_shown_at = excluded.last_shown_at,
                    times_shown = excluded.times_shown
            ''', (
                record.source_id,
                record.source_type,
                record.last_shown_at,
                record.times_shown,
            ))
            self.conn.commit()

    def get_source(self, source_id: str) -> Optional[SourceRecord]:
        """Get a source record by source_id.

        Args:
            source_id: Source identifier.

        Returns:
            SourceRecord if found, None otherwise.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM sources WHERE source_id = ?', (source_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return SourceRecord(
                source_id=row['source_id'],
                source_type=row['source_type'],
                last_shown_at=row['last_shown_at'],
                times_shown=row['times_shown'],
            )

    def get_all_sources(self) -> List[SourceRecord]:
        """Get all source records.

        Returns:
            List of all SourceRecords in the database.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM sources')
            return [
                SourceRecord(
                    source_id=row['source_id'],
                    source_type=row['source_type'],
                    last_shown_at=row['last_shown_at'],
                    times_shown=row['times_shown'],
                )
                for row in cursor.fetchall()
            ]

    def record_source_shown(self, source_id: str):
        """Record that an image from a source was shown.

        Updates last_shown_at to current time and increments times_shown.

        Args:
            source_id: Source identifier.
        """
        with self._lock:
            cursor = self.conn.cursor()
            now = int(time.time())
            cursor.execute('''
                UPDATE sources SET
                    last_shown_at = ?,
                    times_shown = times_shown + 1
                WHERE source_id = ?
            ''', (now, source_id))
            self.conn.commit()

    # =========================================================================
    # Palette CRUD Operations
    # =========================================================================

    def upsert_palette(self, record: PaletteRecord):
        """Insert or update a palette record.

        Args:
            record: PaletteRecord to upsert.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO palettes (
                    filepath, color0, color1, color2, color3, color4, color5, color6, color7,
                    color8, color9, color10, color11, color12, color13, color14, color15,
                    background, foreground, avg_hue, avg_saturation, avg_lightness,
                    color_temperature, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filepath) DO UPDATE SET
                    color0 = excluded.color0, color1 = excluded.color1,
                    color2 = excluded.color2, color3 = excluded.color3,
                    color4 = excluded.color4, color5 = excluded.color5,
                    color6 = excluded.color6, color7 = excluded.color7,
                    color8 = excluded.color8, color9 = excluded.color9,
                    color10 = excluded.color10, color11 = excluded.color11,
                    color12 = excluded.color12, color13 = excluded.color13,
                    color14 = excluded.color14, color15 = excluded.color15,
                    background = excluded.background, foreground = excluded.foreground,
                    avg_hue = excluded.avg_hue, avg_saturation = excluded.avg_saturation,
                    avg_lightness = excluded.avg_lightness,
                    color_temperature = excluded.color_temperature,
                    indexed_at = excluded.indexed_at
            ''', (
                record.filepath,
                record.color0, record.color1, record.color2, record.color3,
                record.color4, record.color5, record.color6, record.color7,
                record.color8, record.color9, record.color10, record.color11,
                record.color12, record.color13, record.color14, record.color15,
                record.background, record.foreground,
                record.avg_hue, record.avg_saturation, record.avg_lightness,
                record.color_temperature, record.indexed_at,
            ))
            self.conn.commit()

    def get_palette(self, filepath: str) -> Optional[PaletteRecord]:
        """Get a palette record by filepath.

        Args:
            filepath: Path to the image.

        Returns:
            PaletteRecord if found, None otherwise.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM palettes WHERE filepath = ?', (filepath,))
            row = cursor.fetchone()
            if row is None:
                return None
            return PaletteRecord(
                filepath=row['filepath'],
                color0=row['color0'], color1=row['color1'],
                color2=row['color2'], color3=row['color3'],
                color4=row['color4'], color5=row['color5'],
                color6=row['color6'], color7=row['color7'],
                color8=row['color8'], color9=row['color9'],
                color10=row['color10'], color11=row['color11'],
                color12=row['color12'], color13=row['color13'],
                color14=row['color14'], color15=row['color15'],
                background=row['background'], foreground=row['foreground'],
                avg_hue=row['avg_hue'], avg_saturation=row['avg_saturation'],
                avg_lightness=row['avg_lightness'],
                color_temperature=row['color_temperature'],
                indexed_at=row['indexed_at'],
            )

    def get_images_with_palettes(self) -> List[ImageRecord]:
        """Get images that have palette data.

        Returns:
            List of ImageRecords that have associated palette records.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT i.* FROM images i
                INNER JOIN palettes p ON i.filepath = p.filepath
            ''')
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_images_without_palettes(self) -> List[ImageRecord]:
        """Get images that don't have palette data.

        Returns:
            List of ImageRecords without associated palette records.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT i.* FROM images i
                LEFT JOIN palettes p ON i.filepath = p.filepath
                WHERE p.filepath IS NULL
            ''')
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    # =========================================================================
    # Statistics Queries
    # =========================================================================

    def count_images(self) -> int:
        """Count total number of indexed images.

        Returns:
            Total number of images in the database.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM images')
            return cursor.fetchone()[0]

    def count_sources(self) -> int:
        """Count total number of sources.

        Returns:
            Total number of sources in the database.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM sources')
            return cursor.fetchone()[0]

    def count_images_with_palettes(self) -> int:
        """Count images that have palette data.

        Returns:
            Number of images with associated palette records.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM palettes')
            return cursor.fetchone()[0]

    def sum_times_shown(self) -> int:
        """Sum total selection count across all images.

        Returns:
            Total number of times any image has been shown.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COALESCE(SUM(times_shown), 0) FROM images')
            return cursor.fetchone()[0]

    def count_shown_images(self) -> int:
        """Count images that have been shown at least once.

        Returns:
            Number of unique images that have been shown.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM images WHERE times_shown > 0')
            return cursor.fetchone()[0]

    def clear_history(self):
        """Clear selection history (reset times_shown and last_shown_at).

        This keeps all indexed images but resets their selection tracking.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE images SET times_shown = 0, last_shown_at = NULL')
            cursor.execute('UPDATE sources SET times_shown = 0, last_shown_at = NULL')
            self.conn.commit()

    def delete_all_images(self):
        """Delete all image records from the database.

        Also deletes associated palette and source records.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM palettes')
            cursor.execute('DELETE FROM images')
            cursor.execute('DELETE FROM sources')
            self.conn.commit()
