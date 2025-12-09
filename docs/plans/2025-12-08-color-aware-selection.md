# Color-Aware Selection - Implementation Plan

**Date:** 2025-12-08
**Status:** Planned
**Agent:** b19c664f

---

## Executive Summary

Implement color-aware wallpaper selection based on palette similarity, temperature preferences, and color continuity with the current wallpaper.

---

## Current Implementation Analysis

### Existing Components

1. **`palette.py`** - Contains:
   - `hex_to_hsl()` / `hsl_to_hex()` - Color space conversions
   - `calculate_temperature()` - Maps hue to temperature (-1 to +1)
   - `palette_similarity()` - **Already implemented** with weighted components

2. **`selector.py`** - Contains:
   - `_get_candidates()` - Already filters by `constraints.target_palette`
   - Color similarity filtering works as hard threshold

3. **`weights.py`** - Contains:
   - `calculate_weight()` - Combines recency, source, favorite, new_boost
   - **Does not yet include color affinity**

4. **`VarietyWindow.py`** - Contains:
   - `_get_smart_color_constraints()` - Generates target palettes for warm/cool/neutral/adaptive

### Current `palette_similarity()` Algorithm

```python
def palette_similarity(palette1, palette2):
    # Hue: circular distance, normalized to 0-1
    hue_diff = min(abs(h1 - h2), 360 - abs(h1 - h2)) / 180.0
    hue_similarity = 1 - hue_diff

    # Saturation/Lightness: linear distance
    sat_similarity = 1 - abs(s1 - s2)
    light_similarity = 1 - abs(l1 - l2)

    # Temperature: scaled distance (-1 to +1 range)
    temp_similarity = 1 - abs(t1 - t2) / 2.0

    # Weights: hue=35%, saturation=15%, lightness=35%, temperature=15%
    return weighted_sum(...)
```

---

## Enhanced Palette Similarity Algorithm

### Problem with Current Implementation

The current algorithm only uses aggregate metrics (avg_hue, avg_saturation, etc.). This loses information about individual color matching.

### Proposed Enhanced Algorithm

```python
def calculate_palette_similarity_enhanced(
    palette1: PaletteRecord,
    palette2: PaletteRecord,
    mode: str = 'hybrid'  # 'aggregate', 'per_color', 'hybrid'
) -> float:
    """Calculate similarity between two palettes."""
```

#### Mode 1: Aggregate (Fast)
- Time: ~0.01ms
- Uses avg_* metrics

#### Mode 2: Per-Color (Accurate)
- Time: ~0.1ms
- Compares individual colors with weighted importance

```python
def _per_color_similarity(p1: PaletteRecord, p2: PaletteRecord) -> float:
    """Compare individual palette colors with weighted importance."""

    # Color importance weights (exponential decay)
    WEIGHTS = [
        0.15, 0.12, 0.10, 0.08,  # color0-3: 45% total (dominant)
        0.08, 0.07, 0.06, 0.05,  # color4-7: 26% total (accent)
        0.04, 0.04, 0.03, 0.03,  # color8-11: 14% total
        0.03, 0.03, 0.02, 0.02,  # color12-15: 10% total
        0.05,  # background: 5%
    ]

    total_similarity = 0.0
    total_weight = 0.0

    for i in range(16):
        color1 = getattr(p1, f'color{i}')
        color2 = getattr(p2, f'color{i}')

        if color1 and color2:
            similarity = _color_distance_to_similarity(color1, color2)
            total_similarity += similarity * WEIGHTS[i]
            total_weight += WEIGHTS[i]

    return total_similarity / total_weight if total_weight > 0 else 0.0


def _color_distance_to_similarity(hex1: str, hex2: str) -> float:
    """Calculate similarity using HSL-based perceptual distance."""
    h1, s1, l1 = hex_to_hsl(hex1)
    h2, s2, l2 = hex_to_hsl(hex2)

    # Circular hue distance
    hue_diff = abs(h1 - h2)
    if hue_diff > 180:
        hue_diff = 360 - hue_diff
    hue_distance = hue_diff / 180.0

    sat_distance = abs(s1 - s2)
    light_distance = abs(l1 - l2)

    # Weighted Euclidean distance
    distance = math.sqrt(
        0.4 * (hue_distance ** 2) +
        0.2 * (sat_distance ** 2) +
        0.4 * (light_distance ** 2)
    )

    return 1.0 - min(1.0, distance)
```

