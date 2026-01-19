#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.selection.engine - SelectionEngine."""

import os
import tempfile
import shutil
import unittest
from unittest.mock import Mock, patch, MagicMock


class TestSelectionEngineTimeAdaptation(unittest.TestCase):
    """Tests for time adaptation in SelectionEngine.

    These tests verify that score_candidates() properly integrates
    with TimeAdapter for time-based palette preferences.
    """

    def setUp(self):
        """Create temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_score_candidates_uses_time_adapter_when_enabled(self):
        """score_candidates() calls TimeAdapter.get_palette_target() when enabled."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        config = SelectionConfig(time_adaptation_enabled=True)
        engine = SelectionEngine(db, config)

        # Create a mock time adapter
        mock_adapter = Mock()
        mock_target = Mock()
        mock_target.lightness = 0.3
        mock_target.temperature = 0.4
        mock_target.saturation = 0.4
        mock_adapter.get_palette_target.return_value = mock_target
        engine._time_adapter = mock_adapter

        # Create test candidates
        candidates = [
            ImageRecord(filepath="/test/img1.jpg", filename="img1.jpg"),
            ImageRecord(filepath="/test/img2.jpg", filename="img2.jpg"),
        ]

        # Add images to database
        for img in candidates:
            db.upsert_image(img)

        # Score candidates
        scored = engine.score_candidates(candidates)

        # Verify time adapter was called
        mock_adapter.get_palette_target.assert_called_once()

        # Verify we got scored candidates back
        self.assertEqual(len(scored), 2)

        db.close()

    def test_score_candidates_passes_time_target_to_weight_calculation(self):
        """score_candidates() passes time target values to calculate_weight()."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        config = SelectionConfig(time_adaptation_enabled=True)
        engine = SelectionEngine(db, config)

        # Create a mock time adapter with known values
        mock_adapter = Mock()
        mock_target = Mock()
        mock_target.lightness = 0.25
        mock_target.temperature = -0.3
        mock_target.saturation = 0.5
        mock_adapter.get_palette_target.return_value = mock_target
        engine._time_adapter = mock_adapter

        candidates = [
            ImageRecord(filepath="/test/img1.jpg", filename="img1.jpg"),
        ]
        for img in candidates:
            db.upsert_image(img)

        # Mock calculate_weight to capture arguments
        with patch('variety.smart_selection.selection.engine.calculate_weight') as mock_calc:
            mock_calc.return_value = 1.0
            engine.score_candidates(candidates)

            # Verify calculate_weight was called with time target values
            call_kwargs = mock_calc.call_args[1]
            self.assertEqual(call_kwargs['time_target_lightness'], 0.25)
            self.assertEqual(call_kwargs['time_target_temperature'], -0.3)
            self.assertEqual(call_kwargs['time_target_saturation'], 0.5)

        db.close()

    def test_score_candidates_without_time_adaptation(self):
        """score_candidates() works correctly when time adaptation is disabled."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        config = SelectionConfig(time_adaptation_enabled=False)
        engine = SelectionEngine(db, config)

        # Verify no time adapter was created
        self.assertIsNone(engine._time_adapter)

        candidates = [
            ImageRecord(filepath="/test/img1.jpg", filename="img1.jpg"),
        ]
        for img in candidates:
            db.upsert_image(img)

        # Should work without time adapter
        with patch('variety.smart_selection.selection.engine.calculate_weight') as mock_calc:
            mock_calc.return_value = 1.0
            scored = engine.score_candidates(candidates)

            # Verify time target values are None
            call_kwargs = mock_calc.call_args[1]
            self.assertIsNone(call_kwargs['time_target_lightness'])
            self.assertIsNone(call_kwargs['time_target_temperature'])
            self.assertIsNone(call_kwargs['time_target_saturation'])

        self.assertEqual(len(scored), 1)
        db.close()

    def test_score_candidates_handles_time_adapter_error_gracefully(self):
        """score_candidates() continues working if TimeAdapter raises an error."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        config = SelectionConfig(time_adaptation_enabled=True)
        engine = SelectionEngine(db, config)

        # Create a failing time adapter
        mock_adapter = Mock()
        mock_adapter.get_palette_target.side_effect = Exception("Test error")
        engine._time_adapter = mock_adapter

        candidates = [
            ImageRecord(filepath="/test/img1.jpg", filename="img1.jpg"),
        ]
        for img in candidates:
            db.upsert_image(img)

        # Should not raise, should fall back to no time adaptation
        scored = engine.score_candidates(candidates)

        # Verify we still got results
        self.assertEqual(len(scored), 1)

        db.close()


class TestSelectionEngineWeightedSelection(unittest.TestCase):
    """Tests for the weighted selection algorithm (A-ES reservoir sampling)."""

    def setUp(self):
        """Create temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_weighted_selection_returns_correct_count(self):
        """_weighted_selection returns exactly the requested count."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        config = SelectionConfig(enabled=False)  # Disable weighting for simple test
        engine = SelectionEngine(db, config)

        candidates = [
            ImageRecord(filepath=f"/test/img{i}.jpg", filename=f"img{i}.jpg")
            for i in range(20)
        ]
        weights = [1.0] * 20

        selected = engine._weighted_selection(candidates, weights, count=5)
        self.assertEqual(len(selected), 5)

        db.close()

    def test_weighted_selection_handles_zero_weights(self):
        """_weighted_selection falls back to uniform sampling for all-zero weights."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)
        config = SelectionConfig()
        engine = SelectionEngine(db, config)

        candidates = [
            ImageRecord(filepath=f"/test/img{i}.jpg", filename=f"img{i}.jpg")
            for i in range(10)
        ]
        weights = [0.0] * 10

        # Should not crash, should return some selection
        selected = engine._weighted_selection(candidates, weights, count=3)
        self.assertEqual(len(selected), 3)

        db.close()

    def test_weighted_selection_respects_weights(self):
        """_weighted_selection preferentially selects higher-weighted items."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.selection.engine import SelectionEngine
        from variety.smart_selection.models import ImageRecord
        import random

        random.seed(42)  # Deterministic for testing

        db = ImageDatabase(self.db_path)
        config = SelectionConfig()
        engine = SelectionEngine(db, config)

        # Create candidates with very different weights
        candidates = [
            ImageRecord(filepath="/test/heavy.jpg", filename="heavy.jpg"),
            ImageRecord(filepath="/test/light1.jpg", filename="light1.jpg"),
            ImageRecord(filepath="/test/light2.jpg", filename="light2.jpg"),
        ]
        # Heavy item has 1000x the weight
        weights = [1000.0, 1.0, 1.0]

        # Run selection many times, heavy item should almost always be selected
        heavy_count = 0
        trials = 100
        for _ in range(trials):
            selected = engine._weighted_selection(candidates, weights, count=1)
            if selected[0] == "/test/heavy.jpg":
                heavy_count += 1

        # Heavy item should be selected most of the time
        self.assertGreater(heavy_count, trials * 0.9)

        db.close()


if __name__ == '__main__':
    unittest.main()
