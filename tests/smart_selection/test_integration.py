# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Integration tests for Smart Selection Engine."""

import os
import shutil
import tempfile
import unittest
from PIL import Image


class TestStartupIndexing(unittest.TestCase):
    """Tests for startup indexing behavior."""

    def setUp(self):
        """Create temporary directories simulating Variety folder structure."""
        self.temp_dir = tempfile.mkdtemp()

        # Create folder structure
        self.favorites_dir = os.path.join(self.temp_dir, 'Favorites')
        self.downloaded_dir = os.path.join(self.temp_dir, 'Downloaded')
        self.fetched_dir = os.path.join(self.temp_dir, 'Fetched')
        self.user_folder = os.path.join(self.temp_dir, 'UserFolder')
        self.db_path = os.path.join(self.temp_dir, 'smart_selection.db')

        for folder in [self.favorites_dir, self.downloaded_dir,
                       self.fetched_dir, self.user_folder]:
            os.makedirs(folder)

        # Create test images in each folder
        self.images = {}
        for name, folder in [('fav', self.favorites_dir),
                              ('dl', self.downloaded_dir),
                              ('fetch', self.fetched_dir),
                              ('user', self.user_folder)]:
            paths = []
            for i in range(3):
                img_path = os.path.join(folder, f'{name}_{i}.jpg')
                img = Image.new('RGB', (100, 100), color=(i*50, i*50, i*50))
                img.save(img_path)
                paths.append(img_path)
            self.images[name] = paths

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_startup_indexes_all_enabled_sources(self):
        """Startup should index favorites, downloaded, fetched, and user folders."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        # Simulate what _init_smart_selector should do
        config = SelectionConfig()

        with SmartSelector(self.db_path, config) as selector:
            indexer = ImageIndexer(selector.db, favorites_folder=self.favorites_dir)

            # Index all source folders (this is what we're testing should happen)
            folders_to_index = [
                self.favorites_dir,
                self.downloaded_dir,
                self.fetched_dir,
                self.user_folder,
            ]

            total_indexed = 0
            for folder in folders_to_index:
                count = indexer.index_directory(folder, recursive=True)
                total_indexed += count

            # Verify all images are indexed
            db_count = selector.db.count_images()
            self.assertEqual(db_count, 12,
                f"Expected 12 images indexed (3 per folder), got {db_count}")

            # Verify favorites are marked correctly
            for fav_path in self.images['fav']:
                img = selector.db.get_image(fav_path)
                self.assertIsNotNone(img)
                self.assertTrue(img.is_favorite,
                    f"Image {fav_path} should be marked as favorite")


class TestOnTheFlyIndexing(unittest.TestCase):
    """Tests for indexing images when they are shown."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create a test image
        self.test_image = os.path.join(self.images_dir, 'test.jpg')
        img = Image.new('RGB', (100, 100))
        img.save(self.test_image)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_record_shown_indexes_unknown_image(self):
        """record_shown should index an image if it's not in the database."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Image is not in database yet
            img = selector.db.get_image(self.test_image)
            self.assertIsNone(img, "Image should not be in database yet")

            # Call record_shown (simulates wallpaper being set)
            selector.record_shown(self.test_image)

            # Image should now be in database
            img = selector.db.get_image(self.test_image)
            self.assertIsNotNone(img, "Image should be indexed after record_shown")
            self.assertEqual(img.times_shown, 1)


if __name__ == '__main__':
    unittest.main()
