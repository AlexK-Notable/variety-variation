# Time Adaptation & User Documentation Design

**Date:** 2025-12-30
**Status:** Approved for Implementation

---

## Overview

Two features for the Smart Selection Engine:

1. **Time Adaptation**: Automatically adjust wallpaper palette preferences based on time of day
2. **User Documentation**: Tooltips and info popovers for all Smart Selection controls

---

## Part 1: Time Adaptation

### 1.1 Timing Methods

Three user-selectable methods to determine day vs night:

#### Sunrise/Sunset
- User enters location (city name resolved to coordinates, or manual lat/long)
- Calculate sunrise/sunset using astronomical formulas
- Use Python `astral` library (already handles DST, timezones)
- Optional: GeoClue D-Bus integration for automatic location

**Implementation:**
```python
# variety/smart_selection/time_adapter.py
from astral import LocationInfo
from astral.sun import sun

def get_sun_times(lat: float, lon: float, date: datetime.date) -> Tuple[datetime, datetime]:
    """Calculate sunrise and sunset for given location and date."""
    location = LocationInfo(latitude=lat, longitude=lon)
    s = sun(location.observer, date=date)
    return s['sunrise'], s['sunset']
```

#### Fixed Schedule
- Two time values: day_start_time, night_start_time
- Defaults: "07:00" and "19:00"
- Simple string comparison with current time

#### System Theme
- Monitor `org.freedesktop.portal.Settings` for `org.freedesktop.appearance color-scheme`
- Fallback to `org.gnome.desktop.interface color-scheme` via Gio.Settings
- Values: 0=no preference, 1=dark, 2=light

**Implementation:**
```python
# variety/smart_selection/time_adapter.py
from gi.repository import Gio

def get_system_theme_preference() -> str:
    """Get current system theme preference. Returns 'day' or 'night'."""
    try:
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        scheme = settings.get_string("color-scheme")
        return "night" if scheme == "prefer-dark" else "day"
    except Exception:
        return "day"  # Default to day if detection fails
```

### 1.2 Palette Preferences

#### Preset Profiles

```python
# variety/smart_selection/time_adapter.py
PALETTE_PRESETS = {
    "bright_day": {
        "lightness": 0.7,
        "temperature": 0.3,
        "saturation": 0.6,
        "description": "Energetic, sunlit feel"
    },
    "neutral_day": {
        "lightness": 0.6,
        "temperature": 0.0,
        "saturation": 0.5,
        "description": "Balanced, non-distracting"
    },
    "cozy_night": {
        "lightness": 0.3,
        "temperature": 0.4,
        "saturation": 0.4,
        "description": "Warm, dim, relaxed"
    },
    "cool_night": {
        "lightness": 0.25,
        "temperature": -0.3,
        "saturation": 0.5,
        "description": "Blue-tinted, modern"
    },
    "dark_mode": {
        "lightness": 0.2,
        "temperature": 0.0,
        "saturation": 0.4,
        "description": "Minimal eye strain"
    },
    "custom": {
        "lightness": None,
        "temperature": None,
        "saturation": None,
        "description": "User-defined values"
    }
}
```

#### Custom Sliders

When preset is "custom" or "Advanced" is toggled:
- **Target Lightness** (0.0–1.0): Scale with 0.05 steps
- **Target Temperature** (-1.0 to +1.0): Scale with 0.1 steps
- **Target Saturation** (0.0–1.0): Scale with 0.05 steps
- **Tolerance** (0.1–0.5): How strictly to match, 0.05 steps

### 1.3 Selection Engine Integration

#### TimeAdapter Class

```python
# variety/smart_selection/time_adapter.py

@dataclass
class PaletteTarget:
    """Target palette characteristics for a time period."""
    lightness: float
    temperature: float
    saturation: float
    tolerance: float = 0.3

class TimeAdapter:
    """Manages time-based palette preferences."""

    def __init__(self, config: SelectionConfig):
        self.config = config
        self._last_period: Optional[str] = None

    def get_current_period(self) -> str:
        """Get current time period: 'day' or 'night'."""
        method = self.config.time_adaptation_method

        if method == "sunrise_sunset":
            return self._get_period_sunrise_sunset()
        elif method == "fixed":
            return self._get_period_fixed()
        elif method == "system_theme":
            return self._get_period_system_theme()
        else:
            return "day"

    def get_palette_target(self) -> PaletteTarget:
        """Get target palette for current time period."""
        period = self.get_current_period()

        if period == "day":
            preset = self.config.day_preset
            if preset == "custom":
                return PaletteTarget(
                    lightness=self.config.day_lightness,
                    temperature=self.config.day_temperature,
                    saturation=self.config.day_saturation,
                    tolerance=self.config.palette_tolerance,
                )
            return self._preset_to_target(preset)
        else:
            preset = self.config.night_preset
            if preset == "custom":
                return PaletteTarget(
                    lightness=self.config.night_lightness,
                    temperature=self.config.night_temperature,
                    saturation=self.config.night_saturation,
                    tolerance=self.config.palette_tolerance,
                )
            return self._preset_to_target(preset)
```

