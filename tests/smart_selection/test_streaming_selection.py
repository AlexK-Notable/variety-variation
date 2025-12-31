#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for memory-efficient streaming selection (PERF-001).

Tests for:
- get_images_cursor() batched iteration in database.py
- select_images_streaming() weighted reservoir sampling in selector.py

These features reduce memory usage from O(n) to O(batch_size) when selecting
from large collections (50K+ images).
"""

import os
import random
import tempfile
import shutil
import time
import unittest
from collections import Counter
from unittest.mock import patch, MagicMock
from PIL import Image


class TestDatabaseStreamingCursor(unittest.TestCase):
    """Tests for ImageDatabase.get_images_cursor() batched iteration."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        from variety.smart_selection.database import ImageDatabase
        self.db = ImageDatabase(self.db_path)

    def tearDown(self):
        """Clean up temporary database."""
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_get_images_cursor_returns_iterator(self):
        """get_images_cursor returns an iterator of batches."""
        from variety.smart_selection.models import ImageRecord

        # Insert test images
        for i in range(10):
            self.db.insert_image(ImageRecord(
                filepath=f'/path/to/image{i}.jpg',
                filename=f'image{i}.jpg',
            ))

        cursor = self.db.get_images_cursor(batch_size=5)

        # Should be an iterator
        self.assertTrue(hasattr(cursor, '__iter__'))
        self.assertTrue(hasattr(cursor, '__next__'))

    def test_get_images_cursor_yields_correct_batch_sizes(self):
        """get_images_cursor yields batches of the requested size."""
        from variety.smart_selection.models import ImageRecord

        # Insert 23 images
        for i in range(23):
            self.db.insert_image(ImageRecord(
                filepath=f'/path/to/image{i}.jpg',
                filename=f'image{i}.jpg',
            ))

        batch_sizes = []
        for batch in self.db.get_images_cursor(batch_size=10):
            batch_sizes.append(len(batch))

        # Should have 3 batches: 10, 10, 3
        self.assertEqual(batch_sizes, [10, 10, 3])

    def test_get_images_cursor_yields_all_images(self):
        """get_images_cursor yields all images across batches."""
        from variety.smart_selection.models import ImageRecord

        # Insert 50 images
        expected_paths = set()
        for i in range(50):
            filepath = f'/path/to/image{i}.jpg'
            expected_paths.add(filepath)
            self.db.insert_image(ImageRecord(
                filepath=filepath,
                filename=f'image{i}.jpg',
            ))

        # Collect all images from cursor
        collected_paths = set()
        for batch in self.db.get_images_cursor(batch_size=17):
            for img in batch:
                collected_paths.add(img.filepath)

        self.assertEqual(collected_paths, expected_paths)

    def test_get_images_cursor_empty_database(self):
        """get_images_cursor yields nothing for empty database."""
        batches = list(self.db.get_images_cursor(batch_size=100))
        self.assertEqual(batches, [])

    def test_get_images_cursor_single_batch(self):
        """get_images_cursor handles case where all fit in one batch."""
        from variety.smart_selection.models import ImageRecord

        # Insert 5 images, batch size 100
        for i in range(5):
            self.db.insert_image(ImageRecord(
                filepath=f'/path/to/image{i}.jpg',
                filename=f'image{i}.jpg',
            ))

        batches = list(self.db.get_images_cursor(batch_size=100))
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 5)

    def test_get_images_cursor_batch_size_one(self):
        """get_images_cursor handles batch_size=1."""
        from variety.smart_selection.models import ImageRecord

        # Insert 3 images
        for i in range(3):
            self.db.insert_image(ImageRecord(
                filepath=f'/path/to/image{i}.jpg',
                filename=f'image{i}.jpg',
            ))

        batch_sizes = []
        for batch in self.db.get_images_cursor(batch_size=1):
            batch_sizes.append(len(batch))

        self.assertEqual(batch_sizes, [1, 1, 1])

    def test_get_images_cursor_with_source_filter(self):
        """get_images_cursor can filter by source_id."""
        from variety.smart_selection.models import ImageRecord

        # Insert images from different sources
        for i in range(10):
            self.db.insert_image(ImageRecord(
                filepath=f'/unsplash/image{i}.jpg',
                filename=f'image{i}.jpg',
                source_id='unsplash',
            ))
        for i in range(5):
            self.db.insert_image(ImageRecord(
                filepath=f'/wallhaven/image{i}.jpg',
                filename=f'image{i}.jpg',
                source_id='wallhaven',
            ))

        # Get only unsplash images
        unsplash_images = []
        for batch in self.db.get_images_cursor(batch_size=4, source_id='unsplash'):
            unsplash_images.extend(batch)

        self.assertEqual(len(unsplash_images), 10)
        for img in unsplash_images:
            self.assertEqual(img.source_id, 'unsplash')

    def test_get_images_cursor_returns_image_records(self):
        """get_images_cursor yields batches of ImageRecord objects."""
        from variety.smart_selection.models import ImageRecord

        self.db.insert_image(ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
            width=1920,
            height=1080,
            is_favorite=True,
            times_shown=5,
        ))

        for batch in self.db.get_images_cursor(batch_size=10):
            for img in batch:
                self.assertIsInstance(img, ImageRecord)
                self.assertEqual(img.filepath, '/path/to/image.jpg')
                self.assertEqual(img.width, 1920)
                self.assertEqual(img.is_favorite, True)
                self.assertEqual(img.times_shown, 5)


