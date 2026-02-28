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


class TestPaletteRecordToDict(unittest.TestCase):
    """Tests for PaletteRecord.to_dict() method.

    Phase 0 refactoring: PaletteRecord gains a to_dict() method that returns
    a dict with color0-15, background, foreground, cursor keys -- the format
    expected by TemplateProcessor.

    Tests are written against the planned interface. They will fail with
    AttributeError until the feature code is implemented -- this is expected.
    """

    def _create_full_record(self):
        """Create a PaletteRecord with all fields populated."""
        from variety.smart_selection.models import PaletteRecord
        return PaletteRecord(
            filepath='/test/image.jpg',
            color0='#1a1b26',
            color1='#f7768e',
            color2='#9ece6a',
            color3='#e0af68',
            color4='#7aa2f7',
            color5='#bb9af7',
            color6='#7dcfff',
            color7='#c0caf5',
            color8='#414868',
            color9='#f7768e',
            color10='#9ece6a',
            color11='#e0af68',
            color12='#7aa2f7',
            color13='#bb9af7',
            color14='#7dcfff',
            color15='#c0caf5',
            background='#1a1b26',
            foreground='#c0caf5',
            cursor='#c0caf5',
            avg_hue=230.5,
            avg_saturation=0.45,
            avg_lightness=0.52,
            color_temperature=-0.15,
            indexed_at=1700000000,
        )

    def _skip_if_no_to_dict(self):
        """Skip test if to_dict is not yet implemented."""
        from variety.smart_selection.models import PaletteRecord
        if not hasattr(PaletteRecord, 'to_dict'):
            raise unittest.SkipTest(
                "PaletteRecord.to_dict() not yet implemented (Phase 0 pending)"
            )

    def test_to_dict_returns_dict(self):
        """to_dict() returns a plain dict, not a dataclass or other type.

        Bug caught: returning dataclass.__dict__ or asdict() which includes
        internal fields.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict()

        self.assertIsInstance(result, dict)

    def test_to_dict_includes_color_keys(self):
        """to_dict() includes color0-15, background, foreground, cursor.

        Bug caught: missing color keys that TemplateProcessor expects for
        variable substitution.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict()

        for i in range(16):
            key = f'color{i}'
            self.assertIn(key, result, f"Missing '{key}' in to_dict() output")
            self.assertEqual(result[key], getattr(record, key))

        self.assertIn('background', result)
        self.assertEqual(result['background'], '#1a1b26')
        self.assertIn('foreground', result)
        self.assertEqual(result['foreground'], '#c0caf5')
        self.assertIn('cursor', result)
        self.assertEqual(result['cursor'], '#c0caf5')

    def test_to_dict_excludes_filepath(self):
        """to_dict() does NOT include filepath (internal implementation detail).

        Bug caught: exposing internal fields that TemplateProcessor doesn't
        expect, potentially causing template variable collision.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict()

        self.assertNotIn('filepath', result)

    def test_to_dict_excludes_indexed_at(self):
        """to_dict() does NOT include indexed_at (internal metadata).

        Bug caught: internal metadata leaking into template context.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict()

        self.assertNotIn('indexed_at', result)

    def test_to_dict_excludes_metrics_by_default(self):
        """to_dict() without include_metrics does NOT include avg_hue etc.

        Bug caught: metric keys in template context could interfere with
        template variable substitution when only color keys are expected.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict()

        self.assertNotIn('avg_hue', result)
        self.assertNotIn('avg_saturation', result)
        self.assertNotIn('avg_lightness', result)
        self.assertNotIn('color_temperature', result)

    def test_to_dict_include_metrics_true(self):
        """to_dict(include_metrics=True) includes avg_hue, avg_saturation,
        avg_lightness, and color_temperature.

        Bug caught: include_metrics flag ignored or only includes some metrics.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict(include_metrics=True)

        self.assertIn('avg_hue', result)
        self.assertAlmostEqual(result['avg_hue'], 230.5, places=1)
        self.assertIn('avg_saturation', result)
        self.assertAlmostEqual(result['avg_saturation'], 0.45, places=2)
        self.assertIn('avg_lightness', result)
        self.assertAlmostEqual(result['avg_lightness'], 0.52, places=2)
        self.assertIn('color_temperature', result)
        self.assertAlmostEqual(result['color_temperature'], -0.15, places=2)

    def test_to_dict_include_metrics_still_has_colors(self):
        """to_dict(include_metrics=True) still includes all color keys.

        Bug caught: include_metrics replaces color keys instead of augmenting.
        """
        self._skip_if_no_to_dict()
        record = self._create_full_record()
        result = record.to_dict(include_metrics=True)

        for i in range(16):
            self.assertIn(f'color{i}', result)
        self.assertIn('background', result)
        self.assertIn('foreground', result)
        self.assertIn('cursor', result)

    def test_to_dict_with_none_colors(self):
        """to_dict() with None color values handles gracefully.

        Bug caught: crash on None values, or incorrect dict contents.
        Contract: None-valued color fields are omitted from the result dict,
        consistent with parse_wallust_json() which only includes keys present
        in the input.
        """
        self._skip_if_no_to_dict()
        from variety.smart_selection.models import PaletteRecord

        record = PaletteRecord(
            filepath='/test/sparse.jpg',
            color0='#FF0000',
            # color1 through color15 are None (default)
            background='#000000',
            foreground='#FFFFFF',
            cursor='#FFFFFF',
        )
        # Must not raise
        result = record.to_dict()

        self.assertIsInstance(result, dict)
        self.assertEqual(result['color0'], '#FF0000')
        self.assertEqual(result['background'], '#000000')
        self.assertEqual(result['foreground'], '#FFFFFF')
        self.assertEqual(result['cursor'], '#FFFFFF')
        # None-valued color fields are omitted (consistent with parse_wallust_json)
        self.assertNotIn('color1', result)
        self.assertNotIn('color15', result)

    def test_to_dict_with_minimal_record(self):
        """to_dict() works with filepath-only PaletteRecord (all else None).

        Bug caught: crash when all optional fields are None, or internal fields
        leaking into result.
        """
        self._skip_if_no_to_dict()
        from variety.smart_selection.models import PaletteRecord

        record = PaletteRecord(filepath='/test/minimal.jpg')
        result = record.to_dict()

        self.assertIsInstance(result, dict)
        self.assertNotIn('filepath', result)
        self.assertNotIn('indexed_at', result)
        # With all colors as None, result should be empty
        # (None-valued fields are omitted, consistent with parse_wallust_json)
        self.assertEqual(len(result), 0)

    def test_to_dict_output_is_template_compatible(self):
        """to_dict() output has the same key structure as parse_wallust_json() colors.

        Bug caught: dict shape incompatible with existing TemplateProcessor
        which expects colorN, background, foreground, cursor keys from
        parse_wallust_json().
        """
        self._skip_if_no_to_dict()
        from variety.smart_selection.palette import parse_wallust_json

        # Get reference dict shape from parse_wallust_json
        json_data = {
            'color0': '#1a1b26', 'color1': '#f7768e', 'color2': '#9ece6a',
            'color3': '#e0af68', 'color4': '#7aa2f7', 'color5': '#bb9af7',
            'color6': '#7dcfff', 'color7': '#c0caf5', 'color8': '#414868',
            'color9': '#f7768e', 'color10': '#9ece6a', 'color11': '#e0af68',
            'color12': '#7aa2f7', 'color13': '#bb9af7', 'color14': '#7dcfff',
            'color15': '#c0caf5',
            'background': '#1a1b26', 'foreground': '#c0caf5', 'cursor': '#c0caf5',
        }
        reference = parse_wallust_json(json_data)
        reference_color_keys = {
            k for k in reference
            if k.startswith('color') and k[5:].isdigit()
            or k in ('background', 'foreground', 'cursor')
        }

        # to_dict() should have at least the same color keys
        record = self._create_full_record()
        to_dict_result = record.to_dict()
        to_dict_keys = set(to_dict_result.keys())

        missing = reference_color_keys - to_dict_keys
        self.assertFalse(
            missing,
            f"to_dict() missing keys that parse_wallust_json() provides: {missing}"
        )