#### Mode 3: Hybrid (Recommended)
- Combines both: 60% aggregate + 40% per-color (dominant only)
- Best balance of speed and accuracy

---

## Color Continuity Mode

Color continuity prefers wallpapers similar to the current one, creating smooth visual transitions.

### Implementation

```python
# In SelectionConstraints (models.py)
@dataclass
class SelectionConstraints:
    target_palette: Optional[Dict[str, Any]] = None
    min_color_similarity: Optional[float] = None
    continuity_enabled: bool = False  # NEW
    continuity_weight: float = 0.5    # NEW

# In VarietyWindow.py
def _get_smart_color_constraints(self):
    continuity_mode = getattr(self.options, 'smart_color_continuity', False)

    if continuity_mode:
        current_wp = self.get_desktop_wallpaper()
        if current_wp and hasattr(self, 'smart_selector'):
            current_palette = self.smart_selector.db.get_palette(current_wp)
            if current_palette:
                return SelectionConstraints(
                    target_palette=self._palette_record_to_dict(current_palette),
                    min_color_similarity=0.3,
                    continuity_enabled=True,
                    continuity_weight=0.5,
                )
```

---

## Color Affinity in Weight Calculation

### Current Formula
```python
weight = recency * source * favorite_boost * new_boost
```

### Enhanced Formula
```python
weight = recency * source * favorite_boost * new_boost * color_affinity
```

### Color Affinity Factor

```python
def color_affinity_factor(
    image_palette: Optional[PaletteRecord],
    target_palette: Optional[Dict[str, Any]],
    config: SelectionConfig,
    constraints: SelectionConstraints,
) -> float:
    """Calculate color affinity weight multiplier.

    Returns:
        Multiplier between 0.1 and 2.0:
        - 0.1 = Very dissimilar (strong penalty)
        - 1.0 = Neutral (no filtering or missing data)
        - 2.0 = Very similar (strong boost)
    """
    if not config.color_match_weight or not target_palette:
        return 1.0

    if not image_palette:
        return 0.8  # Slight penalty for unknown colors

    similarity = palette_similarity(target_palette, {
        'avg_hue': image_palette.avg_hue,
        'avg_saturation': image_palette.avg_saturation,
        'avg_lightness': image_palette.avg_lightness,
        'color_temperature': image_palette.color_temperature,
    })

    weight = constraints.continuity_weight if constraints.continuity_enabled else config.color_match_weight

    # Map similarity to affinity
    # 0.0 -> 0.1, 0.5 -> 1.0, 1.0 -> 2.0
    if similarity >= 0.5:
        affinity = 1.0 + (similarity - 0.5) * 2.0 * weight
    else:
        affinity = 0.1 + (similarity / 0.5) * 0.9

    return max(0.1, min(2.0, affinity))
```

---

## Temperature/Lightness Filtering

### Enhanced Constraint Filtering

```python
# In selector.py _get_candidates()

if constraints and constraints.temperature_preference:
    pref = constraints.temperature_preference

    if pref == 'warm':
        candidates = [c for c in candidates
                     if palette.color_temperature and palette.color_temperature > 0.2]
    elif pref == 'cool':
        candidates = [c for c in candidates
                     if palette.color_temperature and palette.color_temperature < -0.2]

if constraints and constraints.lightness_preference:
    pref = constraints.lightness_preference

    if pref == 'dark':
        candidates = [c for c in candidates
                     if palette.avg_lightness and palette.avg_lightness < 0.35]
    elif pref == 'light':
        candidates = [c for c in candidates
                     if palette.avg_lightness and palette.avg_lightness > 0.65]
```

