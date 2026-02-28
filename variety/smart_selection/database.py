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
from typing import Optional, List, Dict, Iterator

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

    SCHEMA_VERSION = 7

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
                    times_shown INTEGER DEFAULT 0,
                    palette_status TEXT DEFAULT 'pending'
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

            # These indexes depend on columns added by migrations.
            # Check if columns exist before creating to support old databases.
            cursor.execute("PRAGMA table_info(images)")
            image_columns = [row[1] for row in cursor.fetchall()]
            if 'palette_status' in image_columns:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_palette_status ON images(palette_status)')

            cursor.execute("PRAGMA table_info(palettes)")
            palette_columns = [row[1] for row in cursor.fetchall()]
            if all(col in palette_columns for col in ['avg_lightness', 'color_temperature', 'avg_saturation']):
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_palettes_color_filter ON palettes(avg_lightness, color_temperature, avg_saturation)')

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
            3: self._migrate_v2_to_v3,
            4: self._migrate_v3_to_v4,
            5: self._migrate_v4_to_v5,
            6: self._migrate_v5_to_v6,
            7: self._migrate_v6_to_v7,
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
        # Check if column already exists (idempotent migration)
        cursor.execute("PRAGMA table_info(palettes)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'cursor' not in columns:
            cursor.execute('ALTER TABLE palettes ADD COLUMN cursor TEXT')
            logger.info("Migration v1→v2: Added cursor column to palettes")
        self.conn.commit()

    def _migrate_v2_to_v3(self):
        """Migrate schema from v2 to v3.

        Adds palette_status column to images table for eager palette extraction.
        Images start as 'pending' and become 'extracted' once palette is generated.
        Also marks existing images with palettes as 'extracted'.
        """
        cursor = self.conn.cursor()
        # Check if column already exists (idempotent migration)
        cursor.execute("PRAGMA table_info(images)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'palette_status' not in columns:
            # Add the new column with default 'pending'
            cursor.execute("ALTER TABLE images ADD COLUMN palette_status TEXT DEFAULT 'pending'")
            logger.info("Migration v2→v3: Added palette_status column")
        # Create index for efficient filtering (IF NOT EXISTS is already idempotent)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_palette_status ON images(palette_status)')
        # Mark images that already have palettes as 'extracted'
        cursor.execute('''
            UPDATE images SET palette_status = 'extracted'
            WHERE filepath IN (SELECT filepath FROM palettes)
        ''')
        self.conn.commit()
        logger.info("Migration v2→v3: Marked existing palettes as extracted")

    def _migrate_v3_to_v4(self):
        """Migrate schema from v3 to v4.

        Adds compound index for efficient color filtering queries.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_palettes_color_filter '
            'ON palettes(avg_lightness, color_temperature, avg_saturation)'
        )
        self.conn.commit()
        logger.info("Migration v3→v4: Added compound index for color filtering")

    def _migrate_v4_to_v5(self):
        """Migrate schema from v4 to v5.

        Adds stale_at column to images table for soft-delete support.
        When an image file is missing, instead of deleting the record immediately,
        we set stale_at to the current timestamp. This allows recovery if the file
        returns (e.g., unmounted drives) and preserves palette data for 2 weeks.

        Also recreates palettes table without ON DELETE CASCADE to prevent
        automatic palette deletion when images are modified.
        """
        cursor = self.conn.cursor()

        # Check if stale_at column already exists (idempotent migration)
        cursor.execute("PRAGMA table_info(images)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'stale_at' not in columns:
            cursor.execute('ALTER TABLE images ADD COLUMN stale_at INTEGER')
            logger.info("Migration v4→v5: Added stale_at column to images")

        # Create index for efficient stale queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_stale ON images(stale_at)')

        # Note: We cannot easily modify the FK constraint on existing palettes table
        # in SQLite without recreating the table. The ON DELETE CASCADE is still
        # present but won't trigger for soft-deletes (we set stale_at instead of
        # deleting). When we hard-delete during purge, we explicitly delete palettes
        # first to maintain control over the process.

        self.conn.commit()
        logger.info("Migration v4→v5: Soft-delete support enabled")

    def _migrate_v5_to_v6(self):
        """Migrate schema from v5 to v6.

        Adds metadata tracking tables for rich source metadata (Wallhaven, etc.):
        - image_metadata: category, purity, colors, uploader, popularity
        - tags: normalized tag definitions
        - image_tags: many-to-many image-tag relationships
        - user_actions: track favorite/trash for analytics
        """
        cursor = self.conn.cursor()

        # image_metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_metadata (
                filepath TEXT PRIMARY KEY,
                category TEXT,
                purity TEXT,
                sfw_rating INTEGER,
                source_colors TEXT,
                uploader TEXT,
                source_url TEXT,
                views INTEGER,
                favorites INTEGER,
                uploaded_at INTEGER,
                metadata_fetched_at INTEGER,
                FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE
            )
        ''')
        logger.info("Migration v5→v6: Created image_metadata table")

        # tags table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                tag_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                alias TEXT,
                category TEXT,
                purity TEXT,
                UNIQUE(name)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)')
        logger.info("Migration v5→v6: Created tags table")

        # image_tags join table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_tags (
                filepath TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (filepath, tag_id),
                FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_tags_filepath ON image_tags(filepath)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_tags_tag_id ON image_tags(tag_id)')
        logger.info("Migration v5→v6: Created image_tags table")

        # user_actions table for tracking favorites/trash
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT NOT NULL,
                action TEXT NOT NULL,
                action_at INTEGER NOT NULL,
                FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_filepath ON user_actions(filepath)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_action ON user_actions(action)')
        logger.info("Migration v5→v6: Created user_actions table")

        self.conn.commit()
        logger.info("Migration v5→v6: Metadata tracking tables created")

    def _migrate_v6_to_v7(self):
        """Migrate schema from v6 to v7.

        Extends tags table for the Wallhaven tag scraping pipeline:
        - popularity_rank: Position in most-tagged sort
        - wallpaper_count: Number of wallpapers with this tag
        - alias_source: Where alias came from ('firecrawl', 'api', 'organic')
        - alias_updated_at: When alias was last updated
        - scraped_at: When tag was scraped from list page
        - detail_fetched_at: When tag detail was fetched

        Adds scrape job tracking tables:
        - scrape_jobs: Track Firecrawl/API batch jobs
        - tag_scrape_status: Track individual tag fetch status
        """
        cursor = self.conn.cursor()

        # Check existing columns for idempotent migration
        cursor.execute("PRAGMA table_info(tags)")
        columns = [row[1] for row in cursor.fetchall()]

        # Add new columns to tags table
        new_columns = [
            ('popularity_rank', 'INTEGER'),
            ('wallpaper_count', 'INTEGER'),
            ('alias_source', 'TEXT'),
            ('alias_updated_at', 'INTEGER'),
            ('scraped_at', 'INTEGER'),
            ('detail_fetched_at', 'INTEGER'),
        ]
        for col_name, col_type in new_columns:
            if col_name not in columns:
                cursor.execute(f'ALTER TABLE tags ADD COLUMN {col_name} {col_type}')
                logger.info(f"Migration v6→v7: Added {col_name} column to tags")

        # Index for efficient popularity queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_popularity ON tags(popularity_rank)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_wallpaper_count ON tags(wallpaper_count DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_alias ON tags(alias)')

        # scrape_jobs table for tracking batch jobs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at INTEGER,
                completed_at INTEGER,
                progress_cursor TEXT,
                items_total INTEGER DEFAULT 0,
                items_completed INTEGER DEFAULT 0,
                credits_budget INTEGER,
                credits_used INTEGER DEFAULT 0,
                error_message TEXT,
                metadata TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status ON scrape_jobs(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scrape_jobs_type ON scrape_jobs(job_type)')
        logger.info("Migration v6→v7: Created scrape_jobs table")

        # tag_scrape_status for individual tag tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tag_scrape_status (
                tag_id INTEGER PRIMARY KEY,
                list_scraped INTEGER DEFAULT 0,
                firecrawl_status TEXT,
                firecrawl_job_id INTEGER,
                firecrawl_attempted_at INTEGER,
                api_status TEXT,
                api_attempted_at INTEGER,
                last_error TEXT,
                FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                FOREIGN KEY (firecrawl_job_id) REFERENCES scrape_jobs(job_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tag_scrape_firecrawl ON tag_scrape_status(firecrawl_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tag_scrape_api ON tag_scrape_status(api_status)')
        logger.info("Migration v6→v7: Created tag_scrape_status table")

        self.conn.commit()
        logger.info("Migration v6→v7: Tag scraping pipeline tables created")

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
                    last_indexed_at, last_shown_at, times_shown, palette_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                record.palette_status,
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
            cursor.execute(
                'SELECT * FROM images WHERE filepath = ? AND stale_at IS NULL',
                (filepath,)
            )
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
                    times_shown = ?,
                    palette_status = ?
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
                record.palette_status,
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
                    last_indexed_at, last_shown_at, times_shown, palette_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    times_shown = excluded.times_shown,
                    palette_status = excluded.palette_status
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
                record.palette_status,
            ))
            self.conn.commit()

    def delete_image(self, filepath: str, soft_delete: bool = True) -> bool:
        """Delete an image record by filepath.

        By default uses soft-delete (marks as stale) to preserve palette data.
        Use soft_delete=False for hard deletion.

        Args:
            filepath: Path to the image to delete.
            soft_delete: If True (default), mark as stale instead of deleting.
                If False, hard delete the image and its palette.

        Returns:
            True if the image was found and affected, False otherwise.
        """
        if soft_delete:
            # Soft-delete: mark as stale
            return self.mark_images_stale([filepath]) > 0

        # Hard delete
        with self._lock:
            cursor = self.conn.cursor()
            # Delete palette first (explicit control)
            cursor.execute('DELETE FROM palettes WHERE filepath = ?', (filepath,))
            cursor.execute('DELETE FROM images WHERE filepath = ?', (filepath,))
            deleted = cursor.rowcount > 0
            self.conn.commit()
            return deleted

    def get_all_images(self) -> List[ImageRecord]:
        """Get all image records.

        Returns:
            List of all ImageRecords in the database.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM images WHERE stale_at IS NULL')
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
            cursor.execute(
                'SELECT * FROM images WHERE source_id = ? AND stale_at IS NULL',
                (source_id,)
            )
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_favorite_images(self) -> List[ImageRecord]:
        """Get all favorite images.

        Returns:
            List of ImageRecords marked as favorites.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT * FROM images WHERE is_favorite = 1 AND stale_at IS NULL'
            )
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_images_cursor(
        self,
        batch_size: int = 1000,
        source_id: Optional[str] = None,
    ) -> Iterator[List[ImageRecord]]:
        """Stream images in batches from database.

        Memory efficient alternative to get_all_images(). Iterates over
        the database using LIMIT/OFFSET pagination to avoid loading all
        records into memory at once.

        Args:
            batch_size: Number of records per batch. Default 1000.
            source_id: Optional source_id to filter by. If None, returns all.

        Yields:
            Lists of ImageRecord, up to batch_size each.

        Example:
            for batch in db.get_images_cursor(batch_size=500):
                for image in batch:
                    process(image)
        """
        offset = 0
        while True:
            with self._lock:
                cursor = self.conn.cursor()
                if source_id is not None:
                    cursor.execute(
                        'SELECT * FROM images WHERE source_id = ? AND stale_at IS NULL '
                        'ORDER BY filepath LIMIT ? OFFSET ?',
                        (source_id, batch_size, offset)
                    )
                else:
                    cursor.execute(
                        'SELECT * FROM images WHERE stale_at IS NULL '
                        'ORDER BY filepath LIMIT ? OFFSET ?',
                        (batch_size, offset)
                    )
                rows = cursor.fetchall()

            if not rows:
                break

            yield [self._row_to_image_record(row) for row in rows]
            offset += len(rows)

            # If we got fewer than batch_size, we've reached the end
            if len(rows) < batch_size:
                break

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
            palette_status=row['palette_status'] or 'pending',
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

    def count_images_per_source(
        self, source_prefix: Optional[str] = None
    ) -> Dict[str, int]:
        """Count images grouped by source_id.

        Efficiently returns image counts per source without loading all records.
        Useful for displaying statistics in the Wallhaven Manager UI.

        Args:
            source_prefix: Optional prefix to filter sources (e.g., 'wallhaven_'
                to get only Wallhaven sources). Uses SQL LIKE with prefix%.

        Returns:
            Dict mapping source_id to image count.

        Example:
            # Get counts for all Wallhaven sources
            counts = db.count_images_per_source('wallhaven_')
            # {'wallhaven_abstract': 45, 'wallhaven_nature': 23}
        """
        with self._lock:
            cursor = self.conn.cursor()
            if source_prefix:
                cursor.execute('''
                    SELECT source_id, COUNT(*) as count
                    FROM images
                    WHERE source_id LIKE ? AND stale_at IS NULL
                    GROUP BY source_id
                ''', (f"{source_prefix}%",))
            else:
                cursor.execute('''
                    SELECT source_id, COUNT(*) as count
                    FROM images
                    WHERE stale_at IS NULL
                    GROUP BY source_id
                ''')
            return {row['source_id']: row['count'] for row in cursor.fetchall()}

    def get_source_shown_counts(
        self, source_prefix: Optional[str] = None
    ) -> Dict[str, int]:
        """Get total times_shown aggregated by source_id.

        Sums times_shown for all images grouped by source_id.
        Useful for displaying selection statistics in the Wallhaven Manager UI.

        Args:
            source_prefix: Optional prefix to filter sources (e.g., 'wallhaven_'
                to get only Wallhaven sources). Uses SQL LIKE with prefix%.

        Returns:
            Dict mapping source_id to total times_shown across all images.

        Example:
            # Get shown counts for all Wallhaven sources
            counts = db.get_source_shown_counts('wallhaven_')
            # {'wallhaven_abstract': 12, 'wallhaven_nature': 5}
        """
        with self._lock:
            cursor = self.conn.cursor()
            if source_prefix:
                cursor.execute('''
                    SELECT source_id, SUM(times_shown) as total_shown
                    FROM images
                    WHERE source_id LIKE ? AND stale_at IS NULL
                    GROUP BY source_id
                ''', (f"{source_prefix}%",))
            else:
                cursor.execute('''
                    SELECT source_id, SUM(times_shown) as total_shown
                    FROM images
                    WHERE stale_at IS NULL
                    GROUP BY source_id
                ''')
            return {row['source_id']: row['total_shown'] or 0 for row in cursor.fetchall()}

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
                WHERE i.stale_at IS NULL
            ''')
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_images_without_palettes(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[ImageRecord]:
        """Get images that don't have palette records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip (for pagination).

        Returns:
            List of ImageRecord objects without associated palettes.
        """
        with self._lock:
            cursor = self.conn.cursor()
            query = '''
                SELECT i.* FROM images i
                LEFT JOIN palettes p ON i.filepath = p.filepath
                WHERE p.filepath IS NULL AND i.stale_at IS NULL
            '''
            if limit:
                query += f' LIMIT {limit} OFFSET {offset}'

            cursor.execute(query)
            rows = cursor.fetchall()

        return [self._row_to_image_record(row) for row in rows]

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

    def upsert_palettes_batch(self, records: List[PaletteRecord]):
        """Insert or update multiple palette records in a single transaction.

        More efficient than calling upsert_palette() in a loop, especially
        useful for parallel palette extraction where results arrive in batches.

        Args:
            records: List of PaletteRecords to upsert.
        """
        if not records:
            return

        with self._lock:
            cursor = self.conn.cursor()
            cursor.executemany('''
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
            ''', [
                (
                    r.filepath,
                    r.color0, r.color1, r.color2, r.color3,
                    r.color4, r.color5, r.color6, r.color7,
                    r.color8, r.color9, r.color10, r.color11,
                    r.color12, r.color13, r.color14, r.color15,
                    r.background, r.foreground, r.cursor,
                    r.avg_hue, r.avg_saturation, r.avg_lightness,
                    r.color_temperature, r.indexed_at,
                )
                for r in records
            ])
            self.conn.commit()

    # =========================================================================
    # Palette Status Operations
    # =========================================================================

    def update_palette_status(self, filepath: str, status: str):
        """Update the palette extraction status for an image.

        Args:
            filepath: Path to the image.
            status: New status ('pending', 'extracted', 'failed').
        """
        if status not in ('pending', 'extracted', 'failed'):
            raise ValueError(f"Invalid palette status: {status}")

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                'UPDATE images SET palette_status = ? WHERE filepath = ?',
                (status, filepath)
            )
            self.conn.commit()

    def batch_update_palette_status(self, filepaths: List[str], status: str):
        """Update palette status for multiple images.

        Args:
            filepaths: List of image filepaths.
            status: New status ('pending', 'extracted', 'failed').
        """
        if not filepaths:
            return
        if status not in ('pending', 'extracted', 'failed'):
            raise ValueError(f"Invalid palette status: {status}")

        with self._lock:
            cursor = self.conn.cursor()
            # Process in chunks to avoid SQLite parameter limit
            for i in range(0, len(filepaths), 500):
                chunk = filepaths[i:i+500]
                placeholders = ','.join('?' * len(chunk))
                cursor.execute(
                    f'UPDATE images SET palette_status = ? WHERE filepath IN ({placeholders})',
                    [status] + chunk
                )
            self.conn.commit()

    def get_selectable_images(
        self,
        source_id: Optional[str] = None,
        favorites_only: bool = False,
    ) -> List[ImageRecord]:
        """Get images that are eligible for time-based selection.

        Only returns images with palette_status='extracted', ensuring all
        returned images have palette data for time-based filtering.

        Args:
            source_id: Optional source_id to filter by.
            favorites_only: If True, only return favorites.

        Returns:
            List of ImageRecords with extracted palettes.
        """
        with self._lock:
            cursor = self.conn.cursor()
            query = "SELECT * FROM images WHERE palette_status = 'extracted' AND stale_at IS NULL"
            params = []

            if source_id is not None:
                query += ' AND source_id = ?'
                params.append(source_id)

            if favorites_only:
                query += ' AND is_favorite = 1'

            cursor.execute(query, params)
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_pending_palette_images(self, limit: Optional[int] = None) -> List[ImageRecord]:
        """Get images that need palette extraction.

        Returns images with palette_status='pending'.

        Args:
            limit: Maximum number of images to return.

        Returns:
            List of ImageRecords needing palette extraction.
        """
        with self._lock:
            cursor = self.conn.cursor()
            query = "SELECT * FROM images WHERE palette_status = 'pending' AND stale_at IS NULL"
            if limit:
                query += f' LIMIT {limit}'
            cursor.execute(query)
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def get_failed_palette_images(self, limit: Optional[int] = None) -> List[ImageRecord]:
        """Get images where palette extraction failed.

        Returns images with palette_status='failed' for retry.

        Args:
            limit: Maximum number of images to return.

        Returns:
            List of ImageRecords with failed extraction.
        """
        with self._lock:
            cursor = self.conn.cursor()
            query = "SELECT * FROM images WHERE palette_status = 'failed' AND stale_at IS NULL"
            if limit:
                query += f' LIMIT {limit}'
            cursor.execute(query)
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

    def count_images_by_palette_status(self) -> Dict[str, int]:
        """Count images grouped by palette extraction status.

        Returns:
            Dict with status as key and count as value.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN palette_status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN palette_status = 'extracted' THEN 1 ELSE 0 END) as extracted,
                    SUM(CASE WHEN palette_status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM images
                WHERE stale_at IS NULL
            ''')
            row = cursor.fetchone()
            return {
                'pending': row['pending'] or 0,
                'extracted': row['extracted'] or 0,
                'failed': row['failed'] or 0,
            }

    # =========================================================================
    # Image Metadata Operations
    # =========================================================================

    def upsert_image_metadata(
        self,
        filepath: str,
        category: Optional[str] = None,
        purity: Optional[str] = None,
        sfw_rating: Optional[int] = None,
        source_colors: Optional[List[str]] = None,
        uploader: Optional[str] = None,
        source_url: Optional[str] = None,
        views: Optional[int] = None,
        favorites: Optional[int] = None,
        uploaded_at: Optional[int] = None,
    ):
        """Insert or update metadata for an image.

        Args:
            filepath: Path to the image (must exist in images table).
            category: Content category (e.g., 'general', 'anime', 'people').
            purity: Content purity (e.g., 'sfw', 'sketchy', 'nsfw').
            sfw_rating: Numeric SFW rating 0-100.
            source_colors: List of hex color strings from source API.
            uploader: Username of uploader.
            source_url: Original source attribution URL.
            views: View count from source.
            favorites: Favorite count from source.
            uploaded_at: Upload timestamp from source.
        """
        import json
        colors_json = json.dumps(source_colors) if source_colors else None

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO image_metadata (
                    filepath, category, purity, sfw_rating, source_colors,
                    uploader, source_url, views, favorites, uploaded_at,
                    metadata_fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filepath) DO UPDATE SET
                    category = COALESCE(excluded.category, category),
                    purity = COALESCE(excluded.purity, purity),
                    sfw_rating = COALESCE(excluded.sfw_rating, sfw_rating),
                    source_colors = COALESCE(excluded.source_colors, source_colors),
                    uploader = COALESCE(excluded.uploader, uploader),
                    source_url = COALESCE(excluded.source_url, source_url),
                    views = COALESCE(excluded.views, views),
                    favorites = COALESCE(excluded.favorites, favorites),
                    uploaded_at = COALESCE(excluded.uploaded_at, uploaded_at),
                    metadata_fetched_at = excluded.metadata_fetched_at
            ''', (
                filepath, category, purity, sfw_rating, colors_json,
                uploader, source_url, views, favorites, uploaded_at,
                int(time.time())
            ))
            self.conn.commit()

    def get_image_metadata(self, filepath: str) -> Optional[Dict]:
        """Get metadata for an image.

        Args:
            filepath: Path to the image.

        Returns:
            Dictionary with metadata fields, or None if not found.
        """
        import json
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT * FROM image_metadata WHERE filepath = ?',
                (filepath,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            result = dict(row)
            if result.get('source_colors'):
                result['source_colors'] = json.loads(result['source_colors'])
            return result

    # =========================================================================
    # Tag Operations
    # =========================================================================

    def upsert_tag(
        self,
        tag_id: int,
        name: str,
        alias: Optional[str] = None,
        category: Optional[str] = None,
        purity: Optional[str] = None,
        popularity_rank: Optional[int] = None,
        wallpaper_count: Optional[int] = None,
        alias_source: Optional[str] = None,
    ) -> int:
        """Insert or update a tag.

        Args:
            tag_id: Unique tag ID (from source API, or auto-generated).
            name: Tag name.
            alias: Alternative name for the tag.
            category: Tag category.
            purity: Tag purity rating.
            popularity_rank: Position in most-tagged sort (lower = more popular).
            wallpaper_count: Number of wallpapers with this tag.
            alias_source: Where alias came from ('firecrawl', 'api', 'organic').

        Returns:
            The tag_id.
        """
        now = int(time.time())
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO tags (tag_id, name, alias, category, purity,
                                  popularity_rank, wallpaper_count, alias_source,
                                  alias_updated_at, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tag_id) DO UPDATE SET
                    name = excluded.name,
                    alias = COALESCE(excluded.alias, alias),
                    category = COALESCE(excluded.category, category),
                    purity = COALESCE(excluded.purity, purity),
                    popularity_rank = COALESCE(excluded.popularity_rank, popularity_rank),
                    wallpaper_count = COALESCE(excluded.wallpaper_count, wallpaper_count),
                    alias_source = CASE
                        WHEN excluded.alias IS NOT NULL AND excluded.alias != ''
                        THEN COALESCE(excluded.alias_source, alias_source)
                        ELSE alias_source
                    END,
                    alias_updated_at = CASE
                        WHEN excluded.alias IS NOT NULL AND excluded.alias != ''
                        THEN excluded.alias_updated_at
                        ELSE alias_updated_at
                    END,
                    scraped_at = COALESCE(excluded.scraped_at, scraped_at)
            ''', (tag_id, name, alias, category, purity, popularity_rank,
                  wallpaper_count, alias_source, now if alias else None, now))
            self.conn.commit()
            return tag_id

    def upsert_tags_batch(self, tags: List[Dict]) -> List[int]:
        """Insert or update multiple tags.

        Args:
            tags: List of dicts with keys: tag_id, name, and optional:
                  alias, category, purity, popularity_rank, wallpaper_count, alias_source.

        Returns:
            List of tag_ids.
        """
        if not tags:
            return []

        now = int(time.time())
        with self._lock:
            cursor = self.conn.cursor()
            cursor.executemany('''
                INSERT INTO tags (tag_id, name, alias, category, purity,
                                  popularity_rank, wallpaper_count, alias_source,
                                  alias_updated_at, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tag_id) DO UPDATE SET
                    name = excluded.name,
                    alias = COALESCE(excluded.alias, alias),
                    category = COALESCE(excluded.category, category),
                    purity = COALESCE(excluded.purity, purity),
                    popularity_rank = COALESCE(excluded.popularity_rank, popularity_rank),
                    wallpaper_count = COALESCE(excluded.wallpaper_count, wallpaper_count),
                    alias_source = CASE
                        WHEN excluded.alias IS NOT NULL AND excluded.alias != ''
                        THEN COALESCE(excluded.alias_source, alias_source)
                        ELSE alias_source
                    END,
                    alias_updated_at = CASE
                        WHEN excluded.alias IS NOT NULL AND excluded.alias != ''
                        THEN excluded.alias_updated_at
                        ELSE alias_updated_at
                    END,
                    scraped_at = COALESCE(excluded.scraped_at, scraped_at)
            ''', [
                (
                    t['tag_id'], t['name'], t.get('alias'), t.get('category'), t.get('purity'),
                    t.get('popularity_rank'), t.get('wallpaper_count'), t.get('alias_source'),
                    now if t.get('alias') else None, now
                )
                for t in tags
            ])
            self.conn.commit()
            return [t['tag_id'] for t in tags]

    def get_tag_by_name(self, name: str) -> Optional[Dict]:
        """Get a tag by name.

        Args:
            name: Tag name to look up.

        Returns:
            Dictionary with tag fields, or None if not found.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM tags WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def link_image_tags(self, filepath: str, tag_ids: List[int]):
        """Link an image to multiple tags.

        Replaces all existing tag links for the image.

        Args:
            filepath: Path to the image.
            tag_ids: List of tag IDs to link.
        """
        with self._lock:
            cursor = self.conn.cursor()
            # Remove existing links
            cursor.execute('DELETE FROM image_tags WHERE filepath = ?', (filepath,))
            # Add new links
            if tag_ids:
                cursor.executemany(
                    'INSERT OR IGNORE INTO image_tags (filepath, tag_id) VALUES (?, ?)',
                    [(filepath, tag_id) for tag_id in tag_ids]
                )
            self.conn.commit()

    def get_tags_for_image(self, filepath: str) -> List[Dict]:
        """Get all tags for an image.

        Args:
            filepath: Path to the image.

        Returns:
            List of tag dictionaries.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT t.* FROM tags t
                JOIN image_tags it ON t.tag_id = it.tag_id
                WHERE it.filepath = ?
            ''', (filepath,))
            return [dict(row) for row in cursor.fetchall()]

    def get_images_by_tag(self, tag_name: str, limit: int = 100) -> List[str]:
        """Get image filepaths that have a specific tag.

        Args:
            tag_name: Name of the tag to search for.
            limit: Maximum number of results.

        Returns:
            List of filepaths.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT it.filepath FROM image_tags it
                JOIN tags t ON it.tag_id = t.tag_id
                WHERE t.name = ?
                LIMIT ?
            ''', (tag_name, limit))
            return [row[0] for row in cursor.fetchall()]

    def get_tag_statistics(
        self,
        action_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get tag usage statistics.

        Args:
            action_filter: If set, only count images with this action ('favorite', 'trash').
            limit: Maximum number of tags to return.

        Returns:
            List of dicts with 'name', 'count' keys, sorted by count descending.
        """
        with self._lock:
            cursor = self.conn.cursor()
            if action_filter:
                cursor.execute('''
                    SELECT t.name, COUNT(DISTINCT it.filepath) as count
                    FROM tags t
                    JOIN image_tags it ON t.tag_id = it.tag_id
                    JOIN user_actions ua ON it.filepath = ua.filepath
                    WHERE ua.action = ?
                    GROUP BY t.tag_id
                    ORDER BY count DESC
                    LIMIT ?
                ''', (action_filter, limit))
            else:
                cursor.execute('''
                    SELECT t.name, COUNT(DISTINCT it.filepath) as count
                    FROM tags t
                    JOIN image_tags it ON t.tag_id = it.tag_id
                    GROUP BY t.tag_id
                    ORDER BY count DESC
                    LIMIT ?
                ''', (limit,))
            return [{'name': row[0], 'count': row[1]} for row in cursor.fetchall()]

    def get_favorite_tag_statistics(self, limit: int = 50) -> List[Dict]:
        """Get tags most associated with favorited images.

        Args:
            limit: Maximum number of tags to return.

        Returns:
            List of dicts with 'name', 'count' keys.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT t.name, COUNT(DISTINCT it.filepath) as count
                FROM tags t
                JOIN image_tags it ON t.tag_id = it.tag_id
                JOIN images i ON it.filepath = i.filepath
                WHERE i.is_favorite = 1
                GROUP BY t.tag_id
                ORDER BY count DESC
                LIMIT ?
            ''', (limit,))
            return [{'name': row[0], 'count': row[1]} for row in cursor.fetchall()]

    def resolve_tag(self, query: str) -> Optional[Dict]:
        """Resolve a tag name or alias to a tag record.

        Performs case-insensitive matching on both name and alias fields.

        Args:
            query: Tag name or alias to look up.

        Returns:
            Tag dictionary if found, None otherwise.
        """
        with self._lock:
            cursor = self.conn.cursor()
            # Try exact match on name first (case-insensitive)
            cursor.execute(
                'SELECT * FROM tags WHERE LOWER(name) = LOWER(?)',
                (query,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Try exact match on alias
            cursor.execute(
                'SELECT * FROM tags WHERE LOWER(alias) = LOWER(?)',
                (query,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Try partial match on name
            cursor.execute(
                'SELECT * FROM tags WHERE LOWER(name) LIKE LOWER(?) ORDER BY popularity_rank ASC NULLS LAST LIMIT 1',
                (f'%{query}%',)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Try partial match on alias
            cursor.execute(
                'SELECT * FROM tags WHERE LOWER(alias) LIKE LOWER(?) ORDER BY popularity_rank ASC NULLS LAST LIMIT 1',
                (f'%{query}%',)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def resolve_tags(self, queries: List[str]) -> Dict[str, Optional[Dict]]:
        """Resolve multiple tag names/aliases to tag records.

        Args:
            queries: List of tag names or aliases.

        Returns:
            Dict mapping query string to tag dict (or None if not found).
        """
        results = {}
        for query in queries:
            results[query] = self.resolve_tag(query)
        return results

    def get_tags_needing_detail(self, limit: int = 100) -> List[Dict]:
        """Get tags that have been list-scraped but need detail fetching.

        Prioritizes by popularity_rank (most popular first).

        Args:
            limit: Maximum number of tags to return.

        Returns:
            List of tag dictionaries without alias data.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT t.* FROM tags t
                LEFT JOIN tag_scrape_status ts ON t.tag_id = ts.tag_id
                WHERE (t.alias IS NULL OR t.alias = '')
                  AND (ts.firecrawl_status IS NULL OR ts.firecrawl_status = 'pending')
                  AND (ts.api_status IS NULL OR ts.api_status = 'pending')
                ORDER BY t.popularity_rank ASC NULLS LAST
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_tags_for_api_fallback(self, limit: int = 100) -> List[Dict]:
        """Get tags that failed Firecrawl and need API fallback.

        Args:
            limit: Maximum number of tags to return.

        Returns:
            List of tag dictionaries.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT t.* FROM tags t
                JOIN tag_scrape_status ts ON t.tag_id = ts.tag_id
                WHERE t.alias IS NULL
                  AND ts.firecrawl_status = 'failed'
                  AND (ts.api_status IS NULL OR ts.api_status = 'pending')
                ORDER BY t.popularity_rank ASC NULLS LAST
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Scrape Job Tracking
    # =========================================================================

    def create_scrape_job(
        self,
        job_type: str,
        credits_budget: Optional[int] = None,
        metadata: Optional[str] = None,
    ) -> int:
        """Create a new scrape job record.

        Args:
            job_type: Type of job ('smoke_test', 'tag_list', 'tag_detail_firecrawl', 'tag_detail_api').
            credits_budget: Maximum credits to use for this job.
            metadata: JSON string with additional job data.

        Returns:
            The job_id.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO scrape_jobs (job_type, status, started_at, credits_budget, metadata)
                VALUES (?, 'pending', ?, ?, ?)
            ''', (job_type, int(time.time()), credits_budget, metadata))
            self.conn.commit()
            return cursor.lastrowid

    def update_scrape_job(
        self,
        job_id: int,
        status: Optional[str] = None,
        items_total: Optional[int] = None,
        items_completed: Optional[int] = None,
        credits_used: Optional[int] = None,
        progress_cursor: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Update a scrape job record.

        Args:
            job_id: The job ID to update.
            status: New status ('pending', 'in_progress', 'completed', 'failed').
            items_total: Total items to process.
            items_completed: Items completed so far.
            credits_used: Credits consumed so far.
            progress_cursor: JSON cursor for resumption.
            error_message: Error message if failed.
        """
        updates = []
        values = []

        if status is not None:
            updates.append('status = ?')
            values.append(status)
            if status in ('completed', 'failed'):
                updates.append('completed_at = ?')
                values.append(int(time.time()))
        if items_total is not None:
            updates.append('items_total = ?')
            values.append(items_total)
        if items_completed is not None:
            updates.append('items_completed = ?')
            values.append(items_completed)
        if credits_used is not None:
            updates.append('credits_used = ?')
            values.append(credits_used)
        if progress_cursor is not None:
            updates.append('progress_cursor = ?')
            values.append(progress_cursor)
        if error_message is not None:
            updates.append('error_message = ?')
            values.append(error_message)

        if not updates:
            return

        values.append(job_id)
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                f'UPDATE scrape_jobs SET {", ".join(updates)} WHERE job_id = ?',
                values
            )
            self.conn.commit()

    def get_scrape_job(self, job_id: int) -> Optional[Dict]:
        """Get a scrape job by ID.

        Args:
            job_id: The job ID.

        Returns:
            Job dictionary or None.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM scrape_jobs WHERE job_id = ?', (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_latest_job_by_type(self, job_type: str) -> Optional[Dict]:
        """Get the most recent job of a given type.

        Args:
            job_type: The job type to look for.

        Returns:
            Job dictionary or None.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM scrape_jobs
                WHERE job_type = ?
                ORDER BY started_at DESC, job_id DESC
                LIMIT 1
            ''', (job_type,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_resumable_job(self, job_type: str) -> Optional[Dict]:
        """Get an in-progress job that can be resumed.

        Args:
            job_type: The job type to look for.

        Returns:
            Job dictionary or None.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM scrape_jobs
                WHERE job_type = ? AND status = 'in_progress'
                ORDER BY started_at DESC, job_id DESC
                LIMIT 1
            ''', (job_type,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # =========================================================================
    # Tag Scrape Status Tracking
    # =========================================================================

    def update_tag_scrape_status(
        self,
        tag_id: int,
        list_scraped: Optional[bool] = None,
        firecrawl_status: Optional[str] = None,
        firecrawl_job_id: Optional[int] = None,
        api_status: Optional[str] = None,
        last_error: Optional[str] = None,
    ):
        """Update or create scrape status for a tag.

        Args:
            tag_id: The tag ID.
            list_scraped: Whether tag was found in list scrape.
            firecrawl_status: Firecrawl fetch status ('pending', 'success', 'failed').
            firecrawl_job_id: Associated Firecrawl job ID.
            api_status: API fetch status ('pending', 'success', 'failed').
            last_error: Last error message.
        """
        now = int(time.time())
        with self._lock:
            cursor = self.conn.cursor()

            # Build upsert
            columns = ['tag_id']
            values = [tag_id]
            update_parts = []

            if list_scraped is not None:
                columns.append('list_scraped')
                values.append(1 if list_scraped else 0)
                update_parts.append('list_scraped = excluded.list_scraped')

            if firecrawl_status is not None:
                columns.append('firecrawl_status')
                values.append(firecrawl_status)
                update_parts.append('firecrawl_status = excluded.firecrawl_status')
                columns.append('firecrawl_attempted_at')
                values.append(now)
                update_parts.append('firecrawl_attempted_at = excluded.firecrawl_attempted_at')

            if firecrawl_job_id is not None:
                columns.append('firecrawl_job_id')
                values.append(firecrawl_job_id)
                update_parts.append('firecrawl_job_id = excluded.firecrawl_job_id')

            if api_status is not None:
                columns.append('api_status')
                values.append(api_status)
                update_parts.append('api_status = excluded.api_status')
                columns.append('api_attempted_at')
                values.append(now)
                update_parts.append('api_attempted_at = excluded.api_attempted_at')

            if last_error is not None:
                columns.append('last_error')
                values.append(last_error)
                update_parts.append('last_error = excluded.last_error')

            placeholders = ', '.join(['?'] * len(values))
            update_clause = ', '.join(update_parts) if update_parts else 'tag_id = excluded.tag_id'

            cursor.execute(f'''
                INSERT INTO tag_scrape_status ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(tag_id) DO UPDATE SET {update_clause}
            ''', values)
            self.conn.commit()

    def update_tag_scrape_status_batch(
        self,
        tag_ids: List[int],
        list_scraped: Optional[bool] = None,
        firecrawl_status: Optional[str] = None,
        firecrawl_job_id: Optional[int] = None,
    ):
        """Batch update scrape status for multiple tags.

        Args:
            tag_ids: List of tag IDs.
            list_scraped: Whether tags were found in list scrape.
            firecrawl_status: Firecrawl fetch status.
            firecrawl_job_id: Associated Firecrawl job ID.
        """
        if not tag_ids:
            return

        now = int(time.time())
        with self._lock:
            cursor = self.conn.cursor()

            # Build the data tuples
            data = []
            for tag_id in tag_ids:
                row = [tag_id]
                if list_scraped is not None:
                    row.append(1 if list_scraped else 0)
                if firecrawl_status is not None:
                    row.append(firecrawl_status)
                    row.append(now)
                if firecrawl_job_id is not None:
                    row.append(firecrawl_job_id)
                data.append(tuple(row))

            # Build column list
            columns = ['tag_id']
            if list_scraped is not None:
                columns.append('list_scraped')
            if firecrawl_status is not None:
                columns.extend(['firecrawl_status', 'firecrawl_attempted_at'])
            if firecrawl_job_id is not None:
                columns.append('firecrawl_job_id')

            placeholders = ', '.join(['?'] * len(columns))
            update_parts = [f'{col} = excluded.{col}' for col in columns if col != 'tag_id']
            update_clause = ', '.join(update_parts) if update_parts else 'tag_id = excluded.tag_id'

            cursor.executemany(f'''
                INSERT INTO tag_scrape_status ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(tag_id) DO UPDATE SET {update_clause}
            ''', data)
            self.conn.commit()

    def get_scrape_statistics(self) -> Dict:
        """Get statistics about tag scraping progress.

        Returns:
            Dict with counts for various scrape states.
        """
        with self._lock:
            cursor = self.conn.cursor()

            stats = {}

            # Total tags
            cursor.execute('SELECT COUNT(*) FROM tags')
            stats['total_tags'] = cursor.fetchone()[0]

            # Tags with aliases
            cursor.execute('SELECT COUNT(*) FROM tags WHERE alias IS NOT NULL')
            stats['tags_with_alias'] = cursor.fetchone()[0]

            # Tags list-scraped
            cursor.execute('SELECT COUNT(*) FROM tag_scrape_status WHERE list_scraped = 1')
            stats['list_scraped'] = cursor.fetchone()[0]

            # Firecrawl status counts
            cursor.execute('''
                SELECT firecrawl_status, COUNT(*) FROM tag_scrape_status
                WHERE firecrawl_status IS NOT NULL
                GROUP BY firecrawl_status
            ''')
            stats['firecrawl'] = {row[0]: row[1] for row in cursor.fetchall()}

            # API status counts
            cursor.execute('''
                SELECT api_status, COUNT(*) FROM tag_scrape_status
                WHERE api_status IS NOT NULL
                GROUP BY api_status
            ''')
            stats['api'] = {row[0]: row[1] for row in cursor.fetchall()}

            # Tags needing detail fetch (NULL or empty alias)
            cursor.execute('''
                SELECT COUNT(*) FROM tags t
                WHERE (t.alias IS NULL OR t.alias = '')
            ''')
            stats['needs_detail'] = cursor.fetchone()[0]

            return stats

    # =========================================================================
    # User Action Tracking
    # =========================================================================

    def record_user_action(self, filepath: str, action: str):
        """Record a user action on an image.

        Args:
            filepath: Path to the image.
            action: Action type ('favorite', 'unfavorite', 'trash', 'skip').
        """
        valid_actions = ('favorite', 'unfavorite', 'trash', 'skip')
        if action not in valid_actions:
            raise ValueError(f"Invalid action: {action}. Must be one of {valid_actions}")

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO user_actions (filepath, action, action_at)
                VALUES (?, ?, ?)
            ''', (filepath, action, int(time.time())))
            self.conn.commit()

    def get_user_actions(self, filepath: str) -> List[Dict]:
        """Get all recorded actions for an image.

        Args:
            filepath: Path to the image.

        Returns:
            List of action records with 'action' and 'action_at' keys.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT action, action_at FROM user_actions
                WHERE filepath = ?
                ORDER BY action_at DESC
            ''', (filepath,))
            return [{'action': row[0], 'action_at': row[1]} for row in cursor.fetchall()]

    def get_action_counts(self) -> Dict[str, int]:
        """Get counts of each action type.

        Returns:
            Dictionary mapping action names to counts.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT action, COUNT(*) as count
                FROM user_actions
                GROUP BY action
            ''')
            return {row[0]: row[1] for row in cursor.fetchall()}

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
            cursor.execute('SELECT COUNT(*) FROM images WHERE stale_at IS NULL')
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
            cursor.execute('''
                SELECT COUNT(*) FROM palettes p
                INNER JOIN images i ON p.filepath = i.filepath
                WHERE i.stale_at IS NULL
            ''')
            return cursor.fetchone()[0]

    def count_images_without_palettes(self) -> int:
        """Count images that don't have palette data.

        Returns:
            Number of images without associated palette records.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM images i
                LEFT JOIN palettes p ON i.filepath = p.filepath
                WHERE p.filepath IS NULL AND i.stale_at IS NULL
            ''')
            return cursor.fetchone()[0]

    def sum_times_shown(self) -> int:
        """Sum total selection count across all images.

        Returns:
            Total number of times any image has been shown.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT COALESCE(SUM(times_shown), 0) FROM images WHERE stale_at IS NULL'
            )
            return cursor.fetchone()[0]

    def count_shown_images(self) -> int:
        """Count images that have been shown at least once.

        Returns:
            Number of unique images that have been shown.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM images WHERE times_shown > 0 AND stale_at IS NULL'
            )
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
                FROM palettes p
                INNER JOIN images i ON p.filepath = i.filepath
                WHERE i.stale_at IS NULL
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
                FROM palettes p
                INNER JOIN images i ON p.filepath = i.filepath
                WHERE i.stale_at IS NULL
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
                FROM palettes p
                INNER JOIN images i ON p.filepath = i.filepath
                WHERE i.stale_at IS NULL
            ''')
            row = cursor.fetchone()
            return {
                'muted': row['muted'] or 0,
                'moderate': row['moderate'] or 0,
                'saturated': row['saturated'] or 0,
                'vibrant': row['vibrant'] or 0,
            }

    def get_time_suitability_counts(self, day_threshold: float = 0.5, night_threshold: float = 0.5) -> dict:
        """Get image counts by time-of-day suitability.

        Counts images suitable for day vs night based on lightness.
        Day-suitable: lightness >= day_threshold
        Night-suitable: lightness < night_threshold

        Args:
            day_threshold: Minimum lightness for day suitability (default 0.5)
            night_threshold: Maximum lightness for night suitability (default 0.5)

        Returns:
            Dict with 'day_suitable', 'night_suitable', 'both', 'neither' counts.
        """
        with self._lock:
            cursor = self.conn.cursor()
            # day-suitable = lightness >= 0.5, night-suitable = lightness < 0.5
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN avg_lightness >= ? THEN 1 ELSE 0 END) as day_suitable,
                    SUM(CASE WHEN avg_lightness < ? THEN 1 ELSE 0 END) as night_suitable
                FROM palettes p
                INNER JOIN images i ON p.filepath = i.filepath
                WHERE i.stale_at IS NULL
            ''', (day_threshold, night_threshold))
            row = cursor.fetchone()
            return {
                'day_suitable': row['day_suitable'] or 0,
                'night_suitable': row['night_suitable'] or 0,
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
                WHERE stale_at IS NULL
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

    def remove_missing_files(self) -> Dict[str, int]:
        """Handle index entries for files that no longer exist.

        Uses soft-delete: marks missing files as stale instead of deleting them.
        Stale entries are retained for 14 days to allow recovery if files return
        (e.g., unmounted drives, network storage). Also restores previously stale
        entries if their files have reappeared.

        Returns:
            Dict with counts:
            - 'marked_stale': Number of newly stale entries
            - 'restored': Number of stale entries restored (file returned)
        """
        import os

        with self._lock:
            cursor = self.conn.cursor()

            # Get all images including stale ones to check for restoration
            cursor.execute('SELECT filepath, stale_at FROM images')
            all_images = [(row[0], row[1]) for row in cursor.fetchall()]

        # Separate into categories (outside lock for file I/O)
        missing = []
        restored = []
        for filepath, stale_at in all_images:
            exists = os.path.exists(filepath)
            if not exists and stale_at is None:
                # File missing and not yet marked stale
                missing.append(filepath)
            elif exists and stale_at is not None:
                # File returned, was previously stale
                restored.append(filepath)

        results = {'marked_stale': 0, 'restored': 0}

        # Mark missing files as stale
        if missing:
            results['marked_stale'] = self.mark_images_stale(missing)

        # Restore files that have reappeared
        if restored:
            with self._lock:
                cursor = self.conn.cursor()
                for i in range(0, len(restored), 500):
                    chunk = restored[i:i+500]
                    placeholders = ','.join('?' * len(chunk))
                    cursor.execute(
                        f'UPDATE images SET stale_at = NULL WHERE filepath IN ({placeholders})',
                        chunk
                    )
                    results['restored'] += cursor.rowcount
                self.conn.commit()
                if results['restored'] > 0:
                    logger.info(f"Restored {results['restored']} images (files reappeared)")

        return results

    # =========================================================================
    # Soft-Delete Operations
    # =========================================================================

    def mark_images_stale(self, file_paths: List[str]) -> int:
        """Mark images as stale instead of deleting them.

        Soft-delete operation that sets stale_at timestamp. Stale images are
        excluded from selection but retain their data (including palettes) for
        potential recovery. Use purge_stale_images() to permanently remove
        entries that have been stale for more than the retention period.

        Args:
            file_paths: List of image filepaths to mark as stale.

        Returns:
            Number of images marked as stale.
        """
        if not file_paths:
            return 0

        now = int(time.time())
        with self._lock:
            cursor = self.conn.cursor()
            marked = 0
            # SQLite has 999 parameter limit, batch in chunks of 500
            for i in range(0, len(file_paths), 500):
                chunk = file_paths[i:i+500]
                placeholders = ','.join('?' * len(chunk))
                cursor.execute(
                    f'UPDATE images SET stale_at = ? WHERE filepath IN ({placeholders}) '
                    f'AND stale_at IS NULL',
                    [now] + chunk
                )
                marked += cursor.rowcount
            self.conn.commit()
            if marked > 0:
                logger.info(f"Marked {marked} images as stale")
            return marked

    def purge_stale_images(self, older_than_days: int = 14) -> int:
        """Permanently delete images that have been stale for too long.

        Hard-deletes images (and their palettes) that were marked stale more
        than older_than_days ago. This is the final cleanup step for soft-deleted
        entries that haven't been restored.

        Args:
            older_than_days: Only purge entries stale for more than this many days.
                Default is 14 days (2 weeks retention).

        Returns:
            Number of images purged (hard-deleted).
        """
        cutoff = int(time.time()) - (older_than_days * 86400)
        with self._lock:
            cursor = self.conn.cursor()

            # First, get filepaths of images to purge for logging
            cursor.execute(
                'SELECT filepath FROM images WHERE stale_at IS NOT NULL AND stale_at < ?',
                (cutoff,)
            )
            to_purge = [row[0] for row in cursor.fetchall()]

            if not to_purge:
                return 0

            # Delete palettes first (explicit control, not relying on CASCADE)
            placeholders = ','.join('?' * len(to_purge))
            cursor.execute(
                f'DELETE FROM palettes WHERE filepath IN ({placeholders})',
                to_purge
            )

            # Then delete the images
            cursor.execute(
                f'DELETE FROM images WHERE filepath IN ({placeholders})',
                to_purge
            )

            self.conn.commit()
            logger.info(f"Purged {len(to_purge)} stale images (older than {older_than_days} days)")
            return len(to_purge)

    def restore_stale_image(self, file_path: str) -> bool:
        """Restore a stale image by clearing its stale_at timestamp.

        Use this when a previously missing file has returned (e.g., drive
        remounted, file restored from backup). The image becomes eligible
        for selection again with all its data intact.

        Args:
            file_path: Path to the image to restore.

        Returns:
            True if the image was restored, False if not found or not stale.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                'UPDATE images SET stale_at = NULL WHERE filepath = ? AND stale_at IS NOT NULL',
                (file_path,)
            )
            restored = cursor.rowcount > 0
            self.conn.commit()
            if restored:
                logger.debug(f"Restored stale image: {file_path}")
            return restored

    def count_stale_images(self) -> int:
        """Count images currently marked as stale.

        Returns:
            Number of stale images pending purge.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM images WHERE stale_at IS NOT NULL')
            return cursor.fetchone()[0]

    def get_stale_images(self, limit: Optional[int] = None) -> List[ImageRecord]:
        """Get images that are currently marked as stale.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of stale ImageRecords.
        """
        with self._lock:
            cursor = self.conn.cursor()
            query = 'SELECT * FROM images WHERE stale_at IS NOT NULL ORDER BY stale_at'
            if limit:
                query += f' LIMIT {limit}'
            cursor.execute(query)
            return [self._row_to_image_record(row) for row in cursor.fetchall()]

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
                    last_indexed_at, last_shown_at, times_shown, palette_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    times_shown = excluded.times_shown,
                    palette_status = excluded.palette_status
            ''', [
                (
                    r.filepath, r.filename, r.source_id, r.width, r.height,
                    r.aspect_ratio, r.file_size, r.file_mtime,
                    1 if r.is_favorite else 0, r.first_indexed_at,
                    r.last_indexed_at, r.last_shown_at, r.times_shown,
                    r.palette_status,
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

    def batch_delete_images(self, filepaths: List[str], soft_delete: bool = True) -> int:
        """Delete multiple images in a single transaction.

        By default uses soft-delete (marks as stale) to preserve palette data.
        Use soft_delete=False for hard deletion when data should be removed
        completely (e.g., explicit user action).

        Args:
            filepaths: List of filepaths to delete.
            soft_delete: If True (default), mark as stale instead of deleting.
                If False, hard delete images and their palettes.

        Returns:
            Number of images affected (marked stale or deleted).
        """
        if not filepaths:
            return 0

        if soft_delete:
            # Soft-delete: mark as stale, preserve palette data
            return self.mark_images_stale(filepaths)

        # Hard delete: remove images and palettes
        with self._lock:
            cursor = self.conn.cursor()
            deleted = 0
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
                deleted += cursor.rowcount
            self.conn.commit()
            return deleted
