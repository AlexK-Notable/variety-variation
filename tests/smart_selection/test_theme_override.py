# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for smart_selection.theme_override - Theme override state management.

Written against the interface defined in plan phase 3: Theme Override Core Logic.
Tests verify behavior of ThemeOverride state machine and ThemeEngine integration
with theme overrides, not implementation details.

Phase Reference: Reverse Theming Pipeline, Phase 3
Gate Reference: Verification Gate Phase 3
"""

import os
import shutil
import tempfile
import unittest

from variety.smart_selection.theme_override import ThemeOverride
from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.models import ColorThemeRecord


# =============================================================================
# Test Helpers
# =============================================================================

def _make_test_theme(**overrides):
    """Create a ColorThemeRecord with sensible test defaults.

    Returns a ColorThemeRecord suitable for database insertion. All 16 colors,
    background, foreground, cursor, and metrics are populated by default.
    Override any field by passing keyword arguments.
    """
    defaults = dict(
        theme_id='test-theme-1',
        name='Test Theme',
        source_type='zed',
        color0='#1a1a2e',
        color1='#e94560',
        color2='#0f3460',
        color3='#533483',
        color4='#e94560',
        color5='#0f3460',
        color6='#16213e',
        color7='#eaeaea',
        color8='#2a2a4e',
        color9='#ff6b81',
        color10='#1f5480',
        color11='#7344a3',
        color12='#ff6b81',
        color13='#1f5480',
        color14='#26315e',
        color15='#ffffff',
        background='#0f0f23',
        foreground='#eaeaea',
        cursor='#e94560',
        avg_hue=280.0,
        avg_saturation=0.55,
        avg_lightness=0.35,
        color_temperature=-0.3,
    )
    defaults.update(overrides)
    return ColorThemeRecord(**defaults)


def _make_second_theme():
    """Create a distinctly different test theme for cache invalidation tests."""
    return ColorThemeRecord(
        theme_id='test-theme-2',
        name='Second Test Theme',
        source_type='zed',
        color0='#fdf6e3',
        color1='#dc322f',
        color2='#859900',
        color3='#b58900',
        color4='#268bd2',
        color5='#d33682',
        color6='#2aa198',
        color7='#073642',
        color8='#eee8d5',
        color9='#cb4b16',
        color10='#93a1a1',
        color11='#839496',
        color12='#657b83',
        color13='#6c71c4',
        color14='#586e75',
        color15='#002b36',
        background='#fdf6e3',
        foreground='#657b83',
        cursor='#586e75',
        avg_hue=45.0,
        avg_saturation=0.4,
        avg_lightness=0.7,
        color_temperature=0.5,
    )


# =============================================================================
# ThemeOverride State Machine Tests
# =============================================================================

class TestThemeOverrideLifecycle(unittest.TestCase):
    """Tests for ThemeOverride state transitions: inactive -> active -> deactivate."""

    def setUp(self):
        """Create temp database and insert test themes."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        self.db = ImageDatabase(self.db_path)
        self.theme = _make_test_theme()
        self.db.upsert_color_theme(self.theme)

    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_initially_inactive(self):
        """ThemeOverride should be inactive when first created.

        Bug caught: Constructor sets default active state incorrectly.
        """
        override = ThemeOverride(self.db)
        self.assertFalse(override.is_active)

    def test_initial_active_theme_id_is_none(self):
        """Active theme ID should be None when first created."""
        override = ThemeOverride(self.db)
        self.assertIsNone(override.active_theme_id)

    def test_activate_makes_active(self):
        """After activate(valid_id), is_active should be True.

        Bug caught: activate() doesn't update internal state.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        self.assertTrue(override.is_active)

    def test_activate_sets_theme_id(self):
        """activate() sets active_theme_id to the given ID."""
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        self.assertEqual(override.active_theme_id, self.theme.theme_id)

    def test_deactivate_returns_to_inactive(self):
        """After activate then deactivate, is_active should be False.

        Bug caught: deactivate() doesn't clear active state.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        self.assertTrue(override.is_active)

        override.deactivate()
        self.assertFalse(override.is_active)

    def test_deactivate_clears_theme_id(self):
        """deactivate() clears the active_theme_id."""
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        override.deactivate()
        self.assertIsNone(override.active_theme_id)

    def test_reactivate_after_deactivate(self):
        """Can activate a theme after deactivating.

        Bug caught: Deactivation leaves invalid state that prevents reactivation.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        override.deactivate()
        self.assertFalse(override.is_active)

        # Reactivate same theme
        override.activate(self.theme.theme_id)
        self.assertTrue(override.is_active)

    def test_activate_different_theme_switches(self):
        """Activating theme B after theme A switches to theme B.

        Bug caught: Activation doesn't clear previous theme state.
        """
        theme_b = _make_second_theme()
        self.db.upsert_color_theme(theme_b)

        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        self.assertTrue(override.is_active)

        override.activate(theme_b.theme_id)
        self.assertTrue(override.is_active)
        self.assertEqual(override.active_theme_id, theme_b.theme_id)

    def test_activate_clears_old_cache(self):
        """Activating theme B after theme A returns theme B's palette, not A's cached palette.

        Bug caught: Stale cache returns old theme's palette after switching.
        """
        theme_b = _make_second_theme()
        self.db.upsert_color_theme(theme_b)

        override = ThemeOverride(self.db)

        # Activate theme A and fetch palette to populate cache
        override.activate(self.theme.theme_id)
        palette_a = override.get_override_palette()
        self.assertEqual(palette_a['background'], self.theme.background)

        # Activate theme B
        override.activate(theme_b.theme_id)
        palette_b = override.get_override_palette()

        # Must be theme B's palette, not A's cached value
        self.assertEqual(palette_b['background'], theme_b.background)
        self.assertNotEqual(palette_b['background'], palette_a['background'])

    def test_deactivate_clears_cache(self):
        """After deactivate, cached palette should be None.

        Bug caught: Stale cached palette returned after deactivation.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        # Populate cache
        palette = override.get_override_palette()
        self.assertIsNotNone(palette)

        # Deactivate
        override.deactivate()

        # Cache should be cleared
        self.assertIsNone(override.get_override_palette())


