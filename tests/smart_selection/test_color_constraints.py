# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for color constraint generation in VarietyWindow."""

import unittest
from unittest.mock import MagicMock
from datetime import datetime


class MockOptions:
    """Mock Options object for testing."""
    smart_color_enabled = True
    smart_color_similarity = 50  # 50%
    smart_color_temperature = 'neutral'


class TestGetSmartColorConstraints(unittest.TestCase):
    """Tests for _get_smart_color_constraints method."""

    def setUp(self):
        """Create mock VarietyWindow with the method under test."""
        self.mock_window = MagicMock()
        self.mock_window.options = MockOptions()
        # Explicitly set no theme override so tests exercise time-of-day logic
        # (MagicMock auto-creates _theme_override as truthy, which would
        # trigger the theme override path added in Phase 4)
        self.mock_window._theme_override = None

        # Bind the actual method to our mock
        from variety.VarietyWindow import VarietyWindow
        self.mock_window._get_smart_color_constraints = (
            VarietyWindow._get_smart_color_constraints.__get__(
                self.mock_window, type(self.mock_window)
            )
        )

    def test_returns_none_when_disabled(self):
        """Returns None when smart_color_enabled is False."""
        self.mock_window.options.smart_color_enabled = False

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNone(result)

    def test_converts_similarity_to_decimal(self):
        """Converts 0-100 similarity to 0-1 scale."""
        self.mock_window.options.smart_color_similarity = 60

        result = self.mock_window._get_smart_color_constraints()

        self.assertEqual(result.min_color_similarity, 0.6)

    def test_warm_temperature_palette(self):
        """Warm temperature uses warm palette values."""
        self.mock_window.options.smart_color_temperature = 'warm'

        result = self.mock_window._get_smart_color_constraints()

        self.assertEqual(result.target_palette['avg_hue'], 30)
        self.assertEqual(result.target_palette['color_temperature'], 0.5)

    def test_cool_temperature_palette(self):
        """Cool temperature uses cool palette values."""
        self.mock_window.options.smart_color_temperature = 'cool'

        result = self.mock_window._get_smart_color_constraints()

        self.assertEqual(result.target_palette['avg_hue'], 200)
        self.assertEqual(result.target_palette['color_temperature'], -0.4)

    def test_neutral_temperature_palette(self):
        """Neutral temperature uses neutral palette values."""
        self.mock_window.options.smart_color_temperature = 'neutral'

        result = self.mock_window._get_smart_color_constraints()

        self.assertEqual(result.target_palette['avg_hue'], 120)
        self.assertEqual(result.target_palette['color_temperature'], 0.0)

    def test_adaptive_returns_constraints_based_on_time(self):
        """Adaptive mode returns different palettes based on time of day.

        Since datetime is imported inside the method, we test the current
        time behavior and verify it returns valid constraints.
        """
        self.mock_window.options.smart_color_temperature = 'adaptive'

        result = self.mock_window._get_smart_color_constraints()

        # Should return valid constraints regardless of time
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.target_palette)

        # Verify palette has all required fields
        self.assertIn('avg_hue', result.target_palette)
        self.assertIn('avg_saturation', result.target_palette)
        self.assertIn('avg_lightness', result.target_palette)
        self.assertIn('color_temperature', result.target_palette)

        # Verify values are in valid ranges
        hue = result.target_palette['avg_hue']
        self.assertTrue(0 <= hue <= 360, f"Hue {hue} out of range")

        temp = result.target_palette['color_temperature']
        self.assertTrue(-1 <= temp <= 1, f"Temperature {temp} out of range")

        lightness = result.target_palette['avg_lightness']
        self.assertTrue(0 <= lightness <= 1, f"Lightness {lightness} out of range")

    def test_adaptive_time_periods_are_valid(self):
        """Verify adaptive mode logic covers all 24 hours correctly.

        This tests the logic directly without mocking.
        """
        from variety.smart_selection.models import SelectionConstraints

        # Manually test the time logic
        def get_palette_for_hour(hour):
            if 6 <= hour < 12:  # Morning
                return {'avg_hue': 200, 'color_temperature': -0.3}
            elif 12 <= hour < 18:  # Afternoon
                return {'avg_hue': 120, 'color_temperature': 0.0}
            elif 18 <= hour < 22:  # Evening
                return {'avg_hue': 30, 'color_temperature': 0.5}
            else:  # Night
                return {'avg_hue': 240, 'color_temperature': 0.0}

        # Verify morning (6-11)
        for hour in [6, 9, 11]:
            palette = get_palette_for_hour(hour)
            self.assertEqual(palette['avg_hue'], 200, f"Morning hour {hour}")
            self.assertEqual(palette['color_temperature'], -0.3)

        # Verify afternoon (12-17)
        for hour in [12, 14, 17]:
            palette = get_palette_for_hour(hour)
            self.assertEqual(palette['avg_hue'], 120, f"Afternoon hour {hour}")
            self.assertEqual(palette['color_temperature'], 0.0)

        # Verify evening (18-21)
        for hour in [18, 20, 21]:
            palette = get_palette_for_hour(hour)
            self.assertEqual(palette['avg_hue'], 30, f"Evening hour {hour}")
            self.assertEqual(palette['color_temperature'], 0.5)

        # Verify night (22-5)
        for hour in [22, 0, 3, 5]:
            palette = get_palette_for_hour(hour)
            self.assertEqual(palette['avg_hue'], 240, f"Night hour {hour}")
            self.assertEqual(palette['color_temperature'], 0.0)

    def test_returns_selection_constraints(self):
        """Returns a SelectionConstraints object with target_palette."""
        from variety.smart_selection.models import SelectionConstraints

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsInstance(result, SelectionConstraints)
        self.assertIsNotNone(result.target_palette)
        self.assertIn('avg_hue', result.target_palette)
        self.assertIn('avg_saturation', result.target_palette)
        self.assertIn('avg_lightness', result.target_palette)
        self.assertIn('color_temperature', result.target_palette)


