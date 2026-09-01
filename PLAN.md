# Plan: Perceptual Brightness for Wallpaper Selection

> **Status (2026-09-01): Superseded in part.** The brightness-percentile work
> remains relevant, but the palette premise below was incorrect: this host's
> Wallust 3.5.2 pipeline is FastResize -> LchMixed automatic-threshold
> histogram grouping -> Dark16, not k-means. Dark16 contains six selected
> representatives duplicated as dark/bright pairs plus UI-derived colors, and
> its cache does not retain cluster counts. See
> `docs/superpowers/plans/2026-09-01-color-selection-remediation-design.md`
> and `docs/superpowers/plans/2026-09-01-color-selection-remediation.md` for
> the source-aware replacement design and implementation sequence.

## Problem
The current `avg_lightness` metric is computed as the arithmetic mean of HSL lightness across wallust's 16 palette colors. This is inaccurate for two reasons:

1. **HSL lightness is not perceptually uniform.** Yellow `#FFFF00` and blue `#0000FF` both have HSL L=0.50, but yellow looks drastically brighter. HSL is a geometric formula (`(max+min)/2`) with no relationship to human vision.

2. **Unweighted average of generated palette slots.** Dark16's six selected
   representatives are duplicated as dark/bright pairs, while the remaining
   slots are generated for backgrounds, foregrounds, and contrast. Equal slot
   weighting therefore measures neither image area nor theme-role importance.
   A 90% dark image with a small bright element can still get a misleading
   average.

## Solution: Three-Layer Approach

### Layer 1: Replace HSL lightness with BT.709 relative luminance (palette metrics)

BT.709 is the ITU standard for perceived brightness: `Y = 0.2126R + 0.7152G + 0.0722B`. It's used in sRGB, HDTV, and web standards. Unlike HSL lightness, it correctly models that green contributes ~72% of perceived brightness.

**Files:** `palette.py` — `calculate_palette_metrics()` and `_calculate_raw_lightness()`

Change from:
```python
h, s, l = hex_to_hsl(colors[key])
lightnesses.append(l)
```
To:
```python
h, s, l = hex_to_hsl(colors[key])
luminance = hex_to_luminance(colors[key])  # BT.709
lightnesses.append(luminance)
```

Also update `_calculate_raw_lightness()` to use BT.709 instead of `(max+min)/2`.

### Layer 2: Add PIL-based perceived brightness during palette extraction

Compute brightness directly from image pixels — the ground truth. This considers every pixel, weighted by actual coverage.

```python
from PIL import Image, ImageStat
img = Image.open(image_path)
# Downsample for speed (256px wide is sufficient for brightness)
img.thumbnail((256, 256))
gray = img.convert('L')  # ITU-R BT.601 luminance
stats = ImageStat.Stat(gray)
perceived_brightness = stats.median[0] / 255.0  # median, robust to outliers
```

**Why median?** Mean is pulled by extreme pixels (a single bright light source in a dark scene). Median gives "what brightness level is most of the image at?" — a more intuitive match for "how bright does this wallpaper feel?"

**Where to compute:** Inside `extract_palette()` and `_extract_palette_isolated()`, immediately after wallust processing succeeds. The image file is already on disk. PIL's `Image.open()` is lazy (no pixel decode until `.convert()`), and `thumbnail(256,256)` ensures the decode is fast (~2ms for a 4K image).

The result is stored as `perceived_brightness` in the palette dict, flowing through to `create_palette_record()` → DB.

### Layer 3: Store and use `perceived_brightness` as the primary brightness signal

**Schema change (v9 migration):**
```sql
ALTER TABLE palettes ADD COLUMN perceived_brightness REAL;
CREATE INDEX idx_palettes_brightness ON palettes(perceived_brightness);
```

**Model change:** Add `perceived_brightness: Optional[float] = None` to `PaletteRecord`.

**Consumer changes:** All brightness consumers switch from `avg_lightness` to `perceived_brightness` (with `avg_lightness` fallback for unindexed images):
- `constraints.py` — lightness bounds check
- `weights.py` — `calculate_time_affinity()`
- `database.py` — `get_lightness_counts()`, `get_time_adaptation_stats()`

### Layer 4 (bonus): Lightness histogram percentiles

Store P10 (darkest region) and P90 (brightest region) alongside median. This enables richer queries like "reject images with any bright region > 0.7" for night mode — catching the case where a mostly dark image has a blinding sky section.

```python
import numpy as np
pixels = np.array(gray).flatten()
p10 = float(np.percentile(pixels, 10)) / 255.0
p90 = float(np.percentile(pixels, 90)) / 255.0
```

**Schema:** `brightness_p10 REAL, brightness_p90 REAL` on palettes table.
**Usage:** Night mode can additionally reject `brightness_p90 > 0.70` — images where even the bright regions are too intense.

## Files to Modify

| File | Changes |
|------|---------|
| `palette.py` | Add `hex_to_luminance()`. Update `calculate_palette_metrics()` and `_calculate_raw_lightness()` to use BT.709. Add PIL brightness computation in `extract_palette()` and `_extract_palette_isolated()`. |
| `models.py` | Add `perceived_brightness`, `brightness_p10`, `brightness_p90` to `PaletteRecord`. Update `to_dict()`. |
| `database.py` | Add migration v8→v9 for new columns. Update all SQL that inserts/reads PaletteRecord. Update `get_lightness_counts()` and `get_time_adaptation_stats()` queries. |
| `constraints.py` | Use `perceived_brightness` (fallback `avg_lightness`) for lightness bounds. Add P90 check for night mode. |
| `weights.py` | Use `perceived_brightness` (fallback `avg_lightness`) in `calculate_time_affinity()`. |
| `VarietyWindow.py` | Add `max_brightness_p90` constraint for night mode. |
| `selector.py` | No changes needed — data flows through existing pipeline. |
| Tests | Update lightness-related test values. Add tests for BT.709 luminance, PIL brightness extraction, percentile constraints. |

## Implementation Order

1. **palette.py** — `hex_to_luminance()` + update `calculate_palette_metrics()` + `_calculate_raw_lightness()` (Layer 1)
2. **palette.py** — PIL brightness in `extract_palette()` + `_extract_palette_isolated()` (Layer 2)
3. **models.py** — New fields on `PaletteRecord` (Layer 3)
4. **database.py** — Migration v8→v9 + update SQL (Layer 3)
5. **constraints.py** — Use `perceived_brightness` + P90 check (Layer 3+4)
6. **weights.py** — Use `perceived_brightness` (Layer 3)
7. **VarietyWindow.py** — P90 constraint for night mode (Layer 4)
8. **Tests** — Verify all layers work correctly

## Backward Compatibility

- `avg_lightness` column remains (now stores BT.709 luminance instead of HSL L — same scale, just more accurate values)
- `perceived_brightness` is `NULL` for existing images until re-indexed — all consumers fall back to `avg_lightness`
- No changes to config schema or user-facing options
- Existing palettes get corrected `avg_lightness` on next re-index via wallust
