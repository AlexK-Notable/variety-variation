#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.themes - Zed theme extraction and library management."""

import json
import os
import shutil
import tempfile
import unittest

FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'themes'
)


class TestZedThemeExtractorImport(unittest.TestCase):
    """Basic import and instantiation tests."""

    def test_import_classes(self):
        """ZedThemeExtractor and ThemeLibrary can be imported."""
        from variety.smart_selection.themes import ZedThemeExtractor, ThemeLibrary
        self.assertIsNotNone(ZedThemeExtractor)
        self.assertIsNotNone(ThemeLibrary)

    def test_ansi_map_completeness(self):
        """ANSI_MAP covers all 16 standard terminal colors."""
        from variety.smart_selection.themes import ANSI_MAP
        self.assertEqual(len(ANSI_MAP), 16)
        color_keys = set(ANSI_MAP.values())
        expected = {f'color{i}' for i in range(16)}
        self.assertEqual(color_keys, expected)


class TestJSONCStripping(unittest.TestCase):
    """Tests for _strip_jsonc_comments."""

    def _strip(self, text):
        from variety.smart_selection.themes import ZedThemeExtractor
        return ZedThemeExtractor()._strip_jsonc_comments(text)

    def test_single_line_comment(self):
        """Single-line // comments are removed."""
        text = '{"key": "value"} // comment'
        result = self._strip(text)
        self.assertNotIn('//', result)
        data = json.loads(result)
        self.assertEqual(data['key'], 'value')

    def test_block_comment(self):
        """Block /* */ comments are removed."""
        text = '/* header */ {"key": "value"}'
        result = self._strip(text)
        self.assertNotIn('/*', result)
        data = json.loads(result)
        self.assertEqual(data['key'], 'value')

    def test_multiline_block_comment(self):
        """Multi-line block comments are removed."""
        text = '{\n/* multi\nline\ncomment */\n"key": "value"\n}'
        result = self._strip(text)
        data = json.loads(result)
        self.assertEqual(data['key'], 'value')

    def test_comment_like_in_string_preserved(self):
        """// inside a JSON string is NOT stripped."""
        text = '{"url": "https://example.com"}'
        result = self._strip(text)
        data = json.loads(result)
        self.assertEqual(data['url'], 'https://example.com')

    def test_slash_star_in_string_preserved(self):
        """/* inside a JSON string is NOT stripped."""
        text = '{"note": "a /* b */ c"}'
        result = self._strip(text)
        data = json.loads(result)
        self.assertEqual(data['note'], 'a /* b */ c')

    def test_trailing_comma_not_stripped(self):
        """Trailing commas are NOT handled (not our concern, JSON parse may fail)."""
        # Just verify we don't crash
        text = '{"a": 1, // comment\n"b": 2}'
        result = self._strip(text)
        data = json.loads(result)
        self.assertEqual(data['a'], 1)


