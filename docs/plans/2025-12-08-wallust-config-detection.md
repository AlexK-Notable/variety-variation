# Wallust Configuration Detection - Implementation Plan

**Date:** 2025-12-08
**Status:** Planned
**Agent:** 26c9cece

---

## Summary

Implement dynamic detection of wallust palette type from `~/.config/wallust/wallust.toml` instead of hardcoding `*Dark16*`.

---

## Wallust Configuration Format

### Example Configuration
```toml
backend = "wal"
color_space = "lch"
palette = "dark16"
check_contrast = true
[templates]
# ... template definitions
```

### Cache File Naming Pattern
```
~/.cache/wallust/{hash}_{version}/{backend}_{color_space}_{palette_type}
```

Example: `FastResize_Lch_auto_Dark16`

### Supported Palette Types
- `dark16` / `Dark16` - Standard 16-color dark palette (default)
- `light16` / `Light16` - 16-color light palette
- `harddark16` / `Harddark16` - High contrast dark palette
- `hardlight16` / `Hardlight16` - High contrast light palette
- Custom user-defined names

---

## Current Implementation Issues

1. **Code Duplication** - Same logic in `palette.py` and `VarietyWindow.py`
2. **Naive Title Case** - `palette[0].upper() + palette[1:]` breaks custom names
3. **No Caching** - Reads TOML on every palette extraction
4. **Simplistic Regex** - Only handles quoted strings
5. **No Change Detection** - Can't detect config modifications

---

## Proposed Implementation

### 1. Centralized Configuration Parser

Create `/home/komi/repos/variety-variation/variety/smart_selection/wallust_config.py`:

```python
"""Wallust configuration detection with caching."""

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
    """
    if not name:
        return 'Dark16'
    normalized = name.lower()
    return normalized[0].upper() + normalized[1:] if len(normalized) > 1 else normalized.upper()


def parse_wallust_config(config_path: Optional[str] = None) -> Dict[str, str]:
    """Parse wallust.toml and extract relevant settings.

    Returns:
        {
            'palette_type': 'Dark16',
            'backend': 'wal',
            'color_space': 'lch',
            'config_path': '/home/user/.config/wallust/wallust.toml',
            'config_mtime': 1733700000.0
        }
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

                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')

                    if key == 'palette':
                        result['palette_type'] = _normalize_palette_name(value)
                    elif key == 'backend':
                        result['backend'] = value
                    elif key == 'color_space':
                        result['color_space'] = value
    except Exception as e:
        logger.warning(f"Failed to parse wallust config: {e}")

    return result


class WallustConfigManager:
    """Manages wallust.toml parsing with caching and change detection."""

    def __init__(self):
        self._config_cache: Optional[Dict[str, str]] = None
        self._config_mtime: Optional[float] = None

    def get_palette_type(self) -> str:
        """Get palette type, using cache if config unchanged."""
        config = self._get_config()
        return config['palette_type']

    def _get_config(self) -> Dict[str, str]:
        """Get wallust config, re-parsing if file changed."""
        config_path = os.path.expanduser('~/.config/wallust/wallust.toml')

        if not os.path.exists(config_path):
            self._config_cache = None
            self._config_mtime = None
            return {'palette_type': 'Dark16', 'backend': 'wal', 'color_space': 'auto'}

        current_mtime = os.path.getmtime(config_path)

        if self._config_cache is None or self._config_mtime != current_mtime:
            self._config_cache = parse_wallust_config()
            self._config_mtime = current_mtime

        return self._config_cache

    def invalidate_cache(self):
        """Force cache invalidation."""
        self._config_cache = None
        self._config_mtime = None
```

### 2. Cache File Pattern Matching

```python
def find_latest_palette_cache(palette_type: str) -> Optional[str]:
    """Find most recently modified palette cache file.

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

    for entry in os.listdir(cache_dir):
        entry_path = os.path.join(cache_dir, entry)
        if os.path.isdir(entry_path):
            for subfile in os.listdir(entry_path):
                if palette_type in subfile:
                    filepath = os.path.join(entry_path, subfile)
                    mtime = os.path.getmtime(filepath)
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_file = filepath

    return latest_file
```

### 3. Update Existing Code

**In `palette.py`:**
```python
from variety.smart_selection.wallust_config import WallustConfigManager

class PaletteExtractor:
    def __init__(self, ...):
        self._config_manager = WallustConfigManager()

    def _get_palette_type(self) -> str:
        return self._config_manager.get_palette_type()
```

**In `VarietyWindow.py`:**
```python
from variety.smart_selection.wallust_config import WallustConfigManager

# In __init__ or _init_smart_selector:
self._wallust_config = WallustConfigManager()

def _read_wallust_cache_for_image(self, filepath: str):
    palette_type = self._wallust_config.get_palette_type()
    # ... rest of method
```

---

## Test Cases (44 Total)

### Unit Tests - Config Parsing (23)

```python
def test_parse_wallust_config_with_dark16():
def test_parse_wallust_config_with_light16():
def test_parse_wallust_config_with_harddark16():
def test_parse_wallust_config_with_uppercase():
def test_parse_wallust_config_with_mixed_case():
def test_parse_wallust_config_missing_file():
def test_parse_wallust_config_empty_file():
def test_parse_wallust_config_malformed():
def test_parse_wallust_config_palette_unquoted():
def test_parse_wallust_config_palette_single_quoted():
def test_parse_wallust_config_palette_with_spaces():
def test_parse_wallust_config_custom_palette():
def test_normalize_palette_name_lowercase():
def test_normalize_palette_name_uppercase():
def test_normalize_palette_name_mixed():
def test_normalize_palette_name_empty():
# ... more
```

### Cache Management Tests (6)

```python
def test_config_manager_uses_cache():
def test_config_manager_invalidates_on_mtime_change():
def test_config_manager_handles_deleted_file():
def test_config_manager_detects_palette_change():
# ...
```

### Integration Tests (6)

```python
def test_find_latest_palette_cache_dark16():
def test_find_latest_palette_cache_light16():
def test_find_latest_palette_cache_with_multiple_entries():
def test_find_latest_palette_cache_missing():
def test_extract_palette_uses_configured_type():
def test_variety_window_reads_correct_palette_type():
```

### Error Handling Tests (9)

```python
def test_parse_wallust_config_permission_denied():
def test_parse_wallust_config_symlink_loop():
def test_parse_wallust_config_very_large_file():
def test_parse_wallust_config_invalid_utf8():
def test_find_palette_cache_permission_denied():
def test_find_palette_cache_broken_symlink():
# ...
```

---

## Files to Create/Modify

1. **Create:** `variety/smart_selection/wallust_config.py` - New centralized module
2. **Create:** `tests/smart_selection/test_wallust_config.py` - Test suite
3. **Modify:** `variety/smart_selection/palette.py` - Use centralized parser
4. **Modify:** `variety/VarietyWindow.py` - Use centralized parser

---

## Fallback Behavior

1. Try to read `~/.config/wallust/wallust.toml`
2. If missing/unreadable → use default `Dark16`
3. If `palette` setting missing → use default `Dark16`
4. If palette type produces no cache files → try `Dark16` as fallback
5. If still no cache → return None (graceful degradation)
