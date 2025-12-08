# Collection Statistics Feature Design

**Date:** 2025-12-07
**Status:** Approved

## Overview

Add collection statistics to the Smart Selection preferences tab, showing insights about the user's wallpaper collection with progressive disclosure (summary cards that expand to show details).

## Requirements

### Priority Insights (User Selected)
1. **Lightness distribution** - Dark/medium-dark/medium-light/light breakdown
2. **Hue categories** - 8 color families from the color wheel
3. **Saturation gaps** - Identify underrepresented saturation levels
4. **Freshness stats** - Never shown, rarely shown, etc.

### UX Requirements
- Display in Smart Selection preferences tab
- Progressive disclosure: summary cards that expand for details
- Statistics update progressively as database changes
- Non-blocking UI (async calculation with spinner)

## Data Categorization

### Lightness Buckets (avg_lightness 0-1)
| Category | Range |
|----------|-------|
| Dark | 0.00 - 0.25 |
| Medium-dark | 0.25 - 0.50 |
| Medium-light | 0.50 - 0.75 |
| Light | 0.75 - 1.00 |

### Hue Families (avg_hue 0-360°)
| Family | Hue Range |
|--------|-----------|
| Red | 0-15° or 345-360° |
| Orange | 15-45° |
| Yellow | 45-75° |
| Green | 75-165° |
| Cyan | 165-195° |
| Blue | 195-255° |
| Purple | 255-285° |
| Pink | 285-345° |

### Saturation Levels (avg_saturation 0-1)
| Category | Range |
|----------|-------|
| Muted | 0.00 - 0.25 |
| Moderate | 0.25 - 0.50 |
| Saturated | 0.50 - 0.75 |
| Vibrant | 0.75 - 1.00 |

### Freshness Categories (times_shown)
| Category | Range |
|----------|-------|
| Never shown | 0 |
| Rarely shown | 1-4 |
| Often shown | 5-9 |
| Frequently shown | >= 10 |

## Architecture

### New Module: `variety/smart_selection/statistics.py`

```python
class CollectionStatistics:
    """Calculates and caches collection statistics."""

    def __init__(self, db: ImageDatabase):
        self.db = db
        self._cache = {}
        self._cache_valid = False

    def invalidate(self):
        """Mark cache as dirty. Called on data changes."""
        self._cache_valid = False

    def get_lightness_distribution(self) -> Dict[str, int]:
        """Returns {dark: N, medium_dark: N, medium_light: N, light: N}"""

    def get_hue_distribution(self) -> Dict[str, int]:
        """Returns {red: N, orange: N, yellow: N, green: N, ...}"""

    def get_saturation_distribution(self) -> Dict[str, int]:
        """Returns {muted: N, moderate: N, saturated: N, vibrant: N}"""

    def get_freshness_distribution(self) -> Dict[str, int]:
        """Returns {never_shown: N, rarely_shown: N, often_shown: N, frequently_shown: N}"""

    def get_gaps(self) -> List[str]:
        """Returns list of insight strings about underrepresented categories."""

    def get_all_stats(self) -> Dict[str, Any]:
        """Returns all statistics in one call (for UI)."""
```

### Database Methods: `variety/smart_selection/database.py`

Add efficient SQL aggregate queries:

```python
def get_lightness_counts(self) -> Dict[str, int]:
    """GROUP BY lightness bucket using CASE expressions."""

def get_hue_counts(self) -> Dict[str, int]:
    """GROUP BY hue family using CASE expressions."""

def get_saturation_counts(self) -> Dict[str, int]:
    """GROUP BY saturation bucket using CASE expressions."""

def get_freshness_counts(self) -> Dict[str, int]:
    """GROUP BY times_shown ranges using CASE expressions."""
```

### SmartSelector Integration

