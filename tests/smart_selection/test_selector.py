#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.selector - SmartSelector orchestrator."""

import os
import tempfile
import shutil
import time
import unittest
from PIL import Image


class TestSmartSelectorCreation(unittest.TestCase):
    """Tests for SmartSelector instantiation."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_import_smart_selector(self):
        """SmartSelector can be imported from selector module."""
        from variety.smart_selection.selector import SmartSelector
        self.assertIsNotNone(SmartSelector)

    def test_create_smart_selector(self):
        """SmartSelector can be created with db_path and config."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        selector = SmartSelector(self.db_path, SelectionConfig())
        self.assertIsNotNone(selector)

    def test_smart_selector_creates_database(self):
        """SmartSelector creates database file on init."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        SmartSelector(self.db_path, SelectionConfig())
        self.assertTrue(os.path.exists(self.db_path))

    def test_smart_selector_context_manager(self):
        """SmartSelector can be used as context manager."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self.assertIsNotNone(selector)


class TestSmartSelectorSelection(unittest.TestCase):
    """Tests for SmartSelector.select_images()."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test images
        self.image_paths = []
        for i in range(10):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, selector):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

    def test_select_images_returns_filepaths(self):
        """select_images returns list of file paths."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images(count=3)

            self.assertEqual(len(results), 3)
            for path in results:
                self.assertIn(path, self.image_paths)

    def test_select_images_respects_count(self):
        """select_images returns exactly the requested count."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            for count in [1, 5, 10]:
                results = selector.select_images(count=count)
                self.assertEqual(len(results), count)

    def test_select_images_returns_less_if_not_enough(self):
        """select_images returns fewer if database has fewer images."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images(count=100)

            self.assertEqual(len(results), 10)  # Only 10 images in database

    def test_select_images_no_duplicates(self):
        """select_images returns unique paths."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images(count=5)

            self.assertEqual(len(results), len(set(results)))

    def test_select_images_empty_database(self):
        """select_images returns empty list for empty database."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            results = selector.select_images(count=5)
            self.assertEqual(results, [])