class TestExtractAnsiColors(unittest.TestCase):
    """Tests for _extract_ansi_colors."""

    def _extract(self, style):
        from variety.smart_selection.themes import ZedThemeExtractor
        return ZedThemeExtractor()._extract_ansi_colors(style)

    def test_full_ansi_extraction(self):
        """All 16 ANSI colors are extracted correctly."""
        style = {
            'terminal.ansi.black': '#000000',
            'terminal.ansi.red': '#FF0000',
            'terminal.ansi.green': '#00FF00',
            'terminal.ansi.yellow': '#FFFF00',
            'terminal.ansi.blue': '#0000FF',
            'terminal.ansi.magenta': '#FF00FF',
            'terminal.ansi.cyan': '#00FFFF',
            'terminal.ansi.white': '#FFFFFF',
            'terminal.ansi.bright_black': '#808080',
            'terminal.ansi.bright_red': '#FF8080',
            'terminal.ansi.bright_green': '#80FF80',
            'terminal.ansi.bright_yellow': '#FFFF80',
            'terminal.ansi.bright_blue': '#8080FF',
            'terminal.ansi.bright_magenta': '#FF80FF',
            'terminal.ansi.bright_cyan': '#80FFFF',
            'terminal.ansi.bright_white': '#FFFFFF',
            'background': '#1a1b26',
            'terminal.background': '#16161e',
            'editor.foreground': '#c0caf5',
            'players': [{'cursor': '#AABBCC'}],
        }
        result = self._extract(style)
        self.assertIsNotNone(result)
        # Check all 16 colors
        self.assertEqual(result['color0'], '#000000')
        self.assertEqual(result['color1'], '#FF0000')
        self.assertEqual(result['color7'], '#FFFFFF')
        self.assertEqual(result['color8'], '#808080')
        self.assertEqual(result['color15'], '#FFFFFF')
        # Background prefers terminal.background
        self.assertEqual(result['background'], '#16161e')
        # Foreground from editor.foreground (terminal.foreground absent)
        self.assertEqual(result['foreground'], '#c0caf5')
        # Cursor from players
        self.assertEqual(result['cursor'], '#AABBCC')

    def test_terminal_foreground_preferred(self):
        """terminal.foreground is preferred over editor.foreground."""
        style = {
            'terminal.ansi.black': '#000', 'terminal.ansi.red': '#F00',
            'terminal.ansi.green': '#0F0', 'terminal.ansi.yellow': '#FF0',
            'terminal.ansi.blue': '#00F', 'terminal.ansi.magenta': '#F0F',
            'terminal.ansi.cyan': '#0FF', 'terminal.ansi.white': '#FFF',
            'terminal.ansi.bright_black': '#888',
            'terminal.foreground': '#AAAAAA',
            'editor.foreground': '#BBBBBB',
            'players': [{'cursor': '#CCC'}],
        }
        result = self._extract(style)
        self.assertIsNotNone(result)
        self.assertEqual(result['foreground'], '#AAAAAA')

    def test_insufficient_colors_returns_none(self):
        """Returns None when fewer than minimum ANSI colors found."""
        style = {
            'terminal.ansi.black': '#000',
            'terminal.ansi.red': '#F00',
        }
        result = self._extract(style)
        self.assertIsNone(result)

    def test_cursor_fallback_to_foreground(self):
        """Cursor falls back to foreground when no players present."""
        style = {
            'terminal.ansi.black': '#000', 'terminal.ansi.red': '#F00',
            'terminal.ansi.green': '#0F0', 'terminal.ansi.yellow': '#FF0',
            'terminal.ansi.blue': '#00F', 'terminal.ansi.magenta': '#F0F',
            'terminal.ansi.cyan': '#0FF', 'terminal.ansi.white': '#FFF',
            'terminal.ansi.bright_black': '#888',
            'editor.foreground': '#ABCDEF',
        }
        result = self._extract(style)
        self.assertIsNotNone(result)
        self.assertEqual(result['cursor'], '#ABCDEF')

    def test_none_values_skipped(self):
        """ANSI keys with None values (like dim_*) are skipped."""
        style = {
            'terminal.ansi.black': '#000', 'terminal.ansi.red': '#F00',
            'terminal.ansi.green': '#0F0', 'terminal.ansi.yellow': '#FF0',
            'terminal.ansi.blue': '#00F', 'terminal.ansi.magenta': '#F0F',
            'terminal.ansi.cyan': '#0FF', 'terminal.ansi.white': '#FFF',
            'terminal.ansi.bright_black': '#888',
            'terminal.ansi.dim_black': None,
            'editor.foreground': '#FFF',
            'players': [{'cursor': '#FFF'}],
        }
        result = self._extract(style)
        self.assertIsNotNone(result)
        self.assertIn('color0', result)


class TestExtractFallbackColors(unittest.TestCase):
    """Tests for _extract_fallback_colors."""

    def _extract(self, style):
        from variety.smart_selection.themes import ZedThemeExtractor
        return ZedThemeExtractor()._extract_fallback_colors(style)

    def test_fallback_with_syntax_colors(self):
        """Fallback extraction works with syntax highlight colors."""
        style = {
            'background': '#1e1e2e',
            'editor.foreground': '#cdd6f4',
            'syntax': {
                'comment': {'color': '#6c7086'},
                'string': {'color': '#a6e3a1'},
                'keyword': {'color': '#cba6f7'},
                'function': {'color': '#89b4fa'},
                'type': {'color': '#f9e2af'},
                'constant': {'color': '#fab387'},
            },
            'players': [{'cursor': '#f5e0dc'}],
        }
        result = self._extract(style)
        self.assertIsNotNone(result)
        self.assertEqual(result['background'], '#1e1e2e')
        self.assertEqual(result['foreground'], '#cdd6f4')
        self.assertEqual(result['cursor'], '#f5e0dc')
        # Should have color0-15 filled
        for i in range(16):
            self.assertIn(f'color{i}', result)

    def test_fallback_no_background_returns_none(self):
        """Returns None without background color."""
        style = {
            'editor.foreground': '#FFF',
            'syntax': {'comment': {'color': '#888'}},
        }
        result = self._extract(style)
        self.assertIsNone(result)

    def test_fallback_insufficient_syntax_returns_none(self):
        """Returns None with fewer than 4 syntax colors."""
        style = {
            'background': '#000',
            'editor.foreground': '#FFF',
            'syntax': {
                'comment': {'color': '#888'},
            },
        }
        result = self._extract(style)
        self.assertIsNone(result)


