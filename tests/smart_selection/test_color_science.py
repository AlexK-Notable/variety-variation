#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.color_science - Perceptual OKLAB color space utilities."""

import math
import unittest


class TestSRGBLinearConversion(unittest.TestCase):
    """Tests for sRGB to linear RGB conversion."""

    def test_import_srgb_to_linear(self):
        """srgb_to_linear can be imported from color_science module."""
        from variety.smart_selection.color_science import srgb_to_linear
        self.assertIsNotNone(srgb_to_linear)

    def test_import_linear_to_srgb(self):
        """linear_to_srgb can be imported from color_science module."""
        from variety.smart_selection.color_science import linear_to_srgb
        self.assertIsNotNone(linear_to_srgb)

    def test_srgb_to_linear_black(self):
        """Black (0) converts to linear 0."""
        from variety.smart_selection.color_science import srgb_to_linear
        self.assertAlmostEqual(srgb_to_linear(0.0), 0.0, places=6)

    def test_srgb_to_linear_white(self):
        """White (1) converts to linear 1."""
        from variety.smart_selection.color_science import srgb_to_linear
        self.assertAlmostEqual(srgb_to_linear(1.0), 1.0, places=6)

    def test_srgb_to_linear_mid_gray(self):
        """Mid-gray sRGB (0.5) converts to ~0.214 linear."""
        from variety.smart_selection.color_science import srgb_to_linear
        # sRGB 0.5 is perceptually mid-gray but linearly darker
        result = srgb_to_linear(0.5)
        self.assertAlmostEqual(result, 0.214, places=2)

    def test_linear_to_srgb_roundtrip(self):
        """Converting sRGB to linear and back gives same value."""
        from variety.smart_selection.color_science import srgb_to_linear, linear_to_srgb

        test_values = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
        for val in test_values:
            linear = srgb_to_linear(val)
            result = linear_to_srgb(linear)
            self.assertAlmostEqual(result, val, places=5,
                                   msg=f"Roundtrip failed for {val}")


class TestRGBToOKLAB(unittest.TestCase):
    """Tests for RGB to OKLAB conversion."""

    def test_import_rgb_to_oklab(self):
        """rgb_to_oklab can be imported from color_science module."""
        from variety.smart_selection.color_science import rgb_to_oklab
        self.assertIsNotNone(rgb_to_oklab)

    def test_black_oklab(self):
        """Black RGB (0,0,0) converts to OKLAB L=0."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(0, 0, 0)
        self.assertAlmostEqual(L, 0.0, places=4)
        self.assertAlmostEqual(a, 0.0, places=4)
        self.assertAlmostEqual(b, 0.0, places=4)

    def test_white_oklab(self):
        """White RGB (255,255,255) converts to OKLAB L=1."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(255, 255, 255)
        self.assertAlmostEqual(L, 1.0, places=3)
        self.assertAlmostEqual(a, 0.0, places=3)
        self.assertAlmostEqual(b, 0.0, places=3)

    def test_red_oklab(self):
        """Pure red has positive a (red-green axis)."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(255, 0, 0)
        self.assertGreater(a, 0)  # Red is positive on a-axis
        self.assertGreater(b, 0)  # Red leans toward yellow on b-axis

    def test_green_oklab(self):
        """Pure green has negative a (red-green axis)."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(0, 255, 0)
        self.assertLess(a, 0)  # Green is negative on a-axis

    def test_blue_oklab(self):
        """Pure blue has negative b (blue-yellow axis)."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(0, 0, 255)
        self.assertLess(b, 0)  # Blue is negative on b-axis

    def test_gray_oklab_neutral(self):
        """Gray colors have a and b near zero."""
        from variety.smart_selection.color_science import rgb_to_oklab

        # 50% gray
        L, a, b = rgb_to_oklab(128, 128, 128)
        self.assertAlmostEqual(a, 0.0, places=3)
        self.assertAlmostEqual(b, 0.0, places=3)
        # L should be around 0.59 for mid-gray
        self.assertGreater(L, 0.5)
        self.assertLess(L, 0.7)


class TestHexToOKLAB(unittest.TestCase):
    """Tests for hex color to OKLAB conversion."""

    def test_import_hex_to_oklab(self):
        """hex_to_oklab can be imported from color_science module."""
        from variety.smart_selection.color_science import hex_to_oklab
        self.assertIsNotNone(hex_to_oklab)

    def test_hex_to_oklab_black(self):
        """Black hex converts to OKLAB L=0."""
        from variety.smart_selection.color_science import hex_to_oklab

        L, a, b = hex_to_oklab("#000000")
        self.assertAlmostEqual(L, 0.0, places=4)

    def test_hex_to_oklab_white(self):
        """White hex converts to OKLAB L=1."""
        from variety.smart_selection.color_science import hex_to_oklab

        L, a, b = hex_to_oklab("#FFFFFF")
        self.assertAlmostEqual(L, 1.0, places=3)

    def test_hex_to_oklab_lowercase(self):
        """Handles lowercase hex colors."""
        from variety.smart_selection.color_science import hex_to_oklab

        L, a, b = hex_to_oklab("#ff0000")
        self.assertGreater(L, 0)  # Should parse successfully

    def test_hex_to_oklab_no_hash(self):
        """Handles hex colors without # prefix."""
        from variety.smart_selection.color_science import hex_to_oklab

        L1, a1, b1 = hex_to_oklab("#FF0000")
        L2, a2, b2 = hex_to_oklab("FF0000")
        self.assertAlmostEqual(L1, L2, places=6)
        self.assertAlmostEqual(a1, a2, places=6)
        self.assertAlmostEqual(b1, b2, places=6)