class TestStreamingSelection(unittest.TestCase):
    """Tests for SmartSelector.select_images_streaming() with reservoir sampling."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test image files
        self.image_paths = []
        for i in range(50):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 5, i * 5, i * 5))
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, selector, count=None):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

    def test_select_images_streaming_returns_filepaths(self):
        """select_images_streaming returns list of file paths."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images_streaming(count=5, batch_size=10)

            self.assertEqual(len(results), 5)
            for path in results:
                self.assertIn(path, self.image_paths)

    def test_select_images_streaming_respects_count(self):
        """select_images_streaming returns exactly the requested count."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            for count in [1, 5, 10]:
                results = selector.select_images_streaming(count=count, batch_size=10)
                self.assertEqual(len(results), count)

    def test_select_images_streaming_no_duplicates(self):
        """select_images_streaming returns unique paths."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images_streaming(count=20, batch_size=5)

            self.assertEqual(len(results), len(set(results)))

    def test_select_images_streaming_empty_database(self):
        """select_images_streaming returns empty list for empty database."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            results = selector.select_images_streaming(count=5, batch_size=10)
            self.assertEqual(results, [])

    def test_select_images_streaming_returns_less_if_not_enough(self):
        """select_images_streaming returns fewer if database has fewer images."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images_streaming(count=100, batch_size=10)

            # Only 50 images in database
            self.assertEqual(len(results), 50)

    def test_select_images_streaming_filters_nonexistent_files(self):
        """select_images_streaming excludes files that don't exist on disk."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            # Delete half the images
            deleted_paths = []
            for i in range(0, 50, 2):
                os.remove(self.image_paths[i])
                deleted_paths.append(self.image_paths[i])

            results = selector.select_images_streaming(count=50, batch_size=10)

            # Should only have 25 images
            self.assertEqual(len(results), 25)
            for path in deleted_paths:
                self.assertNotIn(path, results)

    def test_select_images_streaming_batch_size_respected(self):
        """Verify that batches are processed at the correct size."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            # Track batch sizes by patching the cursor
            batch_sizes = []
            original_cursor = selector.db.get_images_cursor

            def tracking_cursor(batch_size=1000, **kwargs):
                for batch in original_cursor(batch_size=batch_size, **kwargs):
                    batch_sizes.append(len(batch))
                    yield batch

            selector.db.get_images_cursor = tracking_cursor

            selector.select_images_streaming(count=5, batch_size=7)

            # With 50 images and batch_size=7, should have batches up to size 7
            self.assertTrue(all(size <= 7 for size in batch_sizes[:-1]))


