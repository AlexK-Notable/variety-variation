#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Integration test - Index actual Favorites folder."""

import os
import tempfile
import unittest


class TestRealFavoritesIndexing(unittest.TestCase):
    """Integration test with the actual Favorites folder."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'integration_test.db')
        self.favorites_dir = os.path.expanduser('~/.config/variety/Favorites')

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    @unittest.skipUnless(
        os.path.exists(os.path.expanduser('~/.config/variety/Favorites')),
        "Favorites folder does not exist"
    )
    def test_index_real_favorites(self):
        """Index the actual Favorites folder and verify results."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(self.db_path) as db:
            indexer = ImageIndexer(db, favorites_folder=self.favorites_dir)

            # Index favorites
            count = indexer.index_directory(self.favorites_dir)
            print(f"\nIndexed {count} images from Favorites")

            # Get stats
            stats = indexer.get_index_stats()
            print(f"Total images in database: {stats['total_images']}")
            print(f"Favorites count: {stats['favorites_count']}")
            print(f"Sources: {stats['total_sources']}")

            # Verify all are marked as favorites
            all_images = db.get_all_images()
            favorites = db.get_favorite_images()

            self.assertEqual(len(all_images), len(favorites))
            self.assertTrue(all(img.is_favorite for img in all_images))

            # Verify we got dimensions for all
            images_with_dims = [img for img in all_images if img.width and img.height]
            print(f"Images with dimensions: {len(images_with_dims)}/{len(all_images)}")

            self.assertEqual(len(images_with_dims), len(all_images))

            # Print sample records
            print("\nSample indexed images:")
            for img in all_images[:3]:
                print(f"  {img.filename}: {img.width}x{img.height}, "
                      f"aspect={img.aspect_ratio:.2f}, size={img.file_size/1024/1024:.1f}MB")


if __name__ == '__main__':
    unittest.main(verbosity=2)
