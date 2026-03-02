# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for filtering_options_changed() detecting smart selection changes.

Verifies that changing smart color settings (mode, temperature, similarity,
theme, adherence) triggers queue refresh via filtering_options_changed().

Without these tests, someone could remove the smart_color_* checks from
filtering_options_changed() and the queue-refresh-on-settings-change
feature would silently break — users would have to wait for the buffer
to drain before new settings take effect.
"""

import unittest
from unittest.mock import MagicMock


class MockOptions:
    """Minimal Options mock with all fields filtering_options_changed() checks."""
    # Legacy fields
    safe_mode = False
    desired_color_enabled = False
    desired_color = None
    lightness_enabled = False
    lightness_mode = 'dark'
    min_rating_enabled = False
    min_rating = 4
    min_size_enabled = False
    min_size = 0
    use_landscape_enabled = False
    name_regex_enabled = False
    name_regex = ''

    # Smart selection fields
    smart_color_enabled = True
    smart_color_mode = 'adaptive'
    smart_color_temperature = 'neutral'
    smart_color_similarity = 50
    smart_active_theme_id = None
    smart_theme_adherence = 'moderate'


def _make_window(previous_opts, current_opts):
    """Create a mock VarietyWindow with the real filtering_options_changed bound."""
    from variety.VarietyWindow import VarietyWindow

    mock_window = MagicMock()
    mock_window.previous_options = previous_opts
    mock_window.options = current_opts

    # Bind real methods
    mock_window.filtering_options_changed = (
        VarietyWindow.filtering_options_changed.__get__(
            mock_window, type(mock_window)
        )
    )
    mock_window.size_options_changed = (
        VarietyWindow.size_options_changed.__get__(
            mock_window, type(mock_window)
        )
    )
    return mock_window


def _make_option_pair(**changes):
    """Create previous/current Options pairs differing only in specified fields.

    Returns (previous_options, current_options) where previous has defaults
    and current has the specified overrides applied.
    """
    prev = MockOptions()
    curr = MockOptions()
    for key, value in changes.items():
        setattr(curr, key, value)
    return prev, curr


class TestFilteringOptionsDetectsSmartChanges(unittest.TestCase):
    """Each smart selection field must trigger filtering_options_changed()."""

    def test_no_change_returns_false(self):
        """Baseline: identical options returns False."""
        prev, curr = _make_option_pair()
        window = _make_window(prev, curr)
        self.assertFalse(window.filtering_options_changed())

    def test_smart_color_enabled_change(self):
        """Toggling smart_color_enabled triggers refresh."""
        prev, curr = _make_option_pair(smart_color_enabled=False)
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Changing smart_color_enabled should trigger queue refresh"
        )

    def test_smart_color_mode_change(self):
        """Switching from adaptive to theme triggers refresh."""
        prev, curr = _make_option_pair(smart_color_mode='theme')
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Changing smart_color_mode should trigger queue refresh"
        )

    def test_smart_color_temperature_change(self):
        """Changing temperature from neutral to warm triggers refresh."""
        prev, curr = _make_option_pair(smart_color_temperature='warm')
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Changing smart_color_temperature should trigger queue refresh"
        )

    def test_smart_color_similarity_change(self):
        """Changing similarity threshold triggers refresh."""
        prev, curr = _make_option_pair(smart_color_similarity=80)
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Changing smart_color_similarity should trigger queue refresh"
        )

    def test_smart_active_theme_id_change(self):
        """Activating a theme triggers refresh."""
        prev, curr = _make_option_pair(smart_active_theme_id='tokyo-night')
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Changing smart_active_theme_id should trigger queue refresh"
        )

    def test_smart_theme_adherence_change(self):
        """Changing adherence from moderate to strict triggers refresh."""
        prev, curr = _make_option_pair(smart_theme_adherence='strict')
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Changing smart_theme_adherence should trigger queue refresh"
        )

    def test_only_smart_change_still_triggers(self):
        """Smart changes trigger even when all legacy options are identical."""
        prev, curr = _make_option_pair(smart_color_mode='theme')
        # Explicitly ensure legacy fields match
        prev.desired_color_enabled = True
        curr.desired_color_enabled = True
        prev.desired_color = '#FF0000'
        curr.desired_color = '#FF0000'
        window = _make_window(prev, curr)
        self.assertTrue(
            window.filtering_options_changed(),
            "Smart color mode change should trigger even when legacy options match"
        )


if __name__ == '__main__':
    unittest.main()
