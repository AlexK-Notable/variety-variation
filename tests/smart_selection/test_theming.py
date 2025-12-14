# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for smart_selection.theming - Theming engine."""

import os
import unittest


class TestColorTransformer(unittest.TestCase):
    """Tests for ColorTransformer class."""

    def setUp(self):
        """Create a test palette."""
        self.palette = {
            'color0': '#000000',
            'color1': '#ff0000',
            'color2': '#00ff00',
            'color3': '#0000ff',
            'color4': '#ffff00',
            'color5': '#ff00ff',
            'color6': '#00ffff',
            'color7': '#ffffff',
            'background': '#1a1a1a',
            'foreground': '#e0e0e0',
        }

    def test_import_color_transformer(self):
        """ColorTransformer can be imported."""
        from variety.smart_selection.theming import ColorTransformer
        self.assertIsNotNone(ColorTransformer)

    def test_strip_removes_hash(self):
        """strip() removes # prefix from color."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.strip('#ff0000')

        self.assertEqual(result, 'ff0000')

    def test_strip_handles_no_hash(self):
        """strip() handles colors without # prefix."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.strip('ff0000')

        self.assertEqual(result, 'ff0000')

    def test_darken_reduces_lightness(self):
        """darken() reduces lightness of color."""
        from variety.smart_selection.theming import ColorTransformer
        from variety.smart_selection.palette import hex_to_hsl

        transformer = ColorTransformer(self.palette)
        original = '#808080'  # 50% lightness gray
        darkened = transformer.darken(original, 0.2)

        _, _, l_orig = hex_to_hsl(original)
        _, _, l_dark = hex_to_hsl(darkened)

        self.assertLess(l_dark, l_orig)
        self.assertAlmostEqual(l_dark, 0.3, places=1)

    def test_darken_clamps_to_zero(self):
        """darken() clamps lightness to 0."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.darken('#1a1a1a', 0.9)

        # Should be black or very close
        self.assertEqual(result.lower(), '#000000')

    def test_lighten_increases_lightness(self):
        """lighten() increases lightness of color."""
        from variety.smart_selection.theming import ColorTransformer
        from variety.smart_selection.palette import hex_to_hsl

        transformer = ColorTransformer(self.palette)
        original = '#808080'  # 50% lightness gray
        lightened = transformer.lighten(original, 0.2)

        _, _, l_orig = hex_to_hsl(original)
        _, _, l_light = hex_to_hsl(lightened)

        self.assertGreater(l_light, l_orig)
        self.assertAlmostEqual(l_light, 0.7, places=1)

    def test_lighten_clamps_to_one(self):
        """lighten() clamps lightness to 1."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.lighten('#e0e0e0', 0.9)

        # Should be white
        self.assertEqual(result.lower(), '#ffffff')

    def test_saturate_increases_saturation(self):
        """saturate() increases saturation of color."""
        from variety.smart_selection.theming import ColorTransformer
        from variety.smart_selection.palette import hex_to_hsl

        transformer = ColorTransformer(self.palette)
        # Start with a desaturated red
        original = '#bf4040'
        saturated = transformer.saturate(original, 0.3)

        _, s_orig, _ = hex_to_hsl(original)
        _, s_sat, _ = hex_to_hsl(saturated)

        self.assertGreater(s_sat, s_orig)

    def test_desaturate_decreases_saturation(self):
        """desaturate() decreases saturation of color."""
        from variety.smart_selection.theming import ColorTransformer
        from variety.smart_selection.palette import hex_to_hsl

        transformer = ColorTransformer(self.palette)
        original = '#ff0000'  # Fully saturated red
        desaturated = transformer.desaturate(original, 0.5)

        _, s_orig, _ = hex_to_hsl(original)
        _, s_desat, _ = hex_to_hsl(desaturated)

        self.assertLess(s_desat, s_orig)

    def test_desaturate_to_gray(self):
        """desaturate() with amount 1.0 creates gray."""
        from variety.smart_selection.theming import ColorTransformer
        from variety.smart_selection.palette import hex_to_hsl

        transformer = ColorTransformer(self.palette)
        result = transformer.desaturate('#ff0000', 1.0)

        _, s, _ = hex_to_hsl(result)
        self.assertAlmostEqual(s, 0.0, places=2)

    def test_blend_averages_colors(self):
        """blend() averages RGB values of two colors."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        # Blend black (color0 = #000000) with white (color7 = #ffffff)
        result = transformer.blend('#000000', 'color7')

        # Average of 0 and 255 is 127/128
        self.assertIn(result.lower(), ['#7f7f7f', '#808080'])

    def test_blend_with_missing_color(self):
        """blend() returns original if target color missing."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.blend('#ff0000', 'nonexistent')

        self.assertEqual(result.lower(), '#ff0000')

    def test_apply_filter_strip(self):
        """apply_filter handles 'strip' correctly."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.apply_filter('#ff0000', 'strip')

        self.assertEqual(result, 'ff0000')

    def test_apply_filter_darken(self):
        """apply_filter handles 'darken(0.2)' correctly."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.apply_filter('#808080', 'darken(0.2)')

        # Should be darker
        self.assertNotEqual(result.lower(), '#808080')

    def test_apply_filter_with_spaces(self):
        """apply_filter handles whitespace in expression."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.apply_filter('#808080', '  darken( 0.2 )  ')

        # Should work the same
        expected = transformer.darken('#808080', 0.2)
        self.assertEqual(result.lower(), expected.lower())

    def test_apply_filters_chain(self):
        """apply_filters applies multiple filters in order."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.apply_filters('#808080', ['darken(0.1)', 'strip'])

        # Should be darkened AND stripped (no #)
        self.assertFalse(result.startswith('#'))

    def test_apply_filters_complex_chain(self):
        """apply_filters handles complex filter chains."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        # Typical wallust filter chain
        filters = ['saturate(0.3)', 'darken(0.2)', 'strip']
        result = transformer.apply_filters('#ff0000', filters)

        # Should not start with #
        self.assertFalse(result.startswith('#'))

    def test_unknown_filter_returns_original(self):
        """Unknown filter returns color unchanged."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        result = transformer.apply_filter('#ff0000', 'unknown_filter(0.5)')

        self.assertEqual(result.lower(), '#ff0000')

    def test_invalid_filter_argument_returns_original(self):
        """Filter with invalid argument returns color unchanged."""
        from variety.smart_selection.theming import ColorTransformer

        transformer = ColorTransformer(self.palette)
        # 'not_a_number' can't be converted to float
        result = transformer.apply_filter('#ff0000', 'darken(not_a_number)')

        self.assertEqual(result.lower(), '#ff0000')