class TestSmartSelectorWeighting(unittest.TestCase):
    """Tests for weighted selection behavior."""

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
        for i in range(5):
            path = os.path.join(self.images_dir, f'regular{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)
            self.regular_paths.append(path)

        # Create favorite images
        self.favorite_paths = []
        for i in range(5):
            path = os.path.join(self.favorites_dir, f'fav{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='red')
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

    def test_favorites_selected_more_often(self):
        """Favorites have higher selection probability."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(favorite_boost=3.0)

        with SmartSelector(self.db_path, config) as selector:
            self._populate_database(selector)

            # Select many times and count favorites
            favorite_count = 0
            total_selections = 100

            for _ in range(total_selections):
                results = selector.select_images(count=1)
                if results[0] in self.favorite_paths:
                    favorite_count += 1

            # With 3x boost and equal counts, favorites should be ~75%
            # Allow wide margin due to randomness
            self.assertGreater(favorite_count, 50)

    def test_recently_shown_selected_less(self):
        """Recently shown images have lower selection probability."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(image_cooldown_days=7)

        with SmartSelector(self.db_path, config) as selector:
            self._populate_database(selector)

            # Mark one image as just shown
            shown_image = self.regular_paths[0]
            selector.record_shown(shown_image)

            # Select many times
            shown_count = 0
            total_selections = 50

            for _ in range(total_selections):
                results = selector.select_images(count=1)
                if results[0] == shown_image:
                    shown_count += 1

            # Recently shown should be selected much less
            self.assertLess(shown_count, 10)

    def test_selection_disabled_is_random(self):
        """When disabled, selection is uniform random."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(enabled=False, favorite_boost=10.0)

        with SmartSelector(self.db_path, config) as selector:
            self._populate_database(selector)

            # Count selections
            favorite_count = 0
            total_selections = 100

            for _ in range(total_selections):
                results = selector.select_images(count=1)
                if results[0] in self.favorite_paths:
                    favorite_count += 1

            # Without boost, should be ~50%
            self.assertGreater(favorite_count, 30)
            self.assertLess(favorite_count, 70)


class TestSmartSelectorRecordShown(unittest.TestCase):
    """Tests for SmartSelector.record_shown()."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        self.image_path = os.path.join(self.images_dir, 'test.jpg')
        img = Image.new('RGB', (1920, 1080), color='blue')
        img.save(self.image_path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, selector):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

    def test_record_shown_updates_image(self):
        """record_shown updates image's last_shown_at and times_shown."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            # Get initial state
            before = selector.db.get_image(self.image_path)
            self.assertIsNone(before.last_shown_at)
            self.assertEqual(before.times_shown, 0)

            # Record shown
            selector.record_shown(self.image_path)

            # Verify updated
            after = selector.db.get_image(self.image_path)
            self.assertIsNotNone(after.last_shown_at)
            self.assertEqual(after.times_shown, 1)

    def test_record_shown_increments_times_shown(self):
        """record_shown increments times_shown counter."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            for i in range(3):
                selector.record_shown(self.image_path)

            record = selector.db.get_image(self.image_path)
            self.assertEqual(record.times_shown, 3)

    def test_record_shown_updates_source(self):
        """record_shown updates source's last_shown_at."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)

            selector.record_shown(self.image_path)

            source = selector.db.get_source('images')  # Source ID from directory name
            self.assertIsNotNone(source)
            self.assertIsNotNone(source.last_shown_at)
            self.assertEqual(source.times_shown, 1)


class TestSmartSelectorConstraints(unittest.TestCase):
    """Tests for SelectionConstraints filtering."""

    def setUp(self):
        """Create temporary directory with images of various sizes."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create images with different aspect ratios
        self.wide_path = os.path.join(self.images_dir, 'wide.jpg')
        img = Image.new('RGB', (2560, 1080), color='blue')  # 21:9
        img.save(self.wide_path)

        self.normal_path = os.path.join(self.images_dir, 'normal.jpg')
        img = Image.new('RGB', (1920, 1080), color='green')  # 16:9
        img.save(self.normal_path)

        self.square_path = os.path.join(self.images_dir, 'square.jpg')
        img = Image.new('RGB', (1080, 1080), color='red')  # 1:1
        img.save(self.square_path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, selector):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

    def test_filter_by_min_width(self):
        """Constraints can filter by minimum width."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(min_width=2000)

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images(count=10, constraints=constraints)

            # Only wide image has width >= 2000
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], self.wide_path)

    def test_filter_by_aspect_ratio(self):
        """Constraints can filter by aspect ratio range."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        # Filter for ~16:9 aspect ratio
        constraints = SelectionConstraints(
            min_aspect_ratio=1.7,
            max_aspect_ratio=1.8
        )

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            self._populate_database(selector)
            results = selector.select_images(count=10, constraints=constraints)

            # Only normal image has 16:9 ratio
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], self.normal_path)

    def test_filter_favorites_only(self):
        """Constraints can filter to favorites only."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        # Create favorites directory
        favorites_dir = os.path.join(self.temp_dir, 'favorites')
        os.makedirs(favorites_dir)
        fav_path = os.path.join(favorites_dir, 'fav.jpg')
        img = Image.new('RGB', (1920, 1080), color='gold')
        img.save(fav_path)

        constraints = SelectionConstraints(favorites_only=True)

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            from variety.smart_selection.indexer import ImageIndexer
            indexer = ImageIndexer(selector.db, favorites_folder=favorites_dir)
            indexer.index_directory(self.images_dir)
            indexer.index_directory(favorites_dir)

            results = selector.select_images(count=10, constraints=constraints)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], fav_path)

    def test_filter_by_sources(self):
        """Constraints can filter by source IDs."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        # Create second source
        source2_dir = os.path.join(self.temp_dir, 'source2')
        os.makedirs(source2_dir)
        source2_path = os.path.join(source2_dir, 'img.jpg')
        img = Image.new('RGB', (1920, 1080), color='purple')
        img.save(source2_path)

        constraints = SelectionConstraints(sources=['source2'])

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            from variety.smart_selection.indexer import ImageIndexer
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)
            indexer.index_directory(source2_dir)

            results = selector.select_images(count=10, constraints=constraints)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], source2_path)