class TestStreamingVsBatchEquivalence(unittest.TestCase):
    """Tests verifying streaming and batch methods produce equivalent distributions."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        self.favorites_dir = os.path.join(self.temp_dir, 'favorites')
        os.makedirs(self.images_dir)
        os.makedirs(self.favorites_dir)

        # Create regular images
        self.regular_paths = []
        for i in range(20):
            path = os.path.join(self.images_dir, f'regular{i}.jpg')
            img = Image.new('RGB', (100, 100), color='blue')
            img.save(path)
            self.regular_paths.append(path)

        # Create favorite images
        self.favorite_paths = []
        for i in range(20):
            path = os.path.join(self.favorites_dir, f'fav{i}.jpg')
            img = Image.new('RGB', (100, 100), color='red')
            img.save(path)
            self.favorite_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, selector):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(selector.db, favorites_folder=self.favorites_dir)
        indexer.index_directory(self.images_dir)
        indexer.index_directory(self.favorites_dir)

    def test_streaming_favorites_selection_distribution(self):
        """Streaming selection respects favorites boost similar to batch method."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(favorite_boost=3.0)

        with SmartSelector(self.db_path, config) as selector:
            self._populate_database(selector)

            # Run many selections with streaming
            stream_favorite_count = 0
            total_selections = 200

            for _ in range(total_selections):
                results = selector.select_images_streaming(count=1, batch_size=10)
                if results[0] in self.favorite_paths:
                    stream_favorite_count += 1

            # With 3x boost and equal counts, favorites should be ~75%
            # Allow wide margin due to randomness
            stream_ratio = stream_favorite_count / total_selections
            self.assertGreater(stream_ratio, 0.5,
                f"Streaming favorite ratio {stream_ratio:.2f} too low")

    def test_streaming_recency_penalty_distribution(self):
        """Streaming selection respects recency penalty."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(image_cooldown_days=7)

        with SmartSelector(self.db_path, config) as selector:
            self._populate_database(selector)

            # Mark one image as just shown
            shown_image = self.regular_paths[0]
            selector.record_shown(shown_image)

            # Run many streaming selections
            shown_count = 0
            total_selections = 100

            for _ in range(total_selections):
                results = selector.select_images_streaming(count=1, batch_size=10)
                if results[0] == shown_image:
                    shown_count += 1

            # Recently shown should be selected much less
            self.assertLess(shown_count, 20,
                f"Recently shown image selected {shown_count} times (expected < 20)")


class TestStreamingMemoryBounds(unittest.TestCase):
    """Tests verifying memory usage is bounded for streaming selection."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_cursor_does_not_load_all_records(self):
        """Verify cursor fetches records in batches, not all at once.

        We verify this indirectly by:
        1. Inserting many records
        2. Iterating with cursor and stopping early
        3. Verifying we received the correct number of batches

        If cursor loaded all records at once, we'd get one batch.
        With proper batching, we get multiple smaller batches.
        """
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert many images
        for i in range(5000):
            db.insert_image(ImageRecord(
                filepath=f'/test/image{i}.jpg',
                filename=f'image{i}.jpg',
            ))

        # Iterate through cursor with small batch size and count batches
        batch_count = 0
        total_count = 0
        for batch in db.get_images_cursor(batch_size=100):
            batch_count += 1
            total_count += len(batch)
            # Stop early to verify we're getting proper batches
            if total_count >= 300:
                break

        # Should have received at least 3 batches to get 300 items
        # If cursor loaded all at once, batch_count would be 1
        self.assertGreaterEqual(batch_count, 3)
        self.assertGreaterEqual(total_count, 300)

        # Verify each batch was correct size (100 or less)
        for batch in db.get_images_cursor(batch_size=100):
            self.assertLessEqual(len(batch), 100)

        db.close()

    def test_streaming_selection_with_large_collection(self):
        """Verify streaming selection works with large collections."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Insert many "virtual" images (won't actually exist)
            # We'll mock the file existence check
            for i in range(10000):
                selector.db.insert_image(ImageRecord(
                    filepath=f'/test/image{i}.jpg',
                    filename=f'image{i}.jpg',
                    times_shown=i % 10,
                    is_favorite=(i % 5 == 0),
                ))

            # Mock os.path.exists to return True for our virtual images
            with patch('os.path.exists', return_value=True):
                results = selector.select_images_streaming(
                    count=10,
                    batch_size=500,
                )

            self.assertEqual(len(results), 10)
            # Verify all unique
            self.assertEqual(len(set(results)), 10)


class TestStreamingEmptyBatches(unittest.TestCase):
    """Tests for handling batches that filter to empty."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create just a few test images
        self.image_paths = []
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 50, i * 50, i * 50))
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_handles_batches_filtering_to_empty(self):
        """Streaming handles case where file existence check removes all in batch."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Add some real images
            from variety.smart_selection.indexer import ImageIndexer
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)

            # Also add many "ghost" images that don't exist
            for i in range(100):
                selector.db.insert_image(ImageRecord(
                    filepath=f'/nonexistent/image{i}.jpg',
                    filename=f'image{i}.jpg',
                ))

            # Streaming should still return the real images
            # even though many batches will filter to empty
            results = selector.select_images_streaming(
                count=10,
                batch_size=20,
            )

            # Should have at most 5 (the real images)
            self.assertEqual(len(results), 5)
            for path in results:
                self.assertTrue(os.path.exists(path))


class TestStreamingConstraints(unittest.TestCase):
    """Tests for streaming selection with constraints."""

    def setUp(self):
        """Create temporary directory with test images of various sizes."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create images with different sizes
        self.wide_path = os.path.join(self.images_dir, 'wide.jpg')
        img = Image.new('RGB', (2560, 1080), color='blue')  # 21:9
        img.save(self.wide_path)

        self.normal_paths = []
        for i in range(10):
            path = os.path.join(self.images_dir, f'normal{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='green')  # 16:9
            img.save(path)
            self.normal_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_streaming_with_constraints(self):
        """Streaming selection respects constraints."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints
        from variety.smart_selection.indexer import ImageIndexer

        constraints = SelectionConstraints(min_width=2000)

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)

            results = selector.select_images_streaming(
                count=10,
                batch_size=5,
                constraints=constraints,
            )

            # Only wide image has width >= 2000
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], self.wide_path)


class TestWeightedReservoirSampling(unittest.TestCase):
    """Tests for weighted reservoir sampling algorithm correctness."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_weighted_distribution_correct(self):
        """Verify weighted selection produces correct distribution over many runs.

        With weights [3, 1, 1, 1, 1, 1, 1], the first item should be selected
        approximately 3/9 = 33% of the time, while others ~1/9 = 11% each.
        """
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord

        # Create 7 test images
        paths = []
        for i in range(7):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 30, i * 30, i * 30))
            img.save(path)
            paths.append(path)

        with SmartSelector(self.db_path, SelectionConfig(favorite_boost=3.0)) as selector:
            # Insert images, first one is favorite (3x weight)
            for i, path in enumerate(paths):
                selector.db.insert_image(ImageRecord(
                    filepath=path,
                    filename=os.path.basename(path),
                    is_favorite=(i == 0),
                ))

            # Run many selections
            selections = Counter()
            for _ in range(900):
                results = selector.select_images_streaming(count=1, batch_size=10)
                selections[results[0]] += 1

            # First image (favorite) should be selected ~3x more often
            # With 3x boost: P(fav) = 3/9 = 0.333, P(other) = 1/9 = 0.111
            fav_ratio = selections[paths[0]] / 900
            avg_other_ratio = sum(selections[p] for p in paths[1:]) / (6 * 900)

            # Allow wide tolerance due to randomness
            self.assertGreater(fav_ratio, 0.2,
                f"Favorite ratio {fav_ratio:.3f} too low (expected ~0.33)")
            self.assertLess(fav_ratio, 0.5,
                f"Favorite ratio {fav_ratio:.3f} too high (expected ~0.33)")

            # Favorites should have roughly 3x the selection rate
            if avg_other_ratio > 0.01:  # Avoid division by zero edge case
                boost_observed = fav_ratio / avg_other_ratio
                self.assertGreater(boost_observed, 1.5,
                    f"Boost ratio {boost_observed:.1f} too low (expected ~3)")
                self.assertLess(boost_observed, 6.0,
                    f"Boost ratio {boost_observed:.1f} too high (expected ~3)")


if __name__ == '__main__':
    unittest.main()
