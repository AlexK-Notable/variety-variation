#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.indexer - Directory scanning and indexing."""

import os
import tempfile
import shutil
import unittest
from PIL import Image


class TestImageIndexer(unittest.TestCase):
    """Tests for ImageIndexer class."""

    def setUp(self):
        """Create temporary directories with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

        # Create test image directories
        self.wallpapers_dir = os.path.join(self.temp_dir, 'wallpapers')
        self.unsplash_dir = os.path.join(self.wallpapers_dir, 'unsplash')
        self.wallhaven_dir = os.path.join(self.wallpapers_dir, 'wallhaven')
        self.favorites_dir = os.path.join(self.temp_dir, 'favorites')

        os.makedirs(self.unsplash_dir)
        os.makedirs(self.wallhaven_dir)
        os.makedirs(self.favorites_dir)

        # Create test images
        self._create_test_image(os.path.join(self.unsplash_dir, 'img1.jpg'), 1920, 1080)
        self._create_test_image(os.path.join(self.unsplash_dir, 'img2.png'), 2560, 1440)
        self._create_test_image(os.path.join(self.wallhaven_dir, 'wall1.jpg'), 3840, 2160)
        self._create_test_image(os.path.join(self.favorites_dir, 'fav1.jpg'), 1920, 1080)

        # Create a non-image file
        with open(os.path.join(self.unsplash_dir, 'readme.txt'), 'w') as f:
            f.write('not an image')

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.temp_dir)

    def _create_test_image(self, path: str, width: int, height: int):
        """Create a test image with specified dimensions."""
        img = Image.new('RGB', (width, height), color='blue')
        img.save(path)

    def test_import_image_indexer(self):
        """ImageIndexer can be imported from smart_selection.indexer."""
        from variety.smart_selection.indexer import ImageIndexer
        self.assertIsNotNone(ImageIndexer)

    def test_indexer_creation(self):
        """ImageIndexer can be created with database and config."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            self.assertIsNotNone(indexer)

    def test_scan_directory_finds_images(self):
        """scan_directory finds all image files in a directory."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            images = indexer.scan_directory(self.unsplash_dir)

            # Should find 2 images, not the txt file
            self.assertEqual(len(images), 2)
            filenames = {os.path.basename(img) for img in images}
            self.assertEqual(filenames, {'img1.jpg', 'img2.png'})

    def test_scan_directory_recursive(self):
        """scan_directory can recursively scan subdirectories."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            images = indexer.scan_directory(self.wallpapers_dir, recursive=True)

            # Should find images in both subdirectories
            self.assertEqual(len(images), 3)

    def test_index_image_extracts_metadata(self):
        """index_image extracts correct metadata from an image."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        image_path = os.path.join(self.unsplash_dir, 'img1.jpg')

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            record = indexer.index_image(image_path)

            self.assertEqual(record.filepath, image_path)
            self.assertEqual(record.filename, 'img1.jpg')
            self.assertEqual(record.width, 1920)
            self.assertEqual(record.height, 1080)
            self.assertAlmostEqual(record.aspect_ratio, 1920/1080, places=2)
            self.assertIsNotNone(record.file_size)
            self.assertIsNotNone(record.file_mtime)

    def test_index_image_derives_source_id(self):
        """index_image derives source_id from parent directory."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        image_path = os.path.join(self.unsplash_dir, 'img1.jpg')

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            record = indexer.index_image(image_path)

            self.assertEqual(record.source_id, 'unsplash')

    def test_index_directory_populates_database(self):
        """index_directory scans and adds images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            count = indexer.index_directory(self.unsplash_dir)

            self.assertEqual(count, 2)

            # Verify images are in database
            all_images = db.get_all_images()
            self.assertEqual(len(all_images), 2)

    def test_index_directory_marks_favorites(self):
        """index_directory marks images in favorites folder as favorites."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db, favorites_folder=self.favorites_dir)
            indexer.index_directory(self.favorites_dir)

            favorites = db.get_favorite_images()
            self.assertEqual(len(favorites), 1)
            self.assertTrue(favorites[0].is_favorite)

    def test_index_directory_creates_sources(self):
        """index_directory creates source records for each source."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(self.wallpapers_dir, recursive=True)

            sources = db.get_all_sources()
            source_ids = {s.source_id for s in sources}

            self.assertIn('unsplash', source_ids)
            self.assertIn('wallhaven', source_ids)

    def test_index_directory_skips_existing_unchanged(self):
        """index_directory skips images that haven't changed."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)

            # First index
            count1 = indexer.index_directory(self.unsplash_dir)
            self.assertEqual(count1, 2)

            # Second index should skip unchanged
            count2 = indexer.index_directory(self.unsplash_dir)
            self.assertEqual(count2, 0)

    def test_index_directory_updates_changed(self):
        """index_directory re-indexes images that have changed."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)

            # First index
            indexer.index_directory(self.unsplash_dir)

            # Modify an image and set mtime to future to ensure detection
            image_path = os.path.join(self.unsplash_dir, 'img1.jpg')
            self._create_test_image(image_path, 800, 600)
            # Set mtime to 10 seconds in the future to ensure change is detected
            future_time = int(os.path.getmtime(image_path)) + 10
            os.utime(image_path, (future_time, future_time))

            # Second index should update the changed image
            count = indexer.index_directory(self.unsplash_dir)
            self.assertEqual(count, 1)

            # Verify updated dimensions
            record = db.get_image(image_path)
            self.assertEqual(record.width, 800)
            self.assertEqual(record.height, 600)


class TestIndexerImageFormats(unittest.TestCase):
    """Tests for supported image formats."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _create_test_image(self, path: str, format: str = 'RGB'):
        """Create a test image in specified format."""
        img = Image.new(format, (100, 100), color='red')
        img.save(path)

    def test_indexes_jpg(self):
        """Indexer handles JPG files."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        path = os.path.join(self.temp_dir, 'test.jpg')
        self._create_test_image(path)

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            record = indexer.index_image(path)
            self.assertIsNotNone(record)

    def test_indexes_png(self):
        """Indexer handles PNG files."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        path = os.path.join(self.temp_dir, 'test.png')
        self._create_test_image(path, 'RGBA')

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            record = indexer.index_image(path)
            self.assertIsNotNone(record)

    def test_indexes_webp(self):
        """Indexer handles WebP files."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        path = os.path.join(self.temp_dir, 'test.webp')
        self._create_test_image(path)

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            record = indexer.index_image(path)
            self.assertIsNotNone(record)

    def test_skips_non_images(self):
        """Indexer skips non-image files."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        path = os.path.join(self.temp_dir, 'test.txt')
        with open(path, 'w') as f:
            f.write('not an image')

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            record = indexer.index_image(path)
            self.assertIsNone(record)


class TestIndexerStatistics(unittest.TestCase):
    """Tests for indexer statistics and reporting."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

        # Create test images
        for i in range(5):
            img = Image.new('RGB', (100, 100), color='blue')
            img.save(os.path.join(self.temp_dir, f'img{i}.jpg'))

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_get_index_stats(self):
        """get_index_stats returns correct statistics."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(self.temp_dir)

            stats = indexer.get_index_stats()

            self.assertEqual(stats['total_images'], 5)
            self.assertIn('total_sources', stats)
            self.assertIn('images_with_palettes', stats)


if __name__ == '__main__':
    unittest.main()