#### Weight Calculation Integration

```python
# In weights.py - add time affinity factor

def calculate_time_affinity(
    image_palette: Optional[PaletteRecord],
    target: PaletteTarget,
    use_oklab: bool = True,
) -> float:
    """Calculate affinity score between image palette and time target.

    Returns:
        Multiplier from 0.5 (poor match) to 1.5 (excellent match).
    """
    if not image_palette:
        return 1.0  # No penalty if no palette data

    # Calculate distance in each dimension
    lightness_diff = abs(image_palette.avg_lightness - target.lightness)
    temp_diff = abs(image_palette.color_temperature - target.temperature)
    sat_diff = abs(image_palette.avg_saturation - target.saturation)

    # Weighted average (lightness matters most for day/night)
    distance = (lightness_diff * 0.5) + (temp_diff * 0.3) + (sat_diff * 0.2)

    # Convert distance to affinity score using tolerance
    # distance=0 -> 1.5, distance>=tolerance -> 0.5
    if distance >= target.tolerance:
        return 0.5

    affinity = 1.5 - (distance / target.tolerance)
    return max(0.5, min(1.5, affinity))
```

### 1.4 Configuration Options

Add to `variety/Options.py`:

```python
# Time adaptation settings
self.smart_time_adaptation = True
self.smart_time_method = "fixed"  # "sunrise_sunset", "fixed", "system_theme"
self.smart_day_start = "07:00"
self.smart_night_start = "19:00"
self.smart_location_lat = None
self.smart_location_lon = None
self.smart_location_name = ""
self.smart_day_preset = "neutral_day"
self.smart_night_preset = "cozy_night"
self.smart_day_lightness = 0.6
self.smart_day_temperature = 0.0
self.smart_day_saturation = 0.5
self.smart_night_lightness = 0.3
self.smart_night_temperature = 0.4
self.smart_night_saturation = 0.4
self.smart_palette_tolerance = 0.3
```

Add to `variety/smart_selection/config.py`:

```python
@dataclass
class SelectionConfig:
    # ... existing fields ...

    # Time adaptation
    time_adaptation_enabled: bool = True
    time_adaptation_method: str = "fixed"
    day_start_time: str = "07:00"
    night_start_time: str = "19:00"
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    day_preset: str = "neutral_day"
    night_preset: str = "cozy_night"
    day_lightness: float = 0.6
    day_temperature: float = 0.0
    day_saturation: float = 0.5
    night_lightness: float = 0.3
    night_temperature: float = 0.4
    night_saturation: float = 0.4
    palette_tolerance: float = 0.3
```

### 1.5 UI Changes

#### Unhide Existing Controls
- Remove `set_visible(False)` calls in `PreferencesVarietyDialog.py:1559-1564`

#### Add New Controls to PreferencesVarietyDialog.ui

```
Smart Selection Tab
└── Time Adaptation Section
    ├── [x] Enable time adaptation (checkbox)
    ├── Timing Method: [Dropdown: Sunrise/Sunset | Fixed Schedule | System Theme]
    │
    ├── [If Sunrise/Sunset]
    │   ├── Location: [Entry] [Lookup Button]
    │   └── Status: "Sunrise: 07:23, Sunset: 17:45"
    │
    ├── [If Fixed Schedule]
    │   ├── Day starts at: [Time Picker]
    │   └── Night starts at: [Time Picker]
    │
    ├── [If System Theme]
    │   └── Status: "Following system theme (currently: Dark)"
    │
    ├── Current Mode: "Day" / "Night" indicator
    │
    ├── Day Preferences
    │   ├── Preset: [Dropdown]
    │   └── [Advanced toggle reveals sliders]
    │
    └── Night Preferences
        ├── Preset: [Dropdown]
        └── [Advanced toggle reveals sliders]
```

---

## Part 2: User Documentation (Tooltips & Popovers)

### 2.1 Tooltip Content

Every control gets a concise tooltip (one sentence):

| Control | Tooltip |
|---------|---------|
| Smart Selection enabled | "Use intelligent selection instead of random" |
| Image cooldown | "Days before a wallpaper can repeat" |
| Source cooldown | "Days before favoring the same source again" |
| Favorites boost | "How much more likely favorites are selected" |
| Color matching | "Prefer wallpapers with similar color palettes" |
| Time adaptation | "Adjust palette preferences based on time of day" |
| Timing method | "How to determine day vs night" |
| Day/Night preset | "Quick palette preference settings" |
| Lightness slider | "Target brightness: 0=dark, 1=bright" |
| Temperature slider | "Color warmth: -1=cool/blue, +1=warm/orange" |
| Saturation slider | "Color intensity: 0=muted, 1=vibrant" |
| Tolerance slider | "How strictly to match: lower=stricter" |

### 2.2 Info Popover Content

Each section gets an info button (?) that opens a popover with 2-3 paragraphs:

#### Smart Selection Overview
> Smart Selection replaces random wallpaper rotation with intelligent weighted selection. Images are scored based on recency (recently shown = lower score), source diversity, favorites status, and color palette matching.
>
> The algorithm ensures variety while respecting your preferences. Favorites appear more often, recently shown images get a cooldown period, and sources are balanced so one folder doesn't dominate.
>
> Statistics show how many images are indexed, how many have color palettes extracted, and selection history.

#### Time Adaptation
> Time adaptation adjusts which wallpapers are preferred based on the time of day. During the day, brighter and optionally warmer palettes are favored. At night, darker and cooler palettes take priority.
>
> Three timing methods are available: Sunrise/Sunset uses your location to calculate actual daylight hours. Fixed Schedule lets you set specific times. System Theme follows your desktop's dark/light mode setting.
>
> Presets provide quick configurations, or use Custom with the sliders for precise control. The Tolerance setting controls how strictly palettes must match—lower values mean stricter matching with less variety.

#### Color Matching
> Color matching uses the OKLAB perceptual color space to find wallpapers with similar palettes. OKLAB ensures that visually similar colors are mathematically close, unlike simpler color models.
>
> When enabled, wallpapers with palettes similar to your target preferences receive a selection boost. This works alongside time adaptation—if both are enabled, the current time period's target palette is used.
>
> Palettes are automatically extracted when wallpapers are shown, using wallust. The "Images with palettes" statistic shows extraction progress.

### 2.3 Implementation

```python
# variety/PreferencesVarietyDialog.py

TOOLTIPS = {
    "smart_selection_enabled": _("Use intelligent selection instead of random"),
    "smart_image_cooldown": _("Days before a wallpaper can repeat"),
    # ... etc
}

HELP_CONTENT = {
    "smart_selection_overview": _(
        "Smart Selection replaces random wallpaper rotation with intelligent "
        "weighted selection. Images are scored based on recency, source diversity, "
        "favorites status, and color palette matching.\n\n"
        "The algorithm ensures variety while respecting your preferences..."
    ),
    # ... etc
}

def _setup_tooltips(self):
    """Apply tooltips to all Smart Selection controls."""
    for widget_name, tooltip in TOOLTIPS.items():
        widget = getattr(self.ui, widget_name, None)
        if widget:
            widget.set_tooltip_text(tooltip)

def _setup_help_buttons(self):
    """Connect info buttons to popover displays."""
    # Each info button shows a Gtk.Popover with formatted help text
    pass
```

---

## Implementation Plan

### Agent 1: Time Adapter Core
**Files:** `variety/smart_selection/time_adapter.py` (new), tests
**Scope:**
- TimeAdapter class with all three timing methods
- PaletteTarget dataclass
- PALETTE_PRESETS dictionary
- Sunrise/sunset calculation (astral library)
- System theme detection (GSettings/portal)
- Unit tests for all timing methods

### Agent 2: Config & Weight Integration
**Files:** `variety/smart_selection/config.py`, `variety/smart_selection/weights.py`, `variety/Options.py`, tests
**Scope:**
- Add all time adaptation config fields to SelectionConfig
- Add config fields to Options.py with load/save
- Implement calculate_time_affinity() in weights.py
- Integrate time affinity into calculate_weight()
- Unit tests for config and weight calculations

### Agent 3: UI Implementation
**Files:** `data/ui/PreferencesVarietyDialog.ui`, `variety/PreferencesVarietyDialog.py`
**Scope:**
- Unhide time adaptation controls
- Add new UI elements (timing method dropdown, presets, sliders)
- Wire up all controls to config values
- Add current mode indicator
- Conditional visibility based on timing method

### Agent 4: Tooltips & Help Popovers
**Files:** `variety/PreferencesVarietyDialog.py`
**Scope:**
- Define TOOLTIPS dictionary
- Define HELP_CONTENT dictionary
- Implement _setup_tooltips() method
- Implement info button popovers
- Apply to all Smart Selection controls

### Agent 5: Integration & Selector Updates
**Files:** `variety/smart_selection/selector.py`, `variety/VarietyWindow.py`
**Scope:**
- Instantiate TimeAdapter in SmartSelector
- Pass time affinity to selection pipeline
- Update VarietyWindow integration if needed
- Integration tests

---

## Dependencies

- `astral` library for sunrise/sunset (add to requirements)
- Existing: `gi.repository.Gio` for GSettings

---

## Test Requirements

- Unit tests for each timing method
- Unit tests for palette target calculation
- Unit tests for time affinity scoring
- Integration test: full selection with time adaptation enabled
- UI tests: control visibility, value persistence

---

## Checklist

- [ ] TimeAdapter class implemented
- [ ] All three timing methods working
- [ ] PALETTE_PRESETS defined
- [ ] Config fields added to SelectionConfig
- [ ] Config fields added to Options.py
- [ ] Time affinity integrated into weights.py
- [ ] UI controls unhidden and new controls added
- [ ] All controls wired to config
- [ ] Tooltips applied to all controls
- [ ] Help popovers implemented
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Code review complete