class TestParseThemeFile(unittest.TestCase):
    """Tests for parse_theme_file with real fixture files."""

    def test_parse_valid_ansi_theme(self):
        """Parses valid theme file with ANSI colors."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'valid-ansi-theme.json')
        results = ext.parse_theme_file(fixture)
        self.assertEqual(len(results), 2)
        # First theme: dark
        self.assertEqual(results[0].name, 'Test Dark')
        self.assertEqual(results[0].appearance, 'dark')
        self.assertEqual(results[0].color0, '#15161e')
        self.assertEqual(results[0].color1, '#f7768e')
        self.assertEqual(results[0].color15, '#c0caf5')
        self.assertEqual(results[0].source_type, 'zed')
        self.assertEqual(results[0].theme_id, 'zed:valid-ansi-theme:Test Dark')
        # Second theme: light
        self.assertEqual(results[1].name, 'Test Light')
        self.assertEqual(results[1].appearance, 'light')

    def test_parse_jsonc_theme(self):
        """Parses JSONC theme file with // and /* */ comments."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'jsonc-theme.jsonc')
        results = ext.parse_theme_file(fixture)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, 'JSONC Dark')
        self.assertEqual(results[0].color0, '#282c34')
        self.assertEqual(results[0].cursor, '#528bff')

    def test_parse_fallback_theme(self):
        """Parses theme without ANSI keys using fallback extraction."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'fallback-theme.json')
        results = ext.parse_theme_file(fixture)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, 'Fallback No ANSI')
        self.assertIsNotNone(results[0].color0)
        self.assertIsNotNone(results[0].background)
        self.assertIsNotNone(results[0].foreground)

    def test_malformed_json_returns_empty(self):
        """Malformed JSON returns empty list, no exception."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        try:
            f.write('{truncated')
            f.close()
            results = ext.parse_theme_file(f.name)
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(f.name)

    def test_nonexistent_file_returns_empty(self):
        """Nonexistent file returns empty list, no exception."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        results = ext.parse_theme_file('/nonexistent/path/theme.json')
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_empty_themes_array(self):
        """File with empty themes array returns empty list."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        try:
            json.dump({"themes": []}, f)
            f.close()
            results = ext.parse_theme_file(f.name)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(f.name)

    def test_theme_without_name_skipped(self):
        """Theme variant without a name is skipped."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        try:
            data = {"themes": [{"style": {}}]}
            json.dump(data, f)
            f.close()
            results = ext.parse_theme_file(f.name)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(f.name)


class TestDerivedMetrics(unittest.TestCase):
    """Tests for derived metrics on extracted themes."""

    def test_metrics_present_on_ansi_theme(self):
        """Extracted ANSI theme has all 4 derived metrics."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'valid-ansi-theme.json')
        results = ext.parse_theme_file(fixture)
        self.assertTrue(len(results) >= 1)
        r = results[0]
        self.assertIsNotNone(r.avg_hue)
        self.assertIsNotNone(r.avg_saturation)
        self.assertIsNotNone(r.avg_lightness)
        self.assertIsNotNone(r.color_temperature)

    def test_metrics_present_on_fallback_theme(self):
        """Extracted fallback theme has all 4 derived metrics."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'fallback-theme.json')
        results = ext.parse_theme_file(fixture)
        self.assertTrue(len(results) >= 1)
        r = results[0]
        self.assertIsNotNone(r.avg_hue)
        self.assertIsNotNone(r.avg_saturation)
        self.assertIsNotNone(r.avg_lightness)
        self.assertIsNotNone(r.color_temperature)

    def test_metrics_in_valid_range(self):
        """Derived metrics fall within expected ranges."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'valid-ansi-theme.json')
        results = ext.parse_theme_file(fixture)
        r = results[0]
        self.assertGreaterEqual(r.avg_hue, 0)
        self.assertLessEqual(r.avg_hue, 360)
        self.assertGreaterEqual(r.avg_saturation, 0)
        self.assertLessEqual(r.avg_saturation, 1)
        self.assertGreaterEqual(r.avg_lightness, 0)
        self.assertLessEqual(r.avg_lightness, 1)
        self.assertGreaterEqual(r.color_temperature, -1)
        self.assertLessEqual(r.color_temperature, 1)


class TestScan(unittest.TestCase):
    """Tests for ZedThemeExtractor.scan."""

    def test_scan_extra_paths(self):
        """scan() finds JSON/JSONC files in extra_paths."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        results = ext.scan(extra_paths=[FIXTURES_DIR])
        # Should find at least our fixture files
        basenames = [os.path.basename(p) for p in results]
        self.assertIn('valid-ansi-theme.json', basenames)
        self.assertIn('jsonc-theme.jsonc', basenames)

    def test_scan_nonexistent_path_ignored(self):
        """scan() silently ignores nonexistent directories."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        results = ext.scan(extra_paths=['/nonexistent/dir'])
        # Should not crash; may return files from default paths or empty
        self.assertIsInstance(results, list)


