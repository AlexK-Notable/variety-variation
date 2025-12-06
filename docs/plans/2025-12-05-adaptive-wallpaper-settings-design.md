# Adaptive Wallpaper Settings Panel Design

## Overview

Add a new "Smart Selection" tab to Variety's preferences dialog that exposes the Smart Selection Engine configuration to users, enabling personalized wallpaper selection behavior.

## Goals

1. **Expose hidden intelligence** - Make smart selection configurable
2. **Enable color preferences** - Let users choose warm/cool/adaptive colors
3. **Add time-of-day adaptation** - Automatically adjust color temperature by time
4. **Provide feedback** - Show selection statistics and behavior insights

## UI Design

### Tab Structure

New tab: **"Smart Selection"** (position: after Filters, index 7)

```
┌─────────────────────────────────────────────────────────────┐
│ [General] [Wallpaper] [Quotes] [Clock] [Sources] [Filters]  │
│ [Smart Selection] [Customize] [Tips] [Changelog] [Donate]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ☑ Enable Smart Selection                                   │
│                                                             │
│  ─── Selection Behavior ─────────────────────────────────   │
│                                                             │
│  Image cooldown:     [████████░░░░░░] 7 days                │
│  Source cooldown:    [██░░░░░░░░░░░░] 1 day                 │
│  Favorites boost:    [████░░░░░░░░░░] 2.0x                  │
│  New image boost:    [███░░░░░░░░░░░] 1.5x                  │
│  Decay function:     [Exponential ▼]                        │
│                                                             │
│  ─── Color Preferences ──────────────────────────────────   │
│                                                             │
│  ☑ Enable color-aware selection                             │
│  Color temperature:  [Adaptive (time-based) ▼]              │
│  Color similarity:   [██████░░░░░░░░] 60%                   │
│                                                             │
│  ─── Time-of-Day Adaptation ─────────────────────────────   │
│                                                             │
│  ☑ Adjust colors by time of day                             │
│     Morning (6-12):  Cool/bright wallpapers                 │
│     Afternoon (12-18): Neutral tones                        │
│     Evening (18-22): Warm/cozy wallpapers                   │
│     Night (22-6):    Dark/muted wallpapers                  │
│                                                             │
│  ─── Statistics ─────────────────────────────────────────   │
│                                                             │
│  Images indexed: 1,234     Sources: 5                       │
│  Images with palettes: 892 (72%)                            │
│  Total selections: 4,521   Unique shown: 678                │
│                                                             │
│  [Rebuild Index]  [Extract All Palettes]  [Clear History]   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Widget Specifications

#### Enable Smart Selection
- **Widget**: GtkCheckButton
- **ID**: `smart_selection_enabled`
- **Default**: True
- **Behavior**: Disables all other controls when unchecked

#### Image Cooldown
- **Widget**: GtkScale + GtkLabel
- **ID**: `smart_image_cooldown`, `smart_image_cooldown_label`
- **Range**: 0-30 days
- **Default**: 7
- **Label format**: "{value} days" or "Disabled" if 0

#### Source Cooldown
- **Widget**: GtkScale + GtkLabel
- **ID**: `smart_source_cooldown`, `smart_source_cooldown_label`
- **Range**: 0-7 days
- **Default**: 1
- **Label format**: "{value} days" or "Disabled" if 0

#### Favorites Boost
- **Widget**: GtkScale + GtkLabel
- **ID**: `smart_favorite_boost`, `smart_favorite_boost_label`
- **Range**: 1.0-5.0
- **Default**: 2.0
- **Step**: 0.5
- **Label format**: "{value:.1f}x"

#### New Image Boost
- **Widget**: GtkScale + GtkLabel
- **ID**: `smart_new_boost`, `smart_new_boost_label`
- **Range**: 1.0-3.0
- **Default**: 1.5
- **Step**: 0.25
- **Label format**: "{value:.1f}x"

#### Decay Function
- **Widget**: GtkComboBoxText
- **ID**: `smart_decay_type`
- **Options**: Exponential (smooth), Linear, Step (hard cutoff)
- **Default**: Exponential

#### Color-Aware Selection
- **Widget**: GtkCheckButton
- **ID**: `smart_color_enabled`
- **Default**: False
- **Behavior**: Enables color temperature and similarity controls

#### Color Temperature
- **Widget**: GtkComboBoxText
- **ID**: `smart_color_temperature`
- **Options**:
  - Warm (cozy, sunset tones)
  - Neutral (balanced)
  - Cool (crisp, blue tones)
  - Adaptive (time-based)
- **Default**: Adaptive

#### Color Similarity Threshold
- **Widget**: GtkScale + GtkLabel
- **ID**: `smart_color_similarity`, `smart_color_similarity_label`
- **Range**: 0-100%
- **Default**: 50
- **Label format**: "{value}%"

#### Time-of-Day Adaptation
- **Widget**: GtkCheckButton
- **ID**: `smart_time_adaptation`
- **Default**: True (when color-aware is enabled)
- **Behavior**: Only visible when "Adaptive" temperature selected

#### Statistics Labels
- **Widget**: GtkLabel (read-only)
- **IDs**: `smart_stats_indexed`, `smart_stats_sources`, `smart_stats_palettes`, `smart_stats_selections`
- **Updated**: On tab activation and after operations

#### Action Buttons
- **Rebuild Index**: Re-scan all configured source folders
- **Extract All Palettes**: Extract color palettes for all indexed images
- **Clear History**: Reset selection history (keep index)

## Configuration

### New Options (variety.conf)

```ini
# Smart Selection
smart_selection_enabled = True
smart_image_cooldown_days = 7
smart_source_cooldown_days = 1
smart_favorite_boost = 2.0
smart_new_boost = 1.5
smart_decay_type = exponential
smart_color_enabled = False
smart_color_temperature = adaptive
smart_color_similarity = 50
smart_time_adaptation = True
```

### Options.py Changes

Add to `set_defaults()`:
```python
self.smart_selection_enabled = True
self.smart_image_cooldown_days = 7.0
self.smart_source_cooldown_days = 1.0
self.smart_favorite_boost = 2.0
self.smart_new_boost = 1.5
self.smart_decay_type = 'exponential'
self.smart_color_enabled = False
self.smart_color_temperature = 'adaptive'
self.smart_color_similarity = 50
self.smart_time_adaptation = True
```

## Time-of-Day Logic

### Color Temperature by Time Period

| Period | Hours | Temperature Target | Description |
|--------|-------|-------------------|-------------|
| Morning | 6:00-12:00 | Cool (0.3) | Bright, energizing |
| Afternoon | 12:00-18:00 | Neutral (0.5) | Balanced |
| Evening | 18:00-22:00 | Warm (0.7) | Cozy, relaxing |
| Night | 22:00-6:00 | Neutral-dark (0.4) | Muted, calm |

### Implementation

Add to `selector.py`:
```python
def get_time_based_temperature(self) -> float:
    """Get target color temperature based on current time."""
    hour = datetime.now().hour

    if 6 <= hour < 12:      # Morning
        return 0.3  # Cool
    elif 12 <= hour < 18:   # Afternoon
        return 0.5  # Neutral
    elif 18 <= hour < 22:   # Evening
        return 0.7  # Warm
    else:                   # Night
        return 0.4  # Neutral-dark
