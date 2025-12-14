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

    def test_close_is_thread_safe(self):
        """Verify close() holds lock to prevent use-after-close."""
        import threading
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    # This should either succeed or raise cleanly
                    try:
                        db.get_all_images()
                    except Exception as e:
                        if "closed database" in str(e).lower():
                            errors.append(e)
            except Exception as e:
                errors.append(e)

        # Start worker threads
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()

        # Close database while threads are running
        time.sleep(0.01)
        db.close()

        for t in threads:
            t.join()

        # Should not have any "closed database" errors - threads should
        # either complete before close or be blocked by the lock
        closed_errors = [e for e in errors if "closed" in str(e).lower()]
        self.assertEqual(len(closed_errors), 0, f"Got use-after-close errors: {closed_errors}")

    def test_close_idempotent(self):
        """Verify close() can be called multiple times safely."""
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        db.close()
        db.close()  # Should not raise
        db.close()  # Should not raise


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


class TestStatisticsQueries(unittest.TestCase):
    """Tests for collection statistics aggregate queries."""

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

    def test_get_lightness_counts_empty_database(self):
        """get_lightness_counts returns zeros for empty database."""
        counts = self.db.get_lightness_counts()

        self.assertEqual(counts['dark'], 0)
        self.assertEqual(counts['medium_dark'], 0)
        self.assertEqual(counts['medium_light'], 0)
        self.assertEqual(counts['light'], 0)

    def test_get_lightness_counts_with_data(self):
        """get_lightness_counts correctly buckets images by lightness."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Add images with palettes in different lightness ranges
        images = [
            ('/dark1.jpg', 0.10),      # dark
            ('/dark2.jpg', 0.24),      # dark
            ('/medium_dark.jpg', 0.30), # medium_dark
            ('/medium_light.jpg', 0.60), # medium_light
            ('/light1.jpg', 0.80),     # light
            ('/light2.jpg', 0.95),     # light
        ]

        for filepath, lightness in images:
            self.db.insert_image(ImageRecord(filepath=filepath, filename=filepath.split('/')[-1]))
            self.db.upsert_palette(PaletteRecord(filepath=filepath, avg_lightness=lightness))

        counts = self.db.get_lightness_counts()

        self.assertEqual(counts['dark'], 2)
        self.assertEqual(counts['medium_dark'], 1)
        self.assertEqual(counts['medium_light'], 1)
        self.assertEqual(counts['light'], 2)

    def test_get_lightness_counts_boundary_values(self):
        """get_lightness_counts handles boundary values correctly."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Test exact boundary values
        images = [
            ('/boundary_0.jpg', 0.0),    # dark
            ('/boundary_25.jpg', 0.25),  # medium_dark
            ('/boundary_50.jpg', 0.50),  # medium_light
            ('/boundary_75.jpg', 0.75),  # light
            ('/boundary_100.jpg', 1.0),  # light
        ]

        for filepath, lightness in images:
            self.db.insert_image(ImageRecord(filepath=filepath, filename=filepath.split('/')[-1]))
            self.db.upsert_palette(PaletteRecord(filepath=filepath, avg_lightness=lightness))

        counts = self.db.get_lightness_counts()

        self.assertEqual(counts['dark'], 1)
        self.assertEqual(counts['medium_dark'], 1)
        self.assertEqual(counts['medium_light'], 1)
        self.assertEqual(counts['light'], 2)

    def test_get_hue_counts_empty_database(self):
        """get_hue_counts returns zeros for empty database."""
        counts = self.db.get_hue_counts()

        self.assertEqual(counts['neutral'], 0)
        self.assertEqual(counts['red'], 0)
        self.assertEqual(counts['orange'], 0)
        self.assertEqual(counts['yellow'], 0)
        self.assertEqual(counts['green'], 0)
        self.assertEqual(counts['cyan'], 0)
        self.assertEqual(counts['blue'], 0)
        self.assertEqual(counts['purple'], 0)
        self.assertEqual(counts['pink'], 0)

    def test_get_hue_counts_with_data(self):
        """get_hue_counts correctly categorizes images by hue family."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Add images with palettes in different hue families
        images = [
            ('/red1.jpg', 5.0, 0.8),      # red
            ('/red2.jpg', 350.0, 0.7),    # red (wraps around)
            ('/orange.jpg', 30.0, 0.6),   # orange
            ('/yellow.jpg', 60.0, 0.7),   # yellow
            ('/green1.jpg', 100.0, 0.8),  # green
            ('/green2.jpg', 150.0, 0.6),  # green
            ('/cyan.jpg', 180.0, 0.7),    # cyan
            ('/blue1.jpg', 220.0, 0.9),   # blue
            ('/blue2.jpg', 240.0, 0.8),   # blue
            ('/purple.jpg', 270.0, 0.7),  # purple
            ('/pink.jpg', 310.0, 0.8),    # pink
        ]

        for filepath, hue, saturation in images:
            self.db.insert_image(ImageRecord(filepath=filepath, filename=filepath.split('/')[-1]))
            self.db.upsert_palette(PaletteRecord(
                filepath=filepath,
                avg_hue=hue,
                avg_saturation=saturation
            ))

        counts = self.db.get_hue_counts()

        self.assertEqual(counts['neutral'], 0)
        self.assertEqual(counts['red'], 2)
        self.assertEqual(counts['orange'], 1)
        self.assertEqual(counts['yellow'], 1)
        self.assertEqual(counts['green'], 2)
        self.assertEqual(counts['cyan'], 1)
        self.assertEqual(counts['blue'], 2)
        self.assertEqual(counts['purple'], 1)
        self.assertEqual(counts['pink'], 1)

    def test_get_hue_counts_neutral_grayscale(self):
        """get_hue_counts categorizes low-saturation images as neutral."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Add grayscale/desaturated images with various hue values
        images = [
            ('/gray1.jpg', 0.0, 0.05),    # neutral (low saturation)
            ('/gray2.jpg', 180.0, 0.08),  # neutral (low saturation)
            ('/gray3.jpg', 270.0, 0.02),  # neutral (low saturation)
            ('/color.jpg', 120.0, 0.8),   # green (high saturation)
        ]

        for filepath, hue, saturation in images:
            self.db.insert_image(ImageRecord(filepath=filepath, filename=filepath.split('/')[-1]))
            self.db.upsert_palette(PaletteRecord(
                filepath=filepath,
                avg_hue=hue,
                avg_saturation=saturation
            ))

        counts = self.db.get_hue_counts()

        self.assertEqual(counts['neutral'], 3)
        self.assertEqual(counts['green'], 1)

    def test_get_saturation_counts_empty_database(self):
        """get_saturation_counts returns zeros for empty database."""
        counts = self.db.get_saturation_counts()

        self.assertEqual(counts['muted'], 0)
        self.assertEqual(counts['moderate'], 0)
        self.assertEqual(counts['saturated'], 0)
        self.assertEqual(counts['vibrant'], 0)

    def test_get_saturation_counts_with_data(self):
        """get_saturation_counts correctly buckets images by saturation."""
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Add images with palettes in different saturation ranges
        images = [
            ('/muted1.jpg', 0.10),      # muted
            ('/muted2.jpg', 0.20),      # muted
            ('/moderate.jpg', 0.40),    # moderate
            ('/saturated1.jpg', 0.60),  # saturated
            ('/saturated2.jpg', 0.70),  # saturated
            ('/vibrant1.jpg', 0.85),    # vibrant
            ('/vibrant2.jpg', 0.95),    # vibrant
        ]

        for filepath, saturation in images:
            self.db.insert_image(ImageRecord(filepath=filepath, filename=filepath.split('/')[-1]))
            self.db.upsert_palette(PaletteRecord(filepath=filepath, avg_saturation=saturation))

        counts = self.db.get_saturation_counts()

        self.assertEqual(counts['muted'], 2)
        self.assertEqual(counts['moderate'], 1)
        self.assertEqual(counts['saturated'], 2)
        self.assertEqual(counts['vibrant'], 2)

    def test_get_freshness_counts_empty_database(self):
        """get_freshness_counts returns zeros for empty database."""
        counts = self.db.get_freshness_counts()

        self.assertEqual(counts['never_shown'], 0)
        self.assertEqual(counts['rarely_shown'], 0)
        self.assertEqual(counts['often_shown'], 0)
        self.assertEqual(counts['frequently_shown'], 0)

    def test_get_freshness_counts_with_data(self):
        """get_freshness_counts correctly categorizes images by times_shown."""
        from variety.smart_selection.models import ImageRecord

        # Add images with different times_shown values
        images = [
            ('/never1.jpg', 0),           # never_shown
            ('/never2.jpg', 0),           # never_shown
            ('/rarely1.jpg', 1),          # rarely_shown
            ('/rarely2.jpg', 4),          # rarely_shown
            ('/often1.jpg', 5),           # often_shown
            ('/often2.jpg', 9),           # often_shown
            ('/frequent1.jpg', 10),       # frequently_shown
            ('/frequent2.jpg', 25),       # frequently_shown
            ('/frequent3.jpg', 100),      # frequently_shown
        ]

        for filepath, times_shown in images:
            self.db.insert_image(ImageRecord(
                filepath=filepath,
                filename=filepath.split('/')[-1],
                times_shown=times_shown
            ))

        counts = self.db.get_freshness_counts()

        self.assertEqual(counts['never_shown'], 2)
        self.assertEqual(counts['rarely_shown'], 2)
        self.assertEqual(counts['often_shown'], 2)
        self.assertEqual(counts['frequently_shown'], 3)

    def test_get_freshness_counts_boundary_values(self):
        """get_freshness_counts handles boundary values correctly."""
        from variety.smart_selection.models import ImageRecord

        # Test exact boundary values
        images = [
            ('/boundary_0.jpg', 0),   # never_shown
            ('/boundary_1.jpg', 1),   # rarely_shown
            ('/boundary_4.jpg', 4),   # rarely_shown
            ('/boundary_5.jpg', 5),   # often_shown
            ('/boundary_9.jpg', 9),   # often_shown
            ('/boundary_10.jpg', 10), # frequently_shown
        ]

        for filepath, times_shown in images:
            self.db.insert_image(ImageRecord(
                filepath=filepath,
                filename=filepath.split('/')[-1],
                times_shown=times_shown
            ))

        counts = self.db.get_freshness_counts()

        self.assertEqual(counts['never_shown'], 1)
        self.assertEqual(counts['rarely_shown'], 2)
        self.assertEqual(counts['often_shown'], 2)
        self.assertEqual(counts['frequently_shown'], 1)

    def test_statistics_queries_are_thread_safe(self):
        """Statistics queries work correctly with concurrent access."""
        import threading
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        # Pre-populate database
        for i in range(20):
            self.db.insert_image(ImageRecord(
                filepath=f'/img{i}.jpg',
                filename=f'img{i}.jpg',
                times_shown=i
            ))
            self.db.upsert_palette(PaletteRecord(
                filepath=f'/img{i}.jpg',
                avg_lightness=i / 20.0,
                avg_saturation=i / 20.0,
                avg_hue=i * 18.0  # 0-360 spread
            ))

        errors = []
        results = []

        def query_stats():
            try:
                lightness = self.db.get_lightness_counts()
                hue = self.db.get_hue_counts()
                saturation = self.db.get_saturation_counts()
                freshness = self.db.get_freshness_counts()
                results.append((lightness, hue, saturation, freshness))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=query_stats) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        self.assertEqual(errors, [], f"Thread errors occurred: {errors}")

        # All threads should get the same results
        self.assertEqual(len(results), 5)
        for result in results[1:]:
            self.assertEqual(result, results[0])


