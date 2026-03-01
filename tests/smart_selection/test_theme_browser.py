# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for Phase 5: Theme Browser UI - Widget types, smoke tests, page constants.

Written against the interface defined in plan phase 5: Theme Browser UI.
Tests verify widget types, method signatures, and page index constants.
GTK widget tests are intentionally thin -- 2 smoke tests per the test strategy.
Full visual testing requires a display server and human inspection.

Phase Reference: Reverse Theming Pipeline, Phase 5
Gate Reference: Verification Gate Phase 5
"""

import os
import unittest
from unittest.mock import MagicMock, patch

# GTK display detection -- tests that instantiate widgets need a display server.
# Detect once at module level to avoid repeated checks.
_HAS_DISPLAY = False
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk
    _display = Gdk.Display.get_default()
    _HAS_DISPLAY = _display is not None
except Exception:
    pass


def _make_test_palette():
    """Create a valid 16-color terminal palette dict for testing.

    Returns a dict with color0-15, background, foreground, and cursor keys.
    This is the same format used throughout the smart_selection pipeline.
    """
    return {
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


# =============================================================================
# Import Tests -- These do NOT require a display server
# =============================================================================

class TestThemeBrowserImports(unittest.TestCase):
    """Verify that Phase 5 modules are importable and expose expected classes.

    Bug caught: Module not created, classes not exported, import path wrong.
    """

    def test_theme_browser_page_importable(self):
        """ThemeBrowserPage can be imported from variety.ThemeBrowserPage."""
        from variety.ThemeBrowserPage import ThemeBrowserPage
        self.assertIsNotNone(ThemeBrowserPage)

    def test_terminal_preview_widget_importable(self):
        """TerminalPreviewWidget can be imported from variety.TerminalPreviewWidget."""
        from variety.TerminalPreviewWidget import TerminalPreviewWidget
        self.assertIsNotNone(TerminalPreviewWidget)


# =============================================================================
# Type Hierarchy Tests -- Require GTK but not instantiation
# =============================================================================

@unittest.skipUnless(_HAS_DISPLAY, "No display server available for GTK tests")
class TestWidgetTypes(unittest.TestCase):
    """Verify that UI widgets inherit from the correct GTK base classes.

    The plan specifies:
    - ThemeBrowserPage is a Gtk.Box (or Gtk container widget)
    - TerminalPreviewWidget is a Gtk.DrawingArea
    - ColorSwatchGrid (if present) is a Gtk.Grid

    Bug caught: Widget subclasses wrong GTK parent, breaking layout expectations.
    """

    def test_theme_browser_page_is_gtk_container(self):
        """ThemeBrowserPage must be a GTK container widget (Box, Paned, etc).

        The gate allows any of: Gtk.Box, Gtk.Paned, Gtk.Frame,
        Gtk.ScrolledWindow, Gtk.Grid.
        """
        from variety.ThemeBrowserPage import ThemeBrowserPage
        allowed_containers = (Gtk.Box, Gtk.Paned, Gtk.Frame,
                              Gtk.ScrolledWindow, Gtk.Grid)
        self.assertTrue(
            issubclass(ThemeBrowserPage, allowed_containers),
            f"ThemeBrowserPage must be a GTK container, "
            f"got MRO: {ThemeBrowserPage.__mro__}"
        )

    def test_terminal_preview_widget_is_drawing_area(self):
        """TerminalPreviewWidget must be a Gtk.DrawingArea for Cairo rendering."""
        from variety.TerminalPreviewWidget import TerminalPreviewWidget
        self.assertTrue(
            issubclass(TerminalPreviewWidget, Gtk.DrawingArea),
            f"TerminalPreviewWidget must be a Gtk.DrawingArea, "
            f"got MRO: {TerminalPreviewWidget.__mro__}"
        )


# =============================================================================
# Widget Smoke Tests -- Require display server for instantiation
# =============================================================================

@unittest.skipUnless(_HAS_DISPLAY, "No display server available for GTK tests")
class TestTerminalPreviewWidgetSmoke(unittest.TestCase):
    """Smoke tests for TerminalPreviewWidget instantiation and set_palette().

    These tests verify that the widget can be created and configured without
    crashing. They do NOT test visual rendering (which requires human eyes).

    Bug caught: Widget constructor crashes, set_palette rejects valid palette,
    palette key mismatch between theme pipeline and widget.
    """

    def test_instantiation_no_crash(self):
        """TerminalPreviewWidget can be instantiated without arguments."""
        from variety.TerminalPreviewWidget import TerminalPreviewWidget
        widget = TerminalPreviewWidget()
        self.assertIsInstance(widget, Gtk.DrawingArea)

    def test_set_palette_accepts_valid_palette(self):
        """set_palette() accepts a standard 16-color palette dict without error.

        Uses the same palette dict format as the rest of the smart_selection
        pipeline (color0-15, background, foreground, cursor).
        """
        from variety.TerminalPreviewWidget import TerminalPreviewWidget
        widget = TerminalPreviewWidget()
        palette = _make_test_palette()
        # Should not raise
        widget.set_palette(palette)

    def test_set_palette_with_all_red(self):
        """set_palette() accepts a palette where all colors are the same."""
        from variety.TerminalPreviewWidget import TerminalPreviewWidget
        widget = TerminalPreviewWidget()
        palette = {f'color{i}': '#FF0000' for i in range(16)}
        palette['background'] = '#000000'
        palette['foreground'] = '#FFFFFF'
        palette['cursor'] = '#FFFFFF'
        widget.set_palette(palette)


@unittest.skipUnless(_HAS_DISPLAY, "No display server available for GTK tests")
class TestThemeBrowserPageSmoke(unittest.TestCase):
    """Smoke tests for ThemeBrowserPage instantiation.

    Bug caught: Constructor crashes due to missing GTK widget setup,
    theme library dependency not handled, button signal wiring fails.
    """

    def test_instantiation_no_crash(self):
        """ThemeBrowserPage can be instantiated without crashing.

        The gate requires this to print 'CONSTRUCT OK' -- meaning the
        constructor must complete successfully.
        """
        from variety.ThemeBrowserPage import ThemeBrowserPage
        page = ThemeBrowserPage()
        self.assertIsNotNone(page)


# =============================================================================
# Page Index Constant Tests -- Pure Python, no display needed
# =============================================================================

class TestPageIndexConstants(unittest.TestCase):
    """Verify notebook page index constants in PreferencesVarietyDialog.

    Phase 5 inserts a new theme browser page at index 8 (after Smart Selection
    at index 7), which shifts DONATE_PAGE_INDEX from 11 to 12. Other constants
    must remain unchanged.

    Bug caught: Page index not updated after insertion, breaking donation page
    navigation or smart selection tab switching.
    """

    def test_donate_page_index_updated_to_12(self):
        """DONATE_PAGE_INDEX must be 12 after theme browser page insertion.

        Previously 11, incremented by 1 due to new page at index 8.
        """
        from variety.PreferencesVarietyDialog import DONATE_PAGE_INDEX
        self.assertEqual(
            DONATE_PAGE_INDEX, 12,
            f"Expected DONATE_PAGE_INDEX=12 after theme page insertion, "
            f"got {DONATE_PAGE_INDEX}"
        )

    def test_smart_selection_page_index_unchanged(self):
        """SMART_SELECTION_PAGE_INDEX must remain 7 (before theme browser).

        The theme browser page is inserted AFTER smart selection, so this
        index must not change.
        """
        from variety.PreferencesVarietyDialog import SMART_SELECTION_PAGE_INDEX
        self.assertEqual(
            SMART_SELECTION_PAGE_INDEX, 7,
            f"Expected SMART_SELECTION_PAGE_INDEX=7 (unchanged), "
            f"got {SMART_SELECTION_PAGE_INDEX}"
        )

    def test_slideshow_page_index_unchanged(self):
        """SLIDESHOW_PAGE_INDEX must remain 4 (well before theme browser).

        This index is used for removing the slideshow page when disabled.
        It must not change.
        """
        from variety.PreferencesVarietyDialog import SLIDESHOW_PAGE_INDEX
        self.assertEqual(
            SLIDESHOW_PAGE_INDEX, 4,
            f"Expected SLIDESHOW_PAGE_INDEX=4 (unchanged), "
            f"got {SLIDESHOW_PAGE_INDEX}"
        )


# =============================================================================
# Action Button Tests -- Verify UI wiring without full interaction
# =============================================================================

@unittest.skipUnless(_HAS_DISPLAY, "No display server available for GTK tests")
class TestThemeBrowserActions(unittest.TestCase):
    """Verify that ThemeBrowserPage has apply and clear override functionality.

    Per the plan, ThemeBrowserPage must have:
    - Apply button that calls ThemeOverride.activate()
    - Clear Override button that calls ThemeOverride.deactivate()
    - Refresh button that triggers re-import from Zed extensions

    These tests check that the page exposes these capabilities, not that
    the buttons render correctly (which requires visual inspection).

    Bug caught: Button not created, signal not connected, method missing.
    """

    def _make_page(self):
        """Create a ThemeBrowserPage for testing."""
        from variety.ThemeBrowserPage import ThemeBrowserPage
        return ThemeBrowserPage()

    def test_has_apply_method_or_handler(self):
        """ThemeBrowserPage has apply functionality.

        The page must have some way to trigger theme application, either
        through a public method or internally via button signals.
        """
        page = self._make_page()
        # Check for any of the likely apply method names
        has_apply = (
            hasattr(page, 'on_apply_clicked') or
            hasattr(page, '_on_apply_clicked') or
            hasattr(page, 'apply_theme') or
            hasattr(page, '_apply_theme')
        )
        self.assertTrue(
            has_apply,
            "ThemeBrowserPage must have apply functionality "
            "(on_apply_clicked, apply_theme, or similar)"
        )

    def test_has_clear_method_or_handler(self):
        """ThemeBrowserPage has clear override functionality.

        The page must have some way to clear/deactivate the active theme.
        """
        page = self._make_page()
        has_clear = (
            hasattr(page, 'on_clear_clicked') or
            hasattr(page, '_on_clear_clicked') or
            hasattr(page, 'clear_override') or
            hasattr(page, '_clear_override')
        )
        self.assertTrue(
            has_clear,
            "ThemeBrowserPage must have clear override functionality "
            "(on_clear_clicked, clear_override, or similar)"
        )

    def test_has_refresh_method_or_handler(self):
        """ThemeBrowserPage has refresh/reimport functionality.

        The page must have some way to trigger re-scanning of Zed extensions.
        """
        page = self._make_page()
        has_refresh = (
            hasattr(page, 'on_refresh_clicked') or
            hasattr(page, '_on_refresh_clicked') or
            hasattr(page, 'refresh_themes') or
            hasattr(page, '_refresh_themes')
        )
        self.assertTrue(
            has_refresh,
            "ThemeBrowserPage must have refresh functionality "
            "(on_refresh_clicked, refresh_themes, or similar)"
        )


if __name__ == '__main__':
    unittest.main()