class TestColorThemeRecord(unittest.TestCase):
    """Tests for ColorThemeRecord dataclass.

    Phase 1 adds a ColorThemeRecord model to represent color themes
    stored in the color_themes database table. Tests verify field
    definitions, defaults, and to_dict() behavior.

    The to_dict() method must produce a dict compatible with
    PaletteRecord.to_dict() for TemplateProcessor interoperability.
    """

    def _skip_if_not_defined(self):
        """Skip test if ColorThemeRecord is not yet defined."""
        try:
            from variety.smart_selection.models import ColorThemeRecord
        except ImportError:
            raise unittest.SkipTest(
                "ColorThemeRecord not yet defined (Phase 1 model not yet implemented)"
            )

    def _create_full_record(self):
        """Create a ColorThemeRecord with all fields populated."""
        from variety.smart_selection.models import ColorThemeRecord
        return ColorThemeRecord(
            theme_id='test-theme',
            name='Tokyo Night',
            source_type='zed',
            source_path='/themes/tokyo-night.json',
            appearance='dark',
            color0='#1a1b26',
            color1='#f7768e',
            color2='#9ece6a',
            color3='#e0af68',
            color4='#7aa2f7',
            color5='#bb9af7',
            color6='#7dcfff',
            color7='#c0caf5',
            color8='#414868',
            color9='#f7768e',
            color10='#9ece6a',
            color11='#e0af68',
            color12='#7aa2f7',
            color13='#bb9af7',
            color14='#7dcfff',
            color15='#c0caf5',
            background='#1a1b26',
            foreground='#c0caf5',
            cursor='#c0caf5',
            avg_hue=230.5,
            avg_saturation=0.45,
            avg_lightness=0.52,
            color_temperature=-0.15,
            imported_at=1700000000,
            is_custom=False,
            parent_theme_id=None,
        )

    def test_import_color_theme_record(self):
        """ColorThemeRecord can be imported from smart_selection.models.

        Bug caught: Class not defined or not exported from models.py.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord
        self.assertIsNotNone(ColorThemeRecord)

    def test_color_theme_record_has_required_fields(self):
        """ColorThemeRecord has all fields matching the color_themes table.

        Bug caught: Missing field that the database CRUD methods expect,
        causing AttributeError during insert/retrieve.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord

        field_names = {f.name for f in fields(ColorThemeRecord)}
        required_fields = {
            'theme_id', 'name', 'source_type', 'source_path', 'appearance',
            'background', 'foreground', 'cursor',
            'avg_hue', 'avg_saturation', 'avg_lightness', 'color_temperature',
            'imported_at', 'is_custom', 'parent_theme_id',
        }
        # Color fields
        required_fields.update(f'color{i}' for i in range(16))

        missing = required_fields - field_names
        self.assertFalse(
            missing,
            f"ColorThemeRecord missing fields: {missing}"
        )

    def test_color_theme_record_creation_with_defaults(self):
        """ColorThemeRecord can be created with minimal required fields.

        Bug caught: Required fields without defaults causing TypeError
        on construction.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord

        record = ColorThemeRecord(
            theme_id='test',
            name='Test Theme',
            source_type='custom',
        )
        self.assertEqual(record.theme_id, 'test')
        self.assertEqual(record.name, 'Test Theme')
        self.assertEqual(record.source_type, 'custom')
        self.assertIsNone(record.color0)
        self.assertIsNone(record.appearance)
        self.assertIsNone(record.avg_hue)
        self.assertIsNone(record.cursor)

    def test_color_theme_record_creation_with_all_fields(self):
        """ColorThemeRecord can be created with all fields specified.

        Bug caught: Typo in field name or incorrect type annotation
        causing construction failure.
        """
        self._skip_if_not_defined()
        record = self._create_full_record()

        self.assertEqual(record.theme_id, 'test-theme')
        self.assertEqual(record.name, 'Tokyo Night')
        self.assertEqual(record.source_type, 'zed')
        self.assertEqual(record.appearance, 'dark')
        self.assertEqual(record.color0, '#1a1b26')
        self.assertEqual(record.color15, '#c0caf5')
        self.assertEqual(record.cursor, '#c0caf5')
        self.assertAlmostEqual(record.avg_hue, 230.5, places=1)
        self.assertFalse(record.is_custom)
        self.assertIsNone(record.parent_theme_id)

    def test_to_dict_returns_color_keys(self):
        """to_dict() returns dict with color0-15, background, foreground, cursor.

        Bug caught: Missing keys that TemplateProcessor expects for
        variable substitution, or wrong key names.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord
        if not hasattr(ColorThemeRecord, 'to_dict'):
            raise unittest.SkipTest(
                "ColorThemeRecord.to_dict() not yet implemented"
            )

        record = self._create_full_record()
        result = record.to_dict()

        self.assertIsInstance(result, dict)

        # All 16 color keys present
        for i in range(16):
            key = f'color{i}'
            self.assertIn(key, result, f"Missing '{key}' in to_dict() output")
            self.assertEqual(result[key], getattr(record, key))

        # background, foreground, and cursor
        self.assertIn('background', result)
        self.assertEqual(result['background'], '#1a1b26')
        self.assertIn('foreground', result)
        self.assertEqual(result['foreground'], '#c0caf5')
        self.assertIn('cursor', result)
        self.assertEqual(result['cursor'], '#c0caf5')

    def test_to_dict_include_metrics(self):
        """to_dict(include_metrics=True) includes avg_hue, avg_saturation,
        avg_lightness, and color_temperature.

        Bug caught: include_metrics parameter not implemented, or only
        partial metrics included.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord
        if not hasattr(ColorThemeRecord, 'to_dict'):
            raise unittest.SkipTest(
                "ColorThemeRecord.to_dict() not yet implemented"
            )

        record = self._create_full_record()
        result = record.to_dict(include_metrics=True)

        self.assertIn('avg_hue', result)
        self.assertAlmostEqual(result['avg_hue'], 230.5, places=1)
        self.assertIn('avg_saturation', result)
        self.assertAlmostEqual(result['avg_saturation'], 0.45, places=2)
        self.assertIn('avg_lightness', result)
        self.assertAlmostEqual(result['avg_lightness'], 0.52, places=2)
        self.assertIn('color_temperature', result)
        self.assertAlmostEqual(result['color_temperature'], -0.15, places=2)

    def test_to_dict_excludes_metrics_by_default(self):
        """to_dict() without include_metrics does NOT include metric keys.

        Bug caught: Metrics always included regardless of flag.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord
        if not hasattr(ColorThemeRecord, 'to_dict'):
            raise unittest.SkipTest(
                "ColorThemeRecord.to_dict() not yet implemented"
            )

        record = self._create_full_record()
        result = record.to_dict()

        self.assertNotIn('avg_hue', result)
        self.assertNotIn('avg_saturation', result)
        self.assertNotIn('avg_lightness', result)
        self.assertNotIn('color_temperature', result)

    def test_to_dict_excludes_internal_fields(self):
        """to_dict() does NOT include theme_id, name, source_type,
        source_path, imported_at, is_custom, parent_theme_id.

        Bug caught: Internal/metadata fields leaking into the palette
        dict that TemplateProcessor uses for variable substitution.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord
        if not hasattr(ColorThemeRecord, 'to_dict'):
            raise unittest.SkipTest(
                "ColorThemeRecord.to_dict() not yet implemented"
            )

        record = self._create_full_record()
        result = record.to_dict()

        internal_fields = [
            'theme_id', 'name', 'source_type', 'source_path',
            'appearance', 'imported_at', 'is_custom', 'parent_theme_id',
        ]
        for field_name in internal_fields:
            self.assertNotIn(field_name, result,
                             f"Internal field '{field_name}' should not be in to_dict()")

    def test_to_dict_with_none_colors(self):
        """to_dict() with None color values omits them (consistent with
        PaletteRecord.to_dict() behavior).

        Bug caught: Including None values as keys, breaking template
        substitution which expects string values.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord
        if not hasattr(ColorThemeRecord, 'to_dict'):
            raise unittest.SkipTest(
                "ColorThemeRecord.to_dict() not yet implemented"
            )

        record = ColorThemeRecord(
            theme_id='sparse',
            name='Sparse',
            source_type='custom',
            color0='#FF0000',
            background='#000000',
            foreground='#FFFFFF',
            cursor='#FFFFFF',
        )
        result = record.to_dict()

        self.assertEqual(result['color0'], '#FF0000')
        self.assertEqual(result['background'], '#000000')
        self.assertEqual(result['cursor'], '#FFFFFF')
        # None-valued color fields should be omitted
        self.assertNotIn('color1', result)
        self.assertNotIn('color15', result)

    def test_to_dict_compatible_with_palette_record(self):
        """ColorThemeRecord.to_dict() produces the same key structure as
        PaletteRecord.to_dict() for the same color values.

        Bug caught: Key structure divergence between the two record
        types, causing TemplateProcessor to fail when switching between
        wallpaper-derived and theme-derived palettes.
        """
        self._skip_if_not_defined()
        from variety.smart_selection.models import ColorThemeRecord, PaletteRecord
        if not hasattr(ColorThemeRecord, 'to_dict'):
            raise unittest.SkipTest(
                "ColorThemeRecord.to_dict() not yet implemented"
            )

        # Create PaletteRecord and ColorThemeRecord with same colors
        palette = PaletteRecord(
            filepath='/test.jpg',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a',
            color3='#e0af68', color4='#7aa2f7', color5='#bb9af7',
            color6='#7dcfff', color7='#c0caf5', color8='#414868',
            color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff',
            color15='#c0caf5',
            background='#1a1b26', foreground='#c0caf5', cursor='#c0caf5',
        )
        theme = ColorThemeRecord(
            theme_id='test', name='Test', source_type='zed',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a',
            color3='#e0af68', color4='#7aa2f7', color5='#bb9af7',
            color6='#7dcfff', color7='#c0caf5', color8='#414868',
            color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff',
            color15='#c0caf5',
            background='#1a1b26', foreground='#c0caf5', cursor='#c0caf5',
        )

        palette_dict = palette.to_dict()
        theme_dict = theme.to_dict()

        # Same keys
        self.assertEqual(set(palette_dict.keys()), set(theme_dict.keys()))

        # Same values
        for key in palette_dict:
            self.assertEqual(
                palette_dict[key], theme_dict[key],
                f"Value mismatch for key '{key}': "
                f"PaletteRecord={palette_dict[key]}, "
                f"ColorThemeRecord={theme_dict[key]}"
            )


if __name__ == '__main__':
    unittest.main()
