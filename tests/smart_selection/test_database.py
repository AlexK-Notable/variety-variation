#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.database - SQLite database operations."""

import os
import tempfile
import unittest
import time


class TestImageDatabase(unittest.TestCase):
    """Tests for ImageDatabase class."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_import_image_database(self):
        """ImageDatabase can be imported from smart_selection.database."""
        from variety.smart_selection.database import ImageDatabase
        self.assertIsNotNone(ImageDatabase)

    def test_database_creates_file(self):
        """Database file is created when ImageDatabase is instantiated."""
        from variety.smart_selection.database import ImageDatabase

        self.assertFalse(os.path.exists(self.db_path))
        db = ImageDatabase(self.db_path)
        db.close()
        self.assertTrue(os.path.exists(self.db_path))

    def test_database_creates_images_table(self):
        """Images table is created with correct schema."""
        from variety.smart_selection.database import ImageDatabase
        import sqlite3

        db = ImageDatabase(self.db_path)
        db.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
        result = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'images')

    def test_database_creates_sources_table(self):
        """Sources table is created with correct schema."""
        from variety.smart_selection.database import ImageDatabase
        import sqlite3

        db = ImageDatabase(self.db_path)
        db.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sources'")
        result = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(result)

    def test_database_creates_palettes_table(self):
        """Palettes table is created with correct schema."""
        from variety.smart_selection.database import ImageDatabase
        import sqlite3

        db = ImageDatabase(self.db_path)
        db.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='palettes'")
        result = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(result)


class TestImageCRUD(unittest.TestCase):
    """Tests for ImageRecord CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        from variety.smart_selection.database import ImageDatabase
        self.db = ImageDatabase(self.db_path)

    def tearDown(self):
        """Clean up temporary database."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_insert_image(self):
        """Can insert an ImageRecord into the database."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
            source_id='unsplash',
            width=1920,
            height=1080,
        )
        self.db.insert_image(record)

        # Verify it was inserted
        result = self.db.get_image('/path/to/image.jpg')
        self.assertIsNotNone(result)
        self.assertEqual(result.filepath, '/path/to/image.jpg')
        self.assertEqual(result.width, 1920)

    def test_get_image_returns_none_for_nonexistent(self):
        """get_image returns None for nonexistent filepath."""
        result = self.db.get_image('/nonexistent/path.jpg')
        self.assertIsNone(result)

    def test_update_image(self):
        """Can update an existing ImageRecord."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
            times_shown=0,
        )
        self.db.insert_image(record)

        # Update the record
        record.times_shown = 5
        record.last_shown_at = int(time.time())
        self.db.update_image(record)

        # Verify update
        result = self.db.get_image('/path/to/image.jpg')
        self.assertEqual(result.times_shown, 5)
        self.assertIsNotNone(result.last_shown_at)

    def test_upsert_image_inserts_new(self):
        """upsert_image inserts a new record if it doesn't exist."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/new.jpg',
            filename='new.jpg',
        )
        self.db.upsert_image(record)

        result = self.db.get_image('/path/to/new.jpg')
        self.assertIsNotNone(result)

    def test_upsert_image_updates_existing(self):
        """upsert_image updates an existing record."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
            times_shown=0,
        )
        self.db.insert_image(record)

        # Upsert with new data
        record.times_shown = 10
        self.db.upsert_image(record)

        result = self.db.get_image('/path/to/image.jpg')
        self.assertEqual(result.times_shown, 10)

    def test_delete_image(self):
        """Can delete an ImageRecord from the database."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
        )
        self.db.insert_image(record)
        self.assertIsNotNone(self.db.get_image('/path/to/image.jpg'))

        self.db.delete_image('/path/to/image.jpg')
        self.assertIsNone(self.db.get_image('/path/to/image.jpg'))

    def test_get_all_images(self):
        """Can retrieve all images from the database."""
        from variety.smart_selection.models import ImageRecord

        for i in range(5):
            record = ImageRecord(
                filepath=f'/path/to/image{i}.jpg',
                filename=f'image{i}.jpg',
            )
            self.db.insert_image(record)

        results = self.db.get_all_images()
        self.assertEqual(len(results), 5)

    def test_get_images_by_source(self):
        """Can filter images by source_id."""
        from variety.smart_selection.models import ImageRecord

        for i in range(3):
            self.db.insert_image(ImageRecord(
                filepath=f'/unsplash/image{i}.jpg',
                filename=f'image{i}.jpg',
                source_id='unsplash',
            ))

        for i in range(2):
            self.db.insert_image(ImageRecord(
                filepath=f'/wallhaven/image{i}.jpg',
                filename=f'image{i}.jpg',
                source_id='wallhaven',
            ))

        unsplash_images = self.db.get_images_by_source('unsplash')
        self.assertEqual(len(unsplash_images), 3)

        wallhaven_images = self.db.get_images_by_source('wallhaven')
        self.assertEqual(len(wallhaven_images), 2)

    def test_get_favorite_images(self):
        """Can filter to only favorite images."""
        from variety.smart_selection.models import ImageRecord

        self.db.insert_image(ImageRecord(
            filepath='/fav1.jpg', filename='fav1.jpg', is_favorite=True
        ))
        self.db.insert_image(ImageRecord(
            filepath='/fav2.jpg', filename='fav2.jpg', is_favorite=True
        ))
        self.db.insert_image(ImageRecord(
            filepath='/normal.jpg', filename='normal.jpg', is_favorite=False
        ))

        favorites = self.db.get_favorite_images()
        self.assertEqual(len(favorites), 2)
        self.assertTrue(all(img.is_favorite for img in favorites))

    def test_record_image_shown(self):
        """record_image_shown updates last_shown_at and increments times_shown."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
            times_shown=0,
        )
        self.db.insert_image(record)

        before_time = int(time.time())
        self.db.record_image_shown('/path/to/image.jpg')

        result = self.db.get_image('/path/to/image.jpg')
        self.assertEqual(result.times_shown, 1)
        self.assertGreaterEqual(result.last_shown_at, before_time)


class TestSourceCRUD(unittest.TestCase):
    """Tests for SourceRecord CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        from variety.smart_selection.database import ImageDatabase
        self.db = ImageDatabase(self.db_path)

    def tearDown(self):
        """Clean up temporary database."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_upsert_source(self):
        """Can upsert a SourceRecord."""
        from variety.smart_selection.models import SourceRecord

        source = SourceRecord(
            source_id='unsplash',
            source_type='remote',
        )
        self.db.upsert_source(source)

        result = self.db.get_source('unsplash')
        self.assertIsNotNone(result)
        self.assertEqual(result.source_id, 'unsplash')

    def test_get_source_returns_none_for_nonexistent(self):
        """get_source returns None for nonexistent source_id."""
        result = self.db.get_source('nonexistent')
        self.assertIsNone(result)

    def test_record_source_shown(self):
        """record_source_shown updates last_shown_at and increments times_shown."""
        from variety.smart_selection.models import SourceRecord

        source = SourceRecord(source_id='unsplash', times_shown=0)
        self.db.upsert_source(source)

        before_time = int(time.time())
        self.db.record_source_shown('unsplash')

        result = self.db.get_source('unsplash')
        self.assertEqual(result.times_shown, 1)
        self.assertGreaterEqual(result.last_shown_at, before_time)

    def test_get_all_sources(self):
        """Can retrieve all sources."""
        from variety.smart_selection.models import SourceRecord

        self.db.upsert_source(SourceRecord(source_id='unsplash'))
        self.db.upsert_source(SourceRecord(source_id='wallhaven'))
        self.db.upsert_source(SourceRecord(source_id='local'))

        sources = self.db.get_all_sources()
        self.assertEqual(len(sources), 3)


class TestPaletteCRUD(unittest.TestCase):
    """Tests for PaletteRecord CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord
        self.db = ImageDatabase(self.db_path)
        # Insert an image first (foreign key constraint)
        self.db.insert_image(ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
        ))

    def tearDown(self):
        """Clean up temporary database."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_upsert_palette(self):
        """Can upsert a PaletteRecord."""
        from variety.smart_selection.models import PaletteRecord

        palette = PaletteRecord(
            filepath='/path/to/image.jpg',
            color0='#1a1b26',
            color1='#f7768e',
            background='#1a1b26',
            foreground='#c0caf5',
            avg_lightness=0.3,
        )
        self.db.upsert_palette(palette)

        result = self.db.get_palette('/path/to/image.jpg')
        self.assertIsNotNone(result)
        self.assertEqual(result.color0, '#1a1b26')
        self.assertEqual(result.avg_lightness, 0.3)

    def test_get_palette_returns_none_for_nonexistent(self):
        """get_palette returns None for nonexistent filepath."""
        result = self.db.get_palette('/nonexistent/path.jpg')
        self.assertIsNone(result)

    def test_get_images_with_palettes(self):
        """Can get images that have palette data."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Add more images
        self.db.insert_image(ImageRecord(filepath='/img2.jpg', filename='img2.jpg'))
        self.db.insert_image(ImageRecord(filepath='/img3.jpg', filename='img3.jpg'))

        # Add palette to only the first image
        self.db.upsert_palette(PaletteRecord(
            filepath='/path/to/image.jpg',
            color0='#000000',
        ))

        images_with_palettes = self.db.get_images_with_palettes()
        self.assertEqual(len(images_with_palettes), 1)
        self.assertEqual(images_with_palettes[0].filepath, '/path/to/image.jpg')

    def test_get_images_without_palettes(self):
        """Can get images that don't have palette data."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Add more images
        self.db.insert_image(ImageRecord(filepath='/img2.jpg', filename='img2.jpg'))
        self.db.insert_image(ImageRecord(filepath='/img3.jpg', filename='img3.jpg'))

        # Add palette to only the first image
        self.db.upsert_palette(PaletteRecord(
            filepath='/path/to/image.jpg',
            color0='#000000',
        ))

        images_without_palettes = self.db.get_images_without_palettes()
        self.assertEqual(len(images_without_palettes), 2)


class TestDatabaseContextManager(unittest.TestCase):
    """Tests for database context manager support."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_context_manager(self):
        """Database supports context manager protocol."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        with ImageDatabase(self.db_path) as db:
            db.insert_image(ImageRecord(
                filepath='/test.jpg',
                filename='test.jpg',
            ))
            result = db.get_image('/test.jpg')
            self.assertIsNotNone(result)


class TestDatabaseThreadSafety(unittest.TestCase):
    """Tests for thread-safe database operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_concurrent_inserts_are_thread_safe(self):
        """Multiple threads can insert records without data corruption."""
        import threading
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        errors = []
        num_threads = 10
        inserts_per_thread = 20

        def insert_records(thread_id):
            try:
                for i in range(inserts_per_thread):
                    record = ImageRecord(
                        filepath=f'/thread_{thread_id}_image_{i}.jpg',
                        filename=f'thread_{thread_id}_image_{i}.jpg',
                    )
                    db.insert_image(record)
            except Exception as e:
                errors.append((thread_id, e))

        threads = [
            threading.Thread(target=insert_records, args=(i,))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        db.close()

        # Should have no errors
        self.assertEqual(errors, [], f"Thread errors occurred: {errors}")

        # Verify all records were inserted
        db2 = ImageDatabase(self.db_path)
        count = db2.count_images()
        db2.close()
        expected = num_threads * inserts_per_thread
        self.assertEqual(count, expected,
                        f"Expected {expected} images, got {count}")

    def test_concurrent_reads_and_writes_are_thread_safe(self):
        """Concurrent read and write operations don't corrupt data."""
        import threading
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Pre-populate with some data
        for i in range(50):
            db.insert_image(ImageRecord(
                filepath=f'/initial_{i}.jpg',
                filename=f'initial_{i}.jpg',
            ))

        errors = []
        read_results = []

        def writer(writer_id):
            try:
                for i in range(20):
                    record = ImageRecord(
                        filepath=f'/writer_{writer_id}_image_{i}.jpg',
                        filename=f'writer_{writer_id}_image_{i}.jpg',
                    )
                    db.insert_image(record)
                    time.sleep(0.001)  # Small delay to interleave operations
            except Exception as e:
                errors.append(('writer', writer_id, e))

        def reader(reader_id):
            try:
                for _ in range(30):
                    images = db.get_all_images()
                    read_results.append(len(images))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(('reader', reader_id, e))

        # Create writer and reader threads
        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=writer, args=(i,)))
        for i in range(3):
            threads.append(threading.Thread(target=reader, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        db.close()

        # Should have no errors
        self.assertEqual(errors, [], f"Thread errors occurred: {errors}")

        # All reads should have returned valid counts
        self.assertTrue(all(r >= 50 for r in read_results),
                       "Read results should be >= initial count")

    def test_record_shown_is_thread_safe(self):
        """Concurrent record_shown calls update correctly."""
        import threading
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Create a single image
        db.insert_image(ImageRecord(
            filepath='/test_image.jpg',
            filename='test_image.jpg',
        ))

        errors = []
        num_threads = 10
        updates_per_thread = 10

        def update_shown(thread_id):
            try:
                for _ in range(updates_per_thread):
                    db.record_image_shown('/test_image.jpg')
            except Exception as e:
                errors.append((thread_id, e))

        threads = [
            threading.Thread(target=update_shown, args=(i,))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify times_shown is correct
        image = db.get_image('/test_image.jpg')
        db.close()

        self.assertEqual(errors, [], f"Thread errors occurred: {errors}")

        expected = num_threads * updates_per_thread
        self.assertEqual(image.times_shown, expected,
                        f"Expected times_shown={expected}, got {image.times_shown}")


class TestDatabaseResilience(unittest.TestCase):
    """Tests for database crash resilience and durability."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_wal_mode_enabled(self):
        """Database uses WAL mode for crash resilience.

        WAL (Write-Ahead Logging) mode provides:
        - Better crash recovery
        - Improved concurrent read/write performance
        - Reduced risk of database corruption
        """
        from variety.smart_selection.database import ImageDatabase
        import sqlite3

        db = ImageDatabase(self.db_path)
        db.close()

        # Check journal mode
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(mode.lower(), 'wal',
                        f"Expected WAL mode, got {mode}")


if __name__ == '__main__':
    unittest.main()