class TestThemeLibrary(unittest.TestCase):
    """Tests for ThemeLibrary."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _make_db(self):
        from variety.smart_selection.database import ImageDatabase
        return ImageDatabase(self.db_path)

    def test_import_from_zed_with_fixtures(self):
        """import_from_zed() imports themes from fixture directory."""
        from variety.smart_selection.themes import ThemeLibrary
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            count = lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            # Fixture directory contains multiple theme files;
            # verify at least our 3 new files contribute themes
            self.assertGreaterEqual(count, 4)
            # Verify database matches import count
            all_themes = db.get_all_color_themes()
            self.assertEqual(len(all_themes), count)
        finally:
            db.close()

    def test_import_from_zed_empty_paths(self):
        """import_from_zed() with empty scan_paths returns 0."""
        from variety.smart_selection.themes import ThemeLibrary
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            count = lib.import_from_zed(scan_paths=[])
            self.assertIsInstance(count, int)
            self.assertEqual(count, 0)
        finally:
            db.close()

    def test_import_idempotent(self):
        """Importing same themes twice does not duplicate."""
        from variety.smart_selection.themes import ThemeLibrary
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            count1 = lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            count2 = lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            self.assertEqual(count1, count2)
            all_themes = db.get_all_color_themes()
            self.assertEqual(len(all_themes), count1)
        finally:
            db.close()

    def test_get_theme_palette(self):
        """get_theme_palette() returns palette dict with color0-15 keys."""
        from variety.smart_selection.themes import ThemeLibrary
        from variety.smart_selection.models import ColorThemeRecord
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            t = ColorThemeRecord(
                theme_id='test-pal', name='Test', source_type='zed',
                color0='#FF0000', color1='#00FF00', color2='#0000FF',
                color3='#FFFF00', color4='#FF00FF', color5='#00FFFF',
                color6='#808080', color7='#FFFFFF',
                background='#000000', foreground='#FFFFFF', cursor='#FFFFFF',
            )
            db.upsert_color_theme(t)
            p = lib.get_theme_palette('test-pal')
            self.assertIsNotNone(p)
            self.assertIn('color0', p)
            self.assertIn('background', p)
            self.assertIn('foreground', p)
            self.assertEqual(p['color0'], '#FF0000')
        finally:
            db.close()

    def test_get_theme_palette_not_found(self):
        """get_theme_palette() returns None for nonexistent theme."""
        from variety.smart_selection.themes import ThemeLibrary
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            p = lib.get_theme_palette('nonexistent')
            self.assertIsNone(p)
        finally:
            db.close()

    def test_fork_theme(self):
        """fork_theme() creates a custom copy with parent link."""
        from variety.smart_selection.themes import ThemeLibrary
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            # Fork the first dark theme
            forked = lib.fork_theme('zed:valid-ansi-theme:Test Dark', 'My Custom')
            self.assertIsNotNone(forked)
            self.assertEqual(forked.name, 'My Custom')
            self.assertEqual(forked.source_type, 'custom')
            self.assertTrue(forked.is_custom)
            self.assertEqual(forked.parent_theme_id, 'zed:valid-ansi-theme:Test Dark')
            # Verify it has the same colors
            self.assertEqual(forked.color0, '#15161e')
            # Verify it's in the database
            stored = db.get_color_theme(forked.theme_id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.name, 'My Custom')
        finally:
            db.close()

    def test_fork_nonexistent_returns_none(self):
        """fork_theme() returns None when parent not found."""
        from variety.smart_selection.themes import ThemeLibrary
        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            result = lib.fork_theme('nonexistent', 'Copy')
            self.assertIsNone(result)
        finally:
            db.close()


class TestThemeIdGeneration(unittest.TestCase):
    """Tests for deterministic theme_id generation."""

    def test_theme_id_format(self):
        """Theme IDs follow source_type:filename_stem:name format."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'valid-ansi-theme.json')
        results = ext.parse_theme_file(fixture)
        self.assertEqual(results[0].theme_id, 'zed:valid-ansi-theme:Test Dark')
        self.assertEqual(results[1].theme_id, 'zed:valid-ansi-theme:Test Light')

    def test_theme_id_deterministic(self):
        """Parsing same file twice produces same theme_ids."""
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'valid-ansi-theme.json')
        r1 = ext.parse_theme_file(fixture)
        r2 = ext.parse_theme_file(fixture)
        ids1 = [r.theme_id for r in r1]
        ids2 = [r.theme_id for r in r2]
        self.assertEqual(ids1, ids2)


# =====================================================================
# Supplementary gate-criteria tests (test-scaffolder additions)
# =====================================================================