class TestColorAwareSelection(unittest.TestCase):
    """Tests for Phase 4: Color-aware image selection."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test images with different colors
        self.warm_image = os.path.join(self.images_dir, 'warm.jpg')
        self.cool_image = os.path.join(self.images_dir, 'cool.jpg')
        self.neutral_image = os.path.join(self.images_dir, 'neutral.jpg')

        # Red/orange gradient (warm)
        img = Image.new('RGB', (100, 100))
        pixels = img.load()
        for y in range(100):
            for x in range(100):
                pixels[x, y] = (255, int(x * 1.5), int(y * 0.5))
        img.save(self.warm_image)

        # Blue/cyan gradient (cool)
        img = Image.new('RGB', (100, 100))
        pixels = img.load()
        for y in range(100):
            for x in range(100):
                pixels[x, y] = (int(y * 0.5), int(x * 1.5), 255)
        img.save(self.cool_image)

        # Gray gradient (neutral)
        img = Image.new('RGB', (100, 100))
        pixels = img.load()
        for y in range(100):
            for x in range(100):
                v = int((x + y) / 2 * 1.275)
                pixels[x, y] = (v, v, v)
        img.save(self.neutral_image)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_selection_constraints_accepts_min_color_similarity(self):
        """SelectionConstraints accepts min_color_similarity parameter."""
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(
            min_color_similarity=0.8,
            target_palette={'avg_hue': 180, 'avg_saturation': 0.5}
        )

        self.assertEqual(constraints.min_color_similarity, 0.8)
        self.assertIsNotNone(constraints.target_palette)

    def test_select_images_with_color_constraint_returns_similar(self):
        """select_images with target_palette returns color-similar images."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.palette import PaletteExtractor

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Index images
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)

            # Extract and store palettes for all images
            extractor = PaletteExtractor()
            if not extractor.is_wallust_available():
                self.skipTest("wallust not installed")

            from variety.smart_selection.palette import create_palette_record

            for img_path in [self.warm_image, self.cool_image, self.neutral_image]:
                palette_data = extractor.extract_palette(img_path)
                if palette_data:
                    record = create_palette_record(img_path, palette_data)
                    selector.db.upsert_palette(record)

            # Get warm image's palette as target
            warm_palette = selector.db.get_palette(self.warm_image)
            self.assertIsNotNone(warm_palette, "warm_palette should exist")

            target = {
                'avg_hue': warm_palette.avg_hue,
                'avg_saturation': warm_palette.avg_saturation,
                'avg_lightness': warm_palette.avg_lightness,
                'color_temperature': warm_palette.color_temperature,
            }

            # Select with color constraint - should prefer warm image
            constraints = SelectionConstraints(
                target_palette=target,
                min_color_similarity=0.7,
            )
            results = selector.select_images(count=3, constraints=constraints)

            # At minimum, warm image should be in results (most similar to itself)
            self.assertIn(self.warm_image, results)

    def test_select_images_excludes_dissimilar_colors(self):
        """select_images excludes images below min_color_similarity threshold."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.palette import PaletteExtractor, create_palette_record

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Index images
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)

            # Extract and store palettes
            extractor = PaletteExtractor()
            if not extractor.is_wallust_available():
                self.skipTest("wallust not installed")

            for img_path in [self.warm_image, self.cool_image]:
                palette_data = extractor.extract_palette(img_path)
                if palette_data:
                    record = create_palette_record(img_path, palette_data)
                    selector.db.upsert_palette(record)

            # Get warm palette as target
            warm_palette = selector.db.get_palette(self.warm_image)
            target = {
                'avg_hue': warm_palette.avg_hue,
                'avg_saturation': warm_palette.avg_saturation,
                'avg_lightness': warm_palette.avg_lightness,
                'color_temperature': warm_palette.color_temperature,
            }

            # High similarity threshold should exclude cool image
            constraints = SelectionConstraints(
                target_palette=target,
                min_color_similarity=0.95,  # Very strict
            )
            results = selector.select_images(count=3, constraints=constraints)

            # Cool image should be excluded due to color difference
            # Note: neutral_image has no palette so also excluded
            self.assertNotIn(self.cool_image, results)

    def test_images_without_palette_excluded_when_color_filtering(self):
        """Images without palettes are excluded when target_palette is set."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.palette import PaletteExtractor, create_palette_record

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Index images
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)

            # Only store palette for warm image
            extractor = PaletteExtractor()
            if not extractor.is_wallust_available():
                self.skipTest("wallust not installed")

            palette_data = extractor.extract_palette(self.warm_image)
            if palette_data:
                record = create_palette_record(self.warm_image, palette_data)
                selector.db.upsert_palette(record)

            warm_palette = selector.db.get_palette(self.warm_image)
            target = {
                'avg_hue': warm_palette.avg_hue,
                'avg_saturation': warm_palette.avg_saturation,
                'avg_lightness': warm_palette.avg_lightness,
                'color_temperature': warm_palette.color_temperature,
            }

            # Select with color constraint
            constraints = SelectionConstraints(
                target_palette=target,
                min_color_similarity=0.5,
            )
            results = selector.select_images(count=3, constraints=constraints)

            # Only warm_image has a palette, so only it should be returned
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], self.warm_image)


