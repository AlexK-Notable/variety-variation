"""Wallust configuration detection with caching.

This module provides centralized parsing of ~/.config/wallust/wallust.toml
for detecting the configured palette type. It replaces duplicate code in
palette.py and VarietyWindow.py with a cached, efficient implementation.
"""

import os
import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _normalize_palette_name(name: str) -> str:
    """Normalize palette name to title case.

    Examples:
        'dark16' -> 'Dark16'
        'LIGHT16' -> 'Light16'
        'harddark16' -> 'Harddark16'
        'myCustomPalette' -> 'Mycustompalette'

    Args:
        name: Raw palette name from config

    Returns:
        Normalized palette name with first letter capitalized
    """
    if not name:
        return 'Dark16'
    normalized = name.lower()
    return normalized[0].upper() + normalized[1:] if len(normalized) > 1 else normalized.upper()


def parse_wallust_config(config_path: Optional[str] = None) -> Dict[str, str]:
    """Parse wallust.toml and extract relevant settings.

    This is a simple line-by-line parser that handles both quoted
    and unquoted values.

    Args:
        config_path: Path to wallust.toml. If None, uses default location.

    Returns:
        Dictionary with keys:
            - palette_type: Normalized palette type (e.g., 'Dark16')
            - backend: Backend setting (e.g., 'wal', 'resized')
            - color_space: Color space setting (e.g., 'lch', 'lab')
            - config_path: Path to config file
            - config_mtime: Modification time of config file, or None
    """
    if config_path is None:
        config_path = os.path.expanduser('~/.config/wallust/wallust.toml')

    result = {
        'palette_type': 'Dark16',
        'backend': 'wal',
        'color_space': 'auto',
        'config_path': config_path,
        'config_mtime': None,
    }

    if not os.path.exists(config_path):
        return result

    try:
        result['config_mtime'] = os.path.getmtime(config_path)

        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Stop at [templates] section - only care about main settings
                if line.startswith('['):
                    break

                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    # Remove quotes (single or double) and whitespace
                    value = value.strip().strip('"\'')

                    if key == 'palette':
                        result['palette_type'] = _normalize_palette_name(value)
                    elif key == 'backend':
                        result['backend'] = value
                    elif key == 'color_space':
                        result['color_space'] = value
    except Exception as e:
        logger.warning("Failed to parse wallust config: %s", e)

    return result


class WallustConfigManager:
    """Manages wallust.toml parsing with caching and change detection.

    This class caches the parsed configuration and automatically
    re-parses when the config file's modification time changes.
    """

    def __init__(self):
        self._config_cache: Optional[Dict[str, str]] = None
        self._config_mtime: Optional[float] = None

    def get_palette_type(self) -> str:
        """Get palette type, using cache if config unchanged.

        Returns:
            Palette type string like 'Dark16', 'Light16', etc.
        """
        config = self._get_config()
        return config['palette_type']

    def get_config(self) -> Dict[str, str]:
        """Get full configuration dictionary.

        Returns:
            Dictionary with palette_type, backend, color_space keys.
        """
        return self._get_config().copy()

    def _get_config(self) -> Dict[str, str]:
        """Get wallust config, re-parsing if file changed."""
        config_path = os.path.expanduser('~/.config/wallust/wallust.toml')

        if not os.path.exists(config_path):
            self._config_cache = None
            self._config_mtime = None
            return {'palette_type': 'Dark16', 'backend': 'wal', 'color_space': 'auto'}

        try:
            current_mtime = os.path.getmtime(config_path)
        except OSError:
            return {'palette_type': 'Dark16', 'backend': 'wal', 'color_space': 'auto'}

        if self._config_cache is None or self._config_mtime != current_mtime:
            self._config_cache = parse_wallust_config()
            self._config_mtime = current_mtime

        return self._config_cache

    def invalidate_cache(self):
        """Force cache invalidation."""
        self._config_cache = None
        self._config_mtime = None


def find_latest_palette_cache(palette_type: str) -> Optional[str]:
    """Find most recently modified palette cache file.

    Searches ~/.cache/wallust for cache files containing the
    specified palette type.

    Args:
        palette_type: Palette type like 'Dark16'

    Returns:
        Path to latest cache file or None if not found
    """
    cache_dir = os.path.expanduser('~/.cache/wallust')
    if not os.path.isdir(cache_dir):
        return None

    latest_file = None
    latest_time = 0

    try:
        for entry in os.listdir(cache_dir):
            entry_path = os.path.join(cache_dir, entry)
            if os.path.isdir(entry_path):
                try:
                    for subfile in os.listdir(entry_path):
                        if palette_type in subfile:
                            filepath = os.path.join(entry_path, subfile)
                            try:
                                mtime = os.path.getmtime(filepath)
                                if mtime > latest_time:
                                    latest_time = mtime
                                    latest_file = filepath
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        return None

    return latest_file


# Global shared instance for efficiency
_global_config_manager: Optional[WallustConfigManager] = None


def get_config_manager() -> WallustConfigManager:
    """Get the global WallustConfigManager instance.

    Returns:
        Shared WallustConfigManager instance
    """
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = WallustConfigManager()
    return _global_config_manager
