#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for ConstraintApplier - color and dimension filtering."""

import os
import tempfile
import shutil
import unittest
from PIL import Image


class TestColorConstraints(unittest.TestCase):
    """Tests for ColorConstraints dataclass."""

    def test_color_constraints_import(self):
        """ColorConstraints can be imported from constraints module."""
        from variety.smart_selection.selection.constraints import ColorConstraints
        self.assertIsNotNone(ColorConstraints)

    def test_color_constraints_default_values(self):
        """ColorConstraints has sensible defaults."""
        from variety.smart_selection.selection.constraints import ColorConstraints

        constraints = ColorConstraints()

        self.assertIsNone(constraints.target_palette)
        self.assertIsNone(constraints.min_lightness)
        self.assertIsNone(constraints.max_lightness)
        self.assertIsNone(constraints.min_saturation)
        self.assertIsNone(constraints.max_saturation)
        self.assertIsNone(constraints.temperature)
        self.assertEqual(constraints.similarity_threshold, 0.5)

    def test_color_constraints_with_values(self):
        """ColorConstraints accepts custom values."""
        from variety.smart_selection.selection.constraints import ColorConstraints

        constraints = ColorConstraints(
            target_palette={'avg_hue': 180, 'avg_saturation': 0.5},
            min_lightness=0.2,
            max_lightness=0.8,
            min_saturation=0.3,
            max_saturation=0.9,
            temperature=0.5,
            similarity_threshold=0.7,
        )

        self.assertEqual(constraints.target_palette, {'avg_hue': 180, 'avg_saturation': 0.5})
        self.assertEqual(constraints.min_lightness, 0.2)
        self.assertEqual(constraints.max_lightness, 0.8)
        self.assertEqual(constraints.min_saturation, 0.3)
        self.assertEqual(constraints.max_saturation, 0.9)
        self.assertEqual(constraints.temperature, 0.5)
        self.assertEqual(constraints.similarity_threshold, 0.7)