class TestPreviewCandidates(unittest.TestCase):
    """Tests for get_preview_candidates method."""

    def setUp(self):
        """Create temporary directory and test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

        # Create test images
        self.images = []
        for i in range(5):
            img_path = os.path.join(self.temp_dir, f'image_{i}.png')
            img = Image.new('RGB', (100, 100), color=(i * 50, i * 50, i * 50))
            img.save(img_path)
            self.images.append(img_path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_get_preview_candidates_returns_list(self):
        """get_preview_candidates returns a list of dicts."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.temp_dir)

            candidates = selector.get_preview_candidates(count=10)
            self.assertIsInstance(candidates, list)

    def test_get_preview_candidates_contains_expected_keys(self):
        """Each candidate dict contains expected keys."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.temp_dir)

            candidates = selector.get_preview_candidates(count=10)
            self.assertGreater(len(candidates), 0)

            expected_keys = ['filepath', 'filename', 'weight', 'is_favorite',
                            'times_shown', 'source_id', 'normalized_weight']
            for candidate in candidates:
                for key in expected_keys:
                    self.assertIn(key, candidate, f"Missing key: {key}")

    def test_get_preview_candidates_respects_count(self):
        """get_preview_candidates returns at most count candidates."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.temp_dir)

            # Request fewer than available
            candidates = selector.get_preview_candidates(count=2)
            self.assertLessEqual(len(candidates), 2)

    def test_get_preview_candidates_sorted_by_weight(self):
        """Candidates are sorted by weight in descending order."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.temp_dir)

            candidates = selector.get_preview_candidates(count=10)
            self.assertGreater(len(candidates), 1)

            # Weights should be in descending order
            weights = [c['weight'] for c in candidates]
            self.assertEqual(weights, sorted(weights, reverse=True))


class TestWeightedSelectionFloatPrecision(unittest.TestCase):
    """Tests for floating point precision in weighted selection."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create actual image files for float precision tests
        self.image_paths = []
        for i in range(5):  # Create 5 for the largest test
            img_path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 40, i * 40, i * 40))
            img.save(img_path)
            self.image_paths.append(img_path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_selection_handles_float_precision_edge_case(self):
        """Selection must work when random value equals total_weight.

        Due to floating point precision, when random.uniform(0, total_weight)
        returns a value very close to total_weight, the cumulative sum may never
        reach that value, causing the loop to fail to select any index.

        This test uses mocking to force the edge case and verify correct handling.
        """
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord
        from unittest.mock import patch

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Insert test images using real paths
            for i in range(3):
                selector.db.insert_image(ImageRecord(
                    filepath=self.image_paths[i],
                    filename=os.path.basename(self.image_paths[i]),
                    times_shown=0))

            # Mock random.uniform to return exactly the total_weight
            # This triggers the floating point precision edge case
            with patch('variety.smart_selection.selector.random.uniform') as mock_uniform:
                # The weights sum to some value, we return that exact value
                # which could cause the loop to never hit r <= cumulative
                def return_max_weight(low, high):
                    return high  # Return exactly total_weight

                mock_uniform.side_effect = return_max_weight

                # This should NOT raise an error or return empty
                # Even when r == total_weight, we should select the last item
                results = selector.select_images(count=1)

                self.assertEqual(len(results), 1,
                    "Must select exactly 1 image even with edge case float values")

    def test_selection_handles_accumulated_float_error(self):
        """Selection handles accumulated float error in cumulative sum.

        When summing many floating point weights, the cumulative sum may
        differ slightly from the expected total due to accumulated errors.
        This can cause r <= cumulative to never be true even when r equals
        the pre-calculated total_weight.

        The fix should ensure the last element is always selected when
        the loop completes without finding a match.
        """
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord
        from unittest.mock import patch, MagicMock

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Insert test images using real paths
            for i in range(3):
                selector.db.insert_image(ImageRecord(
                    filepath=self.image_paths[i],
                    filename=os.path.basename(self.image_paths[i]),
                    times_shown=0))

            # Patch calculate_weight to return specific values that
            # will cause float precision issues when accumulated
            with patch('variety.smart_selection.selector.calculate_weight') as mock_weight:
                # Use values that cause float precision issues when summed
                # For example, 0.1 + 0.1 + 0.1 != 0.3 in float
                mock_weight.return_value = 0.1

                # Now patch random.uniform to return a value slightly greater
                # than what cumulative sum can reach (simulating the bug)
                with patch('variety.smart_selection.selector.random.uniform') as mock_uniform:
                    # 0.1 + 0.1 + 0.1 in float might be 0.30000000000000004
                    # but 3 * 0.1 = 0.30000000000000004 as well
                    # Let's force a value that definitely exceeds cumulative
                    def return_slightly_more(low, high):
                        # Return a value that's higher than float sum can reach
                        return high + 1e-10  # Tiny bit more than total

                    mock_uniform.side_effect = return_slightly_more

                    # The current buggy code will return an incorrect result
                    # because idx will stay at 0 when r > cumulative for all items
                    results = selector.select_images(count=1)

                    # Verify we got a result (the fix ensures we always select something)
                    self.assertEqual(len(results), 1,
                        "Must select 1 image even with float precision edge case")

    def test_selection_handles_tiny_float_differences(self):
        """Selection handles cases where float differences are very small.

        Weights that differ by less than float epsilon can cause issues
        in cumulative comparisons.
        """
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Insert test images using real paths
            for i in range(5):
                selector.db.insert_image(ImageRecord(
                    filepath=self.image_paths[i],
                    filename=os.path.basename(self.image_paths[i]),
                    times_shown=0))

            # Run many selections to check for any edge cases
            for _ in range(100):
                results = selector.select_images(count=1)
                self.assertEqual(len(results), 1,
                    "Must always select exactly 1 image")
                self.assertIn(results[0], self.image_paths,
                    "Selected image must be a valid path")


class TestFileExistenceValidation(unittest.TestCase):
    """Tests for filtering out non-existent files from selection."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create actual image files
        self.real_images = []
        for i in range(3):
            img_path = os.path.join(self.images_dir, f'real_{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 50, i * 50, i * 50))
            img.save(img_path)
            self.real_images.append(img_path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_deleted_files_excluded_from_selection(self):
        """Files deleted after indexing are excluded from selection.

        This prevents the selector from returning paths to files that
        no longer exist, which would cause errors in the wallpaper setter.
        """
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Index all real images
            indexer = ImageIndexer(selector.db)
            indexer.index_directory(self.images_dir)

            # Verify all are indexed
            count = selector.db.count_images()
            self.assertEqual(count, 3)

            # Delete one image file
            deleted_path = self.real_images[1]
            os.remove(deleted_path)

            # Select images - should only return existing files
            results = selector.select_images(count=10)

            # Should have 2 results (not 3)
            self.assertEqual(len(results), 2,
                "Deleted files should be excluded from selection")

            # Verify deleted file is not in results
            self.assertNotIn(deleted_path, results,
                "Deleted file path should not be returned")

            # Verify all returned paths exist
            for path in results:
                self.assertTrue(os.path.exists(path),
                    f"Returned path should exist: {path}")

    def test_missing_files_removed_from_candidates(self):
        """Files that don't exist are filtered during candidate gathering."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import ImageRecord

        with SmartSelector(self.db_path, SelectionConfig()) as selector:
            # Insert records for both existing and non-existing files
            selector.db.insert_image(ImageRecord(
                filepath=self.real_images[0],
                filename='real_0.jpg',
                times_shown=0,
            ))
            selector.db.insert_image(ImageRecord(
                filepath='/nonexistent/fake_image.jpg',
                filename='fake_image.jpg',
                times_shown=0,
            ))

            # Select should only return the existing file
            results = selector.select_images(count=10)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], self.real_images[0])


if __name__ == '__main__':
    unittest.main()
