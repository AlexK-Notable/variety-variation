#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for SelectionEngine - weighted random selection algorithm."""

import os
import tempfile
import shutil
import time
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image


class TestScoredCandidate(unittest.TestCase):
    """Tests for ScoredCandidate dataclass."""

    def test_scored_candidate_import(self):
        """ScoredCandidate can be imported from engine module."""
        from variety.smart_selection.selection.engine import ScoredCandidate
        self.assertIsNotNone(ScoredCandidate)

    def test_scored_candidate_creation(self):
        """ScoredCandidate can be created with required fields."""
        from variety.smart_selection.selection.engine import ScoredCandidate
        from variety.smart_selection.models import ImageRecord

        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg')
        candidate = ScoredCandidate(image=image, weight=0.75)

        self.assertEqual(candidate.image.filepath, '/test/img.jpg')
        self.assertEqual(candidate.weight, 0.75)
        self.assertIsNone(candidate.weight_breakdown)

    def test_scored_candidate_with_breakdown(self):
        """ScoredCandidate accepts optional weight_breakdown."""
        from variety.smart_selection.selection.engine import ScoredCandidate
        from variety.smart_selection.models import ImageRecord

        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg')
        breakdown = {'recency': 0.8, 'favorite': 2.0, 'source': 0.9}
        candidate = ScoredCandidate(
            image=image,
            weight=1.44,
            weight_breakdown=breakdown,
        )

        self.assertEqual(candidate.weight_breakdown, breakdown)


class TestSelectionEngineCreation(unittest.TestCase):
    """Tests for SelectionEngine instantiation."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_selection_engine_import(self):
        """SelectionEngine can be imported from engine module."""
        from variety.smart_selection.selection.engine import SelectionEngine
        self.assertIsNotNone(SelectionEngine)

    def test_selection_engine_creation(self):
        """SelectionEngine can be created with database and config."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            engine = SelectionEngine(db, SelectionConfig())
            self.assertIsNotNone(engine)
        finally:
            db.close()