class TestAnsiColorMappingComplete(unittest.TestCase):
    """Verify all 16 ANSI positions map correctly using catppuccin fixture.

    Gate criterion #5: color0=black, color1=red, ..., color15=bright_white
    (all 16 correct). Uses the gate-specified catppuccin fixture.
    """

    def test_all_16_ansi_positions_catppuccin_mocha(self):
        """Catppuccin Mocha: all 16 ANSI colors map to correct positions.

        Bug caught: ANSI position mapping off-by-one or wrong key-to-index
        mapping in ANSI_MAP constant.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)
        mocha = [r for r in results if r.name == 'Catppuccin Mocha']
        self.assertEqual(len(mocha), 1, "Should find Catppuccin Mocha variant")
        m = mocha[0]

        expected = {
            'color0': '#45475a',   # black
            'color1': '#f38ba8',   # red
            'color2': '#a6e3a1',   # green
            'color3': '#f9e2af',   # yellow
            'color4': '#89b4fa',   # blue
            'color5': '#f5c2e7',   # magenta
            'color6': '#94e2d5',   # cyan
            'color7': '#bac2de',   # white
            'color8': '#585b70',   # bright_black
            'color9': '#f38ba8',   # bright_red
            'color10': '#a6e3a1',  # bright_green
            'color11': '#f9e2af',  # bright_yellow
            'color12': '#89b4fa',  # bright_blue
            'color13': '#f5c2e7',  # bright_magenta
            'color14': '#94e2d5',  # bright_cyan
            'color15': '#a6adc8',  # bright_white
        }

        for key, expected_hex in expected.items():
            actual = getattr(m, key, None)
            self.assertIsNotNone(actual, f"{key} should not be None")
            self.assertEqual(
                actual.lower(), expected_hex.lower(),
                f"{key}: expected {expected_hex}, got {actual}"
            )

    def test_catppuccin_mocha_bg_fg_cursor(self):
        """Catppuccin Mocha: background, foreground, cursor extracted correctly.

        Bug caught: Background/foreground mapped from wrong JSON key
        or cursor not reaching into players array.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)
        mocha = [r for r in results if r.name == 'Catppuccin Mocha'][0]

        self.assertEqual(mocha.background.lower(), '#1e1e2e')
        self.assertEqual(mocha.foreground.lower(), '#cdd6f4')
        self.assertEqual(mocha.cursor.lower(), '#f5e0dc')

    def test_catppuccin_two_variants(self):
        """Catppuccin file with 2 variants returns 2 theme dicts.

        Bug caught: Only extracting the first variant, ignoring rest.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)
        self.assertGreaterEqual(len(results), 2)

        names = {r.name for r in results}
        self.assertIn('Catppuccin Mocha', names)
        self.assertIn('Catppuccin Latte', names)

    def test_catppuccin_mocha_dark_latte_light(self):
        """Catppuccin Mocha is dark, Latte is light.

        Bug caught: Appearance not extracted or assigned to wrong variant.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)

        mocha = [r for r in results if r.name == 'Catppuccin Mocha'][0]
        latte = [r for r in results if r.name == 'Catppuccin Latte'][0]
        self.assertEqual(mocha.appearance, 'dark')
        self.assertEqual(latte.appearance, 'light')

    def test_unique_theme_ids_across_variants(self):
        """Each variant in the same file has a unique theme_id.

        Bug caught: theme_id not generated uniquely per variant,
        causing database insert collision.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)

        ids = [r.theme_id for r in results]
        self.assertEqual(len(ids), len(set(ids)), "theme_ids must be unique")

    def test_all_variants_have_source_type_zed(self):
        """All extracted themes have source_type='zed'.

        Bug caught: source_type not set or set to wrong value.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)

        for r in results:
            self.assertEqual(r.source_type, 'zed',
                             f"source_type should be 'zed' for {r.name}")

    def test_all_variants_have_source_path(self):
        """All extracted themes store the source file path.

        Bug caught: source_path not recorded, losing traceability.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)

        for r in results:
            self.assertIsNotNone(r.source_path,
                                 f"source_path should be set for {r.name}")
            self.assertTrue(r.source_path.endswith('catppuccin_mocha.json'))


class TestDerivedMetricsParity(unittest.TestCase):
    """Verify derived metrics match calculate_palette_metrics() output.

    Gate criterion #8: All extracted themes have non-null derived metrics.
    Also verifies that metrics are computed via the Phase 0 function
    (not reimplemented), preventing metric divergence.
    """

    def test_metrics_match_calculate_palette_metrics(self):
        """Derived metrics on extracted theme match direct calculation.

        Bug caught: Metrics computed by a different code path, causing
        divergence from calculate_palette_metrics() in palette.py.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        from variety.smart_selection.palette import calculate_palette_metrics

        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)

        for theme in results:
            # Reconstruct palette dict from extracted colors
            palette = {}
            for i in range(16):
                val = getattr(theme, f'color{i}', None)
                if val is not None:
                    palette[f'color{i}'] = val

            expected = calculate_palette_metrics(palette)

            self.assertAlmostEqual(
                theme.avg_hue, expected['avg_hue'], places=2,
                msg=f"avg_hue mismatch for {theme.name}"
            )
            self.assertAlmostEqual(
                theme.avg_saturation, expected['avg_saturation'], places=4,
                msg=f"avg_saturation mismatch for {theme.name}"
            )
            self.assertAlmostEqual(
                theme.avg_lightness, expected['avg_lightness'], places=4,
                msg=f"avg_lightness mismatch for {theme.name}"
            )
            self.assertAlmostEqual(
                theme.color_temperature, expected['color_temperature'], places=4,
                msg=f"color_temperature mismatch for {theme.name}"
            )

    def test_dark_and_light_variants_have_distinct_metrics(self):
        """Dark and light variants produce measurably different metrics.

        Bug caught: All variants producing identical metrics (indicating
        the same colors are extracted for both, or metrics are hardcoded).

        Note: avg_lightness is computed from the 16 ANSI palette colors,
        not the background. Catppuccin Mocha (dark) uses pastel ANSI colors
        while Latte (light) uses deeper tones, so the relationship between
        ANSI lightness and theme appearance is not straightforward.
        We verify the metrics differ, proving each variant is independently
        computed.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json')
        results = ext.parse_theme_file(fixture)

        mocha = [r for r in results if r.name == 'Catppuccin Mocha'][0]
        latte = [r for r in results if r.name == 'Catppuccin Latte'][0]

        # Metrics should differ between variants (proving independent computation)
        self.assertNotAlmostEqual(
            mocha.avg_lightness, latte.avg_lightness, places=2,
            msg="Dark and light variants should have different lightness"
        )
        self.assertNotAlmostEqual(
            mocha.avg_hue, latte.avg_hue, places=2,
            msg="Dark and light variants should have different hue"
        )

    def test_metrics_in_valid_ranges_all_fixtures(self):
        """All metrics from all fixture files fall within valid ranges.

        Bug caught: Metric calculation producing out-of-range values
        (negative saturation, hue > 360, etc).
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()

        fixture_files = [
            'catppuccin_mocha.json', 'valid-ansi-theme.json',
            'single_variant.json', 'no_cursor_theme.json',
        ]

        for fname in fixture_files:
            fixture = os.path.join(FIXTURES_DIR, fname)
            if not os.path.exists(fixture):
                continue
            results = ext.parse_theme_file(fixture)
            for r in results:
                self.assertIsNotNone(r.avg_hue, f"avg_hue None for {r.name}")
                self.assertGreaterEqual(r.avg_hue, 0.0)
                self.assertLessEqual(r.avg_hue, 360.0)
                self.assertIsNotNone(r.avg_saturation,
                                     f"avg_saturation None for {r.name}")
                self.assertGreaterEqual(r.avg_saturation, 0.0)
                self.assertLessEqual(r.avg_saturation, 1.0)
                self.assertIsNotNone(r.avg_lightness,
                                     f"avg_lightness None for {r.name}")
                self.assertGreaterEqual(r.avg_lightness, 0.0)
                self.assertLessEqual(r.avg_lightness, 1.0)
                self.assertIsNotNone(r.color_temperature,
                                     f"color_temperature None for {r.name}")