class TestOKLABDistance(unittest.TestCase):
    """Tests for OKLAB color distance calculation."""

    def test_import_oklab_distance(self):
        """oklab_distance can be imported from color_science module."""
        from variety.smart_selection.color_science import oklab_distance
        self.assertIsNotNone(oklab_distance)

    def test_black_white_maximum_distance(self):
        """Black and white have maximum distance (L difference of 1)."""
        from variety.smart_selection.color_science import rgb_to_oklab, oklab_distance

        black = rgb_to_oklab(0, 0, 0)
        white = rgb_to_oklab(255, 255, 255)

        distance = oklab_distance(black, white)
        # Distance should be approximately 1.0 (only L differs)
        self.assertAlmostEqual(distance, 1.0, places=2)

    def test_identical_colors_zero_distance(self):
        """Identical colors have zero distance."""
        from variety.smart_selection.color_science import rgb_to_oklab, oklab_distance

        red = rgb_to_oklab(255, 0, 0)
        distance = oklab_distance(red, red)
        self.assertAlmostEqual(distance, 0.0, places=6)

    def test_similar_colors_close_distance(self):
        """Similar greens have small distance."""
        from variety.smart_selection.color_science import rgb_to_oklab, oklab_distance

        green1 = rgb_to_oklab(0, 200, 0)
        green2 = rgb_to_oklab(0, 210, 0)

        distance = oklab_distance(green1, green2)
        # Similar colors should have small distance
        self.assertLess(distance, 0.05)

    def test_distance_symmetry(self):
        """Distance is symmetric: d(a,b) == d(b,a)."""
        from variety.smart_selection.color_science import rgb_to_oklab, oklab_distance

        color1 = rgb_to_oklab(100, 50, 200)
        color2 = rgb_to_oklab(200, 100, 50)

        d1 = oklab_distance(color1, color2)
        d2 = oklab_distance(color2, color1)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_perceptual_uniformity(self):
        """Equal RGB steps give approximately equal OKLAB distances.

        This is a key property of OKLAB - perceptual uniformity means
        equal numeric distances correspond to equal perceived differences.
        """
        from variety.smart_selection.color_science import rgb_to_oklab, oklab_distance

        # Compare distances between consecutive grays
        # In a perceptually uniform space, these should be similar
        gray_50 = rgb_to_oklab(50, 50, 50)
        gray_100 = rgb_to_oklab(100, 100, 100)
        gray_150 = rgb_to_oklab(150, 150, 150)
        gray_200 = rgb_to_oklab(200, 200, 200)

        d1 = oklab_distance(gray_50, gray_100)
        d2 = oklab_distance(gray_100, gray_150)
        d3 = oklab_distance(gray_150, gray_200)

        # The distances should be similar (within 50% of each other)
        # This is much better than sRGB where high values are compressed
        avg = (d1 + d2 + d3) / 3
        self.assertLess(abs(d1 - avg) / avg, 0.5)
        self.assertLess(abs(d2 - avg) / avg, 0.5)
        self.assertLess(abs(d3 - avg) / avg, 0.5)


