# Smart Selection Engine - Completion Master Plan

**Date:** 2025-12-08
**Status:** Planning
**Target:** Production-ready Smart Selection with full validation

## Executive Summary

Complete the Smart Selection Engine with 7 major tasks, full quality pipeline, and end-to-end validation. Each task includes unit tests, integration tests, code review, and documentation.

---

## Task 1: Commit Current Work with Validation

### Objective
Commit 430 lines of uncommitted changes after validation.

### Current Changes
- `variety/smart_selection/theming.py` - Complete theming engine (new file, already committed)
- `variety/VarietyWindow.py` - ThemeEngine integration, color constraints logging
- `variety/smart_selection/palette.py` - `hsl_to_hex`, wallust cache format parsing
- `variety/smart_selection/database.py` - Schema updates
- `variety/smart_selection/models.py` - cursor field addition
- `variety/smart_selection/selector.py` - Minor enhancements
- `tests/smart_selection/test_palette.py` - New palette tests
- `tests/smart_selection/test_theming.py` - New theming tests

### Validation Criteria
1. All existing tests pass (322 tests)
2. New tests for theming pass
3. No regressions in smart selection functionality
4. Code review: no obvious issues

### Deliverables
- [ ] Run full test suite, record results
- [ ] Code review agent validates changes
- [ ] Commit with descriptive message
- [ ] Tag: `smart-selection-v0.3-theming`

---

## Task 2: Fix Race Condition in record_shown

### Problem Statement
From Phase 3 notes:
```
set_wallpaper():
  Line 2088: set_wp_throttled(img)  ← Returns IMMEDIATELY (spawns thread)
  Line 2093: record_shown(img)      ← Runs NOW, before wallust runs!

Background thread (async):
  do_set_wp() → set_desktop_wallpaper() → subprocess.check_call(script)
  → Script runs wallust (creates cache AFTER record_shown already ran)
```

### Solution
Move `record_shown()` inside `do_set_wp()` AFTER `set_desktop_wallpaper()` completes.

### Implementation Steps
1. Locate `do_set_wp()` method (~line 2000)
2. Find where `set_desktop_wallpaper()` is called
3. Add `record_shown()` call AFTER wallpaper is set
4. Read wallust cache at that point (palette is now available)
5. Remove `record_shown()` from `set_wallpaper()` method
6. Handle thread safety (record_shown already uses thread-safe DB)

### Validation Criteria
1. **Unit Test**: Mock `set_desktop_wallpaper`, verify `record_shown` called after
2. **Integration Test**: Set wallpaper, verify palette is captured in DB
3. **Manual Test**: Run variety, change wallpaper, check logs for palette capture
4. **Timing Test**: Verify no race window exists

### Test Cases
```python
def test_record_shown_called_after_wallpaper_set():
    """Verify record_shown is called AFTER set_desktop_wallpaper completes."""

def test_palette_captured_on_wallpaper_change():
    """Verify wallust palette is read and stored when wallpaper changes."""

def test_palette_not_captured_when_cache_missing():
    """Verify graceful handling when wallust cache doesn't exist."""
```

### Deliverables
- [ ] Modified `do_set_wp()` with correct ordering
- [ ] Unit tests for race condition fix
- [ ] Integration test proving palette capture works
- [ ] Code review validation

---

## Task 3: UI Polish (Progress Bars, Button States)

### Problem Statement
1. Extract Palettes button: No progress feedback, can be clicked multiple times
2. Thumbnail loading: Synchronous, freezes UI
3. No wallust installation check

### Implementation Steps

#### 3.1 Extract Palettes Button
- Add progress bar to Smart Selection dialog
- Disable button during extraction
- Add cancel button
- Show completion notification

#### 3.2 Thumbnail Loading
- Use `GLib.idle_add()` for incremental loading
- Load 10 thumbnails at a time
- Show placeholder during load

#### 3.3 Wallust Check
- Check for wallust binary on feature enable
- Show warning dialog if not installed
- Provide installation instructions

### Validation Criteria
1. **UI Test**: Button disabled during operation
2. **Progress Test**: Progress bar updates correctly
3. **Cancel Test**: Cancel stops extraction cleanly
4. **Performance Test**: Dialog opens in <500ms with 100+ images