# =============================================================================
# ThemeOverride Palette Retrieval Tests
# =============================================================================

class TestThemeOverridePalette(unittest.TestCase):
    """Tests for get_override_palette() and get_target_palette_for_selection()."""

    def setUp(self):
        """Create temp database and insert test theme with full palette."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        self.db = ImageDatabase(self.db_path)
        self.theme = _make_test_theme()
        self.db.upsert_color_theme(self.theme)

    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_get_override_palette_when_active(self):
        """When active, get_override_palette() returns dict with all color keys.

        Bug caught: Missing palette keys crash TemplateProcessor.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_override_palette()
        self.assertIsNotNone(palette)
        self.assertIsInstance(palette, dict)

        # Must have color0 through color15
        for i in range(16):
            self.assertIn(f'color{i}', palette, f'Missing color{i} in palette')

        # Must have background, foreground, cursor
        self.assertIn('background', palette)
        self.assertIn('foreground', palette)
        self.assertIn('cursor', palette)

    def test_get_override_palette_when_inactive(self):
        """When inactive, get_override_palette() returns None.

        Bug caught: Returns stale or default palette when no theme is active.
        """
        override = ThemeOverride(self.db)
        result = override.get_override_palette()
        self.assertIsNone(result)

    def test_get_override_palette_color_values_match_theme(self):
        """Palette color values should match what was stored in the database.

        Bug caught: Color values swapped or truncated during retrieval.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_override_palette()

        # Verify specific colors match the theme
        self.assertEqual(palette['color0'], self.theme.color0)
        self.assertEqual(palette['color1'], self.theme.color1)
        self.assertEqual(palette['background'], self.theme.background)
        self.assertEqual(palette['foreground'], self.theme.foreground)
        self.assertEqual(palette['cursor'], self.theme.cursor)

    def test_get_override_palette_does_not_include_metrics(self):
        """Override palette for template processing should not include metrics.

        Bug caught: Metric keys leak into template processing and cause
        {{avg_hue}} substitutions where not expected.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_override_palette()

        self.assertNotIn('avg_hue', palette)
        self.assertNotIn('avg_saturation', palette)
        self.assertNotIn('avg_lightness', palette)
        self.assertNotIn('color_temperature', palette)

    def test_get_override_palette_returns_none_after_deactivate(self):
        """After deactivate, palette is None."""
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)
        override.deactivate()
        self.assertIsNone(override.get_override_palette())

    def test_get_target_palette_for_selection_when_active(self):
        """When active, get_target_palette_for_selection() returns dict with metric keys.

        These metrics are required by color_affinity_factor() in the selection engine.

        Bug caught: Missing metrics neutralizes color_affinity_factor (returns 1.0 always).
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_target_palette_for_selection()
        self.assertIsNotNone(palette)
        self.assertIsInstance(palette, dict)

        # Must include metric keys for selection engine
        self.assertIn('avg_hue', palette)
        self.assertIn('avg_saturation', palette)
        self.assertIn('avg_lightness', palette)
        self.assertIn('color_temperature', palette)

    def test_get_target_palette_for_selection_metric_values(self):
        """Selection palette metrics should match the theme's stored values.

        Bug caught: Metrics recalculated or defaulted instead of using stored values.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_target_palette_for_selection()

        self.assertAlmostEqual(palette['avg_hue'], self.theme.avg_hue, places=1)
        self.assertAlmostEqual(palette['avg_saturation'], self.theme.avg_saturation, places=2)
        self.assertAlmostEqual(palette['avg_lightness'], self.theme.avg_lightness, places=2)
        self.assertAlmostEqual(palette['color_temperature'], self.theme.color_temperature, places=2)

    def test_get_target_palette_for_selection_when_inactive(self):
        """When inactive, get_target_palette_for_selection() returns None.

        Bug caught: Returns empty dict or default metrics when no theme active.
        """
        override = ThemeOverride(self.db)
        result = override.get_target_palette_for_selection()
        self.assertIsNone(result)

    def test_get_target_palette_for_selection_includes_colors(self):
        """Selection palette should include color keys alongside metrics.

        Bug caught: Selection palette only has metrics, missing color keys.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_target_palette_for_selection()

        for i in range(16):
            self.assertIn(f'color{i}', palette, f'Missing color{i} in selection palette')
        self.assertIn('background', palette)
        self.assertIn('foreground', palette)

    def test_get_target_palette_for_selection_none_if_theme_deleted(self):
        """If theme is deleted from DB after activation, selection palette returns None.

        Bug caught: Crash on stale reference to deleted theme.
        """
        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        # Delete theme from database
        self.db.delete_color_theme(self.theme.theme_id)

        # get_target_palette_for_selection re-fetches from DB
        result = override.get_target_palette_for_selection()
        self.assertIsNone(result)


# =============================================================================
# ThemeOverride Error Handling Tests
# =============================================================================

class TestThemeOverrideErrors(unittest.TestCase):
    """Tests for error handling in ThemeOverride."""

    def setUp(self):
        """Create temp database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        self.db = ImageDatabase(self.db_path)

    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_activate_nonexistent_theme_raises_error(self):
        """activate() with nonexistent theme_id should raise ValueError.

        Bug caught: Silent failure when activating deleted or nonexistent theme,
        leading to get_override_palette() returning None while is_active is True.
        """
        override = ThemeOverride(self.db)

        with self.assertRaises(ValueError):
            override.activate('nonexistent-theme-id-that-does-not-exist')

    def test_activate_nonexistent_theme_stays_inactive(self):
        """After failed activate, state should remain inactive.

        Bug caught: Partial state update on error (is_active=True but no palette).
        """
        override = ThemeOverride(self.db)

        try:
            override.activate('nonexistent-theme-id')
        except ValueError:
            pass

        self.assertFalse(override.is_active)
        self.assertIsNone(override.get_override_palette())

    def test_activate_nonexistent_does_not_clear_active_theme(self):
        """If already active and activate() fails for a new theme, previous theme stays active.

        Bug caught: Failed activation clears previous working state.
        """
        theme = _make_test_theme()
        self.db.upsert_color_theme(theme)

        override = ThemeOverride(self.db)
        override.activate(theme.theme_id)
        self.assertTrue(override.is_active)

        try:
            override.activate('nonexistent-theme-id')
        except ValueError:
            pass

        # Should still be active with the original theme
        self.assertTrue(override.is_active)
        palette = override.get_override_palette()
        self.assertIsNotNone(palette)
        self.assertEqual(palette['background'], theme.background)

    def test_deactivate_when_already_inactive(self):
        """deactivate() when already inactive should be a no-op, not raise.

        Bug caught: Double-deactivate crashes.
        """
        override = ThemeOverride(self.db)
        # Should not raise
        override.deactivate()
        self.assertFalse(override.is_active)

    def test_theme_with_sparse_colors(self):
        """Theme with only some colors set still returns a valid palette.

        Bug caught: KeyError when theme doesn't have all 16 colors.
        """
        sparse_theme = ColorThemeRecord(
            theme_id='sparse-theme',
            name='Sparse Theme',
            source_type='custom',
            color0='#000000',
            color1='#ff0000',
            background='#111111',
            foreground='#eeeeee',
            # No color2-15, no cursor
        )
        self.db.upsert_color_theme(sparse_theme)

        override = ThemeOverride(self.db)
        override.activate('sparse-theme')

        palette = override.get_override_palette()
        self.assertIsNotNone(palette)
        # Should have at least the colors that were set
        self.assertEqual(palette['color0'], '#000000')
        self.assertEqual(palette['background'], '#111111')