class TestColorsEquivalent(unittest.TestCase):
    """Tests for colors_equivalent function."""

    def test_import_colors_equivalent(self):
        """colors_equivalent can be imported."""
        from variety.smart_selection.theming import colors_equivalent
        self.assertIsNotNone(colors_equivalent)

    def test_identical_colors_are_equivalent(self):
        """Identical colors are equivalent."""
        from variety.smart_selection.theming import colors_equivalent

        self.assertTrue(colors_equivalent('#ff0000', '#ff0000'))

    def test_one_off_colors_are_equivalent(self):
        """Colors differing by 1 in one channel are equivalent."""
        from variety.smart_selection.theming import colors_equivalent

        self.assertTrue(colors_equivalent('#ff0000', '#fe0000'))
        self.assertTrue(colors_equivalent('#00ff00', '#00fe00'))
        self.assertTrue(colors_equivalent('#0000ff', '#0000fe'))

    def test_two_off_colors_are_not_equivalent(self):
        """Colors differing by 2 are not equivalent with default tolerance."""
        from variety.smart_selection.theming import colors_equivalent

        self.assertFalse(colors_equivalent('#ff0000', '#fd0000'))

    def test_custom_tolerance(self):
        """Custom tolerance works."""
        from variety.smart_selection.theming import colors_equivalent

        # With tolerance=2, should be equivalent
        self.assertTrue(colors_equivalent('#ff0000', '#fd0000', tolerance=2))

    def test_case_insensitive(self):
        """Comparison is case insensitive."""
        from variety.smart_selection.theming import colors_equivalent

        self.assertTrue(colors_equivalent('#FF0000', '#ff0000'))
        self.assertTrue(colors_equivalent('#AABBCC', '#aabbcc'))


