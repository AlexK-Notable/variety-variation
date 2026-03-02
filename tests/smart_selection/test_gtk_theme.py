#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for GTK dynamic theme integration.

Tests cover:
- GTK3 template rendering (widget selectors)
- GTK4 template rendering (:root CSS custom properties)
- GTK theme scaffold creation and idempotency
- gsettings reload allowlist
- DEFAULT_RELOADS entries for gtk3-dynamic and gtk4-dynamic
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from variety.smart_selection.theming import (
    DEFAULT_RELOADS,
    SAFE_RELOAD_EXECUTABLES,
    TemplateProcessor,
    ThemeEngine,
)

# Shared test palette — deterministic colors for reproducible assertions
PALETTE = {f'color{i}': f'#{"aa" if i < 8 else "cc"}{i:02x}{i:02x}' for i in range(16)}
PALETTE.update({
    'background': '#1a1b26',
    'foreground': '#c0caf5',
    'cursor': '#c0caf5',
})

# Path to bundled templates (relative to repo root)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GTK3_TEMPLATE = os.path.join(_REPO_ROOT, 'data', 'config', 'templates', 'gtk3-theme.css')
GTK4_TEMPLATE = os.path.join(_REPO_ROOT, 'data', 'config', 'templates', 'gtk4-theme.css')


class TestGtk3TemplateRendersAllWidgetSelectors(unittest.TestCase):
    """GTK3 template produces CSS for all expected widget selectors."""

    def setUp(self):
        self.processor = TemplateProcessor(PALETTE)
        with open(GTK3_TEMPLATE, 'r', encoding='utf-8') as f:
            self.raw_template = f.read()
        self.output = self.processor.process(self.raw_template)

    def test_gtk3_template_renders_all_widget_selectors(self):
        """Template processing produces expected CSS selectors."""
        expected_selectors = [
            'window',
            'headerbar',
            'button',
            'entry',
            'treeview.view',
            'scrollbar',
            'switch',
            'checkbutton',
            'scale',
            'progressbar',
            'popover',
            'tooltip',
            'notebook',
            'separator',
            'placessidebar',
        ]

        for selector in expected_selectors:
            self.assertIn(
                selector,
                self.output,
                f"GTK3 CSS output missing expected selector: {selector}",
            )

    def test_gtk3_no_unresolved_variables(self):
        """All {{...}} variables are resolved (no leftover placeholders)."""
        self.assertNotIn('{{', self.output)
        self.assertNotIn('}}', self.output)

    def test_gtk3_comments_stripped(self):
        """Template comments ({# ... #}) are stripped from output."""
        self.assertNotIn('{#', self.output)
        self.assertNotIn('#}', self.output)

    def test_gtk3_background_color_present(self):
        """Background color from palette appears in output."""
        self.assertIn(PALETTE['background'], self.output)

    def test_gtk3_foreground_color_present(self):
        """Foreground color from palette appears in output."""
        self.assertIn(PALETTE['foreground'], self.output)


class TestGtk4TemplateRendersRootVars(unittest.TestCase):
    """GTK4 template produces :root { } block with CSS custom properties."""

    def setUp(self):
        self.processor = TemplateProcessor(PALETTE)
        with open(GTK4_TEMPLATE, 'r', encoding='utf-8') as f:
            self.raw_template = f.read()
        self.output = self.processor.process(self.raw_template)

    def test_gtk4_template_renders_root_vars(self):
        """GTK4 template produces :root { } block with CSS custom properties."""
        self.assertIn(':root {', self.output)

        # Check for key CSS custom properties within :root block
        expected_vars = [
            '--window-bg-color',
            '--window-fg-color',
            '--view-bg-color',
            '--headerbar-bg-color',
            '--accent-bg-color',
            '--accent-color',
            '--destructive-bg-color',
            '--success-bg-color',
            '--warning-bg-color',
            '--popover-bg-color',
            '--sidebar-bg-color',
        ]

        for var in expected_vars:
            self.assertIn(
                var,
                self.output,
                f"GTK4 CSS output missing expected custom property: {var}",
            )

    def test_gtk4_no_unresolved_variables(self):
        """All {{...}} variables are resolved in GTK4 template."""
        self.assertNotIn('{{', self.output)
        self.assertNotIn('}}', self.output)

    def test_gtk4_has_define_color_compat(self):
        """GTK4 template retains @define-color for backward compatibility."""
        self.assertIn('@define-color', self.output)