```

## Statistics Collection

### Database Queries

```python
def get_selection_statistics(self) -> dict:
    """Get statistics for the preferences display."""
    return {
        'images_indexed': self.db.count_images(),
        'sources_count': self.db.count_sources(),
        'images_with_palettes': self.db.count_images_with_palettes(),
        'total_selections': self.db.sum_times_shown(),
        'unique_shown': self.db.count_shown_images(),
    }
```

## Integration Points

### VarietyWindow.py

1. Load smart selection config from options
2. Pass config to SmartSelector initialization
3. Reload selector when preferences change
4. Enable palette extraction when color-aware enabled

### PreferencesVarietyDialog.py

1. Add reload logic for new widgets
2. Add apply logic to save settings
3. Add statistics refresh on tab activation
4. Add handlers for action buttons

## File Changes Summary

| File | Changes |
|------|---------|
| `Options.py` | Add 10 new options |
| `PreferencesVarietyDialog.py` | Add reload/apply for Smart Selection tab |
| `PreferencesVarietyDialog.ui` | Add Smart Selection tab with all widgets |
| `selector.py` | Add time-based temperature, statistics methods |
| `database.py` | Add count/statistics queries |
| `VarietyWindow.py` | Load config from options, reload on change |

## Testing

1. UI renders correctly with all widgets
2. Settings save and load properly
3. Smart selection respects new config
4. Time-of-day adaptation works
5. Statistics display accurately
6. Action buttons function correctly