### Database Optimization

```python
def get_images_by_temperature_range(self, min_temp: float, max_temp: float) -> List[ImageRecord]:
    """Get images within a temperature range using indexed query."""
    with self._lock:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT i.* FROM images i
            INNER JOIN palettes p ON i.filepath = p.filepath
            WHERE p.color_temperature BETWEEN ? AND ?
        ''', (min_temp, max_temp))
        return [self._row_to_image_record(row) for row in cursor.fetchall()]
```

---

## Performance Targets

| Operation | Expected Time |
|-----------|---------------|
| Aggregate similarity | ~0.01ms |
| Per-color (16 colors) | ~0.1ms |
| Hybrid (9 colors) | ~0.05ms |
| Full weight calculation | ~0.1ms |

### Caching Strategy

```python
class SimilarityCache:
    """LRU cache for palette similarity calculations."""

    def __init__(self, max_size: int = 1000):
        self._cache = OrderedDict()
        self._max_size = max_size

    def get_or_compute(self, key1: str, key2: str, compute_fn) -> float:
        key = (key1, key2)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        result = compute_fn()
        self._cache[key] = result

        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

        return result
```

---

## Implementation Phases

### Phase 4.1: Enhanced Similarity (1-2 days)
1. Add `_per_color_similarity()` to `palette.py`
2. Add `_hybrid_similarity()` to `palette.py`
3. Update `palette_similarity()` with `mode` parameter
4. Add unit tests

### Phase 4.2: Color Affinity in Weights (1 day)
1. Add `color_affinity_factor()` to `weights.py`
2. Update `calculate_weight()` signature
3. Update `selector.py` to pass palette data
4. Add unit tests

### Phase 4.3: Color Continuity Mode (1 day)
1. Add fields to `SelectionConstraints`
2. Update `_get_smart_color_constraints()`
3. Add Options.py configuration
4. Add unit tests

### Phase 4.4: Database Optimization (0.5 day)
1. Add `get_images_by_temperature_range()`
2. Add `get_images_by_lightness_range()`
3. Optimize `_get_candidates()`

### Phase 4.5: UI Integration (1-2 days)
1. Add color continuity toggle
2. Add temperature/lightness dropdowns
3. Add similarity threshold slider
4. Visual preview

---

## Test Cases

### Unit Tests

```python
def test_per_color_identical_palettes():
    """Identical palettes have similarity 1.0."""

def test_per_color_opposite_palettes():
    """Opposite palettes have low similarity."""

def test_hybrid_mode_performance():
    """Hybrid mode completes in <1ms."""

def test_color_weights_sum_to_one():
    """Per-color weights sum to 1.0."""

def test_affinity_neutral_without_target():
    """No target palette returns 1.0."""

def test_affinity_boost_for_similar():
    """Similar palettes get boost > 1.0."""

def test_affinity_penalty_for_dissimilar():
    """Dissimilar palettes get penalty < 1.0."""

def test_continuity_uses_current_wallpaper():
    """Continuity mode uses current wallpaper as target."""
```

### Visual Validation

```python
# tools/validate_color_similarity.py
def visual_validation_suite():
    """Generate HTML report for manual color similarity validation."""
```

---

## Files to Modify

1. **`variety/smart_selection/palette.py`** - Add enhanced similarity algorithms
2. **`variety/smart_selection/weights.py`** - Add `color_affinity_factor()`
3. **`variety/smart_selection/models.py`** - Add continuity fields to `SelectionConstraints`
4. **`variety/smart_selection/selector.py`** - Pass palette data to weight calculation
5. **`variety/VarietyWindow.py`** - Update `_get_smart_color_constraints()`