class TestHexRgbConversion(unittest.TestCase):
    """Tests for hex/RGB conversion utilities."""

    def test_hex_to_rgb(self):
        """hex_to_rgb converts correctly."""
        from variety.smart_selection.theming import hex_to_rgb

        self.assertEqual(hex_to_rgb('#ff0000'), (255, 0, 0))
        self.assertEqual(hex_to_rgb('#00ff00'), (0, 255, 0))
        self.assertEqual(hex_to_rgb('#0000ff'), (0, 0, 255))
        self.assertEqual(hex_to_rgb('#ffffff'), (255, 255, 255))
        self.assertEqual(hex_to_rgb('#000000'), (0, 0, 0))

    def test_hex_to_rgb_without_hash(self):
        """hex_to_rgb works without # prefix."""
        from variety.smart_selection.theming import hex_to_rgb

        self.assertEqual(hex_to_rgb('ff0000'), (255, 0, 0))

    def test_rgb_to_hex(self):
        """rgb_to_hex converts correctly."""
        from variety.smart_selection.theming import rgb_to_hex

        self.assertEqual(rgb_to_hex(255, 0, 0), '#ff0000')
        self.assertEqual(rgb_to_hex(0, 255, 0), '#00ff00')
        self.assertEqual(rgb_to_hex(0, 0, 255), '#0000ff')
        self.assertEqual(rgb_to_hex(255, 255, 255), '#ffffff')
        self.assertEqual(rgb_to_hex(0, 0, 0), '#000000')

    def test_rgb_to_hex_clamps_values(self):
        """rgb_to_hex clamps out-of-range values."""
        from variety.smart_selection.theming import rgb_to_hex

        # Values > 255 should clamp
        self.assertEqual(rgb_to_hex(300, 0, 0), '#ff0000')
        # Negative values should clamp
        self.assertEqual(rgb_to_hex(-10, 0, 0), '#000000')


class TestTemplateProcessor(unittest.TestCase):
    """Tests for TemplateProcessor class."""

    def setUp(self):
        """Create a test palette."""
        self.palette = {
            'color0': '#1a1a1a',
            'color1': '#ff0000',
            'color2': '#00ff00',
            'color3': '#0000ff',
            'color4': '#ffff00',
            'color7': '#ffffff',
            'background': '#000000',
            'foreground': '#e0e0e0',
            'cursor': '#ff5500',
        }

    def test_import_template_processor(self):
        """TemplateProcessor can be imported."""
        from variety.smart_selection.theming import TemplateProcessor
        self.assertIsNotNone(TemplateProcessor)

    def test_simple_variable_substitution(self):
        """Simple {{variable}} is replaced."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        result = processor.process('color is {{color1}}')

        self.assertEqual(result, 'color is #ff0000')

    def test_variable_with_single_filter(self):
        """{{variable | filter}} applies filter."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        result = processor.process('color is {{color1 | strip}}')

        self.assertEqual(result, 'color is ff0000')

    def test_variable_with_filter_chain(self):
        """{{variable | filter1 | filter2}} applies chain."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        result = processor.process('{{color1 | darken(0.1) | strip}}')

        # Should be stripped (no #)
        self.assertFalse(result.startswith('#'))

    def test_multiple_variables_in_template(self):
        """Multiple variables are all replaced."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        template = 'bg={{background}} fg={{foreground}}'
        result = processor.process(template)

        self.assertEqual(result, 'bg=#000000 fg=#e0e0e0')

    def test_comment_stripping(self):
        """Template comments {# #} are stripped."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        template = '{# This is a comment #}color={{color1}}'
        result = processor.process(template)

        self.assertEqual(result, 'color=#ff0000')

    def test_multiline_comment(self):
        """Multiline comments are stripped."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        template = '{# Multi\nline\ncomment #}color={{color1}}'
        result = processor.process(template)

        self.assertEqual(result, 'color=#ff0000')

    def test_unknown_variable_preserved(self):
        """Unknown variables are preserved as-is."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        result = processor.process('{{unknown_var}}')

        self.assertEqual(result, '{{unknown_var}}')

    def test_whitespace_handling(self):
        """Extra whitespace around variable/filters is handled."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        result = processor.process('{{  color1  |  strip  }}')

        self.assertEqual(result, 'ff0000')

    def test_real_hyprland_template_line(self):
        """Real template line from hyprland.conf works."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        template = '$color4 = rgb({{color4 | strip}})'
        result = processor.process(template)

        self.assertEqual(result, '$color4 = rgb(ffff00)')

    def test_complex_filter_chain(self):
        """Complex filter chain from real template works."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        template = '$color_inactive = rgb({{color4 | saturate(0.3) | darken(0.2) | strip}})'
        result = processor.process(template)

        # Should be processed without errors
        self.assertTrue('rgb(' in result)
        self.assertFalse('{{' in result)

    def test_preserves_non_variable_content(self):
        """Non-variable content is preserved exactly."""
        from variety.smart_selection.theming import TemplateProcessor

        processor = TemplateProcessor(self.palette)
        template = '# Comment\n$var = {{color1}}\n# End'
        result = processor.process(template)

        self.assertTrue(result.startswith('# Comment\n'))
        self.assertTrue(result.endswith('\n# End'))


