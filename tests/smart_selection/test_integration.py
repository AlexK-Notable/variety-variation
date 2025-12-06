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


if __name__ == '__main__':
    unittest.main()