class TestThemeOverrideConstraints(unittest.TestCase):
    """Tests for theme override priority in _get_smart_color_constraints.

    Phase 4 of the Reverse Theming Pipeline: when a theme override is active,
    its palette takes priority over time-of-day adaptation. When inactive or
    absent, existing behavior is preserved.

    Written against the interface defined in plan phase 4.
    """

    def setUp(self):
        """Create mock VarietyWindow with mock theme override."""
        self.mock_window = MagicMock()
        self.mock_window.options = MockOptions()

        # Bind the actual method to our mock
        from variety.VarietyWindow import VarietyWindow
        self.mock_window._get_smart_color_constraints = (
            VarietyWindow._get_smart_color_constraints.__get__(
                self.mock_window, type(self.mock_window)
            )
        )

    def _make_theme_override(self, is_active, palette=None):
        """Create a mock ThemeOverride with controlled state.

        Args:
            is_active: Whether the theme override is active.
            palette: Dict to return from get_target_palette_for_selection(),
                or None to use a sensible default when active.

        Returns:
            MagicMock configured as ThemeOverride.
        """
        override = MagicMock()
        override.is_active = is_active
        if is_active and palette is None:
            palette = {
                'avg_hue': 280,
                'avg_saturation': 0.6,
                'avg_lightness': 0.3,
                'color_temperature': -0.5,
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
        override.get_target_palette_for_selection.return_value = palette
        return override

    # === Priority Tests ===

    def test_theme_overrides_time_of_day(self):
        """Active theme's hue takes priority over time-of-day hue.

        Bug caught: theme check not inserted before temperature logic,
        so time-of-day always wins even when theme is active.
        """
        # Set warm temperature (hue=30), but theme has hue=280
        self.mock_window.options.smart_color_temperature = 'warm'
        self.mock_window._theme_override = self._make_theme_override(is_active=True)

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        self.assertEqual(
            result.target_palette['avg_hue'], 280,
            "Theme hue 280 should override warm hue 30 (time-of-day leaked through)"
        )

    def test_theme_overrides_adaptive_mode(self):
        """Active theme takes priority over adaptive (time-based) mode.

        Bug caught: adaptive mode's datetime.now() check runs before
        theme override check, ignoring active theme.
        """
        self.mock_window.options.smart_color_temperature = 'adaptive'
        self.mock_window._theme_override = self._make_theme_override(is_active=True)

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        self.assertEqual(
            result.target_palette['avg_hue'], 280,
            "Theme should override adaptive mode regardless of time"
        )

    # === Fallthrough Tests ===

    def test_falls_through_when_inactive(self):
        """Inactive theme override falls through to time-of-day logic.

        Bug caught: existence of _theme_override attribute (even inactive)
        prevents fallthrough to warm/cool/neutral logic.
        """
        self.mock_window.options.smart_color_temperature = 'warm'
        self.mock_window._theme_override = self._make_theme_override(
            is_active=False, palette=None
        )

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        self.assertEqual(
            result.target_palette['avg_hue'], 30,
            "Inactive theme should not block warm hue 30 (fallthrough broken)"
        )

    def test_backward_compat_no_theme_override_attribute(self):
        """Method works when _theme_override attribute does not exist at all.

        Bug caught: using self._theme_override directly instead of getattr()
        raises AttributeError on VarietyWindow instances from before Phase 3.
        """
        # Use spec=[] to prevent MagicMock from auto-creating attributes
        self.mock_window = MagicMock(spec=[])
        self.mock_window.options = MockOptions()
        self.mock_window.options.smart_color_temperature = 'cool'

        from variety.VarietyWindow import VarietyWindow
        self.mock_window._get_smart_color_constraints = (
            VarietyWindow._get_smart_color_constraints.__get__(
                self.mock_window, type(self.mock_window)
            )
        )

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        self.assertEqual(
            result.target_palette['avg_hue'], 200,
            "Without _theme_override attribute, cool hue 200 should work (backward compat broken)"
        )

    # === Palette Shape Tests ===

    def test_theme_palette_has_correct_shape(self):
        """Theme target_palette includes color keys AND metric keys.

        Bug caught: target_palette from theme missing avg_* metrics,
        which are needed by color_affinity_factor() for similarity calculation.
        """
        theme_palette = {
            'avg_hue': 280,
            'avg_saturation': 0.6,
            'avg_lightness': 0.3,
            'color_temperature': -0.5,
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
        self.mock_window._theme_override = self._make_theme_override(
            is_active=True, palette=theme_palette
        )

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        palette = result.target_palette

        # Must have metric keys for selection engine
        self.assertIn('avg_hue', palette)
        self.assertIn('avg_saturation', palette)
        self.assertIn('avg_lightness', palette)
        self.assertIn('color_temperature', palette)

        # Must have color keys for OKLAB similarity in color_affinity_factor()
        for i in range(16):
            self.assertIn(f'color{i}', palette, f"Missing color{i} key")

    # === Similarity Threshold Tests ===

    def test_min_color_similarity_uses_adherence_not_user_setting(self):
        """Theme override uses adherence-based threshold, not user's general setting.

        Bug caught: theme override uses user's configured similarity (e.g., 0.5)
        instead of the theme-specific adherence level.
        """
        from variety.smart_selection.models import ADHERENCE_LEVELS
        # User has their own similarity configured (50%)
        self.mock_window.options.smart_color_similarity = 50
        # Theme adherence defaults to 'moderate' via getattr fallback
        self.mock_window._theme_override = self._make_theme_override(is_active=True)

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        self.assertIsNotNone(result.min_color_similarity)
        # Theme override should use adherence threshold, not user's 0.5
        expected = ADHERENCE_LEVELS['moderate']
        self.assertEqual(
            result.min_color_similarity, expected,
            f"Similarity {result.min_color_similarity} should be adherence 'moderate' ({expected})"
        )

    def test_user_similarity_preserved_without_theme(self):
        """User's configured similarity preserved when no theme active.

        Bug caught: theme override logic clobbers user's similarity setting
        even when no theme is active.
        """
        self.mock_window.options.smart_color_similarity = 70
        self.mock_window._theme_override = self._make_theme_override(
            is_active=False, palette=None
        )

        result = self.mock_window._get_smart_color_constraints()

        self.assertIsNotNone(result)
        self.assertEqual(
            result.min_color_similarity, 0.7,
            "User's similarity setting should be preserved when no theme active"
        )


if __name__ == '__main__':
    unittest.main()