class TestScaffoldCreatesStructure(unittest.TestCase):
    """_ensure_gtk_theme_scaffold creates directory + index.theme."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.theme_dir = os.path.join(self.temp_dir, 'Variety-Dynamic')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_engine(self):
        """Create a minimal ThemeEngine instance for scaffold testing."""
        engine = ThemeEngine.__new__(ThemeEngine)
        engine.GTK_THEME_DIR = self.theme_dir
        engine.GTK_INDEX_THEME = '/nonexistent'  # force inline fallback
        return engine

    def test_scaffold_creates_structure(self):
        """Directory + index.theme created in a temp dir."""
        engine = self._make_engine()
        engine._ensure_gtk_theme_scaffold()

        # Verify directory structure
        self.assertTrue(os.path.isdir(os.path.join(self.theme_dir, 'gtk-3.0')))
        self.assertTrue(os.path.isdir(os.path.join(self.theme_dir, 'gtk-4.0')))

        # Verify index.theme exists and has expected content
        index_path = os.path.join(self.theme_dir, 'index.theme')
        self.assertTrue(os.path.isfile(index_path))

        with open(index_path, 'r') as f:
            content = f.read()

        self.assertIn('[Desktop Entry]', content)
        self.assertIn('Name=Variety-Dynamic', content)
        self.assertIn('[X-GNOME-Metatheme]', content)
        self.assertIn('GtkTheme=Variety-Dynamic', content)


class TestScaffoldIdempotent(unittest.TestCase):
    """Second scaffold call is a no-op (doesn't error, doesn't modify)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.theme_dir = os.path.join(self.temp_dir, 'Variety-Dynamic')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_engine(self):
        """Create a minimal ThemeEngine instance for scaffold testing."""
        engine = ThemeEngine.__new__(ThemeEngine)
        engine.GTK_THEME_DIR = self.theme_dir
        engine.GTK_INDEX_THEME = '/nonexistent'  # force inline fallback
        return engine

    def test_scaffold_idempotent(self):
        """Second call is a no-op (doesn't error, doesn't modify)."""
        engine = self._make_engine()

        # First call creates everything
        engine._ensure_gtk_theme_scaffold()
        index_path = os.path.join(self.theme_dir, 'index.theme')
        mtime_first = os.path.getmtime(index_path)

        # Second call should be a no-op (early return because index.theme exists)
        engine._ensure_gtk_theme_scaffold()
        mtime_second = os.path.getmtime(index_path)

        # mtime should be unchanged (file was not rewritten)
        self.assertEqual(mtime_first, mtime_second)

        # Structure still intact
        self.assertTrue(os.path.isdir(os.path.join(self.theme_dir, 'gtk-3.0')))
        self.assertTrue(os.path.isdir(os.path.join(self.theme_dir, 'gtk-4.0')))
        self.assertTrue(os.path.isfile(index_path))


class TestGsettingsInAllowlist(unittest.TestCase):
    """gsettings is whitelisted in SAFE_RELOAD_EXECUTABLES."""

    def test_gsettings_in_allowlist(self):
        """gsettings is present in SAFE_RELOAD_EXECUTABLES."""
        self.assertIn('gsettings', SAFE_RELOAD_EXECUTABLES)

    def test_safe_reload_executables_is_set(self):
        """SAFE_RELOAD_EXECUTABLES is a set for O(1) lookups."""
        self.assertIsInstance(SAFE_RELOAD_EXECUTABLES, set)


class TestGtkDynamicReloadCommand(unittest.TestCase):
    """GTK dynamic theme reload is handled by _reload_gtk_theme() toggle."""

    def test_gtk_dynamic_reload_is_none(self):
        """gtk3-dynamic and gtk4-dynamic have None reload commands.

        Reload is handled by ThemeEngine._reload_gtk_theme() which toggles
        the gsettings theme to force GTK apps to re-read CSS. A simple
        gsettings set to the same value is a no-op.
        """
        self.assertIn('gtk3-dynamic', DEFAULT_RELOADS)
        self.assertIn('gtk4-dynamic', DEFAULT_RELOADS)
        self.assertIsNone(DEFAULT_RELOADS['gtk3-dynamic'])
        self.assertIsNone(DEFAULT_RELOADS['gtk4-dynamic'])

    def test_gtk_static_reloads_are_none(self):
        """Static gtk3/gtk4 entries have None reload (apps pick up on next open)."""
        self.assertIn('gtk3', DEFAULT_RELOADS)
        self.assertIn('gtk4', DEFAULT_RELOADS)
        self.assertIsNone(DEFAULT_RELOADS['gtk3'])
        self.assertIsNone(DEFAULT_RELOADS['gtk4'])


if __name__ == '__main__':
    unittest.main()