### Deliverables
- [ ] Progress bar implementation
- [ ] Button state management
- [ ] Thumbnail lazy loading
- [ ] Wallust installation check
- [ ] UI/UX review

---

## Task 4: Preferences UI for Smart Selection Settings

### Current State
Options exist in code but no preferences dialog.

### Settings to Expose
```python
smart_selection_enabled = True
image_cooldown_days = 7
source_cooldown_days = 1
favorite_boost = 2.0
new_image_boost = 1.5
smart_color_enabled = False
smart_color_similarity = 70  # 0-100
smart_color_temperature = 'neutral'  # warm/cool/neutral/adaptive
smart_theming_enabled = True
```

### Implementation Steps
1. Add "Smart Selection" tab to Preferences dialog
2. Create GTK widgets for each setting
3. Connect to Options.py (existing schema)
4. Add tooltips explaining each setting
5. Live preview of weight calculation

### UI Layout
```
┌─ Smart Selection ─────────────────────────────────┐
│ ☑ Enable Smart Selection                          │
│                                                   │
│ ─ Selection Weights ──────────────────────────── │
│ Image cooldown:  [7    ▼] days                   │
│ Source cooldown: [1    ▼] days                   │
│ Favorite boost:  [═══════●══] 2.0x               │
│ New image boost: [═══════●══] 1.5x               │
│                                                   │
│ ─ Color Features ─────────────────────────────── │
│ ☐ Enable color-aware selection                   │
│ Similarity threshold: [══════●════] 70%          │
│ Temperature: (●) Neutral ( ) Warm ( ) Cool       │
│              ( ) Adaptive (time-based)           │
│                                                   │
│ ─ Theming Engine ─────────────────────────────── │
│ ☑ Enable instant theme switching                 │
│ Templates: 12 enabled [Configure...]             │
└───────────────────────────────────────────────────┘
```

### Validation Criteria
1. All settings persist across restart
2. Changes take effect immediately (no restart required)
3. Invalid values rejected with feedback
4. Defaults restore correctly

### Deliverables
- [ ] Preferences tab implementation
- [ ] Options.py schema validated
- [ ] Settings persistence tests
- [ ] UI accessibility review

---

## Task 5: Wallust Config Detection

### Problem Statement
Currently hardcoded to look for `*Dark16*` palette files.

### Solution
Read `~/.config/wallust/wallust.toml` to detect:
1. Palette type (dark16, light16, etc.)
2. Template definitions
3. Backend settings

### Implementation Steps
1. Add `parse_wallust_config()` to palette.py
2. Extract `palette` setting from TOML
3. Use detected pattern for cache file matching
4. Fall back to `*Dark16*` if config unreadable

### Validation Criteria
1. Correctly detects various palette types
2. Handles missing config gracefully
3. Handles malformed config gracefully
4. Updates when config changes

### Test Cases
```python
def test_detect_dark16_palette():
def test_detect_light16_palette():
def test_detect_custom_palette():
def test_missing_wallust_config():
def test_malformed_wallust_config():
```

### Deliverables
- [ ] Config parser implementation
- [ ] Unit tests for all palette types
- [ ] Integration with cache reading
- [ ] Documentation of supported configs

---

## Task 6: Full Collection Indexing

### Current State
Only indexes favorites on startup. Full collection not indexed.

### Implementation Steps
1. Add background indexer for Downloaded folder
2. Index on startup (after favorites)
3. Incremental re-index on directory changes
4. Progress reporting for large collections

### Performance Requirements
- Index 10,000 images in <30 seconds
- Re-index changed files only
- Don't block UI during indexing

### Validation Criteria
1. **Performance**: 10K images indexed in <30s
2. **Correctness**: All images in Downloaded are indexed
3. **Incremental**: Only changed files re-indexed
4. **Memory**: <100MB RAM during indexing

### Test Cases
```python
def test_full_collection_indexed():
def test_incremental_reindex():
def test_deleted_files_removed():
def test_new_files_added():
def test_index_performance_10k():
```

### Deliverables
- [ ] Background indexer implementation
- [ ] Performance benchmarks
- [ ] Memory profiling results
- [ ] Integration tests

---

## Task 7: Color-Aware Selection (Phase 4)

### Features
1. Palette similarity calculation
2. Color continuity mode (similar to previous wallpaper)
3. Temperature/lightness filtering
4. Hue range filtering