class TestJSONCWithGateFixtures(unittest.TestCase):
    """JSONC handling using the gate-specified with_comments.jsonc fixture.

    Gate criterion #3: File with // and /* */ comments parses successfully.
    """

    def test_gate_jsonc_fixture_parses(self):
        """Gate fixture with_comments.jsonc parses despite comments.

        Bug caught: JSON parser choking on JSONC syntax.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'with_comments.jsonc')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1,
                                "JSONC fixture should parse successfully")

    def test_gate_jsonc_colors_not_corrupted(self):
        """Comment stripping does not corrupt hex color values.

        Bug caught: Regex-based comment stripping mangling hex values
        that contain // or /* in adjacent JSON keys.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'with_comments.jsonc')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1)
        theme = results[0]
        # All 16 colors should be valid hex
        for i in range(16):
            val = getattr(theme, f'color{i}', None)
            if val is not None:
                self.assertTrue(
                    val.startswith('#') and len(val) >= 4,
                    f"color{i} looks corrupted: {val}"
                )


class TestMalformedAndEdgeCases(unittest.TestCase):
    """Additional malformed/edge-case tests from gate criteria.

    Gate criterion #4: Malformed JSON returns empty list (no crash).
    """

    def test_gate_malformed_fixture(self):
        """Gate fixture malformed.json returns empty list.

        Bug caught: Unhandled json.JSONDecodeError crashing import.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'malformed.json')
        results = ext.parse_theme_file(fixture)

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_empty_file_returns_empty_list(self):
        """Empty file returns empty list, no crash.

        Bug caught: Empty string causing JSONDecodeError.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()

        empty_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        try:
            empty_file.close()
            results = ext.parse_theme_file(empty_file.name)
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(empty_file.name)

    def test_json_with_no_themes_key(self):
        """JSON without 'themes' key returns empty list.

        Bug caught: KeyError when themes key is missing.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()

        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        try:
            json.dump({"name": "No themes key"}, f)
            f.close()
            results = ext.parse_theme_file(f.name)
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(f.name)

    def test_json_array_at_root(self):
        """JSON array at root (not object) returns empty list.

        Bug caught: TypeError when data.get() called on a list.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()

        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        try:
            json.dump([{"name": "Array root"}], f)
            f.close()
            results = ext.parse_theme_file(f.name)
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(f.name)


