# Theming Engine Design

**Date:** 2025-12-07
**Status:** Draft
**Goal:** Pre-generate wallust templates from cached palette data for instant theme switching on wallpaper change.

## Problem

Currently, when Variety changes wallpaper, wallust must:
1. Process the image to extract colors (~100-200ms)
2. Generate all template files (~50ms)
3. Write to target locations

This delays theme application. We want to front-load computation by pre-indexing palettes and generating templates ourselves from cached data.

## Solution Overview

New module `variety/smart_selection/theming.py` that:
- Reads palette data from our database (already indexed)
- Parses wallust template syntax
- Applies color transformations (darken, lighten, saturate, etc.)
- Writes to target paths from wallust.toml
- Triggers app reload commands

**Performance target:** <20ms template generation (vs ~200ms with wallust)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ThemeEngine                          │
├─────────────────────────────────────────────────────────┤
│  ColorTransformer    │  TemplateProcessor  │  Reloader │
│  - darken()          │  - parse_template() │  - reload │
│  - lighten()         │  - apply_filters()  │    apps   │
│  - saturate()        │  - render()         │           │
│  - desaturate()      │                     │           │
│  - blend()           │                     │           │
│  - strip()           │                     │           │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. Wallpaper changes → Look up palette in our database
2. If not found → Extract via wallust, store in DB
3. Load template config from `~/.config/wallust/wallust.toml`
4. Check `~/.config/variety/theming.json` for enabled/disabled overrides
5. For each enabled template:
   - Read template file
   - Apply color transformations
   - Write to target path
6. Trigger reload commands for affected apps

### Database Change

Add `cursor` field to `PaletteRecord` (used by 3 templates: alacritty, ghostty, hyprland).

## Configuration

### Template Source: `~/.config/wallust/wallust.toml`

We parse the existing wallust config to get template definitions:
```toml
[templates]
hyprland = { template = "hyprland.conf", target = "/home/user/.config/hypr/colors.conf" }
waybar = { template = "waybar.css", target = "/home/user/.config/waybar/colors.css" }
```

### Variety Override: `~/.config/variety/theming.json`

Optional config to enable/disable specific templates and override reload commands:
```json
{
  "enabled": true,
  "templates": {
    "hyprland": true,
    "waybar": true,
    "discord": false,
    "wofi_colors": false
  },
  "reload_commands": {
    "hyprland": "hyprctl reload",
    "waybar": "killall -SIGUSR2 waybar"
  }
}
```

**Behavior:**
- Template listed with `true` → process it
- Template listed with `false` → skip it
- Template not listed → enabled by default (from wallust.toml)
- `reload_commands` override built-in defaults
- Set `"enabled": false` to disable theming entirely
- File is optional - if missing, all templates processed with defaults

## Color Transformations

### Supported Filters

| Filter | Description | Example |
|--------|-------------|---------|
| `strip` | Remove `#` prefix | `#ff0000` → `ff0000` |
| `darken(n)` | Reduce lightness by n | `darken(0.2)` |
| `lighten(n)` | Increase lightness by n | `lighten(0.1)` |
| `saturate(n)` | Increase saturation by n | `saturate(0.5)` |
| `desaturate(n)` | Decrease saturation by n | `desaturate(0.8)` |
| `blend(color)` | Average RGB with another palette color | `blend(color2)` |

### Filter Chaining

Filters are applied left-to-right:
```
{{color4 | saturate(0.3) | darken(0.2) | strip}}
```

### Implementation

```python
def hex_to_hsl(hex_color: str) -> Tuple[float, float, float]  # exists in palette.py
def hsl_to_hex(h: float, s: float, l: float) -> str           # new
def blend_colors(hex1: str, hex2: str) -> str                  # new
def apply_filter(color: str, filter_name: str, arg: Any, palette: dict) -> str
```

Note: `blend(colorN)` requires access to full palette dict to resolve color references.

## Reload Commands

### Built-in Defaults

```python
DEFAULT_RELOADS = {
    "hyprland": "hyprctl reload",
    "waybar": "killall -SIGUSR2 waybar",
    "gtk3": None,      # Apps pick up on next window open
    "gtk4": None,
    "alacritty": None, # Auto-reloads on file change
    "ghostty": None,   # Auto-reloads on file change
    "kvantum": "kvantummanager --set Wallust",
}
```

Apps like Alacritty and Ghostty watch their config files and auto-reload.

### Override via Config

Users can override in `theming.json`:
```json
{
  "reload_commands": {
    "waybar": "systemctl --user restart waybar"
  }
}
```

## Integration with Variety

### Automatic Theming

In `VarietyWindow.set_wallpaper()`:
```python
def set_wallpaper(self, filepath, ...):
    # ... existing wallpaper setting code ...

    if self.theme_engine:
        self.theme_engine.apply(filepath)
```

### CLI Commands

New options:
- `variety --apply-theme` - Apply theme for current wallpaper
- `variety --apply-theme /path/to/image.jpg` - Apply theme for specific image

### Fallback Behavior

- Palette not in DB → Extract via wallust, store, then apply
- Wallust unavailable → Log warning, skip theming
- Template file missing → Skip that template, continue others
- Target directory missing → Create parent directories

## Indexing Strategy

### Hybrid Approach

1. **On-demand:** Extract palette when wallpaper is first shown (immediate use)
2. **Background batch:** Scan all wallpapers during idle time to pre-index