### Implementation Steps
1. Implement `calculate_palette_similarity()` in weights.py
2. Add `color_affinity_factor` to weight calculation
3. Implement `SelectionConstraints.target_palette`
4. Add color filters to constraint matching
5. Integrate with `_get_color_constraints()` in VarietyWindow

### Algorithm: Palette Similarity
```python
def calculate_palette_similarity(palette1, palette2):
    """Calculate similarity between two palettes (0-1).

    Compares:
    - Dominant colors (color0-7) with weighted importance
    - Average hue, saturation, lightness
    - Color temperature

    Returns weighted combination of metrics.
    """
```

### Validation Criteria
1. Similar palettes score >0.8 similarity
2. Dissimilar palettes score <0.3 similarity
3. Selection respects color preferences
4. Performance: <10ms per similarity calculation

### Test Cases
```python
def test_identical_palettes_similarity():
def test_opposite_palettes_similarity():
def test_warm_palette_preference():
def test_cool_palette_preference():
def test_adaptive_time_based_selection():
def test_color_continuity_mode():
```

### Deliverables
- [ ] Similarity algorithm implementation
- [ ] Weight integration
- [ ] Constraint filtering
- [ ] Performance benchmarks
- [ ] Visual validation (manual review of selections)

---

## End-to-End Validation Suite

### Test Scenarios

#### E2E-1: Fresh Install Flow
1. Start variety with empty database
2. Index favorites (should work)
3. Index full collection
4. Change wallpaper 10 times
5. Verify no repeats within cooldown
6. Verify source rotation

#### E2E-2: Color-Aware Selection
1. Enable color features
2. Set temperature to "warm"
3. Change wallpaper 5 times
4. Verify all selected wallpapers have warm palettes

#### E2E-3: Theming Engine
1. Set wallpaper with cached palette
2. Verify templates generated in <20ms
3. Verify reload commands executed
4. Verify config files contain correct colors

#### E2E-4: Recency Tracking
1. Set wallpaper A
2. Request 100 selections
3. Verify A never appears (within cooldown)
4. Advance time past cooldown
5. Verify A can appear again

#### E2E-5: Performance Under Load
1. Index 10,000 images
2. Select 100 images in batch
3. Verify <1 second total
4. Verify memory stays under 200MB

### Validation Recording
All test results recorded to `docs/validation/`:
- `test-results-YYYY-MM-DD.md` - Test output
- `performance-benchmarks.md` - Timing results
- `coverage-report.html` - Code coverage
- `code-review-notes.md` - Review findings

---

## Quality Pipeline

### For Each Task
1. **Implementation**: Write code
2. **Unit Tests**: Test individual functions
3. **Integration Tests**: Test component interactions
4. **Code Review**: Agent reviews for issues
5. **Documentation**: Update relevant docs
6. **Commit**: With descriptive message

### Final Validation
1. Full test suite (all 322+ tests)
2. E2E scenarios (5 scenarios)
3. Performance benchmarks
4. Memory profiling
5. Documentation review
6. Manual smoke test

---

## Timeline (Parallel Execution)

```
Phase 1: Commit + Race Fix (Tasks 1-2)
  └─ Agent A: Validate and commit current work
  └─ Agent B: Implement race condition fix

Phase 2: UI + Config (Tasks 3-5)
  └─ Agent A: UI polish
  └─ Agent B: Preferences UI
  └─ Agent C: Wallust config detection

Phase 3: Indexing + Color (Tasks 6-7)
  └─ Agent A: Full collection indexing
  └─ Agent B: Color-aware selection

Phase 4: E2E Validation
  └─ All agents: Run E2E suite
  └─ Documentation agent: Final review
  └─ Code review agent: Final pass
```

---

## Success Criteria

The Smart Selection Engine is "shippable" when:

1. **All Tests Pass**: 400+ tests (including new ones)
2. **E2E Scenarios Pass**: All 5 scenarios validated
3. **Performance Targets Met**:
   - Index 10K images in <30s
   - Select 100 images in <1s
   - Theme apply in <20ms
4. **No Critical Bugs**: Code review finds no blockers
5. **Documentation Complete**: All features documented
6. **User-Facing Polish**: UI is intuitive and responsive