class TestPaletteSimilarityOKLAB(unittest.TestCase):
    """Tests for palette similarity using OKLAB color space."""

    def test_import_palette_similarity_oklab(self):
        """palette_similarity_oklab can be imported from color_science module."""
        from variety.smart_selection.color_science import palette_similarity_oklab
        self.assertIsNotNone(palette_similarity_oklab)

    def test_identical_palettes_similarity_one(self):
        """Identical palettes have similarity of 1.0."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        palette = {
            'colors': ['#FF0000', '#00FF00', '#0000FF', '#FFFF00',
                       '#FF00FF', '#00FFFF', '#FFFFFF', '#000000']
        }

        similarity = palette_similarity_oklab(palette, palette)
        self.assertAlmostEqual(similarity, 1.0, places=4)

    def test_similarity_symmetric(self):
        """Similarity is symmetric: sim(a,b) == sim(b,a)."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        palette1 = {'colors': ['#FF0000', '#00FF00', '#0000FF']}
        palette2 = {'colors': ['#FF5500', '#00FF55', '#0055FF']}

        sim1 = palette_similarity_oklab(palette1, palette2)
        sim2 = palette_similarity_oklab(palette2, palette1)
        self.assertAlmostEqual(sim1, sim2, places=4)

    def test_similar_palettes_high_similarity(self):
        """Similar palettes have high similarity score."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        palette1 = {'colors': ['#FF0000', '#00FF00', '#0000FF']}
        palette2 = {'colors': ['#FF1010', '#10FF10', '#1010FF']}

        similarity = palette_similarity_oklab(palette1, palette2)
        self.assertGreater(similarity, 0.9)

    def test_opposite_palettes_low_similarity(self):
        """Very different palettes have low similarity."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        # Bright saturated colors
        palette1 = {'colors': ['#FF0000', '#00FF00', '#0000FF']}
        # Muted gray colors
        palette2 = {'colors': ['#808080', '#909090', '#707070']}

        similarity = palette_similarity_oklab(palette1, palette2)
        self.assertLess(similarity, 0.7)

    def test_empty_palette_returns_zero(self):
        """Empty palettes return 0 similarity."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        palette1 = {'colors': []}
        palette2 = {'colors': ['#FF0000']}

        similarity = palette_similarity_oklab(palette1, palette2)
        self.assertEqual(similarity, 0.0)

    def test_none_palette_returns_zero(self):
        """None palettes return 0 similarity."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        palette = {'colors': ['#FF0000', '#00FF00']}

        self.assertEqual(palette_similarity_oklab(None, palette), 0.0)
        self.assertEqual(palette_similarity_oklab(palette, None), 0.0)
        self.assertEqual(palette_similarity_oklab(None, None), 0.0)

    def test_different_length_palettes(self):
        """Handles palettes of different lengths."""
        from variety.smart_selection.color_science import palette_similarity_oklab

        palette1 = {'colors': ['#FF0000', '#00FF00', '#0000FF']}
        palette2 = {'colors': ['#FF0000', '#00FF00']}

        # Should not crash, should return a valid similarity
        similarity = palette_similarity_oklab(palette1, palette2)
        self.assertGreaterEqual(similarity, 0.0)
        self.assertLessEqual(similarity, 1.0)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_pure_colors_conversion(self):
        """Primary and secondary colors convert correctly."""
        from variety.smart_selection.color_science import hex_to_oklab

        # Test all primary/secondary colors don't crash
        colors = ['#FF0000', '#00FF00', '#0000FF',
                  '#FFFF00', '#FF00FF', '#00FFFF',
                  '#FFFFFF', '#000000']

        for color in colors:
            L, a, b = hex_to_oklab(color)
            # L should be between 0 and 1
            self.assertGreaterEqual(L, 0.0)
            self.assertLessEqual(L, 1.0)
            # a and b should be finite
            self.assertTrue(math.isfinite(a))
            self.assertTrue(math.isfinite(b))

    def test_near_black_colors(self):
        """Very dark colors convert without issues."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(1, 1, 1)
        self.assertGreater(L, 0)
        self.assertTrue(math.isfinite(a))
        self.assertTrue(math.isfinite(b))

    def test_near_white_colors(self):
        """Very bright colors convert without issues."""
        from variety.smart_selection.color_science import rgb_to_oklab

        L, a, b = rgb_to_oklab(254, 254, 254)
        self.assertLess(L, 1.0)
        self.assertTrue(math.isfinite(a))
        self.assertTrue(math.isfinite(b))


class TestColorDistance(unittest.TestCase):
    """Tests for single color distance helper."""

    def test_import_color_distance_oklab(self):
        """color_distance_oklab can be imported."""
        from variety.smart_selection.color_science import color_distance_oklab
        self.assertIsNotNone(color_distance_oklab)

    def test_color_distance_identical(self):
        """Identical hex colors have zero distance."""
        from variety.smart_selection.color_science import color_distance_oklab

        distance = color_distance_oklab('#FF0000', '#FF0000')
        self.assertAlmostEqual(distance, 0.0, places=6)

    def test_color_distance_black_white(self):
        """Black and white have distance ~1.0."""
        from variety.smart_selection.color_science import color_distance_oklab

        distance = color_distance_oklab('#000000', '#FFFFFF')
        self.assertAlmostEqual(distance, 1.0, places=2)


if __name__ == '__main__':
    unittest.main()
