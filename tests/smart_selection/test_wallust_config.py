# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for wallust configuration detection."""

import os
import tempfile
import pytest

from variety.smart_selection.wallust_config import (
    _normalize_palette_name,
    parse_wallust_config,
    WallustConfigManager,
    find_latest_palette_cache,
)


class TestNormalizePaletteName:
    """Tests for _normalize_palette_name function."""

    def test_lowercase_dark16(self):
        assert _normalize_palette_name('dark16') == 'Dark16'

    def test_lowercase_light16(self):
        assert _normalize_palette_name('light16') == 'Light16'

    def test_lowercase_harddark16(self):
        assert _normalize_palette_name('harddark16') == 'Harddark16'

    def test_uppercase_all(self):
        assert _normalize_palette_name('DARK16') == 'Dark16'

    def test_mixed_case(self):
        assert _normalize_palette_name('DaRk16') == 'Dark16'

    def test_empty_string(self):
        assert _normalize_palette_name('') == 'Dark16'

    def test_single_char(self):
        assert _normalize_palette_name('a') == 'A'

    def test_custom_palette(self):
        assert _normalize_palette_name('myCustomPalette') == 'Mycustompalette'


class TestParseWallustConfig:
    """Tests for parse_wallust_config function."""

    def test_parse_standard_config(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('''
backend = "wal"
color_space = "lch"
palette = "dark16"
check_contrast = true
''')
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Dark16'
        assert result['backend'] == 'wal'
        assert result['color_space'] == 'lch'
        assert result['config_mtime'] is not None

    def test_parse_light_palette(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('palette = "light16"')
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Light16'

    def test_parse_unquoted_value(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text("palette = dark16")
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Dark16'

    def test_parse_single_quoted_value(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text("palette = 'harddark16'")
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Harddark16'

    def test_parse_missing_file(self, tmp_path):
        result = parse_wallust_config(str(tmp_path / 'nonexistent.toml'))
        assert result['palette_type'] == 'Dark16'
        assert result['config_mtime'] is None

    def test_parse_empty_file(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('')
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Dark16'

    def test_parse_comments_only(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('''
# This is a comment
# palette = "light16"
''')
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Dark16'

    def test_parse_with_spaces(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('  palette   =   "dark16"  ')
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Dark16'

    def test_parse_stops_at_templates_section(self, tmp_path):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('''
palette = "dark16"
[templates]
palette = "should_be_ignored"
''')
        result = parse_wallust_config(str(config_file))
        assert result['palette_type'] == 'Dark16'


class TestWallustConfigManager:
    """Tests for WallustConfigManager class."""

    def test_get_palette_type_with_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('palette = "light16"')
        monkeypatch.setenv('HOME', str(tmp_path))
        os.makedirs(tmp_path / '.config' / 'wallust', exist_ok=True)
        (tmp_path / '.config' / 'wallust' / 'wallust.toml').write_text('palette = "light16"')

        manager = WallustConfigManager()
        # Clear any cached state
        manager._config_cache = None
        manager._config_mtime = None
        # Monkeypatch the path
        monkeypatch.setattr('os.path.expanduser', lambda x: str(tmp_path / '.config' / 'wallust' / 'wallust.toml') if x == '~/.config/wallust/wallust.toml' else x)

        result = manager.get_palette_type()
        assert result == 'Light16'

    def test_get_palette_type_without_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr('os.path.expanduser', lambda x: str(tmp_path / 'nonexistent' / 'wallust.toml') if x == '~/.config/wallust/wallust.toml' else x)

        manager = WallustConfigManager()
        result = manager.get_palette_type()
        assert result == 'Dark16'

    def test_caching_behavior(self, tmp_path, monkeypatch):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('palette = "dark16"')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(config_file) if x == '~/.config/wallust/wallust.toml' else x)

        manager = WallustConfigManager()
        manager.invalidate_cache()

        # First call should parse
        result1 = manager.get_palette_type()
        assert result1 == 'Dark16'
        assert manager._config_cache is not None

        # Second call should use cache
        cached_config = manager._config_cache
        result2 = manager.get_palette_type()
        assert result2 == 'Dark16'
        assert manager._config_cache is cached_config

    def test_invalidate_cache(self, tmp_path, monkeypatch):
        config_file = tmp_path / 'wallust.toml'
        config_file.write_text('palette = "dark16"')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(config_file) if x == '~/.config/wallust/wallust.toml' else x)

        manager = WallustConfigManager()
        manager.invalidate_cache()
        manager.get_palette_type()
        assert manager._config_cache is not None

        manager.invalidate_cache()
        assert manager._config_cache is None
        assert manager._config_mtime is None


class TestFindLatestPaletteCache:
    """Tests for find_latest_palette_cache function."""

    def test_find_cache_existing(self, tmp_path, monkeypatch):
        # Create mock cache structure
        cache_dir = tmp_path / '.cache' / 'wallust'
        hash_dir = cache_dir / 'abc123_v1'
        hash_dir.mkdir(parents=True)

        palette_file = hash_dir / 'FastResize_Lch_auto_Dark16'
        palette_file.write_text('test')

        monkeypatch.setattr('os.path.expanduser', lambda x: str(cache_dir) if x == '~/.cache/wallust' else x)

        result = find_latest_palette_cache('Dark16')
        assert result is not None
        assert 'Dark16' in result

    def test_find_cache_missing_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr('os.path.expanduser', lambda x: str(tmp_path / 'nonexistent') if x == '~/.cache/wallust' else x)

        result = find_latest_palette_cache('Dark16')
        assert result is None

    def test_find_cache_wrong_palette_type(self, tmp_path, monkeypatch):
        # Create cache for different palette type
        cache_dir = tmp_path / '.cache' / 'wallust'
        hash_dir = cache_dir / 'abc123_v1'
        hash_dir.mkdir(parents=True)

        palette_file = hash_dir / 'FastResize_Lch_auto_Light16'
        palette_file.write_text('test')

        monkeypatch.setattr('os.path.expanduser', lambda x: str(cache_dir) if x == '~/.cache/wallust' else x)

        result = find_latest_palette_cache('Dark16')
        assert result is None

    def test_find_cache_latest_when_multiple(self, tmp_path, monkeypatch):
        import time
        # Create cache structure with multiple entries
        cache_dir = tmp_path / '.cache' / 'wallust'

        # Older entry
        old_dir = cache_dir / 'old_hash_v1'
        old_dir.mkdir(parents=True)
        old_file = old_dir / 'FastResize_Lch_auto_Dark16'
        old_file.write_text('old')

        # Small delay to ensure different mtime
        time.sleep(0.01)

        # Newer entry
        new_dir = cache_dir / 'new_hash_v2'
        new_dir.mkdir(parents=True)
        new_file = new_dir / 'FastResize_Lch_auto_Dark16'
        new_file.write_text('new')

        monkeypatch.setattr('os.path.expanduser', lambda x: str(cache_dir) if x == '~/.cache/wallust' else x)

        result = find_latest_palette_cache('Dark16')
        assert result is not None
        assert 'new_hash_v2' in result