class TestSelectionEngineWeightedSelection(unittest.TestCase):
    """Tests for weighted random selection algorithm."""

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
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)
            self.regular_paths.append(path)

        # Create favorite images
        self.favorite_paths = []
        for i in range(3):
            path = os.path.join(self.favorites_dir, f'fav{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='red')
            img.save(path)
            self.favorite_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db, favorites_folder=self.favorites_dir)
        indexer.index_directory(self.images_dir)
        indexer.index_directory(self.favorites_dir)

    def test_select_returns_filepaths(self):
        """select returns list of file paths."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            results = engine.select(candidates, count=3)

            self.assertEqual(len(results), 3)
            for path in results:
                self.assertTrue(path.startswith(self.temp_dir))
        finally:
            db.close()

    def test_select_respects_count(self):
        """select returns exactly the requested count."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            for count in [1, 3, 5]:
                results = engine.select(candidates, count=count)
                self.assertEqual(len(results), count)
        finally:
            db.close()

    def test_select_returns_less_if_not_enough(self):
        """select returns fewer if candidates has fewer images."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            results = engine.select(candidates, count=100)

            self.assertEqual(len(results), 8)  # Only 8 images
        finally:
            db.close()

    def test_select_returns_no_duplicates(self):
        """select returns unique paths."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            results = engine.select(candidates, count=5)

            self.assertEqual(len(results), len(set(results)))
        finally:
            db.close()

    def test_select_empty_candidates_returns_empty(self):
        """select with empty candidates returns empty list."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            engine = SelectionEngine(db, SelectionConfig())

            results = engine.select([], count=5)

            self.assertEqual(results, [])
        finally:
            db.close()

    def test_favorites_selected_more_often(self):
        """Favorites have higher selection probability with favorite_boost."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(favorite_boost=3.0)

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, config)

            # Select many times and count favorites
            favorite_count = 0
            total_selections = 100

            for _ in range(total_selections):
                results = engine.select(candidates, count=1)
                if results[0] in self.favorite_paths:
                    favorite_count += 1

            # With 3x boost and 3:5 ratio, favorites should be ~64%
            # Allow margin due to randomness
            self.assertGreater(favorite_count, 40)
        finally:
            db.close()

    def test_recently_shown_selected_less(self):
        """Recently shown images have lower selection probability."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(image_cooldown_days=7)

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)

            # Mark one image as just shown
            shown_image = self.regular_paths[0]
            db.record_image_shown(shown_image)

            candidates = db.get_all_images()
            engine = SelectionEngine(db, config)

            # Select many times
            shown_count = 0
            total_selections = 50

            for _ in range(total_selections):
                results = engine.select(candidates, count=1)
                if results[0] == shown_image:
                    shown_count += 1

            # Recently shown should be selected much less
            self.assertLess(shown_count, 10)
        finally:
            db.close()


class TestSelectionEngineDisabled(unittest.TestCase):
    """Tests for uniform random selection when disabled."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        self.favorites_dir = os.path.join(self.temp_dir, 'favorites')
        os.makedirs(self.images_dir)
        os.makedirs(self.favorites_dir)

        # Create images
        self.regular_paths = []
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color='blue')
            img.save(path)
            self.regular_paths.append(path)

        self.favorite_paths = []
        for i in range(5):
            path = os.path.join(self.favorites_dir, f'fav{i}.jpg')
            img = Image.new('RGB', (100, 100), color='red')
            img.save(path)
            self.favorite_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db, favorites_folder=self.favorites_dir)
        indexer.index_directory(self.images_dir)
        indexer.index_directory(self.favorites_dir)

    def test_disabled_uses_uniform_random(self):
        """When disabled, selection is uniform random."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(enabled=False, favorite_boost=10.0)

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, config)

            # Count selections
            favorite_count = 0
            total_selections = 100

            for _ in range(total_selections):
                results = engine.select(candidates, count=1)
                if results[0] in self.favorite_paths:
                    favorite_count += 1

            # Without boost, should be ~50%
            self.assertGreater(favorite_count, 30)
            self.assertLess(favorite_count, 70)
        finally:
            db.close()


class TestSelectionEngineZeroWeightsFallback(unittest.TestCase):
    """Tests for fallback when all weights are zero."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        self.image_paths = []
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 40, i * 40, i * 40))
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db)
        indexer.index_directory(self.images_dir)

    def test_select_with_all_zero_weights_falls_back_to_uniform(self):
        """Selection falls back to uniform random if all weights are zero."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            # Mock calculate_weight to return 0 for all
            with patch('variety.smart_selection.selection.engine.calculate_weight') as mock_weight:
                mock_weight.return_value = 0.0

                # Should still select something (uniform fallback)
                results = engine.select(candidates, count=3)

                self.assertEqual(len(results), 3)
                for path in results:
                    self.assertIn(path, self.image_paths)
        finally:
            db.close()


class TestSelectionEngineFloatPrecision(unittest.TestCase):
    """Tests for floating point precision edge cases."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        self.image_paths = []
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 40, i * 40, i * 40))
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db)
        indexer.index_directory(self.images_dir)

    def test_selection_handles_float_precision_edge_case(self):
        """Selection works when random value equals total_weight."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            # Mock random.uniform to return exactly the total_weight
            with patch('variety.smart_selection.selection.engine.random.uniform') as mock_uniform:
                def return_max_weight(low, high):
                    return high  # Return exactly total_weight

                mock_uniform.side_effect = return_max_weight

                # Should NOT raise an error or return empty
                results = engine.select(candidates, count=1)

                self.assertEqual(len(results), 1,
                    "Must select exactly 1 image even with edge case float values")
        finally:
            db.close()

    def test_selection_handles_tiny_float_differences(self):
        """Selection handles cases where float differences are very small."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            engine = SelectionEngine(db, SelectionConfig())

            # Run many selections to check for any edge cases
            for _ in range(100):
                results = engine.select(candidates, count=1)
                self.assertEqual(len(results), 1,
                    "Must always select exactly 1 image")
                self.assertIn(results[0], self.image_paths,
                    "Selected image must be a valid path")
        finally:
            db.close()


class TestSelectionEngineBatchOptimization(unittest.TestCase):
    """Tests for batch loading optimizations."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        self.image_paths = []
        for i in range(10):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 20, i * 20, i * 20))
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db)
        indexer.index_directory(self.images_dir)

    def test_select_batch_loads_sources(self):
        """select batch-loads source records to avoid N+1 queries."""
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()

            # Track how many times get_sources_by_ids is called
            original_method = db.get_sources_by_ids
            call_count = [0]

            def tracking_get_sources(source_ids):
                call_count[0] += 1
                return original_method(source_ids)

            db.get_sources_by_ids = tracking_get_sources

            engine = SelectionEngine(db, SelectionConfig())
            results = engine.select(candidates, count=5)

            # Should call batch method once, not N times
            self.assertEqual(call_count[0], 1)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
