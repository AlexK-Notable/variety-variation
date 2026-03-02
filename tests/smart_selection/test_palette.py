#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.palette - Wallust color palette integration."""

import os
import tempfile
import shutil
import unittest
from PIL import Image


class TestHexToHSL(unittest.TestCase):
    """Tests for hex_to_hsl color conversion."""

    def test_import_hex_to_hsl(self):
        """hex_to_hsl can be imported from palette module."""
        from variety.smart_selection.palette import hex_to_hsl
        self.assertIsNotNone(hex_to_hsl)

    def test_hex_to_hsl_red(self):
        """Pure red converts to correct HSL."""
        from variety.smart_selection.palette import hex_to_hsl

        h, s, l = hex_to_hsl("#FF0000")
        self.assertAlmostEqual(h, 0, places=1)  # Hue 0 = red
        self.assertAlmostEqual(s, 1.0, places=2)  # Full saturation
        self.assertAlmostEqual(l, 0.5, places=2)  # Mid lightness

    def test_hex_to_hsl_green(self):
        """Pure green converts to correct HSL."""
        from variety.smart_selection.palette import hex_to_hsl

        h, s, l = hex_to_hsl("#00FF00")
        self.assertAlmostEqual(h, 120, places=1)  # Hue 120 = green
        self.assertAlmostEqual(s, 1.0, places=2)
        self.assertAlmostEqual(l, 0.5, places=2)

    def test_hex_to_hsl_blue(self):
        """Pure blue converts to correct HSL."""
        from variety.smart_selection.palette import hex_to_hsl

        h, s, l = hex_to_hsl("#0000FF")
        self.assertAlmostEqual(h, 240, places=1)  # Hue 240 = blue
        self.assertAlmostEqual(s, 1.0, places=2)
        self.assertAlmostEqual(l, 0.5, places=2)

    def test_hex_to_hsl_white(self):
        """White has no saturation and full lightness."""
        from variety.smart_selection.palette import hex_to_hsl

        h, s, l = hex_to_hsl("#FFFFFF")
        self.assertAlmostEqual(s, 0.0, places=2)
        self.assertAlmostEqual(l, 1.0, places=2)

    def test_hex_to_hsl_black(self):
        """Black has no saturation and zero lightness."""
        from variety.smart_selection.palette import hex_to_hsl

        h, s, l = hex_to_hsl("#000000")
        self.assertAlmostEqual(s, 0.0, places=2)
        self.assertAlmostEqual(l, 0.0, places=2)

    def test_hex_to_hsl_lowercase(self):
        """Handles lowercase hex colors."""
        from variety.smart_selection.palette import hex_to_hsl

        h, s, l = hex_to_hsl("#ff0000")
        self.assertAlmostEqual(h, 0, places=1)


class TestHSLToHex(unittest.TestCase):
    """Tests for hsl_to_hex color conversion."""

    def test_import_hsl_to_hex(self):
        """hsl_to_hex can be imported from palette module."""
        from variety.smart_selection.palette import hsl_to_hex
        self.assertIsNotNone(hsl_to_hex)

    def test_hsl_to_hex_red(self):
        """Pure red HSL converts to correct hex."""
        from variety.smart_selection.palette import hsl_to_hex

        result = hsl_to_hex(0, 1.0, 0.5)
        self.assertEqual(result.lower(), "#ff0000")

    def test_hsl_to_hex_green(self):
        """Pure green HSL converts to correct hex."""
        from variety.smart_selection.palette import hsl_to_hex

        result = hsl_to_hex(120, 1.0, 0.5)
        self.assertEqual(result.lower(), "#00ff00")

    def test_hsl_to_hex_blue(self):
        """Pure blue HSL converts to correct hex."""
        from variety.smart_selection.palette import hsl_to_hex

        result = hsl_to_hex(240, 1.0, 0.5)
        self.assertEqual(result.lower(), "#0000ff")

    def test_hsl_to_hex_white(self):
        """White HSL converts to correct hex."""
        from variety.smart_selection.palette import hsl_to_hex

        result = hsl_to_hex(0, 0.0, 1.0)
        self.assertEqual(result.lower(), "#ffffff")

    def test_hsl_to_hex_black(self):
        """Black HSL converts to correct hex."""
        from variety.smart_selection.palette import hsl_to_hex

        result = hsl_to_hex(0, 0.0, 0.0)
        self.assertEqual(result.lower(), "#000000")

    def test_hsl_to_hex_gray(self):
        """Gray HSL converts to correct hex."""
        from variety.smart_selection.palette import hsl_to_hex

        result = hsl_to_hex(0, 0.0, 0.5)
        # Should be ~#808080 (50% gray), allow ±1 for rounding
        # int(0.5 * 255) = 127 = 0x7f
        self.assertIn(result.lower(), ["#7f7f7f", "#808080"])

    def test_roundtrip_conversion(self):
        """Converting hex to HSL and back gives same color."""
        from variety.smart_selection.palette import hex_to_hsl, hsl_to_hex

        original_colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00",
                         "#FF00FF", "#00FFFF", "#808080", "#FFFFFF", "#000000"]

        for original in original_colors:
            h, s, l = hex_to_hsl(original)
            result = hsl_to_hex(h, s, l)
            self.assertEqual(result.lower(), original.lower(),
                           f"Roundtrip failed for {original}")

    def test_hsl_to_hex_clamps_values(self):
        """hsl_to_hex clamps out-of-range values."""
        from variety.smart_selection.palette import hsl_to_hex

        # Negative lightness should clamp to 0 (black)
        result = hsl_to_hex(0, 1.0, -0.5)
        self.assertEqual(result.lower(), "#000000")

        # Lightness > 1 should clamp to 1 (white)
        result = hsl_to_hex(0, 0.0, 1.5)
        self.assertEqual(result.lower(), "#ffffff")

        # Saturation > 1 should clamp to 1
        result = hsl_to_hex(0, 1.5, 0.5)
        self.assertEqual(result.lower(), "#ff0000")


