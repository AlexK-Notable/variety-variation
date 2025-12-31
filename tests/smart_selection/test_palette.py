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


if __name__ == '__main__':
    unittest.main()