```python
class SmartSelector:
    def __init__(self, ...):
        ...
        self._statistics = None

    def get_statistics_analyzer(self) -> CollectionStatistics:
        """Lazy-initialize and return statistics analyzer."""
        if self._statistics is None:
            self._statistics = CollectionStatistics(self.db)
        return self._statistics

    def record_shown(self, filepath, ...):
        ...
        # Invalidate stats cache
        if self._statistics:
            self._statistics.invalidate()
```

### UI Integration: `variety/PreferencesVarietyDialog.py`

Add "Collection Insights" section with 4 expandable cards:

```
┌─────────────────────────────────────────────────┐
│ Collection Insights                    [Refresh]│
├─────────────────────────────────────────────────┤
│ ▶ Lightness Balance                             │
│   "Your collection leans dark (52%)"            │
├─────────────────────────────────────────────────┤
│ ▶ Color Palette                                 │
│   "Dominant: Blue (28%), Purple (19%)"          │
├─────────────────────────────────────────────────┤
│ ▶ Saturation Gaps                               │
│   "⚠️ Only 6% vibrant wallpapers"               │
├─────────────────────────────────────────────────┤
│ ▶ Collection Freshness                          │
│   "142 wallpapers never shown"                  │
└─────────────────────────────────────────────────┘
```

Each card uses `Gtk.Expander` with:
- Header: Icon + summary text + percentage
- Expanded content: Full breakdown with counts/bars

## Implementation Tasks

### Task 1: Database Aggregate Queries
**File:** `variety/smart_selection/database.py`

Add 4 methods:
- `get_lightness_counts()`
- `get_hue_counts()`
- `get_saturation_counts()`
- `get_freshness_counts()`

Each uses SQL CASE expressions for efficient bucketing.

### Task 2: Statistics Module
**File:** `variety/smart_selection/statistics.py` (new)

Create `CollectionStatistics` class with:
- Caching with invalidation
- Distribution methods wrapping DB queries
- Gap detection logic
- Summary text generation

### Task 3: Selector Integration
**File:** `variety/smart_selection/selector.py`

- Add `_statistics` attribute
- Add `get_statistics_analyzer()` method
- Call `invalidate()` in `record_shown()` and `rebuild_index()`

### Task 4: UI Implementation
**File:** `variety/PreferencesVarietyDialog.py`

- Add `_build_insights_section()` method
- Create 4 expandable insight cards
- Async loading with spinner
- Refresh button

### Task 5: Unit Tests
**File:** `tests/smart_selection/test_statistics.py` (new)

Test cases for:
- Each distribution method
- Gap detection
- Cache invalidation
- Edge cases (empty DB, no palettes)

## Edge Cases & Considerations

### Grayscale Images
Images with very low saturation (< 0.1) have meaningless hue values. These should be categorized as "Neutral/Grayscale" rather than assigned to a hue family.

### Images Without Palettes
Many images won't have palette data until wallust processes them. Statistics should:
- Only count images WITH palette data for color stats
- Show "X of Y images analyzed" indicator
- Freshness stats use ALL images (don't require palette)

### Empty States
- Empty collection: "No images indexed yet"
- No palettes: "Run 'Extract Palettes' to enable color insights"

### Thread Safety
Statistics queries must be thread-safe. Use existing database RLock. Cache invalidation is atomic (single boolean flag).

### UI File Update
Need to add container in `data/ui/PreferencesVarietyDialog.ui` for the insights section, or build entirely in code.

### Performance
For large collections, ensure efficient queries:
- Use SQL CASE expressions (single table scan)
- Rely on existing indexes on palettes table

## Success Criteria

1. All 4 insight cards display correctly in preferences
2. Statistics update when images are shown or indexed
3. Expanded view shows detailed breakdown
4. No UI blocking during calculation
5. All new tests pass
6. Graceful handling of edge cases (no palettes, empty DB, grayscale images)

## Future Enhancements (Out of Scope)

- Terminal `variety --stats` command
- Visual charts/graphs
- Time-based trends
- Export statistics to file