class TestFallbackWithGateFixture(unittest.TestCase):
    """Fallback extraction using gate-specified no_ansi_theme.json fixture.

    Gate criterion #6: Theme without terminal.ansi but with editor/syntax
    colors extracts palette.
    """

    def test_no_ansi_theme_produces_results(self):
        """no_ansi_theme.json extracts at least one theme via fallback.

        Bug caught: Fallback path not invoked when ANSI keys are absent.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'no_ansi_theme.json')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1,
                                "Fallback should produce at least 1 theme")

    def test_no_ansi_theme_has_bg_fg(self):
        """Fallback-extracted theme has background and foreground.

        Bug caught: Fallback returns colors but misses bg/fg.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'no_ansi_theme.json')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1)
        theme = results[0]
        self.assertIsNotNone(theme.background)
        self.assertIsNotNone(theme.foreground)

    def test_no_ansi_theme_populates_color_slots(self):
        """Fallback populates at least some color0-15 slots from syntax colors.

        Bug caught: Fallback only sets bg/fg, leaving all color0-15 as None.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'no_ansi_theme.json')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1)
        theme = results[0]
        populated = sum(
            1 for i in range(16)
            if getattr(theme, f'color{i}', None) is not None
        )
        self.assertGreater(populated, 0,
                           "Fallback should populate some color slots")

    def test_no_ansi_theme_has_metrics(self):
        """Fallback-extracted theme has non-null derived metrics.

        Bug caught: _compute_derived_metrics() only called for ANSI path,
        skipped for fallback path.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'no_ansi_theme.json')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1)
        theme = results[0]
        self.assertIsNotNone(theme.avg_hue)
        self.assertIsNotNone(theme.avg_saturation)
        self.assertIsNotNone(theme.avg_lightness)
        self.assertIsNotNone(theme.color_temperature)


class TestCursorFallbackWithGateFixture(unittest.TestCase):
    """Cursor fallback using gate-specified no_cursor_theme.json fixture.

    Gate criterion #7: No players[0].cursor falls back to foreground.
    """

    def test_no_cursor_falls_back(self):
        """Theme with empty players[0] (no cursor) falls back to foreground.

        Bug caught: Missing cursor producing None, breaking TemplateProcessor.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'no_cursor_theme.json')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1)
        theme = results[0]
        self.assertIsNotNone(theme.cursor,
                             "cursor should fall back to foreground")
        self.assertTrue(theme.cursor.startswith('#'),
                        f"cursor should be hex, got: {theme.cursor}")

    def test_no_cursor_equals_foreground(self):
        """When cursor is missing, it falls back to the foreground value.

        Bug caught: Fallback sets cursor to background instead of foreground.
        """
        from variety.smart_selection.themes import ZedThemeExtractor
        ext = ZedThemeExtractor()
        fixture = os.path.join(FIXTURES_DIR, 'no_cursor_theme.json')
        results = ext.parse_theme_file(fixture)

        self.assertGreaterEqual(len(results), 1)
        theme = results[0]
        # The fixture has terminal.foreground=#f8f8f2
        # Cursor should fall back to foreground
        self.assertEqual(theme.cursor, theme.foreground,
                         "cursor should equal foreground when players has no cursor")


class TestScanWithGateCriteria(unittest.TestCase):
    """scan() directory scanning with gate-specified scenarios.

    Gate criterion #9: scan() finds .json and .jsonc files.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _write_file(self, relpath, content='{}'):
        """Write a file relative to temp_dir."""
        full = os.path.join(self.temp_dir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)
        return full

    def test_scan_finds_both_json_and_jsonc(self):
        """scan() discovers both .json and .jsonc files.

        Bug caught: Glob pattern missing .jsonc extension.
        """
        from variety.smart_selection.themes import ZedThemeExtractor

        self._write_file('theme.json')
        self._write_file('theme.jsonc')

        ext = ZedThemeExtractor()
        found = ext.scan(extra_paths=[self.temp_dir])
        basenames = {os.path.basename(p) for p in found}

        self.assertIn('theme.json', basenames)
        self.assertIn('theme.jsonc', basenames)

    def test_scan_recurses_subdirectories(self):
        """scan() finds files in nested subdirectories.

        Bug caught: Only scanning top-level, not using os.walk.
        """
        from variety.smart_selection.themes import ZedThemeExtractor

        self._write_file('ext/catppuccin/themes/catppuccin.json')

        ext = ZedThemeExtractor()
        found = ext.scan(extra_paths=[self.temp_dir])

        self.assertGreaterEqual(len(found), 1,
                                "Should find files in subdirectories")

    def test_scan_empty_dir_no_crash(self):
        """scan() on empty directory returns empty or non-crash result.

        Bug caught: crash on empty directory listing.
        """
        from variety.smart_selection.themes import ZedThemeExtractor

        ext = ZedThemeExtractor()
        found = ext.scan(extra_paths=[self.temp_dir])
        self.assertIsInstance(found, list)

    def test_scan_nonexistent_dir_no_crash(self):
        """scan() with nonexistent directory does not crash.

        Bug caught: FileNotFoundError or OSError not caught.
        """
        from variety.smart_selection.themes import ZedThemeExtractor

        ext = ZedThemeExtractor()
        found = ext.scan(extra_paths=['/nonexistent/zed/extensions'])
        self.assertIsInstance(found, list)