class TestBatchSourceLoading(unittest.TestCase):
    """Tests for batch source loading."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_get_sources_by_ids(self):
        """Verify batch source loading returns correct records."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SourceRecord

        db = ImageDatabase(self.db_path)

        # Create test sources
        for i in range(5):
            source = SourceRecord(
                source_id=f"source_{i}",
                source_type="test",
            )
            db.upsert_source(source)

        # Fetch subset
        result = db.get_sources_by_ids(["source_1", "source_3", "source_99"])

        self.assertEqual(len(result), 2)  # source_99 doesn't exist
        self.assertIn("source_1", result)
        self.assertIn("source_3", result)
        self.assertNotIn("source_99", result)

        db.close()


class TestBatchDeleteImages(unittest.TestCase):
    """Tests for batch_delete_images functionality."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_batch_delete_removes_palettes(self):
        """Verify batch delete also removes associated palette records."""
        from variety.smart_selection.database import ImageDatabase, ImageRecord, PaletteRecord

        db = ImageDatabase(self.db_path)

        # Create test image and palette
        image = ImageRecord(
            filepath="/test/image1.jpg",
            filename="image1.jpg",
            source_id="test",
        )
        db.upsert_image(image)

        palette = PaletteRecord(
            filepath="/test/image1.jpg",
            color0="#ffffff",
            avg_lightness=0.5,
        )
        db.upsert_palette(palette)

        # Verify palette exists
        self.assertIsNotNone(db.get_palette("/test/image1.jpg"))

        # Delete the image
        db.batch_delete_images(["/test/image1.jpg"])

        # Palette should also be deleted
        self.assertIsNone(db.get_palette("/test/image1.jpg"))
        self.assertIsNone(db.get_image("/test/image1.jpg"))

        db.close()

    def test_batch_delete_multiple_with_palettes(self):
        """Verify batch delete handles multiple images with palettes."""
        from variety.smart_selection.database import ImageDatabase, ImageRecord, PaletteRecord

        db = ImageDatabase(self.db_path)

        # Create 3 images, 2 with palettes
        for i in range(3):
            image = ImageRecord(
                filepath=f"/test/image{i}.jpg",
                filename=f"image{i}.jpg",
                source_id="test",
            )
            db.upsert_image(image)

            if i < 2:  # Only first 2 have palettes
                palette = PaletteRecord(
                    filepath=f"/test/image{i}.jpg",
                    color0="#ffffff",
                )
                db.upsert_palette(palette)

        # Delete all 3
        db.batch_delete_images([f"/test/image{i}.jpg" for i in range(3)])

        # All should be gone
        for i in range(3):
            self.assertIsNone(db.get_image(f"/test/image{i}.jpg"))
            self.assertIsNone(db.get_palette(f"/test/image{i}.jpg"))

        db.close()


class TestBatchPaletteLoading(unittest.TestCase):
    """Tests for batch palette loading."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_get_palettes_by_filepaths(self):
        """Verify batch palette loading returns correct records."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        db = ImageDatabase(self.db_path)

        # Create test images and palettes
        for i in range(5):
            filepath = f"/test/image{i}.jpg"
            image = ImageRecord(filepath=filepath, filename=f"image{i}.jpg")
            db.upsert_image(image)

            if i < 3:  # Only first 3 have palettes
                palette = PaletteRecord(filepath=filepath, color0="#ffffff")
                db.upsert_palette(palette)

        # Fetch all filepaths
        filepaths = [f"/test/image{i}.jpg" for i in range(5)]
        result = db.get_palettes_by_filepaths(filepaths)

        self.assertEqual(len(result), 3)  # Only 3 have palettes
        self.assertIn("/test/image0.jpg", result)
        self.assertIn("/test/image1.jpg", result)
        self.assertIn("/test/image2.jpg", result)
        self.assertNotIn("/test/image3.jpg", result)

        db.close()


class TestDatabaseBackup(unittest.TestCase):
    """Tests for database backup functionality."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')

    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_backup_checkpoints_wal(self):
        """Verify backup creates a complete, consistent copy."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Add some data
        for i in range(10):
            image = ImageRecord(
                filepath=f"/test/image{i}.jpg",
                filename=f"image{i}.jpg",
            )
            db.upsert_image(image)

        # Create backup
        backup_path = self.db_path + ".backup"
        result = db.backup(backup_path)
        self.assertTrue(result)

        # Verify backup is readable and complete
        backup_db = ImageDatabase(backup_path)
        images = backup_db.get_all_images()
        self.assertEqual(len(images), 10)

        backup_db.close()
        db.close()


if __name__ == '__main__':
    unittest.main()