class TestConstraintApplierCreation(unittest.TestCase):
    """Tests for ConstraintApplier instantiation."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_constraint_applier_import(self):
        """ConstraintApplier can be imported from constraints module."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        self.assertIsNotNone(ConstraintApplier)

    def test_constraint_applier_creation(self):
        """ConstraintApplier can be created with a database."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            applier = ConstraintApplier(db)
            self.assertIsNotNone(applier)
        finally:
            db.close()


class TestConstraintApplierDimensionFiltering(unittest.TestCase):
    """Tests for dimension constraint filtering."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create images of different sizes
        self.small_path = os.path.join(self.images_dir, 'small.jpg')
        img = Image.new('RGB', (800, 600), color='blue')
        img.save(self.small_path)

        self.medium_path = os.path.join(self.images_dir, 'medium.jpg')
        img = Image.new('RGB', (1920, 1080), color='green')
        img.save(self.medium_path)

        self.large_path = os.path.join(self.images_dir, 'large.jpg')
        img = Image.new('RGB', (3840, 2160), color='red')
        img.save(self.large_path)

        # Create wide aspect ratio image
        self.wide_path = os.path.join(self.images_dir, 'wide.jpg')
        img = Image.new('RGB', (2560, 1080), color='yellow')  # 21:9
        img.save(self.wide_path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db)
        indexer.index_directory(self.images_dir)

    def test_apply_with_no_constraints_returns_all(self):
        """apply with None constraints returns all candidates."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            result = applier.apply(candidates, None)

            self.assertEqual(len(result), 4)
        finally:
            db.close()

    def test_apply_filters_by_min_width(self):
        """apply filters by min_width constraint."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            constraints = SelectionConstraints(min_width=1920)
            result = applier.apply(candidates, constraints)

            # Only medium, large, and wide have width >= 1920
            self.assertEqual(len(result), 3)
            filepaths = [img.filepath for img in result]
            self.assertNotIn(self.small_path, filepaths)
        finally:
            db.close()

    def test_apply_filters_by_min_height(self):
        """apply filters by min_height constraint."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            constraints = SelectionConstraints(min_height=2000)
            result = applier.apply(candidates, constraints)

            # Only large has height >= 2000
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].filepath, self.large_path)
        finally:
            db.close()

    def test_apply_filters_by_aspect_ratio_range(self):
        """apply filters by min/max aspect ratio."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            # Filter for 16:9 aspect ratio (1.77...)
            constraints = SelectionConstraints(
                min_aspect_ratio=1.7,
                max_aspect_ratio=1.8
            )
            result = applier.apply(candidates, constraints)

            # Only medium and large have ~16:9 ratio
            self.assertEqual(len(result), 2)
            filepaths = [img.filepath for img in result]
            self.assertIn(self.medium_path, filepaths)
            self.assertIn(self.large_path, filepaths)
        finally:
            db.close()

    def test_apply_filters_favorites_only(self):
        """apply filters to favorites only when favorites_only=True."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        # Create favorites directory
        favorites_dir = os.path.join(self.temp_dir, 'favorites')
        os.makedirs(favorites_dir)
        fav_path = os.path.join(favorites_dir, 'fav.jpg')
        img = Image.new('RGB', (1920, 1080), color='gold')
        img.save(fav_path)

        db = ImageDatabase(self.db_path)
        try:
            from variety.smart_selection.indexer import ImageIndexer
            indexer = ImageIndexer(db, favorites_folder=favorites_dir)
            indexer.index_directory(self.images_dir)
            indexer.index_directory(favorites_dir)

            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            constraints = SelectionConstraints(favorites_only=True)
            result = applier.apply(candidates, constraints)

            # Only the favorite should remain
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0].is_favorite)
        finally:
            db.close()


class TestConstraintApplierColorFiltering(unittest.TestCase):
    """Tests for color constraint filtering."""

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

        # Red/orange (warm)
        img = Image.new('RGB', (100, 100), color='#FF6600')
        img.save(self.warm_image)

        # Blue/cyan (cool)
        img = Image.new('RGB', (100, 100), color='#0066FF')
        img.save(self.cool_image)

        # Gray (neutral)
        img = Image.new('RGB', (100, 100), color='#808080')
        img.save(self.neutral_image)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database_with_palettes(self, db):
        """Add test images with palettes to database."""
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.models import PaletteRecord

        indexer = ImageIndexer(db)
        indexer.index_directory(self.images_dir)

        # Add mock palette data (warm image)
        warm_palette = PaletteRecord(
            filepath=self.warm_image,
            avg_hue=30.0,  # Orange hue
            avg_saturation=0.8,
            avg_lightness=0.6,
            color_temperature=0.7,  # Warm
        )
        db.upsert_palette(warm_palette)

        # Add mock palette data (cool image)
        cool_palette = PaletteRecord(
            filepath=self.cool_image,
            avg_hue=210.0,  # Blue hue
            avg_saturation=0.8,
            avg_lightness=0.5,
            color_temperature=-0.7,  # Cool
        )
        db.upsert_palette(cool_palette)

        # Neutral image has no palette (tests exclusion)

    def test_apply_excludes_images_without_palette_when_color_filtering(self):
        """Images without palettes are excluded when target_palette is set."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database_with_palettes(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            # Set target palette - neutral has no palette, should be excluded
            constraints = SelectionConstraints(
                target_palette={'avg_hue': 30, 'avg_saturation': 0.8},
                min_color_similarity=0.0,  # Accept all with palettes
            )
            result = applier.apply(candidates, constraints)

            # neutral_image should be excluded (no palette)
            self.assertEqual(len(result), 2)
            filepaths = [img.filepath for img in result]
            self.assertNotIn(self.neutral_image, filepaths)
        finally:
            db.close()

    def test_apply_filters_by_color_similarity_threshold(self):
        """apply filters by min_color_similarity threshold."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database_with_palettes(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            # Target warm colors with high similarity threshold
            constraints = SelectionConstraints(
                target_palette={
                    'avg_hue': 30,
                    'avg_saturation': 0.8,
                    'avg_lightness': 0.6,
                    'color_temperature': 0.7,
                },
                min_color_similarity=0.9,  # Very strict
            )
            result = applier.apply(candidates, constraints)

            # Only warm image should match with high similarity
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].filepath, self.warm_image)
        finally:
            db.close()

    def test_apply_with_low_similarity_threshold_includes_more(self):
        """Lower similarity threshold includes more images."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database_with_palettes(db)
            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            # Target warm colors with low similarity threshold
            constraints = SelectionConstraints(
                target_palette={
                    'avg_hue': 30,
                    'avg_saturation': 0.8,
                    'avg_lightness': 0.6,
                    'color_temperature': 0.7,
                },
                min_color_similarity=0.1,  # Very lenient
            )
            result = applier.apply(candidates, constraints)

            # Both warm and cool should pass low threshold
            self.assertEqual(len(result), 2)
        finally:
            db.close()


class TestConstraintApplierBatchLoading(unittest.TestCase):
    """Tests for batch palette loading optimization."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test images
        self.image_paths = []
        for i in range(10):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (100, 100), color=(i * 20, i * 20, i * 20))
            img.save(path)
            self.image_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_apply_batch_loads_palettes(self):
        """apply batch-loads palettes to avoid N+1 queries."""
        from variety.smart_selection.selection.constraints import ConstraintApplier
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import SelectionConstraints, PaletteRecord
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch

        db = ImageDatabase(self.db_path)
        try:
            indexer = ImageIndexer(db)
            indexer.index_directory(self.images_dir)

            # Add palettes for all images
            for i, path in enumerate(self.image_paths):
                palette = PaletteRecord(
                    filepath=path,
                    avg_hue=float(i * 36),
                    avg_saturation=0.5,
                    avg_lightness=0.5,
                    color_temperature=0.0,
                )
                db.upsert_palette(palette)

            candidates = db.get_all_images()
            applier = ConstraintApplier(db)

            # Track how many times get_palettes_by_filepaths is called
            original_method = db.get_palettes_by_filepaths
            call_count = [0]

            def tracking_get_palettes(filepaths):
                call_count[0] += 1
                return original_method(filepaths)

            db.get_palettes_by_filepaths = tracking_get_palettes

            constraints = SelectionConstraints(
                target_palette={'avg_hue': 0, 'avg_saturation': 0.5},
                min_color_similarity=0.1,
            )
            result = applier.apply(candidates, constraints)

            # Should call batch method once, not N times
            self.assertEqual(call_count[0], 1)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