class TestThemeLibraryIntegrationWithGateFixtures(unittest.TestCase):
    """Integration tests using gate-specified fixtures.

    Covers import -> retrieve -> verify end-to-end workflow.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.close()
        shutil.rmtree(self.temp_dir)

    def _make_db(self):
        from variety.smart_selection.database import ImageDatabase
        self.db = ImageDatabase(self.db_path)
        return self.db

    def test_import_catppuccin_stores_both_variants(self):
        """Importing catppuccin fixture stores both Mocha and Latte variants.

        Bug caught: Only first variant stored, or multiple variants
        overwriting each other.
        """
        from variety.smart_selection.themes import ThemeLibrary

        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            # Use single fixture file directory approach
            catppuccin_dir = tempfile.mkdtemp()
            try:
                import shutil as sh
                sh.copy2(
                    os.path.join(FIXTURES_DIR, 'catppuccin_mocha.json'),
                    os.path.join(catppuccin_dir, 'catppuccin_mocha.json')
                )
                count = lib.import_from_zed(scan_paths=[catppuccin_dir])
                self.assertGreaterEqual(count, 2,
                                        "Should import both Mocha and Latte")

                all_themes = db.get_all_color_themes()
                names = {t.name for t in all_themes}
                self.assertIn('Catppuccin Mocha', names)
                self.assertIn('Catppuccin Latte', names)
            finally:
                sh.rmtree(catppuccin_dir)
        finally:
            db.close()

    def test_imported_themes_all_have_metrics(self):
        """All imported themes from full fixture directory have non-null metrics.

        Bug caught: Metrics not computed during import, or computed only
        for some themes.
        """
        from variety.smart_selection.themes import ThemeLibrary

        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            count = lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            self.assertGreater(count, 0)

            all_themes = db.get_all_color_themes()
            for t in all_themes:
                self.assertIsNotNone(t.avg_hue,
                                     f"avg_hue None for {t.name}")
                self.assertIsNotNone(t.avg_saturation,
                                     f"avg_saturation None for {t.name}")
                self.assertIsNotNone(t.avg_lightness,
                                     f"avg_lightness None for {t.name}")
                self.assertIsNotNone(t.color_temperature,
                                     f"color_temperature None for {t.name}")
        finally:
            db.close()

    def test_import_count_matches_database(self):
        """import_from_zed() return count matches get_all_color_themes() length.

        Bug caught: Count incremented but upsert failed silently.
        """
        from variety.smart_selection.themes import ThemeLibrary

        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            count = lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            all_themes = db.get_all_color_themes()
            self.assertEqual(count, len(all_themes),
                             "Returned count should match stored themes")
        finally:
            db.close()

    def test_get_palette_has_all_expected_keys(self):
        """get_theme_palette() returns dict with color0-15, bg, fg, cursor.

        Bug caught: Missing keys that downstream consumers expect.
        """
        from variety.smart_selection.themes import ThemeLibrary

        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            lib.import_from_zed(scan_paths=[FIXTURES_DIR])
            all_themes = db.get_all_color_themes()
            self.assertGreater(len(all_themes), 0)

            # Find a theme with full ANSI colors (not fallback)
            for t in all_themes:
                if t.color0 is not None and t.color15 is not None:
                    palette = lib.get_theme_palette(t.theme_id)
                    self.assertIsNotNone(palette)
                    for i in range(16):
                        self.assertIn(f'color{i}', palette,
                                      f"color{i} missing from palette")
                    self.assertIn('background', palette)
                    self.assertIn('foreground', palette)
                    self.assertIn('cursor', palette)
                    return  # found and verified one
            self.fail("No fully-populated theme found in fixtures")
        finally:
            db.close()

    def test_fork_sets_parent_and_is_custom(self):
        """fork_theme() sets parent_theme_id and is_custom=True.

        Bug caught: Fork not tracking lineage or custom flag.
        """
        from variety.smart_selection.themes import ThemeLibrary

        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            lib.import_from_zed(scan_paths=[FIXTURES_DIR])

            all_themes = db.get_all_color_themes()
            self.assertGreater(len(all_themes), 0)

            parent = all_themes[0]
            forked = lib.fork_theme(parent.theme_id, 'My Custom')
            self.assertIsNotNone(forked)
            self.assertEqual(forked.parent_theme_id, parent.theme_id)
            self.assertTrue(forked.is_custom)

            # Verify persisted
            stored = db.get_color_theme(forked.theme_id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.parent_theme_id, parent.theme_id)
            self.assertTrue(stored.is_custom)
        finally:
            db.close()

    def test_fork_inherits_all_colors(self):
        """Forked theme inherits all color values from parent.

        Bug caught: Fork creating theme with empty/None colors.
        """
        from variety.smart_selection.themes import ThemeLibrary

        db = self._make_db()
        try:
            lib = ThemeLibrary(db)
            lib.import_from_zed(scan_paths=[FIXTURES_DIR])

            all_themes = db.get_all_color_themes()
            # Find a theme with all 16 colors
            parent = None
            for t in all_themes:
                if all(getattr(t, f'color{i}') is not None for i in range(16)):
                    parent = t
                    break
            self.assertIsNotNone(parent, "Need a fully-populated parent")

            forked = lib.fork_theme(parent.theme_id, 'Color Copy')

            for i in range(16):
                self.assertEqual(
                    getattr(forked, f'color{i}'),
                    getattr(parent, f'color{i}'),
                    f"color{i} should be inherited from parent"
                )
            self.assertEqual(forked.background, parent.background)
            self.assertEqual(forked.foreground, parent.foreground)
            self.assertEqual(forked.cursor, parent.cursor)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