class TestThemeEngine(unittest.TestCase):
    """Tests for ThemeEngine class."""

    def setUp(self):
        """Create test directories and files."""
        import tempfile
        import shutil
        self.temp_dir = tempfile.mkdtemp()

        # Create test palette
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

        # Write wallust.toml
        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'test = {{ template = "{self.template_path}", target = "{self.target_path}" }}\n')

        # Create variety config (optional)
        self.variety_config = os.path.join(self.temp_dir, 'theming.json')

    def tearDown(self):
        """Clean up test directories."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def _get_test_palette(self, image_path: str) -> dict:
        """Mock palette getter."""
        return self.palette

    def test_import_theme_engine(self):
        """ThemeEngine can be imported."""
        from variety.smart_selection.theming import ThemeEngine
        self.assertIsNotNone(ThemeEngine)

    def test_import_template_config(self):
        """TemplateConfig can be imported."""
        from variety.smart_selection.theming import TemplateConfig
        self.assertIsNotNone(TemplateConfig)

    def test_import_default_reloads(self):
        """DEFAULT_RELOADS can be imported."""
        from variety.smart_selection.theming import DEFAULT_RELOADS
        self.assertIsInstance(DEFAULT_RELOADS, dict)
        self.assertIn('hyprland', DEFAULT_RELOADS)

    def test_load_templates_from_wallust_toml(self):
        """Templates are loaded from wallust.toml."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        templates = engine.get_all_templates()
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].name, 'test')

    def test_apply_processes_template(self):
        """apply() processes template and writes output."""
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

    def test_apply_returns_false_for_missing_palette(self):
        """apply() returns False when palette is not available."""
        from variety.smart_selection.theming import ThemeEngine

        def no_palette(path):
            return None

        engine = ThemeEngine(
            no_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertFalse(result)

    def test_variety_config_disables_template(self):
        """theming.json can disable specific templates."""
        import json
        from variety.smart_selection.theming import ThemeEngine

        # Write variety config
        with open(self.variety_config, 'w') as f:
            json.dump({'templates': {'test': False}}, f)

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        enabled = engine.get_enabled_templates()
        self.assertEqual(len(enabled), 0)

    def test_variety_config_global_disable(self):
        """theming.json enabled=false disables all theming."""
        import json
        from variety.smart_selection.theming import ThemeEngine

        with open(self.variety_config, 'w') as f:
            json.dump({'enabled': False}, f)

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertFalse(result)

    def test_template_caching(self):
        """Templates are cached based on mtime."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        # First apply populates cache
        engine.apply('/fake/image.jpg', debounce=False)

        # Check cache exists
        self.assertEqual(len(engine._template_cache), 1)
        self.assertIn('test', engine._template_cache)

    def test_palette_fallbacks(self):
        """Missing palette entries get fallbacks."""
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

        # cursor should fall back to foreground
        self.assertEqual(fallbacks['cursor'], '#ffffff')
        # color7 should fall back to foreground
        self.assertEqual(fallbacks['color7'], '#ffffff')
        # color0 should fall back to background
        self.assertEqual(fallbacks['color0'], '#000000')

    def test_atomic_write(self):
        """_write_atomic creates parent directories and writes file."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        nested_path = os.path.join(self.temp_dir, 'nested', 'dir', 'file.txt')
        result = engine._write_atomic(nested_path, 'test content')

        self.assertTrue(result)
        self.assertTrue(os.path.exists(nested_path))
        with open(nested_path) as f:
            self.assertEqual(f.read(), 'test content')

    def test_cleanup_cancels_timer(self):
        """cleanup() cancels any pending debounce timer."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        # Start a debounced apply
        engine.apply('/fake/image.jpg', debounce=True)

        # Timer should be pending
        self.assertIsNotNone(engine._debounce_timer)

        # Cleanup
        engine.cleanup()

        # Timer should be cancelled
        self.assertIsNone(engine._debounce_timer)

    def test_missing_wallust_config(self):
        """Missing wallust.toml results in empty templates."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path='/nonexistent/path/wallust.toml',
            variety_config_path=self.variety_config,
        )

        templates = engine.get_all_templates()
        self.assertEqual(len(templates), 0)

    def test_reload_command_override(self):
        """theming.json can override reload commands."""
        import json
        from variety.smart_selection.theming import ThemeEngine

        with open(self.variety_config, 'w') as f:
            json.dump({'reload_commands': {'test': 'echo reloaded'}}, f)

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        templates = engine.get_all_templates()
        self.assertEqual(templates[0].reload_command, 'echo reloaded')

    def test_empty_palette_returns_false(self):
        """apply() returns False for empty palette dict."""
        from variety.smart_selection.theming import ThemeEngine

        def empty_palette(path):
            return {}

        engine = ThemeEngine(
            empty_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        result = engine.apply('/fake/image.jpg', debounce=False)
        self.assertFalse(result)

    def test_toml_fallback_target_first_order(self):
        """TOML fallback parser handles target-first order."""
        from variety.smart_selection.theming import ThemeEngine

        # Write wallust.toml with target before template
        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'test = {{ target = "{self.target_path}", template = "{self.template_path}" }}\n')

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        templates = engine.get_all_templates()
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].template_path, self.template_path)
        self.assertEqual(templates[0].target_path, self.target_path)

    def test_reload_config(self):
        """reload_config() reloads templates and clears cache."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        # Populate cache
        engine.apply('/fake/image.jpg', debounce=False)
        self.assertEqual(len(engine._template_cache), 1)

        # Add another template to config
        template2_path = os.path.join(self.templates_dir, 'test2.conf')
        target2_path = os.path.join(self.output_dir, 'test2.conf')
        with open(template2_path, 'w') as f:
            f.write('color={{color1}}')

        with open(self.wallust_config, 'a') as f:
            f.write(f'test2 = {{ template = "{template2_path}", target = "{target2_path}" }}\n')

        # Reload
        engine.reload_config()

        # Should have 2 templates and cleared cache
        self.assertEqual(len(engine.get_all_templates()), 2)
        self.assertEqual(len(engine._template_cache), 0)

    def test_is_enabled(self):
        """is_enabled() returns correct state."""
        import json
        from variety.smart_selection.theming import ThemeEngine

        # Default enabled
        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )
        self.assertTrue(engine.is_enabled())

        # Disabled via config
        with open(self.variety_config, 'w') as f:
            json.dump({'enabled': False}, f)

        engine2 = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )
        self.assertFalse(engine2.is_enabled())


class TestThemeEngineTimerManagement(unittest.TestCase):
    """Tests for timer resource management."""

    def setUp(self):
        """Create test directories and files."""
        import tempfile
        import shutil
        self.temp_dir = tempfile.mkdtemp()

        # Create test palette
        self.palette = {
            'color0': '#1a1a1a',
            'background': '#000000',
            'foreground': '#e0e0e0',
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

        self.target_path = os.path.join(self.output_dir, 'test.conf')

        # Write wallust.toml
        with open(self.wallust_config, 'w') as f:
            f.write('[templates]\n')
            f.write(f'test = {{ template = "{self.template_path}", target = "{self.target_path}" }}\n')

        # Create variety config
        self.variety_config = os.path.join(self.temp_dir, 'theming.json')

    def tearDown(self):
        """Clean up test directories."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def _get_test_palette(self, image_path: str) -> dict:
        """Mock palette getter."""
        return self.palette

    def test_rapid_debounce_does_not_leak_timers(self):
        """Verify rapid apply_debounced calls don't accumulate timer threads."""
        from variety.smart_selection.theming import ThemeEngine
        import threading
        import time

        initial_thread_count = threading.active_count()

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        # Simulate rapid wallpaper changes
        for i in range(100):
            engine.apply(f"/test/image{i}.jpg", debounce=True)

        # Wait a moment for timers to be created/cancelled
        time.sleep(0.1)

        # Active thread count should not have grown significantly
        # Allow for some variance (the debounce timer + a few extra)
        current_thread_count = threading.active_count()
        thread_growth = current_thread_count - initial_thread_count

        # Should have at most a few extra threads (debounce timer, maybe 1-2 others)
        self.assertLess(thread_growth, 10, f"Thread count grew by {thread_growth}, possible timer leak")

        # Clean up
        engine.cleanup()

    def test_cleanup_cancels_pending_timer(self):
        """Verify cleanup() properly cancels any pending debounce timer."""
        from variety.smart_selection.theming import ThemeEngine

        engine = ThemeEngine(
            self._get_test_palette,
            wallust_config_path=self.wallust_config,
            variety_config_path=self.variety_config,
        )

        engine.apply("/test/image.jpg", debounce=True)

        # Timer should be pending
        self.assertIsNotNone(engine._debounce_timer)

        # Cleanup should cancel the timer
        engine.cleanup()

        # Timer should be cancelled and set to None
        self.assertTrue(engine._debounce_timer is None or not engine._debounce_timer.is_alive())


if __name__ == '__main__':
    unittest.main()