# =============================================================================
# ThemeOverride Palette Compatibility with TemplateProcessor
# =============================================================================

class TestThemeOverridePaletteCompatibility(unittest.TestCase):
    """Tests that ThemeOverride palette output is compatible with TemplateProcessor.

    Bug caught: Palette dict shape from ThemeOverride doesn't match what
    TemplateProcessor expects, causing missing variable substitutions.
    """

    def setUp(self):
        """Create temp database and insert test theme."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        self.db = ImageDatabase(self.db_path)
        self.theme = _make_test_theme()
        self.db.upsert_color_theme(self.theme)

    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_palette_accepted_by_template_processor(self):
        """Override palette dict can be passed directly to TemplateProcessor.

        Bug caught: Dict format incompatible with TemplateProcessor constructor.
        """
        from variety.smart_selection.theming import TemplateProcessor

        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_override_palette()
        # Should not raise
        processor = TemplateProcessor(palette)

        # Should process a basic template without errors
        result = processor.process('bg={{background}} fg={{foreground}}')
        self.assertIn(self.theme.background, result)
        self.assertIn(self.theme.foreground, result)

    def test_palette_with_filter_chain(self):
        """Override palette works with filter chains in templates.

        Bug caught: Color values in wrong format for filter processing.
        """
        from variety.smart_selection.theming import TemplateProcessor

        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        palette = override.get_override_palette()
        processor = TemplateProcessor(palette)

        # Test with strip filter
        result = processor.process('{{color1 | strip}}')
        self.assertFalse(result.startswith('#'))

        # Test with darken filter
        result = processor.process('{{color1 | darken(0.2) | strip}}')
        self.assertFalse(result.startswith('#'))
        self.assertNotEqual(result, '{{color1 | darken(0.2) | strip}}')


# =============================================================================
# ThemeEngine Integration Tests
# =============================================================================

class TestThemeEngineNoRegression(unittest.TestCase):
    """ThemeEngine without theme_override should behave identically to before.

    Bug caught: Adding optional theme_override parameter changes default behavior.
    """

    def setUp(self):
        """Create test directories and files matching existing ThemeEngine test pattern."""
        self.temp_dir = tempfile.mkdtemp()

        self.palette = {
            'color0': '#1a1a1a',
            'color1': '#ff0000',
            'color2': '#00ff00',
            'color3': '#0000ff',
            'color4': '#ffff00',
            'color5': '#ff00ff',
            'color6': '#00ffff',
            'color7': '#ffffff',
            'color8': '#808080',
            'color9': '#ff8080',
            'color10': '#80ff80',
            'color11': '#8080ff',
            'color12': '#ffff80',
            'color13': '#ff80ff',
            'color14': '#80ffff',
            'color15': '#c0c0c0',
            'background': '#000000',
            'foreground': '#e0e0e0',
            'cursor': '#ff5500',
        }

        # Create wallust.toml
        self.wallust_config = os.path.join(self.temp_dir, 'wallust.toml')
        self.templates_dir = os.path.join(self.temp_dir, 'templates')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.templates_dir)
        os.makedirs(self.output_dir)

        # Create test template
        self.template_path = os.path.join(self.templates_dir, 'test.conf')
        with open(self.template_path, 'w') as f:
            f.write('background = {{background}}\n')
            f.write('foreground = {{foreground}}\n')
            f.write('color1_stripped = {{color1 | strip}}\n')

        self.target_path = os.path.join(self.output_dir, 'test.conf')

        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'test = {{ template = "{self.template_path}", target = "{self.target_path}" }}\n')

        self.variety_config = os.path.join(self.temp_dir, 'theming.json')

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def _get_test_palette(self, image_path: str) -> dict:
        """Mock palette getter."""
        return self.palette

    def test_apply_without_override_processes_template(self):
        """ThemeEngine without theme_override works exactly as before.

        Bug caught: Optional parameter changes default behavior.
        """
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.target_path))

        with open(self.target_path, 'r') as f:
            content = f.read()

        self.assertIn('background = #000000', content)
        self.assertIn('foreground = #e0e0e0', content)
        self.assertIn('color1_stripped = ff0000', content)

    def test_apply_with_none_override_same_as_no_override(self):
        """ThemeEngine(theme_override=None) behaves same as no override.

        Bug caught: None check fails, passes None to palette lookup.
        """
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
            theme_override=None,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertTrue(result)

        with open(self.target_path, 'r') as f:
            content = f.read()

        self.assertIn('background = #000000', content)

    def test_palette_fallbacks_still_applied(self):
        """Missing palette entries still get fallbacks when no override present.

        Bug caught: Fallback logic bypassed when theme_override parameter exists.
        """
        from variety.smart_selection.theming import ThemeEngine

        minimal_palette = {'background': '#000000', 'foreground': '#ffffff'}

        def get_minimal(path):
            return minimal_palette

        engine = ThemeEngine(
            get_minimal,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        fallbacks = engine._apply_palette_fallbacks(minimal_palette)
        self.assertEqual(fallbacks['cursor'], '#ffffff')
        self.assertEqual(fallbacks['color7'], '#ffffff')
        self.assertEqual(fallbacks['color0'], '#000000')


class TestThemeEngineWithActiveOverride(unittest.TestCase):
    """Tests for ThemeEngine behavior when a theme override is active.

    These tests verify that template processing uses the override palette
    instead of the wallust-derived palette.
    """

    def setUp(self):
        """Create temp database, templates, and ThemeOverride."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_selection.db')
        self.db = ImageDatabase(self.db_path)

        # Insert a test theme
        self.theme = _make_test_theme()
        self.db.upsert_color_theme(self.theme)

        # Create template infrastructure
        self.templates_dir = os.path.join(self.temp_dir, 'templates')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.templates_dir)
        os.makedirs(self.output_dir)

        # Template with several variable types for thorough testing
        self.template_path = os.path.join(self.templates_dir, 'test.conf')
        with open(self.template_path, 'w') as f:
            f.write('background = {{background}}\n')
            f.write('foreground = {{foreground}}\n')
            f.write('cursor = {{cursor}}\n')
            f.write('color0 = {{color0}}\n')
            f.write('color1 = {{color1}}\n')
            f.write('color1_stripped = {{color1 | strip}}\n')

        self.target_path = os.path.join(self.output_dir, 'test.conf')

        self.wallust_config = os.path.join(self.temp_dir, 'wallust.toml')
        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'test = {{ template = "{self.template_path}", target = "{self.target_path}" }}\n')

        self.variety_config = os.path.join(self.temp_dir, 'theming.json')

    def tearDown(self):
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def _get_wrong_palette(self, image_path: str) -> dict:
        """Returns a palette that should NOT appear in output when override is active."""
        return {
            'color0': '#aaaaaa',
            'color1': '#bbbbbb',
            'background': '#cccccc',
            'foreground': '#dddddd',
            'cursor': '#eeeeee',
        }

    def test_active_override_uses_theme_palette(self):
        """When override is active, template output uses theme colors, not wallust colors.

        Bug caught: Override check not inserted in _apply_immediate(), still uses wallust palette.
        """
        from variety.smart_selection.theming import ThemeEngine

        override = ThemeOverride(self.db)
        override.activate(self.theme.theme_id)

        engine = ThemeEngine(
            self._get_wrong_palette,  # This palette should NOT be used
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
            theme_override=override,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertTrue(result)

        with open(self.target_path, 'r') as f:
            content = f.read()

        # Output should use theme palette, NOT the "wrong" palette
        self.assertIn(f'background = {self.theme.background}', content)
        self.assertIn(f'foreground = {self.theme.foreground}', content)
        self.assertIn(f'cursor = {self.theme.cursor}', content)
        self.assertIn(f'color0 = {self.theme.color0}', content)
        self.assertIn(f'color1 = {self.theme.color1}', content)

        # Should NOT contain the "wrong" palette colors
        self.assertNotIn('#cccccc', content)
        self.assertNotIn('#dddddd', content)

    def test_inactive_override_falls_through_to_wallust(self):
        """When override exists but is inactive, template uses wallust palette.

        Bug caught: Mere existence of theme_override parameter blocks wallust path.
        """
        from variety.smart_selection.theming import ThemeEngine

        override = ThemeOverride(self.db)
        # NOT activated -- should fall through

        wallust_palette = {
            'color0': '#111111',
            'color1': '#222222',
            'background': '#333333',
            'foreground': '#444444',
            'cursor': '#555555',
        }

        def get_wallust(path):
            return wallust_palette

        engine = ThemeEngine(
            get_wallust,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
            theme_override=override,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertTrue(result)

        with open(self.target_path, 'r') as f:
            content = f.read()

        # Should use wallust palette since override is inactive
        self.assertIn('background = #333333', content)
        self.assertIn('foreground = #444444', content)

    def test_override_palette_gets_fallbacks(self):
        """Override palette path also applies _apply_palette_fallbacks().

        Bug caught: Override path skips fallback logic, causing missing cursor/color7.
        """
        from variety.smart_selection.theming import ThemeEngine

        # Create theme with missing cursor (common for imported themes)
        sparse_theme = ColorThemeRecord(
            theme_id='sparse-for-fallback',
            name='Sparse Fallback Test',
            source_type='custom',
            color0='#111111',
            color1='#ff0000',
            background='#000000',
            foreground='#ffffff',
            # No cursor, no color7
        )
        self.db.upsert_color_theme(sparse_theme)

        override = ThemeOverride(self.db)
        override.activate('sparse-for-fallback')

        # Template that uses cursor and color7
        cursor_template = os.path.join(self.templates_dir, 'cursor_test.conf')
        cursor_target = os.path.join(self.output_dir, 'cursor_test.conf')
        with open(cursor_template, 'w') as f:
            f.write('cursor = {{cursor}}\n')
            f.write('color7 = {{color7}}\n')

        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'test = {{ template = "{cursor_template}", target = "{cursor_target}" }}\n')

        engine = ThemeEngine(
            self._get_wrong_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
            theme_override=override,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertTrue(result)

        with open(cursor_target, 'r') as f:
            content = f.read()

        # cursor should fall back to foreground (#ffffff)
        self.assertIn('cursor = #ffffff', content)
        # color7 should fall back to foreground (#ffffff)
        self.assertIn('color7 = #ffffff', content)


class TestApplyWithPaletteParity(unittest.TestCase):
    """Tests that template output from override path matches direct TemplateProcessor.

    This is the most critical integration test for Phase 3. It verifies
    that the override code path produces byte-identical template output
    compared to directly using TemplateProcessor with the same palette.

    Bug caught: Second code path diverges from the original.
    """

    def setUp(self):
        """Create temp directory with realistic test template."""
        self.temp_dir = tempfile.mkdtemp()
        self.templates_dir = os.path.join(self.temp_dir, 'templates')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.templates_dir)
        os.makedirs(self.output_dir)

        # Realistic template with variable substitutions and filters
        self.template_content = (
            '{# Hyprland color config #}\n'
            '$background = rgb({{background | strip}})\n'
            '$foreground = rgb({{foreground | strip}})\n'
            '$cursor = rgb({{cursor | strip}})\n'
            '$color0 = rgb({{color0 | strip}})\n'
            '$color1 = rgb({{color1 | strip}})\n'
            '$color4 = rgb({{color4 | strip}})\n'
            '$color_inactive = rgb({{color4 | darken(0.2) | strip}})\n'
            '$color7 = rgb({{color7 | strip}})\n'
        )

        self.template_path = os.path.join(self.templates_dir, 'hyprland.conf')
        with open(self.template_path, 'w') as f:
            f.write(self.template_content)

        self.target_path = os.path.join(self.output_dir, 'hyprland.conf')

        self.wallust_config = os.path.join(self.temp_dir, 'wallust.toml')
        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'hyprland = {{ template = "{self.template_path}", target = "{self.target_path}" }}\n')

        self.variety_config = os.path.join(self.temp_dir, 'theming.json')

        self.test_palette = {
            'color0': '#1a1a2e',
            'color1': '#e94560',
            'color2': '#0f3460',
            'color3': '#533483',
            'color4': '#e94560',
            'color5': '#0f3460',
            'color6': '#16213e',
            'color7': '#eaeaea',
            'color8': '#2a2a4e',
            'color9': '#ff6b81',
            'color10': '#1f5480',
            'color11': '#7344a3',
            'color12': '#ff6b81',
            'color13': '#1f5480',
            'color14': '#26315e',
            'color15': '#ffffff',
            'background': '#0f0f23',
            'foreground': '#eaeaea',
            'cursor': '#e94560',
        }

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def test_direct_processor_output_matches_engine_output(self):
        """TemplateProcessor with a palette produces same output as ThemeEngine apply.

        This verifies the override code path uses the same processing pipeline.

        Bug caught: Override path uses different template processing logic.
        """
        from variety.smart_selection.theming import ThemeEngine, TemplateProcessor

        # Get expected output from TemplateProcessor directly
        fallback_palette = dict(self.test_palette)
        processor = TemplateProcessor(fallback_palette)
        expected_output = processor.process(self.template_content)

        # Get actual output from ThemeEngine
        def get_palette(path):
            return self.test_palette

        engine = ThemeEngine(
            get_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        engine.apply('/fake/image.jpg', debounce=False)

        with open(self.target_path, 'r') as f:
            actual_output = f.read()

        self.assertEqual(actual_output, expected_output)

    def test_override_path_matches_wallust_path_for_same_palette(self):
        """Override path and wallust path produce identical output for the same palette.

        This is the KEY parity test: given the same palette data, both code
        paths must produce byte-identical template output.

        Bug caught: Override code path diverges from normal wallust-driven path.
        """
        from variety.smart_selection.theming import ThemeEngine

        # Run via wallust path (no override)
        def get_palette(path):
            return dict(self.test_palette)

        engine_wallust = ThemeEngine(
            get_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )
        engine_wallust.apply('/fake/image.jpg', debounce=False)

        with open(self.target_path, 'r') as f:
            wallust_output = f.read()

        # Run via override path with the same palette
        override_temp_dir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(override_temp_dir, 'test.db')
            db = ImageDatabase(db_path)

            # Create theme with same colors as the test palette
            theme = ColorThemeRecord(
                theme_id='parity-test',
                name='Parity Test',
                source_type='custom',
                **{k: v for k, v in self.test_palette.items()},
            )
            db.upsert_color_theme(theme)

            override = ThemeOverride(db)
            override.activate('parity-test')

            # Remove wallust output so we can verify override writes it
            os.remove(self.target_path)

            engine_override = ThemeEngine(
                lambda path: None,  # Wallust callback should NOT be called
                wallust_config_path=self.wallust_config,
                variety_config_path=self.variety_config,
                theme_override=override,
            )
            engine_override.apply('/fake/image.jpg', debounce=False)

            with open(self.target_path, 'r') as f:
                override_output = f.read()

            self.assertEqual(override_output, wallust_output,
                             "Override path produced different output than wallust path "
                             "for the same palette data")

            db.close()
        finally:
            shutil.rmtree(override_temp_dir)


# =============================================================================
# Run tests
# =============================================================================

if __name__ == '__main__':
    unittest.main()
