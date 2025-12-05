#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.models - Data models for the smart selection engine."""

import unittest
from dataclasses import fields


class TestImageRecord(unittest.TestCase):
    """Tests for ImageRecord dataclass."""

    def test_import_image_record(self):
        """ImageRecord can be imported from smart_selection.models."""
        from variety.smart_selection.models import ImageRecord
        self.assertIsNotNone(ImageRecord)

    def test_image_record_has_required_fields(self):
        """ImageRecord has all required fields for image metadata."""
        from variety.smart_selection.models import ImageRecord

        field_names = {f.name for f in fields(ImageRecord)}
        required_fields = {
            'filepath',
            'filename',
            'source_id',
            'width',
            'height',
            'aspect_ratio',
            'file_size',
            'file_mtime',
            'is_favorite',
            'first_indexed_at',
            'last_indexed_at',
            'last_shown_at',
            'times_shown',
        }
        self.assertTrue(required_fields.issubset(field_names))

    def test_image_record_creation_with_defaults(self):
        """ImageRecord can be created with minimal required fields."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
        )
        self.assertEqual(record.filepath, '/path/to/image.jpg')
        self.assertEqual(record.filename, 'image.jpg')
        self.assertIsNone(record.source_id)
        self.assertIsNone(record.width)
        self.assertIsNone(record.height)
        self.assertEqual(record.is_favorite, False)
        self.assertEqual(record.times_shown, 0)
        self.assertIsNone(record.last_shown_at)

    def test_image_record_creation_with_all_fields(self):
        """ImageRecord can be created with all fields specified."""
        from variety.smart_selection.models import ImageRecord

        record = ImageRecord(
            filepath='/path/to/image.jpg',
            filename='image.jpg',
            source_id='unsplash',
            width=1920,
            height=1080,
            aspect_ratio=1.778,
            file_size=102400,
            file_mtime=1701600000,
            is_favorite=True,
            first_indexed_at=1701600000,
            last_indexed_at=1701600100,
            last_shown_at=1701600200,
            times_shown=5,
        )
        self.assertEqual(record.width, 1920)
        self.assertEqual(record.height, 1080)
        self.assertTrue(record.is_favorite)
        self.assertEqual(record.times_shown, 5)


class TestSourceRecord(unittest.TestCase):
    """Tests for SourceRecord dataclass."""

    def test_import_source_record(self):
        """SourceRecord can be imported from smart_selection.models."""
        from variety.smart_selection.models import SourceRecord
        self.assertIsNotNone(SourceRecord)

    def test_source_record_has_required_fields(self):
        """SourceRecord has all required fields for source tracking."""
        from variety.smart_selection.models import SourceRecord

        field_names = {f.name for f in fields(SourceRecord)}
        required_fields = {
            'source_id',
            'source_type',
            'last_shown_at',
            'times_shown',
        }
        self.assertTrue(required_fields.issubset(field_names))

    def test_source_record_creation_with_defaults(self):
        """SourceRecord can be created with minimal required fields."""
        from variety.smart_selection.models import SourceRecord

        record = SourceRecord(source_id='unsplash')
        self.assertEqual(record.source_id, 'unsplash')
        self.assertIsNone(record.source_type)
        self.assertIsNone(record.last_shown_at)
        self.assertEqual(record.times_shown, 0)


class TestPaletteRecord(unittest.TestCase):
    """Tests for PaletteRecord dataclass."""

    def test_import_palette_record(self):
        """PaletteRecord can be imported from smart_selection.models."""
        from variety.smart_selection.models import PaletteRecord
        self.assertIsNotNone(PaletteRecord)

    def test_palette_record_has_color_fields(self):
        """PaletteRecord has wallust color fields (color0-15, background, foreground)."""
        from variety.smart_selection.models import PaletteRecord

        field_names = {f.name for f in fields(PaletteRecord)}
        # Check for color fields
        for i in range(16):
            self.assertIn(f'color{i}', field_names)
        self.assertIn('background', field_names)
        self.assertIn('foreground', field_names)

    def test_palette_record_has_derived_metrics(self):
        """PaletteRecord has derived metrics for fast queries."""
        from variety.smart_selection.models import PaletteRecord

        field_names = {f.name for f in fields(PaletteRecord)}
        derived_fields = {
            'filepath',
            'avg_hue',
            'avg_saturation',
            'avg_lightness',
            'color_temperature',
            'indexed_at',
        }
        self.assertTrue(derived_fields.issubset(field_names))

    def test_palette_record_creation_with_defaults(self):
        """PaletteRecord can be created with filepath only."""
        from variety.smart_selection.models import PaletteRecord

        record = PaletteRecord(filepath='/path/to/image.jpg')
        self.assertEqual(record.filepath, '/path/to/image.jpg')
        self.assertIsNone(record.color0)
        self.assertIsNone(record.avg_hue)


class TestSelectionConstraints(unittest.TestCase):
    """Tests for SelectionConstraints dataclass."""

    def test_import_selection_constraints(self):
        """SelectionConstraints can be imported from smart_selection.models."""
        from variety.smart_selection.models import SelectionConstraints
        self.assertIsNotNone(SelectionConstraints)

    def test_selection_constraints_has_filter_fields(self):
        """SelectionConstraints has fields for filtering images."""
        from variety.smart_selection.models import SelectionConstraints

        field_names = {f.name for f in fields(SelectionConstraints)}
        expected_fields = {
            'min_width',
            'min_height',
            'min_aspect_ratio',
            'max_aspect_ratio',
            'target_palette',
            'sources',
            'favorites_only',
        }
        self.assertTrue(expected_fields.issubset(field_names))

    def test_selection_constraints_defaults_to_no_filtering(self):
        """SelectionConstraints defaults allow all images."""
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints()
        self.assertIsNone(constraints.min_width)
        self.assertIsNone(constraints.min_height)
        self.assertFalse(constraints.favorites_only)


if __name__ == '__main__':
    unittest.main()
