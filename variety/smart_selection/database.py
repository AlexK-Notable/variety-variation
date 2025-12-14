# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""SQLite database operations for the Smart Selection Engine.

Provides persistent storage for image metadata, source tracking,
and color palettes using SQLite.
"""

import sqlite3
import shutil
import logging
import threading
import time
import os
from typing import Optional, List, Dict

from variety.smart_selection.models import (
    ImageRecord,
    SourceRecord,
    PaletteRecord,
)

logger = logging.getLogger(__name__)


class ImageDatabase:
    """SQLite database for image indexing and selection tracking.

    Thread-safety: Uses RLock to serialize all database operations.
    This ensures safe multi-threaded access without data corruption.

    Schema Migrations:
        The database tracks its schema version in the 'schema_info' table.
        When the SCHEMA_VERSION is higher than the stored version, migrations
        are applied automatically on initialization.
    """

    SCHEMA_VERSION = 2

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
        self._run_migrations()

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

            # Schema info table for tracking version
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # Initialize schema version if not present
            cursor.execute(
                "INSERT OR IGNORE INTO schema_info (key, value) VALUES ('version', '1')"
            )

            self.conn.commit()

    def _get_schema_version(self) -> int:
        """Get the current schema version from the database.

        Returns:
            Schema version number, or 0 if not found.
        """
        with self._lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute(
                    "SELECT value FROM schema_info WHERE key = 'version'"
                )
                row = cursor.fetchone()
                if row:
                    return int(row[0])
            except sqlite3.OperationalError:
                # Table doesn't exist yet
                pass
            return 0

    def _set_schema_version(self, version: int):
        """Set the schema version in the database.

        Args:
            version: New schema version number.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', ?)",
                (str(version),)
            )
            self.conn.commit()

    def _run_migrations(self):
        """Run any pending schema migrations.

        Migrations are applied in order from current version to SCHEMA_VERSION.
        Each migration should be idempotent.
        """
        current_version = self._get_schema_version()

        if current_version >= self.SCHEMA_VERSION:
            return  # Already up to date

        logger.info(
            f"Running database migrations from v{current_version} to v{self.SCHEMA_VERSION}"
        )

        # Migration map: version -> migration function
        migrations = {
            2: self._migrate_v1_to_v2,
        }

        with self._lock:
            for target_version in range(current_version + 1, self.SCHEMA_VERSION + 1):
                if target_version in migrations:
                    logger.info(f"Applying migration to v{target_version}")
                    try:
                        migrations[target_version]()
                        self._set_schema_version(target_version)
                        logger.info(f"Migration to v{target_version} completed")
                    except Exception as e:
                        logger.error(f"Migration to v{target_version} failed: {e}")
                        raise
                else:
                    # No migration needed for this version step
                    self._set_schema_version(target_version)

    def _migrate_v1_to_v2(self):
        """Migrate schema from v1 to v2.

        Adds cursor column to palettes table for theming engine support.
        """
        cursor = self.conn.cursor()
        cursor.execute('ALTER TABLE palettes ADD COLUMN cursor TEXT')
        self.conn.commit()

    def close(self):
        """Close the database connection.

        Thread-safe: holds lock to prevent use-after-close race.
        Idempotent: safe to call multiple times.
        """
        with self._lock:
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

    def get_sources_by_ids(self, source_ids: List[str]) -> Dict[str, SourceRecord]:
        """Get multiple source records by their IDs.

        Args:
            source_ids: List of source IDs to fetch.

        Returns:
            Dict mapping source_id to SourceRecord (missing IDs omitted).
        """
        if not source_ids:
            return {}

        with self._lock:
            cursor = self.conn.cursor()
            placeholders = ','.join('?' * len(source_ids))
            cursor.execute(
                f'SELECT * FROM sources WHERE source_id IN ({placeholders})',
                source_ids
            )
            rows = cursor.fetchall()

        result = {}
        for row in rows:
            record = SourceRecord(
                source_id=row['source_id'],
                source_type=row['source_type'],
                last_shown_at=row['last_shown_at'],
                times_shown=row['times_shown'],
            )
            result[record.source_id] = record
        return result

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
                    background, foreground, cursor, avg_hue, avg_saturation, avg_lightness,
                    color_temperature, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    cursor = excluded.cursor,
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
                record.background, record.foreground, record.cursor,
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
                cursor=row['cursor'],
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

    def get_palettes_by_filepaths(self, filepaths: List[str]) -> Dict[str, PaletteRecord]:
        """Get multiple palette records by their filepaths.

        Args:
            filepaths: List of image filepaths to fetch palettes for.

        Returns:
            Dict mapping filepath to PaletteRecord (missing filepaths omitted).
        """
        if not filepaths:
            return {}

        with self._lock:
            cursor = self.conn.cursor()
            # Process in chunks to avoid SQLite parameter limit
            result = {}
            for i in range(0, len(filepaths), 500):
                chunk = filepaths[i:i+500]
                placeholders = ','.join('?' * len(chunk))
                cursor.execute(
                    f'SELECT * FROM palettes WHERE filepath IN ({placeholders})',
                    chunk
                )
                for row in cursor.fetchall():
                    record = self._row_to_palette_record(row)
                    result[record.filepath] = record

        return result

    def _row_to_palette_record(self, row) -> PaletteRecord:
        """Convert a database row to a PaletteRecord."""
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
            cursor=row['cursor'],
            avg_hue=row['avg_hue'], avg_saturation=row['avg_saturation'],
            avg_lightness=row['avg_lightness'],
            color_temperature=row['color_temperature'],
            indexed_at=row['indexed_at'],
        )

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

    def get_lightness_counts(self) -> dict:
        """Get image count by lightness bucket.

        Buckets images based on avg_lightness value from palettes:
        - dark: 0.00 - 0.25
        - medium_dark: 0.25 - 0.50
        - medium_light: 0.50 - 0.75
        - light: 0.75 - 1.00

        Returns:
            Dict[str, int] with bucket names as keys and counts as values.
            Returns zeros for all buckets if palettes table is empty.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN avg_lightness >= 0.00 AND avg_lightness < 0.25 THEN 1 ELSE 0 END) as dark,
                    SUM(CASE WHEN avg_lightness >= 0.25 AND avg_lightness < 0.50 THEN 1 ELSE 0 END) as medium_dark,
                    SUM(CASE WHEN avg_lightness >= 0.50 AND avg_lightness < 0.75 THEN 1 ELSE 0 END) as medium_light,
                    SUM(CASE WHEN avg_lightness >= 0.75 AND avg_lightness <= 1.00 THEN 1 ELSE 0 END) as light
                FROM palettes
            ''')
            row = cursor.fetchone()
            return {
                'dark': row['dark'] or 0,
                'medium_dark': row['medium_dark'] or 0,
                'medium_light': row['medium_light'] or 0,
                'light': row['light'] or 0,
            }

    def get_hue_counts(self) -> dict:
        """Get image count by hue family.

        Categorizes images into 8 color families based on avg_hue (0-360°):
        - red: 0-15° or 345-360°
        - orange: 15-45°
        - yellow: 45-75°
        - green: 75-165°
        - cyan: 165-195°
        - blue: 195-255°
        - purple: 255-285°
        - pink: 285-345°

        Images with avg_saturation < 0.1 are categorized as "neutral" instead
        of a hue family (grayscale/desaturated images have meaningless hue).

        Returns:
            Dict[str, int] with hue family names as keys and counts as values.
            Returns zeros for all categories if palettes table is empty.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN avg_saturation < 0.1 THEN 1 ELSE 0 END) as neutral,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND ((avg_hue >= 0 AND avg_hue < 15) OR (avg_hue >= 345 AND avg_hue <= 360)) THEN 1 ELSE 0 END) as red,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 15 AND avg_hue < 45 THEN 1 ELSE 0 END) as orange,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 45 AND avg_hue < 75 THEN 1 ELSE 0 END) as yellow,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 75 AND avg_hue < 165 THEN 1 ELSE 0 END) as green,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 165 AND avg_hue < 195 THEN 1 ELSE 0 END) as cyan,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 195 AND avg_hue < 255 THEN 1 ELSE 0 END) as blue,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 255 AND avg_hue < 285 THEN 1 ELSE 0 END) as purple,
                    SUM(CASE WHEN avg_saturation >= 0.1 AND avg_hue >= 285 AND avg_hue < 345 THEN 1 ELSE 0 END) as pink
                FROM palettes
            ''')
            row = cursor.fetchone()
            return {
                'neutral': row['neutral'] or 0,
                'red': row['red'] or 0,
                'orange': row['orange'] or 0,
                'yellow': row['yellow'] or 0,
                'green': row['green'] or 0,
                'cyan': row['cyan'] or 0,
                'blue': row['blue'] or 0,
                'purple': row['purple'] or 0,
                'pink': row['pink'] or 0,
            }

    def get_saturation_counts(self) -> dict:
        """Get image count by saturation level.

        Buckets images based on avg_saturation value from palettes:
        - muted: 0.00 - 0.25
        - moderate: 0.25 - 0.50
        - saturated: 0.50 - 0.75
        - vibrant: 0.75 - 1.00

        Returns:
            Dict[str, int] with bucket names as keys and counts as values.
            Returns zeros for all buckets if palettes table is empty.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN avg_saturation >= 0.00 AND avg_saturation < 0.25 THEN 1 ELSE 0 END) as muted,
                    SUM(CASE WHEN avg_saturation >= 0.25 AND avg_saturation < 0.50 THEN 1 ELSE 0 END) as moderate,
                    SUM(CASE WHEN avg_saturation >= 0.50 AND avg_saturation < 0.75 THEN 1 ELSE 0 END) as saturated,
                    SUM(CASE WHEN avg_saturation >= 0.75 AND avg_saturation <= 1.00 THEN 1 ELSE 0 END) as vibrant
                FROM palettes
            ''')
            row = cursor.fetchone()
            return {
                'muted': row['muted'] or 0,
                'moderate': row['moderate'] or 0,
                'saturated': row['saturated'] or 0,
                'vibrant': row['vibrant'] or 0,
            }

    def get_freshness_counts(self) -> dict:
        """Get image count by display frequency.

        Categorizes images based on times_shown value:
        - never_shown: 0
        - rarely_shown: 1-4
        - often_shown: 5-9
        - frequently_shown: >= 10

        Returns:
            Dict[str, int] with category names as keys and counts as values.
            Returns zeros for all categories if images table is empty.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN times_shown = 0 THEN 1 ELSE 0 END) as never_shown,
                    SUM(CASE WHEN times_shown >= 1 AND times_shown <= 4 THEN 1 ELSE 0 END) as rarely_shown,
                    SUM(CASE WHEN times_shown >= 5 AND times_shown <= 9 THEN 1 ELSE 0 END) as often_shown,
                    SUM(CASE WHEN times_shown >= 10 THEN 1 ELSE 0 END) as frequently_shown
                FROM images
            ''')
            row = cursor.fetchone()
            return {
                'never_shown': row['never_shown'] or 0,
                'rarely_shown': row['rarely_shown'] or 0,
                'often_shown': row['often_shown'] or 0,
                'frequently_shown': row['frequently_shown'] or 0,
            }

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

    # =========================================================================
    # Maintenance Operations
    # =========================================================================

    def backup(self, backup_path: str) -> bool:
        """Create a backup copy of the database.

        First attempts SQLite's backup API, then falls back to file copy
        after checkpointing WAL to ensure consistency.

        Args:
            backup_path: Path where backup should be created.

        Returns:
            True if backup succeeded, False otherwise.
        """
        with self._lock:
            try:
                # Preferred: SQLite backup API handles WAL automatically
                backup_conn = sqlite3.connect(backup_path)
                self.conn.backup(backup_conn)
                backup_conn.close()
                return True
            except Exception as e:
                logger.warning(f"SQLite backup API failed: {e}, trying file copy")
                try:
                    # Checkpoint WAL before file copy to ensure consistency
                    cursor = self.conn.cursor()
                    cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    cursor.close()

                    # Now safe to copy the main database file
                    shutil.copy2(self.db_path, backup_path)
                    return True
                except Exception as e2:
                    logger.error(f"Backup failed: {e2}")
                    return False

    def vacuum(self) -> bool:
        """Optimize and compact the database.

        Rebuilds the database file to reclaim space from deleted records
        and defragment the file for better performance.

        Returns:
            True if vacuum succeeded, False otherwise.
        """
        with self._lock:
            try:
                # Checkpoint WAL first
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                # Vacuum to reclaim space
                self.conn.execute("VACUUM")
                return True
            except Exception:
                return False

    def verify_integrity(self) -> dict:
        """Verify database integrity and check for orphaned records.

        Checks:
        - SQLite integrity check
        - Orphaned palettes (palettes without matching images)
        - Invalid file references (images pointing to non-existent files)

        Returns:
            Dictionary with verification results:
            - is_valid: True if database passes integrity check
            - orphaned_palettes: List of palette filepaths without images
            - missing_files: List of indexed images that no longer exist
            - total_images: Total image count
            - total_palettes: Total palette count
        """
        import os

        with self._lock:
            cursor = self.conn.cursor()

            # SQLite integrity check
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            is_valid = integrity_result == 'ok'

            # Find orphaned palettes
            cursor.execute('''
                SELECT p.filepath FROM palettes p
                LEFT JOIN images i ON p.filepath = i.filepath
                WHERE i.filepath IS NULL
            ''')
            orphaned_palettes = [row[0] for row in cursor.fetchall()]

            # Find missing files
            cursor.execute('SELECT filepath FROM images')
            all_images = [row[0] for row in cursor.fetchall()]
            missing_files = [fp for fp in all_images if not os.path.exists(fp)]

            # Counts
            cursor.execute('SELECT COUNT(*) FROM images')
            total_images = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM palettes')
            total_palettes = cursor.fetchone()[0]

            return {
                'is_valid': is_valid,
                'integrity_result': integrity_result,
                'orphaned_palettes': orphaned_palettes,
                'missing_files': missing_files,
                'total_images': total_images,
                'total_palettes': total_palettes,
            }

    def cleanup_orphans(self) -> int:
        """Remove orphaned palette records.

        Deletes palettes that reference non-existent images.

        Returns:
            Number of orphaned records removed.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                DELETE FROM palettes WHERE filepath NOT IN (
                    SELECT filepath FROM images
                )
            ''')
            deleted = cursor.rowcount
            self.conn.commit()
            return deleted

    def remove_missing_files(self) -> int:
        """Remove index entries for files that no longer exist.

        Returns:
            Number of missing file entries removed.
        """
        import os

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT filepath FROM images')
            all_images = [row[0] for row in cursor.fetchall()]

            missing = [fp for fp in all_images if not os.path.exists(fp)]
            if missing:
                placeholders = ','.join('?' * len(missing))
                cursor.execute(
                    f'DELETE FROM palettes WHERE filepath IN ({placeholders})',
                    missing
                )
                cursor.execute(
                    f'DELETE FROM images WHERE filepath IN ({placeholders})',
                    missing
                )
                self.conn.commit()

            return len(missing)

    # =========================================================================
    # Batch Operations
    # =========================================================================

    def batch_upsert_images(self, records: List[ImageRecord]):
        """Insert or update multiple image records in a single transaction.

        More efficient than calling upsert_image() in a loop.

        Args:
            records: List of ImageRecords to upsert.
        """
        if not records:
            return

        with self._lock:
            cursor = self.conn.cursor()
            cursor.executemany('''
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
            ''', [
                (
                    r.filepath, r.filename, r.source_id, r.width, r.height,
                    r.aspect_ratio, r.file_size, r.file_mtime,
                    1 if r.is_favorite else 0, r.first_indexed_at,
                    r.last_indexed_at, r.last_shown_at, r.times_shown,
                )
                for r in records
            ])
            self.conn.commit()

    def batch_upsert_sources(self, records: List[SourceRecord]):
        """Insert or update multiple source records in a single transaction.

        Args:
            records: List of SourceRecords to upsert.
        """
        if not records:
            return

        with self._lock:
            cursor = self.conn.cursor()
            cursor.executemany('''
                INSERT INTO sources (source_id, source_type, last_shown_at, times_shown)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_type = excluded.source_type,
                    last_shown_at = excluded.last_shown_at,
                    times_shown = excluded.times_shown
            ''', [
                (r.source_id, r.source_type, r.last_shown_at, r.times_shown)
                for r in records
            ])
            self.conn.commit()

    def get_indexed_mtime_map(self, folder_prefix: str) -> Dict[str, int]:
        """Get filepath→mtime mapping for files under a folder prefix.

        Enables O(1) lookup instead of O(n) queries per file.
        For 10,000 files: ~20MB memory, saves ~10,000 DB queries.

        Args:
            folder_prefix: Folder path prefix to filter by (e.g., '/home/user/Pictures/')

        Returns:
            Dictionary mapping filepath to file_mtime
        """
        with self._lock:
            cursor = self.conn.cursor()
            # Ensure prefix ends with separator for accurate matching
            if folder_prefix and not folder_prefix.endswith(os.sep):
                folder_prefix = folder_prefix + os.sep
            cursor.execute(
                'SELECT filepath, file_mtime FROM images WHERE filepath LIKE ?',
                (folder_prefix + '%',)
            )
            return {row['filepath']: row['file_mtime'] for row in cursor.fetchall()}

    def batch_delete_images(self, filepaths: List[str]):
        """Delete multiple images in a single transaction.

        Also removes associated palette records for deleted images.

        Args:
            filepaths: List of filepaths to delete
        """
        if not filepaths:
            return

        with self._lock:
            cursor = self.conn.cursor()
            # SQLite has 999 parameter limit, batch in chunks of 500
            for i in range(0, len(filepaths), 500):
                chunk = filepaths[i:i+500]
                placeholders = ','.join('?' * len(chunk))

                # First delete associated palettes (palettes use filepath, not image_id)
                cursor.execute(
                    f'DELETE FROM palettes WHERE filepath IN ({placeholders})',
                    chunk
                )

                # Then delete the images
                cursor.execute(
                    f'DELETE FROM images WHERE filepath IN ({placeholders})',
                    chunk
                )
            self.conn.commit()