class TestColorTemperature(unittest.TestCase):
    """Tests for color temperature calculation."""

    def test_import_calculate_temperature(self):
        """calculate_temperature can be imported."""
        from variety.smart_selection.palette import calculate_temperature
        self.assertIsNotNone(calculate_temperature)

    def test_warm_color_positive_temperature(self):
        """Warm colors (red/orange/yellow) have positive temperature."""
        from variety.smart_selection.palette import calculate_temperature

        # Orange (warm)
        temp = calculate_temperature(30, 1.0, 0.5)  # Hue 30 = orange
        self.assertGreater(temp, 0)

    def test_cool_color_negative_temperature(self):
        """Cool colors (blue/cyan) have negative temperature."""
        from variety.smart_selection.palette import calculate_temperature

        # Blue (cool)
        temp = calculate_temperature(240, 1.0, 0.5)  # Hue 240 = blue
        self.assertLess(temp, 0)

    def test_neutral_color_near_zero(self):
        """Neutral/desaturated colors have temperature near zero."""
        from variety.smart_selection.palette import calculate_temperature

        # Gray (no hue, no saturation)
        temp = calculate_temperature(0, 0.0, 0.5)
        self.assertAlmostEqual(temp, 0, places=1)


class TestParsePalette(unittest.TestCase):
    """Tests for parsing wallust JSON output."""

    def test_import_parse_wallust_json(self):
        """parse_wallust_json can be imported."""
        from variety.smart_selection.palette import parse_wallust_json
        self.assertIsNotNone(parse_wallust_json)

    def test_parse_wallust_json_extracts_colors(self):
        """parse_wallust_json extracts all 16 colors plus foreground/background."""
        from variety.smart_selection.palette import parse_wallust_json

        json_data = {
            "background": "#171815",
            "foreground": "#E7E8EC",
            "cursor": "#A5A3A3",
            "color0": "#3E3F3C",
            "color1": "#3F4122",
            "color2": "#4A4743",
            "color3": "#544638",
            "color4": "#5B4622",
            "color5": "#6E7076",
            "color6": "#8C8E97",
            "color7": "#D5D6DC",
            "color8": "#95959A",
            "color9": "#54572D",
            "color10": "#635F5A",
            "color11": "#705E4B",
            "color12": "#7A5D2D",
            "color13": "#93969D",
            "color14": "#BBBDC9",
            "color15": "#D5D6DC",
        }

        result = parse_wallust_json(json_data)

        self.assertEqual(result['background'], "#171815")
        self.assertEqual(result['foreground'], "#E7E8EC")
        self.assertEqual(result['color0'], "#3E3F3C")
        self.assertEqual(result['color15'], "#D5D6DC")

    def test_parse_wallust_json_calculates_avg_metrics(self):
        """parse_wallust_json calculates average hue, saturation, lightness."""
        from variety.smart_selection.palette import parse_wallust_json

        # Simple palette with known values
        json_data = {
            "background": "#FF0000",  # Red
            "foreground": "#FFFFFF",
            "cursor": "#000000",
        }
        # Add colors 0-15 as red for simplicity
        for i in range(16):
            json_data[f"color{i}"] = "#FF0000"

        result = parse_wallust_json(json_data)

        self.assertIn('avg_hue', result)
        self.assertIn('avg_saturation', result)
        self.assertIn('avg_lightness', result)
        self.assertIn('color_temperature', result)

    def test_parse_wallust_json_rgb_list_format(self):
        """parse_wallust_json handles RGB list format from wallust cache."""
        from variety.smart_selection.palette import parse_wallust_json

        # Simulate wallust cache format: [[{RGB}, {RGB}, ...], ...]
        # This is the format stored in ~/.cache/wallust/{hash}/FastResize_*
        rgb_cache_data = [
            [
                {"red": 1.0, "green": 0.0, "blue": 0.0},      # Red
                {"red": 0.0, "green": 1.0, "blue": 0.0},      # Green
                {"red": 0.0, "green": 0.0, "blue": 1.0},      # Blue
                {"red": 1.0, "green": 1.0, "blue": 0.0},      # Yellow
                {"red": 0.5, "green": 0.5, "blue": 0.5},      # Gray
                {"red": 0.0, "green": 1.0, "blue": 1.0},      # Cyan
            ],
            # Additional palettes (light/dark variants)
            [],
        ]

        result = parse_wallust_json(rgb_cache_data)

        # Should convert RGB floats to hex
        self.assertEqual(result['color0'], "#ff0000")  # Red
        self.assertEqual(result['color1'], "#00ff00")  # Green
        self.assertEqual(result['color2'], "#0000ff")  # Blue
        self.assertEqual(result['color3'], "#ffff00")  # Yellow

        # Should calculate metrics
        self.assertIn('avg_hue', result)
        self.assertIn('avg_saturation', result)
        self.assertIn('avg_lightness', result)
        self.assertIn('color_temperature', result)

    def test_parse_wallust_json_empty_input(self):
        """parse_wallust_json handles empty input gracefully."""
        from variety.smart_selection.palette import parse_wallust_json

        result = parse_wallust_json([])
        self.assertEqual(result, {})

        result = parse_wallust_json({})
        self.assertEqual(result, {})