This ensures:
- New wallpapers work immediately
- Over time, all palettes are cached
- Theme application is instant for indexed images

## Testing Strategy

### Comparison Testing

Compare our output against wallust's output for accuracy.

**Test wallpapers:** 12+ images with diverse characteristics:
- 2-3 warm/orange dominant
- 2-3 cool/blue dominant
- 2-3 high saturation/vibrant
- 2-3 low saturation/muted
- 2-3 dark/moody
- 2-3 bright/light

**Comparison points:** 12 wallpapers × ~20 templates = 240+ comparisons

### Fuzzy Matching

Allow ±1 RGB difference per channel for rounding tolerance:
```python
def colors_equivalent(hex1: str, hex2: str, tolerance: int = 1) -> bool:
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    return (abs(r1-r2) <= tolerance and
            abs(g1-g2) <= tolerance and
            abs(b1-b2) <= tolerance)
```

### Unit Tests

Individual tests for each filter function:
- `test_darken_reduces_lightness()`
- `test_lighten_increases_lightness()`
- `test_saturate_increases_saturation()`
- `test_blend_averages_colors()`
- `test_strip_removes_hash()`
- `test_filter_chaining()`

## File Structure

```
variety/smart_selection/
  theming.py          # New: ThemeEngine, ColorTransformer, TemplateProcessor
  models.py           # Modified: Add cursor to PaletteRecord
  palette.py          # Existing: hex_to_hsl (add hsl_to_hex)
  database.py         # Modified: Handle cursor field

tests/smart_selection/
  test_theming.py     # New: Unit tests + comparison tests
```

## Identified Risks & Mitigations

### 1. Template Comments Syntax

**Issue:** Templates use `{# comment #}` syntax (found in discord.css, vesktop-translucence.css) that must be stripped from output.

**Mitigation:** Add comment stripping to TemplateProcessor using regex `\{#.*?#\}` → empty string.

### 2. Color Value Clamping

**Issue:** Extreme filter values could produce invalid colors:
- `darken(0.9)` on already dark colors → negative lightness
- `saturate(1.5)` on saturated colors → saturation > 1.0

**Mitigation:** Clamp all HSL values after each filter operation:
- Hue: wrap to [0, 360)
- Saturation: clamp to [0, 1]
- Lightness: clamp to [0, 1]

### 3. Concurrent Wallpaper Changes

**Issue:** Rapid wallpaper changes could cause:
- Partial template writes (file corruption)
- Race between file write and reload command

**Mitigation:**
- Use atomic writes (write to temp file, then `os.rename()`)
- Add 100ms debounce: skip theming if another change happens within window

### 4. TOML Parsing Errors

**Issue:** wallust.toml could have malformed entries, missing fields, or syntax errors.

**Mitigation:** Wrap parsing in try/except, skip invalid template entries, log warnings, continue with valid entries.

### 5. Reload Command Hangs

**Issue:** A reload command could hang indefinitely (e.g., `hyprctl` when Hyprland is frozen).

**Mitigation:** Run reload commands via subprocess with 5-second timeout. Log timeout errors but don't block.

### 6. File Permission Errors

**Issue:** Target directories might not exist or user might lack write permission.

**Mitigation:**
- Create parent directories with `os.makedirs(exist_ok=True)`
- Catch `PermissionError`, log warning, continue with other templates

### 7. Template I/O Overhead

**Issue:** Reading 20+ template files on every wallpaper change adds latency.

**Mitigation:** Cache parsed templates in memory on first load. Invalidate cache entry if template file mtime changes.

### 8. Incomplete Palettes

**Issue:** Some wallust palettes might be missing colors (e.g., `color7` undefined).

**Mitigation:** Define fallback colors for missing entries:
- `color7` → `foreground`
- `cursor` → `foreground`
- `colorN` → `background` (for any missing 0-15)

## Performance Analysis

### Time Budget Breakdown

| Operation | Estimated Time | Optimization Strategy |
|-----------|----------------|----------------------|
| DB palette lookup | ~1ms | Already indexed by filepath |
| Load & parse templates | ~5ms | Cache in memory, check mtime |
| Apply filters (regex + HSL math) | ~2ms | Pre-compile regex patterns |
| Write 20 files (atomic) | ~10ms | Could use async I/O if needed |
| Reload commands | Variable | Run async with timeout |

**Total estimated time:** ~18ms (within <20ms target)

### Memory Usage

- Template cache: ~500KB for 20 templates (acceptable)
- Compiled regex patterns: negligible
- Palette data: ~2KB per image in database

### Comparison to Wallust

| Approach | Time | Notes |
|----------|------|-------|
| Wallust (full) | ~200ms | Image processing + template generation |
| Wallust (cached palette) | ~50ms | Skip image processing |
| Our ThemeEngine | ~18ms | Pure template processing, no subprocess |

**Speedup:** ~10x faster than full wallust, ~3x faster than cached wallust.

## Success Criteria

1. All 240+ comparison tests pass (our output matches wallust within ±1 RGB tolerance)
2. Template generation completes in <20ms for all templates
3. Reload commands execute successfully with timeout protection
4. Fallback to wallust works when palette not cached
5. CLI commands work as documented
6. Atomic writes prevent file corruption during rapid changes
7. Graceful degradation: individual template failures don't break entire theming