class TestPaletteExtractor(unittest.TestCase):
    """Tests for PaletteExtractor class."""

    def setUp(self):
        """Create temporary directory with test image."""
        self.temp_dir = tempfile.mkdtemp()

        # Create a gradient test image with color variety
        # Wallust needs diverse colors to extract a palette
        self.test_image = os.path.join(self.temp_dir, 'test.jpg')
        img = Image.new('RGB', (100, 100))
        pixels = img.load()
        for y in range(100):
            for x in range(100):
                # Create gradient with variety
                r = int((x / 100) * 255)
                g = int((y / 100) * 255)
                b = int(((x + y) / 200) * 255)
                pixels[x, y] = (r, g, b)
        img.save(self.test_image, quality=95)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_import_palette_extractor(self):
        """PaletteExtractor can be imported."""
        from variety.smart_selection.palette import PaletteExtractor
        self.assertIsNotNone(PaletteExtractor)

    def test_palette_extractor_creation(self):
        """PaletteExtractor can be created."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        self.assertIsNotNone(extractor)

    def test_is_wallust_available(self):
        """is_wallust_available returns True if wallust is installed."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        # This test will pass on systems with wallust installed
        # On systems without wallust, it should return False
        result = extractor.is_wallust_available()
        self.assertIsInstance(result, bool)

    @unittest.skipUnless(
        shutil.which('wallust'),
        "wallust not installed"
    )
    def test_extract_palette_returns_dict(self):
        """extract_palette returns a dictionary with colors."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        result = extractor.extract_palette(self.test_image)

        self.assertIsInstance(result, dict)
        self.assertIn('background', result)
        self.assertIn('foreground', result)
        self.assertIn('color0', result)

    @unittest.skipUnless(
        shutil.which('wallust'),
        "wallust not installed"
    )
    def test_extract_palette_includes_metrics(self):
        """extract_palette includes derived color metrics."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        result = extractor.extract_palette(self.test_image)

        self.assertIn('avg_hue', result)
        self.assertIn('avg_saturation', result)
        self.assertIn('avg_lightness', result)
        self.assertIn('color_temperature', result)

    def test_extract_palette_nonexistent_file(self):
        """extract_palette returns None for nonexistent files."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        result = extractor.extract_palette('/nonexistent/path.jpg')

        self.assertIsNone(result)


class TestCreatePaletteRecord(unittest.TestCase):
    """Tests for creating PaletteRecord from extracted palette."""

    def test_import_create_palette_record(self):
        """create_palette_record can be imported."""
        from variety.smart_selection.palette import create_palette_record
        self.assertIsNotNone(create_palette_record)

    def test_create_palette_record(self):
        """create_palette_record creates valid PaletteRecord."""
        from variety.smart_selection.palette import create_palette_record
        from variety.smart_selection.models import PaletteRecord

        palette_data = {
            'background': '#000000',
            'foreground': '#FFFFFF',
            'color0': '#111111',
            'color1': '#222222',
            'color2': '#333333',
            'color3': '#444444',
            'color4': '#555555',
            'color5': '#666666',
            'color6': '#777777',
            'color7': '#888888',
            'color8': '#999999',
            'color9': '#AAAAAA',
            'color10': '#BBBBBB',
            'color11': '#CCCCCC',
            'color12': '#DDDDDD',
            'color13': '#EEEEEE',
            'color14': '#F0F0F0',
            'color15': '#FFFFFF',
            'avg_hue': 180.0,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }

        record = create_palette_record('/test/image.jpg', palette_data)

        self.assertIsInstance(record, PaletteRecord)
        self.assertEqual(record.filepath, '/test/image.jpg')
        self.assertEqual(record.background, '#000000')
        self.assertEqual(record.foreground, '#FFFFFF')
        self.assertEqual(record.color0, '#111111')
        self.assertEqual(record.avg_hue, 180.0)


class TestColorSimilarity(unittest.TestCase):
    """Tests for color similarity calculation (Phase 4 prep)."""

    def test_import_palette_similarity(self):
        """palette_similarity can be imported."""
        from variety.smart_selection.palette import palette_similarity
        self.assertIsNotNone(palette_similarity)

    def test_identical_palettes_similarity_one(self):
        """Identical palettes have similarity of 1.0."""
        from variety.smart_selection.palette import palette_similarity

        palette = {
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }

        similarity = palette_similarity(palette, palette)
        self.assertAlmostEqual(similarity, 1.0, places=2)

    def test_opposite_palettes_low_similarity(self):
        """Very different palettes have low similarity."""
        from variety.smart_selection.palette import palette_similarity

        warm_bright = {
            'avg_hue': 30,  # Orange
            'avg_saturation': 1.0,
            'avg_lightness': 0.8,
            'color_temperature': 1.0,
        }
        cool_dark = {
            'avg_hue': 240,  # Blue
            'avg_saturation': 1.0,
            'avg_lightness': 0.2,
            'color_temperature': -1.0,
        }

        similarity = palette_similarity(warm_bright, cool_dark)
        self.assertLess(similarity, 0.5)

    def test_similar_palettes_high_similarity(self):
        """Similar palettes have high similarity."""
        from variety.smart_selection.palette import palette_similarity

        palette1 = {
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }
        palette2 = {
            'avg_hue': 185,  # Slightly different
            'avg_saturation': 0.52,
            'avg_lightness': 0.48,
            'color_temperature': 0.05,
        }

        similarity = palette_similarity(palette1, palette2)
        self.assertGreater(similarity, 0.8)

    def test_palette_similarity_uses_oklab_when_colors_present(self):
        """palette_similarity uses OKLAB when color values are present."""
        from variety.smart_selection.palette import palette_similarity

        # Palette with color values should use OKLAB
        palette1 = {
            'color0': '#FF0000',
            'color1': '#00FF00',
            'color2': '#0000FF',
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
        }
        palette2 = {
            'color0': '#FF0000',
            'color1': '#00FF00',
            'color2': '#0000FF',
            'avg_hue': 0,  # Different avg_hue, but same colors
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
        }

        # With OKLAB (default), identical colors should give high similarity
        similarity_oklab = palette_similarity(palette1, palette2, use_oklab=True)
        self.assertAlmostEqual(similarity_oklab, 1.0, places=2)

        # With HSL, the different avg_hue should give lower similarity
        similarity_hsl = palette_similarity(palette1, palette2, use_oklab=False)
        self.assertLess(similarity_hsl, 0.7)  # Different due to hue difference

    def test_palette_similarity_fallback_to_hsl(self):
        """palette_similarity falls back to HSL when no color values present."""
        from variety.smart_selection.palette import palette_similarity

        # Palette without color values
        palette1 = {
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }
        palette2 = {
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }

        # Should fall back to HSL and still work
        similarity = palette_similarity(palette1, palette2, use_oklab=True)
        self.assertAlmostEqual(similarity, 1.0, places=2)

    def test_palette_similarity_hsl_explicit(self):
        """palette_similarity with use_oklab=False uses HSL."""
        from variety.smart_selection.palette import palette_similarity, palette_similarity_hsl

        palette = {
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }

        # Should give same result as explicit HSL function
        result_via_param = palette_similarity(palette, palette, use_oklab=False)
        result_direct = palette_similarity_hsl(palette, palette)
        self.assertAlmostEqual(result_via_param, result_direct, places=6)


class TestCalculatePaletteMetrics(unittest.TestCase):
    """Tests for calculate_palette_metrics() extracted from parse_wallust_json().

    Phase 0 refactoring: the metric computation (lines 245-272 of palette.py)
    is extracted into a standalone function. These tests verify the extracted
    function produces correct results for edge cases and maintains parity
    with the original inline code.

    Tests are written against the planned interface. They will fail with
    ImportError until the feature code is implemented -- this is expected.
    """

    def _import_calculate_palette_metrics(self):
        """Import the function under test, raising SkipTest if not yet implemented."""
        try:
            from variety.smart_selection.palette import calculate_palette_metrics
            return calculate_palette_metrics
        except ImportError:
            raise unittest.SkipTest(
                "calculate_palette_metrics not yet extracted (Phase 0 pending)"
            )

    # --- Happy Path ---

    def test_all_red_palette_hue_near_zero(self):
        """All-red palette (16x #FF0000) should have avg_hue near 0 or 360.

        Bug caught: incorrect circular mean giving arbitrary hue for uniform input.
        """
        calc = self._import_calculate_palette_metrics()
        colors = {f'color{i}': '#FF0000' for i in range(16)}
        result = calc(colors)

        self.assertIn('avg_hue', result)
        # Hue 0 and 360 are equivalent on the color wheel
        hue = result['avg_hue']
        self.assertTrue(
            hue < 5 or hue > 355,
            f"All-red palette avg_hue should be near 0/360, got {hue}"
        )

    def test_all_blue_palette_hue_near_240(self):
        """All-blue palette (16x #0000FF) should have avg_hue near 240.

        Bug caught: hue calculation off by a constant or not using degrees.
        """
        calc = self._import_calculate_palette_metrics()
        colors = {f'color{i}': '#0000FF' for i in range(16)}
        result = calc(colors)

        self.assertIn('avg_hue', result)
        self.assertAlmostEqual(result['avg_hue'], 240, delta=5)

    def test_returns_all_four_metric_keys(self):
        """Result contains avg_hue, avg_saturation, avg_lightness, color_temperature.

        Bug caught: missing key in returned dict breaks downstream consumers.
        """
        calc = self._import_calculate_palette_metrics()
        colors = {f'color{i}': '#FF0000' for i in range(16)}
        result = calc(colors)

        for key in ['avg_hue', 'avg_saturation', 'avg_lightness', 'color_temperature']:
            self.assertIn(key, result, f"Missing key '{key}' in result")

    def test_warm_palette_positive_temperature(self):
        """Warm palette (all oranges) should have positive color_temperature.

        Bug caught: temperature sign inverted or not weighted by saturation.
        """
        calc = self._import_calculate_palette_metrics()
        # Orange hue ~30 degrees, fully saturated
        colors = {f'color{i}': '#FF8000' for i in range(16)}
        result = calc(colors)

        self.assertIn('color_temperature', result)
        self.assertGreater(
            result['color_temperature'], 0,
            f"Orange palette should have positive temperature, got {result['color_temperature']}"
        )

    def test_cool_palette_negative_temperature(self):
        """Cool palette (all blues) should have negative color_temperature.

        Bug caught: temperature sign inverted for cool hues.
        """
        calc = self._import_calculate_palette_metrics()
        colors = {f'color{i}': '#0000FF' for i in range(16)}
        result = calc(colors)

        self.assertIn('color_temperature', result)
        self.assertLess(
            result['color_temperature'], 0,
            f"Blue palette should have negative temperature, got {result['color_temperature']}"
        )

    # --- Circular Hue Edge Cases ---

    def test_circular_hue_wrapping_near_zero(self):
        """8 colors at hue 350 + 8 at hue 10 should average near 0/360, NOT 180.

        Bug caught: naive arithmetic mean of 350 and 10 gives 180 (wrong side
        of the color wheel). Correct circular mean uses sin/cos averaging.
        """
        calc = self._import_calculate_palette_metrics()
        from variety.smart_selection.palette import hsl_to_hex

        colors = {}
        for i in range(8):
            colors[f'color{i}'] = hsl_to_hex(350, 1.0, 0.5)  # Near-red, just below 360
        for i in range(8, 16):
            colors[f'color{i}'] = hsl_to_hex(10, 1.0, 0.5)   # Near-red, just above 0

        result = calc(colors)
        hue = result['avg_hue']

        # Circular mean of 350 and 10 should be near 0 (or equivalently 360)
        # NOT near 180 which is the naive arithmetic mean
        self.assertTrue(
            hue < 20 or hue > 340,
            f"Circular mean of hues 350 and 10 should be near 0/360, got {hue}. "
            f"Naive arithmetic mean (180) indicates non-circular averaging."
        )

    def test_opposite_hues_does_not_crash(self):
        """Hues at 0 and 180 (exact opposites) should not crash.

        Bug caught: atan2(0, 0) is undefined when sin/cos sums cancel perfectly.
        The function must handle this gracefully.
        """
        calc = self._import_calculate_palette_metrics()
        from variety.smart_selection.palette import hsl_to_hex

        colors = {}
        for i in range(8):
            colors[f'color{i}'] = hsl_to_hex(0, 1.0, 0.5)    # Red (hue 0)
        for i in range(8, 16):
            colors[f'color{i}'] = hsl_to_hex(180, 1.0, 0.5)   # Cyan (hue 180)

        # Must not raise any exception
        result = calc(colors)
        self.assertIn('avg_hue', result)
        # The hue value is mathematically ambiguous here, but must be a valid number
        self.assertIsInstance(result['avg_hue'], float)
        self.assertFalse(
            result['avg_hue'] != result['avg_hue'],  # NaN check (NaN != NaN)
            "avg_hue must not be NaN for opposite hues"
        )

    # --- Edge Cases: Unusual Inputs ---

    def test_empty_palette_no_crash(self):
        """Empty dict (no colorN keys) should return dict without crashing.

        Bug caught: division by zero when no colors found, or KeyError on
        missing color keys.
        """
        calc = self._import_calculate_palette_metrics()
        result = calc({})

        self.assertIsInstance(result, dict)
        # Empty input should not produce metric keys (no data to compute from)
        self.assertNotIn('avg_hue', result)

    def test_single_color_valid_metrics(self):
        """Dict with only color0 should still compute valid metrics.

        Bug caught: logic assumes all 16 colors present, crashes or produces
        wrong averages with fewer.
        """
        calc = self._import_calculate_palette_metrics()
        result = calc({'color0': '#FF0000'})

        self.assertIn('avg_hue', result)
        self.assertIn('avg_saturation', result)
        self.assertIn('avg_lightness', result)
        self.assertIn('color_temperature', result)
        # Single red color: hue should be near 0
        hue = result['avg_hue']
        self.assertTrue(
            hue < 5 or hue > 355,
            f"Single red color avg_hue should be near 0/360, got {hue}"
        )

    def test_all_achromatic_saturation_near_zero(self):
        """All-gray palette should have saturation near 0 and hue should not be NaN.

        Bug caught: NaN from achromatic hue (0 saturation makes hue undefined
        in HSL), or division-by-zero in saturation calculation.
        """
        calc = self._import_calculate_palette_metrics()
        # 16 shades of gray
        grays = [
            '#111111', '#222222', '#333333', '#444444',
            '#555555', '#666666', '#777777', '#888888',
            '#999999', '#AAAAAA', '#BBBBBB', '#CCCCCC',
            '#DDDDDD', '#EEEEEE', '#F0F0F0', '#FAFAFA',
        ]
        colors = {f'color{i}': grays[i] for i in range(16)}
        result = calc(colors)

        self.assertIn('avg_saturation', result)
        self.assertAlmostEqual(
            result['avg_saturation'], 0.0, places=2,
            msg=f"All-gray palette saturation should be ~0, got {result['avg_saturation']}"
        )
        self.assertIn('avg_hue', result)
        # Hue must not be NaN
        self.assertFalse(
            result['avg_hue'] != result['avg_hue'],
            "avg_hue must not be NaN for achromatic palette"
        )

    def test_non_color_keys_ignored(self):
        """Keys that are not colorN should not affect metric computation.

        Bug caught: function iterating over all dict keys instead of color0-15.
        """
        calc = self._import_calculate_palette_metrics()
        colors = {f'color{i}': '#FF0000' for i in range(16)}
        colors['background'] = '#000000'
        colors['foreground'] = '#FFFFFF'
        colors['cursor'] = '#FFFFFF'
        colors['some_extra_key'] = 'not_a_color'

        result = calc(colors)
        # Should succeed and produce metrics from the 16 color keys only
        self.assertIn('avg_hue', result)

    # --- Parity Test ---

    def test_parity_with_parse_wallust_json(self):
        """calculate_palette_metrics() produces values within 0.001 of parse_wallust_json().

        Bug caught: refactoring divergence where the extracted function computes
        different values than the original inline code in parse_wallust_json().
        This is the most critical test for Phase 0.
        """
        calc = self._import_calculate_palette_metrics()
        from variety.smart_selection.palette import parse_wallust_json

        # Tokyo Night-inspired palette (realistic, varied colors)
        json_data = {
            'color0': '#1a1b26',
            'color1': '#f7768e',
            'color2': '#9ece6a',
            'color3': '#e0af68',
            'color4': '#7aa2f7',
            'color5': '#bb9af7',
            'color6': '#7dcfff',
            'color7': '#c0caf5',
            'color8': '#414868',
            'color9': '#f7768e',
            'color10': '#9ece6a',
            'color11': '#e0af68',
            'color12': '#7aa2f7',
            'color13': '#bb9af7',
            'color14': '#7dcfff',
            'color15': '#c0caf5',
            'background': '#1a1b26',
            'foreground': '#c0caf5',
            'cursor': '#c0caf5',
        }

        # parse_wallust_json computes metrics inline
        inline_result = parse_wallust_json(json_data)

        # calculate_palette_metrics computes the same metrics standalone
        # It should accept the same color dict format
        extracted_result = calc(json_data)

        # All four metrics must match within floating-point tolerance
        self.assertAlmostEqual(
            inline_result['avg_hue'],
            extracted_result['avg_hue'],
            places=3,
            msg="avg_hue diverged between parse_wallust_json and calculate_palette_metrics"
        )
        self.assertAlmostEqual(
            inline_result['avg_saturation'],
            extracted_result['avg_saturation'],
            places=3,
            msg="avg_saturation diverged"
        )
        self.assertAlmostEqual(
            inline_result['avg_lightness'],
            extracted_result['avg_lightness'],
            places=3,
            msg="avg_lightness diverged"
        )
        self.assertAlmostEqual(
            inline_result['color_temperature'],
            extracted_result['color_temperature'],
            places=3,
            msg="color_temperature diverged"
        )

    def test_parity_with_different_palette(self):
        """Parity test with a second palette to guard against coincidental matches.

        Bug caught: the first parity test could pass by accident if both paths
        produce the same wrong answer for one specific input.
        """
        calc = self._import_calculate_palette_metrics()
        from variety.smart_selection.palette import parse_wallust_json

        # Warm earthy palette (very different from Tokyo Night)
        json_data = {
            'color0': '#3E3F3C',
            'color1': '#3F4122',
            'color2': '#4A4743',
            'color3': '#544638',
            'color4': '#5B4622',
            'color5': '#6E7076',
            'color6': '#8C8E97',
            'color7': '#D5D6DC',
            'color8': '#95959A',
            'color9': '#54572D',
            'color10': '#635F5A',
            'color11': '#705E4B',
            'color12': '#7A5D2D',
            'color13': '#93969D',
            'color14': '#BBBDC9',
            'color15': '#D5D6DC',
            'background': '#171815',
            'foreground': '#E7E8EC',
            'cursor': '#A5A3A3',
        }

        inline_result = parse_wallust_json(json_data)
        extracted_result = calc(json_data)

        self.assertAlmostEqual(
            inline_result['avg_hue'], extracted_result['avg_hue'], places=3
        )
        self.assertAlmostEqual(
            inline_result['avg_saturation'], extracted_result['avg_saturation'], places=3
        )
        self.assertAlmostEqual(
            inline_result['avg_lightness'], extracted_result['avg_lightness'], places=3
        )
        self.assertAlmostEqual(
            inline_result['color_temperature'], extracted_result['color_temperature'], places=3
        )


class TestHexToLuminance(unittest.TestCase):
    """Tests for hex_to_luminance using OKLAB perceptual lightness.

    OKLAB L is perceptually uniform: equal numeric differences correspond
    to equal perceived brightness differences. Unlike BT.709 or HSL,
    #808080 maps to ~0.60 (perceptual mid-gray), not 0.50.
    """

    def test_import_hex_to_luminance(self):
        """hex_to_luminance can be imported from palette module."""
        from variety.smart_selection.palette import hex_to_luminance
        self.assertIsNotNone(hex_to_luminance)

    def test_black_is_zero(self):
        """Black (#000000) has lightness 0.0."""
        from variety.smart_selection.palette import hex_to_luminance
        self.assertAlmostEqual(hex_to_luminance('#000000'), 0.0, places=4)

    def test_white_is_one(self):
        """White (#FFFFFF) has lightness 1.0."""
        from variety.smart_selection.palette import hex_to_luminance
        self.assertAlmostEqual(hex_to_luminance('#FFFFFF'), 1.0, places=4)

    def test_yellow_much_brighter_than_blue(self):
        """Yellow (#FFFF00) is perceptually much brighter than blue (#0000FF).

        OKLAB correctly separates yellow (~0.97) from blue (~0.45),
        matching human perception. HSL gives both L=0.5.
        """
        from variety.smart_selection.palette import hex_to_luminance

        yellow = hex_to_luminance('#FFFF00')
        blue = hex_to_luminance('#0000FF')

        self.assertGreater(yellow, 0.9, f"Yellow should be very bright, got {yellow}")
        self.assertLess(blue, 0.5, f"Blue should be below mid-brightness, got {blue}")
        self.assertGreater(yellow, blue, "Yellow should be brighter than blue")

    def test_green_brighter_than_red(self):
        """Green (#00FF00) should be brighter than red (#FF0000),
        which should be brighter than blue (#0000FF) in OKLAB.
        """
        from variety.smart_selection.palette import hex_to_luminance

        green = hex_to_luminance('#00FF00')
        red = hex_to_luminance('#FF0000')
        blue = hex_to_luminance('#0000FF')

        self.assertGreater(green, red, "Green should be brighter than red")
        self.assertGreater(red, blue, "Red should be brighter than blue")
        # OKLAB L values: green ≈ 0.87, red ≈ 0.63, blue ≈ 0.45
        self.assertAlmostEqual(green, 0.866, places=2)
        self.assertAlmostEqual(red, 0.628, places=2)
        self.assertAlmostEqual(blue, 0.452, places=2)

    def test_50_percent_gray(self):
        """50% gray (#808080) should be ~0.60 in OKLAB (perceptual mid-gray)."""
        from variety.smart_selection.palette import hex_to_luminance

        gray = hex_to_luminance('#808080')
        # OKLAB L for #808080 ≈ 0.60 (perceptual mid-gray, not linear 0.50)
        self.assertAlmostEqual(gray, 0.60, places=1)

    def test_lowercase_hex(self):
        """Handles lowercase hex input."""
        from variety.smart_selection.palette import hex_to_luminance

        upper = hex_to_luminance('#FF0000')
        lower = hex_to_luminance('#ff0000')
        self.assertAlmostEqual(upper, lower, places=6)

    def test_matches_color_science_get_oklab_lightness(self):
        """hex_to_luminance delegates to get_oklab_lightness correctly."""
        from variety.smart_selection.palette import hex_to_luminance
        from variety.smart_selection.color_science import get_oklab_lightness

        test_colors = ['#FF0000', '#00FF00', '#0000FF', '#808080', '#FFFFFF', '#000000']
        for color in test_colors:
            self.assertAlmostEqual(
                hex_to_luminance(color),
                get_oklab_lightness(color),
                places=6,
                msg=f"Mismatch for {color}",
            )


class TestComputePerceivedBrightness(unittest.TestCase):
    """Tests for _compute_pixel_metrics OKLAB-based brightness.

    This function computes OKLAB L per pixel, then takes the median
    plus P10/P90 percentiles for range detection.
    """

    def setUp(self):
        """Create temporary directory for test images."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _make_image(self, name, color, size=(100, 100)):
        """Create a solid-color test image."""
        path = os.path.join(self.temp_dir, name)
        img = Image.new('RGB', size, color=color)
        img.save(path)
        return path

    def test_import(self):
        """_compute_pixel_metrics can be imported."""
        from variety.smart_selection.palette import _compute_pixel_metrics
        self.assertIsNotNone(_compute_pixel_metrics)

    def test_dark_image_low_brightness(self):
        """Near-black image has very low perceived brightness."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._make_image('dark.jpg', '#0A0A0A')
        result = _compute_pixel_metrics(path)

        self.assertIsNotNone(result)
        # OKLAB L for #0A0A0A ≈ 0.145
        self.assertLess(result['perceived_brightness'], 0.2)
        self.assertLess(result['brightness_p90'], 0.2)

    def test_bright_image_high_brightness(self):
        """Near-white image has very high perceived brightness."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._make_image('bright.jpg', '#F0F0F0')
        result = _compute_pixel_metrics(path)

        self.assertIsNotNone(result)
        self.assertGreater(result['perceived_brightness'], 0.9)
        self.assertGreater(result['brightness_p10'], 0.9)

    def test_mixed_image_p90_detects_bright_spots(self):
        """Image with dark + bright areas has P90 above median.

        This is the night-mode use case: median brightness is low (dark image),
        but P90 catches the bright region that would be glaring at night.
        Use PNG to avoid JPEG compression artifacts blurring boundaries.
        """
        from variety.smart_selection.palette import _compute_pixel_metrics

        # Create image: 70% dark, 30% bright (enough for P90 to land in bright)
        img = Image.new('RGB', (100, 100), color='#0A0A0A')
        pixels = img.load()
        # Make bottom 30 rows bright white
        for y in range(70, 100):
            for x in range(100):
                pixels[x, y] = (240, 240, 240)
        path = os.path.join(self.temp_dir, 'mixed.png')
        img.save(path)

        result = _compute_pixel_metrics(path)

        self.assertIsNotNone(result)
        # Median should be low (70% of pixels are dark)
        self.assertLess(result['perceived_brightness'], 0.3)
        # P90 should be high (30% bright pixels means P90 lands in bright area)
        self.assertGreater(result['brightness_p90'], 0.5)
        # P10 should be low (darkest 10% is very dark, OKLAB L ≈ 0.145 for #0A0A0A)
        self.assertLess(result['brightness_p10'], 0.2)

    def test_returns_all_three_keys(self):
        """Result dict contains perceived_brightness, brightness_p10, brightness_p90."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._make_image('gray.jpg', '#808080')
        result = _compute_pixel_metrics(path)

        self.assertIsNotNone(result)
        self.assertIn('perceived_brightness', result)
        self.assertIn('brightness_p10', result)
        self.assertIn('brightness_p90', result)

    def test_values_between_zero_and_one(self):
        """All values are normalized to [0, 1] range."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._make_image('mid.jpg', '#808080')
        result = _compute_pixel_metrics(path)

        for key in ('perceived_brightness', 'brightness_p10', 'brightness_p90'):
            self.assertGreaterEqual(result[key], 0.0)
            self.assertLessEqual(result[key], 1.0)

    def test_p10_less_than_p90(self):
        """P10 should always be <= P90."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        # Gradient image for varied brightness
        img = Image.new('RGB', (100, 100))
        pixels = img.load()
        for y in range(100):
            gray = int((y / 100) * 255)
            for x in range(100):
                pixels[x, y] = (gray, gray, gray)
        path = os.path.join(self.temp_dir, 'gradient.jpg')
        img.save(path)

        result = _compute_pixel_metrics(path)
        self.assertLessEqual(result['brightness_p10'], result['brightness_p90'])

    def test_nonexistent_file_returns_none(self):
        """Returns None for nonexistent file."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        result = _compute_pixel_metrics('/nonexistent/path.jpg')
        self.assertIsNone(result)


class TestOKLABInPaletteMetrics(unittest.TestCase):
    """Tests that calculate_palette_metrics uses OKLAB L for avg_lightness.

    avg_lightness should reflect OKLAB perceptual lightness, not HSL
    lightness. Yellow palettes are bright (~0.97) and blue palettes are
    moderate (~0.45) — matching human perception, with perceptual uniformity.
    """

    def test_yellow_palette_high_lightness(self):
        """All-yellow palette has high avg_lightness (OKLAB ≈ 0.97)."""
        from variety.smart_selection.palette import calculate_palette_metrics

        colors = {f'color{i}': '#FFFF00' for i in range(16)}
        result = calculate_palette_metrics(colors)

        # OKLAB L for yellow ≈ 0.968
        self.assertGreater(
            result['avg_lightness'], 0.9,
            f"Yellow palette should have high OKLAB lightness, got {result['avg_lightness']}"
        )

    def test_blue_palette_moderate_lightness(self):
        """All-blue palette has moderate avg_lightness (OKLAB ≈ 0.45)."""
        from variety.smart_selection.palette import calculate_palette_metrics

        colors = {f'color{i}': '#0000FF' for i in range(16)}
        result = calculate_palette_metrics(colors)

        # OKLAB L for blue ≈ 0.452
        self.assertLess(
            result['avg_lightness'], 0.5,
            f"Blue palette should be below mid-brightness in OKLAB, got {result['avg_lightness']}"
        )
        self.assertGreater(
            result['avg_lightness'], 0.3,
            f"Blue palette shouldn't be near-black in OKLAB, got {result['avg_lightness']}"
        )

    def test_yellow_vs_blue_discrimination(self):
        """Yellow and blue palettes have different avg_lightness.

        With HSL, both would have L=0.5. With OKLAB, yellow ≈ 0.97 and
        blue ≈ 0.45 — a difference of ~0.52.
        """
        from variety.smart_selection.palette import calculate_palette_metrics

        yellow = calculate_palette_metrics({f'color{i}': '#FFFF00' for i in range(16)})
        blue = calculate_palette_metrics({f'color{i}': '#0000FF' for i in range(16)})

        diff = yellow['avg_lightness'] - blue['avg_lightness']
        self.assertGreater(
            diff, 0.4,
            f"Yellow-blue lightness gap should be >0.4 with OKLAB, got {diff:.3f}. "
            f"If ~0.0, HSL lightness is still being used."
        )


class TestComputePixelMetrics(unittest.TestCase):
    """Tests for _compute_pixel_metrics — distribution-aware color signals."""

    def setUp(self):
        """Create temporary directory for test images."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _save_image(self, name, color, size=(100, 100)):
        """Create a solid-color test image."""
        path = os.path.join(self.temp_dir, name)
        img = Image.new('RGB', size, color=color)
        img.save(path)
        return path

    def _save_gradient(self, name, color_start, color_end, size=(100, 100)):
        """Create a horizontal gradient test image."""
        import numpy as np
        w, h = size
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for x in range(w):
            t = x / max(w - 1, 1)
            for c in range(3):
                arr[:, x, c] = int(color_start[c] * (1 - t) + color_end[c] * t)
        path = os.path.join(self.temp_dir, name)
        Image.fromarray(arr).save(path)
        return path

    def test_returns_all_expected_keys(self):
        """_compute_pixel_metrics returns all expected signal keys."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._save_image('red.jpg', '#FF4400')
        result = _compute_pixel_metrics(path)

        self.assertIsNotNone(result)
        expected_keys = [
            'perceived_brightness', 'brightness_p10', 'brightness_p90',
            'pixel_warm_ratio', 'pixel_chroma_median',
            'pixel_hue_entropy', 'pixel_dominant_hue', 'pixel_temperature',
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_warm_image_signals(self):
        """Red/orange image → high warm_ratio, positive temperature."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._save_image('warm.jpg', '#FF6600')
        result = _compute_pixel_metrics(path)

        self.assertGreater(result['pixel_warm_ratio'], 0.7)
        self.assertGreater(result['pixel_temperature'], 0.3)

    def test_cool_image_signals(self):
        """Blue image → low warm_ratio, negative temperature."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._save_image('cool.jpg', '#0066FF')
        result = _compute_pixel_metrics(path)

        self.assertLess(result['pixel_warm_ratio'], 0.3)
        self.assertLess(result['pixel_temperature'], -0.3)

    def test_grayscale_image_signals(self):
        """Grayscale image → low chroma, neutral warm_ratio."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._save_image('gray.jpg', '#808080')
        result = _compute_pixel_metrics(path)

        self.assertLess(result['pixel_chroma_median'], 0.02)
        # Neutral warm ratio for achromatic images
        self.assertAlmostEqual(result['pixel_warm_ratio'], 0.5, places=1)

    def test_rainbow_gradient_high_entropy(self):
        """Rainbow gradient → high hue entropy."""
        import numpy as np
        from variety.smart_selection.palette import _compute_pixel_metrics

        # Create a rainbow gradient: hue varies across width
        w, h = 360, 100
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for x in range(w):
            # Simple HSV to RGB for hue sweep (S=1, V=1)
            hue = x  # degrees
            c = 255
            x_val = int(c * (1 - abs((hue / 60) % 2 - 1)))
            if hue < 60:
                arr[:, x] = [c, x_val, 0]
            elif hue < 120:
                arr[:, x] = [x_val, c, 0]
            elif hue < 180:
                arr[:, x] = [0, c, x_val]
            elif hue < 240:
                arr[:, x] = [0, x_val, c]
            elif hue < 300:
                arr[:, x] = [x_val, 0, c]
            else:
                arr[:, x] = [c, 0, x_val]

        path = os.path.join(self.temp_dir, 'rainbow.jpg')
        Image.fromarray(arr).save(path)
        result = _compute_pixel_metrics(path)

        self.assertGreater(result['pixel_hue_entropy'], 1.5)

    def test_monochromatic_low_entropy(self):
        """Solid color → low hue entropy."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        path = self._save_image('mono.jpg', '#FF0000')
        result = _compute_pixel_metrics(path)

        self.assertLess(result['pixel_hue_entropy'], 0.5)

    def test_nonexistent_file_returns_none(self):
        """Non-existent file returns None."""
        from variety.smart_selection.palette import _compute_pixel_metrics

        result = _compute_pixel_metrics('/nonexistent/path.jpg')
        self.assertIsNone(result)


class TestPaletteSimilarityHSLBugFix(unittest.TestCase):
    """Tests for palette_similarity_hsl None-default bug fix.

    Previously, palettes without avg_* metrics defaulted to 0/0.5,
    making both palettes appear identical → similarity = 1.0.
    After the fix, missing metrics → similarity = 0.0 (unknown).
    """

    def test_both_palettes_missing_metrics_returns_zero(self):
        """Two palettes with only color0-15 (no avg_*) → 0.0, not 1.0."""
        from variety.smart_selection.palette import palette_similarity_hsl

        p1 = {'color0': '#ff0000', 'color1': '#00ff00'}
        p2 = {'color0': '#0000ff', 'color1': '#ffff00'}

        similarity = palette_similarity_hsl(p1, p2)
        self.assertEqual(similarity, 0.0)

    def test_one_palette_missing_metrics_returns_zero(self):
        """One palette with metrics, one without → 0.0."""
        from variety.smart_selection.palette import palette_similarity_hsl

        p1 = {'avg_hue': 30, 'avg_saturation': 0.8, 'avg_lightness': 0.5,
               'color_temperature': 0.7}
        p2 = {'color0': '#0000ff'}

        similarity = palette_similarity_hsl(p1, p2)
        self.assertEqual(similarity, 0.0)

    def test_both_have_metrics_returns_nonzero(self):
        """Both palettes with metrics → normal similarity (not 0.0)."""
        from variety.smart_selection.palette import palette_similarity_hsl

        p1 = {'avg_hue': 30, 'avg_saturation': 0.8, 'avg_lightness': 0.5,
               'color_temperature': 0.7}
        p2 = {'avg_hue': 35, 'avg_saturation': 0.75, 'avg_lightness': 0.55,
               'color_temperature': 0.6}

        similarity = palette_similarity_hsl(p1, p2)
        self.assertGreater(similarity, 0.8)


class TestPixelSimilarity(unittest.TestCase):
    """Tests for pixel_similarity — image pixel signals vs theme metrics."""

    def test_import(self):
        """pixel_similarity can be imported."""
        from variety.smart_selection.palette import pixel_similarity
        self.assertIsNotNone(pixel_similarity)

    def test_warm_image_warm_theme_high_score(self):
        """Warm image metrics vs warm theme → high score."""
        from variety.smart_selection.palette import pixel_similarity

        image = {
            'pixel_temperature': 0.8,
            'pixel_warm_ratio': 0.85,
            'pixel_chroma_median': 0.15,
            'pixel_hue_entropy': 0.5,
        }
        theme = {
            'color_temperature': 0.7,
            'avg_saturation': 0.6,
        }

        score = pixel_similarity(image, theme)
        self.assertGreater(score, 0.7)

    def test_warm_image_cool_theme_low_score(self):
        """Warm image metrics vs cool theme → low score (well below 0.5)."""
        from variety.smart_selection.palette import pixel_similarity

        image = {
            'pixel_temperature': 0.8,
            'pixel_warm_ratio': 0.85,
            'pixel_chroma_median': 0.15,
            'pixel_hue_entropy': 0.5,
        }
        theme = {
            'color_temperature': -0.7,
            'avg_saturation': 0.5,
        }

        score = pixel_similarity(image, theme)
        self.assertLess(score, 0.5)

    def test_cool_image_cool_theme_high_score(self):
        """Cool image metrics vs cool theme → high score."""
        from variety.smart_selection.palette import pixel_similarity

        image = {
            'pixel_temperature': -0.7,
            'pixel_warm_ratio': 0.15,
            'pixel_chroma_median': 0.12,
            'pixel_hue_entropy': 0.4,
        }
        theme = {
            'color_temperature': -0.6,
            'avg_saturation': 0.5,
        }

        score = pixel_similarity(image, theme)
        self.assertGreater(score, 0.7)

    def test_lakeside_scenario_rejects_warm_painting(self):
        """Warm painting vs cool Lakeside theme → score < 0.5 (hard fail).

        This is the core bug scenario: wallhaven-j5263m.jpg (warm amber/orange
        painting) was scoring 0.97 against Atelier Lakeside (cool blue-gray)
        due to wallust palette extraction bias.
        """
        from variety.smart_selection.palette import pixel_similarity

        # Simulate pixel signals for a warm amber/orange painting
        warm_painting = {
            'pixel_temperature': 0.75,
            'pixel_warm_ratio': 0.80,
            'pixel_chroma_median': 0.12,
            'pixel_hue_entropy': 0.8,
        }
        # Atelier Lakeside: cool blue-gray terminal theme
        lakeside = {
            'color_temperature': -0.5,
            'avg_saturation': 0.35,
        }

        score = pixel_similarity(warm_painting, lakeside)
        self.assertLess(score, 0.5,
                        f"Warm painting should NOT match cool Lakeside, got {score:.2f}")

    def test_missing_essential_signals_returns_zero(self):
        """Missing pixel_temperature or theme temperature → 0.0."""
        from variety.smart_selection.palette import pixel_similarity

        self.assertEqual(pixel_similarity({}, {'color_temperature': 0.5}), 0.0)
        self.assertEqual(pixel_similarity({'pixel_temperature': 0.5}, {}), 0.0)


class TestPaletteSimilarityPixelRouting(unittest.TestCase):
    """Tests that palette_similarity() routes to pixel_similarity when pixel_* exists."""

    def test_routes_to_pixel_similarity_when_pixel_signals_present(self):
        """palette_similarity auto-routes to pixel_similarity with pixel_* keys."""
        from variety.smart_selection.palette import palette_similarity

        image = {
            'pixel_temperature': 0.8,
            'pixel_warm_ratio': 0.85,
            'pixel_chroma_median': 0.15,
            'pixel_hue_entropy': 0.5,
        }
        theme = {
            'color_temperature': -0.7,
            'avg_saturation': 0.5,
            'avg_hue': 210,
            'avg_lightness': 0.4,
        }

        # Should use pixel_similarity path → low score (warm vs cool)
        score = palette_similarity(image, theme, use_oklab=False)
        self.assertLess(score, 0.5)

    def test_falls_back_to_hsl_without_pixel_signals(self):
        """palette_similarity uses HSL path when no pixel_* keys."""
        from variety.smart_selection.palette import palette_similarity

        p1 = {'avg_hue': 30, 'avg_saturation': 0.8, 'avg_lightness': 0.5,
               'color_temperature': 0.7}
        p2 = {'avg_hue': 35, 'avg_saturation': 0.75, 'avg_lightness': 0.55,
               'color_temperature': 0.6}

        score = palette_similarity(p1, p2, use_oklab=False)
        self.assertGreater(score, 0.8)


if __name__ == '__main__':
    unittest.main()
