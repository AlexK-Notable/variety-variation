# Phase 3: Wallust Integration Plan - Smart Selection Engine

## Executive Summary

Phase 3 integrates wallust color palette extraction into Variety's Smart Selection Engine, enabling color-aware wallpaper selection. This plan covers architecture, data flow, integration points, UI controls, performance optimization, error handling, testing strategy, and a reflection phase identifying potential gaps.

---

## 1. Current State Analysis

### 1.1 What Exists

| Component | Status | Location |
|-----------|--------|----------|
| PaletteExtractor class | Complete | `variety/smart_selection/palette.py` |
| PaletteRecord model | Complete | `variety/smart_selection/models.py` |
| Database palette CRUD | Complete | `variety/smart_selection/database.py` |
| Color similarity calculation | Complete | `palette.py:palette_similarity()` |
| SelectionConstraints.target_palette | Complete | `models.py` |
| Color filtering in _get_candidates() | Complete | `selector.py:196-217` |
| extract_all_palettes() method | Complete | `selector.py:332-372` |
| Tests for palette extraction | Complete | 209 tests passing |

### 1.2 Wallust Cache Structure

```
~/.cache/wallust/{image_hash}_1.7/
├── FastResize                    # Raw pixel data (~10MB) - NOT USED
├── FastResize_Lch_auto           # Full color analysis JSON
└── FastResize_Lch_auto_Dark16    # 16-color palette JSON <- WE USE THIS
```

**Dark16 JSON format:**
```json
{
  "cursor": "#B8CBA8",
  "background": "#26272A",
  "foreground": "#FBF8A9",
  "color0": "#4C4C4F",
  "color1": "#B93C8C",
  ...
  "color15": "#F1ED7B"
}
```

### 1.3 Current Data Flow

```
Image Selected → set_wallpaper() → record_shown()
                      ↓
              wallust run (themes)     [user's set_wallpaper script]
                      ↓
              Colors applied to Hyprland/Waybar/etc.
```

**Problem:** Variety doesn't capture the palette data that wallust generates.

---

## 2. Architecture Design

### 2.1 Extraction Strategy Options

| Strategy | Pros | Cons | Verdict |
|----------|------|------|---------|
| **A. Eager (at index time)** | Complete data upfront | Slow indexing, wallust may not be installed | Reject |
| **B. Lazy (on first show)** | Fast indexing, guaranteed wallust available | First show slower, data incomplete until shown | Partial |
| **C. Background (async)** | Non-blocking, complete data | Complex threading, resource usage | For bulk |
| **D. Hybrid** | Best of all worlds | More complex | **SELECTED** |

### 2.2 Hybrid Strategy Details

```
┌─────────────────────────────────────────────────────────────────┐
│                      HYBRID EXTRACTION                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. ON SHOW (Primary - Lazy):                                   │
│     set_wallpaper() → wallust runs for themes                   │
│                     → Variety reads from wallust cache          │
│                     → Store palette in database                 │
│                                                                 │
│  2. BACKGROUND (Optional - User-Initiated):                     │
│     Preferences UI → "Extract All Palettes" button              │
│                    → Background thread processes unindexed      │
│                    → Progress bar shows completion              │
│                                                                 │
│  3. SELECTION TIME (Fallback):                                  │
│     If color filtering requested but no palette:                │
│     → Exclude image from color-aware selection                  │
│     → Log warning for visibility                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Key Insight: Reuse Wallust's Cache

**The set_wallpaper script already runs wallust.** Instead of running wallust twice:

1. set_wallpaper runs `wallust run "$WP"` for theme generation
2. Variety reads from wallust's cache afterward
3. No duplicate processing

**Implementation:**
```python
# In record_shown() - AFTER set_wallpaper completes
def record_shown(self, filepath: str, wallust_palette: Dict = None):
    # If no palette provided, try to read from wallust cache
    if wallust_palette is None and self._enable_palette_extraction:
        wallust_palette = self._read_wallust_cache(filepath)

    if wallust_palette:
        palette_record = create_palette_record(filepath, wallust_palette)
        self.db.upsert_palette(palette_record)
```

---

## 3. Integration Points

### 3.1 VarietyWindow.py Changes

```python
# Location: variety/VarietyWindow.py

# 1. In set_wallpaper() - AFTER wallpaper is applied
def set_wallpaper(self, img, ...):
    # ... existing wallpaper setting code ...

    # After wallpaper is set (and set_wallpaper script has run wallust)
    if self.smart_selector:
        # Give wallust time to finish (it runs async in set_wallpaper script)
        GLib.timeout_add(500, self._record_wallpaper_shown, img)

def _record_wallpaper_shown(self, img):
    """Record shown wallpaper and capture palette from wallust cache."""
    if self.smart_selector:
        # Read palette from wallust's cache (created by set_wallpaper script)
        palette = self._read_wallust_cache_for_image(img)
        self.smart_selector.record_shown(img, wallust_palette=palette)
    return False  # Don't repeat

def _read_wallust_cache_for_image(self, filepath: str) -> Optional[Dict]:
    """Read palette data from wallust's cache directory."""
    cache_dir = os.path.expanduser('~/.cache/wallust')
    if not os.path.isdir(cache_dir):
        return None

    # Find most recently modified Dark16 file
    # (wallust just ran, so it should be the freshest)
    latest_file = None
    latest_time = 0

    for entry in os.listdir(cache_dir):
        entry_path = os.path.join(cache_dir, entry)
        if os.path.isdir(entry_path):
            for subfile in os.listdir(entry_path):
                if 'Dark16' in subfile:
                    filepath = os.path.join(entry_path, subfile)
                    mtime = os.path.getmtime(filepath)
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_file = filepath

    if latest_file:
        try:
            with open(latest_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read wallust cache: {e}")

    return None
```

### 3.2 Preferences UI Changes

**File:** `variety/PreferencesVarietyDialog.py`

**New UI Elements:**
1. "Color-Aware Selection" toggle (enable/disable)
2. "Time-Based Colors" toggle (morning=cool, evening=warm)
3. "Extract All Palettes" button with progress bar
4. Statistics: "X of Y images have color data"

```python
# In Smart Selection tab

def _on_extract_palettes_clicked(self, button):
    """Start background palette extraction."""
    if not self.smart_selector:
        return

    # Disable button, show progress
    button.set_sensitive(False)
    self.palette_progress.set_visible(True)

    # Run in background thread
    def extract_worker():
        def progress_callback(current, total):
            GLib.idle_add(self._update_palette_progress, current, total)

        count = self.smart_selector.extract_all_palettes(progress_callback)
        GLib.idle_add(self._extraction_complete, count, button)

    thread = threading.Thread(target=extract_worker)
    thread.daemon = True
    thread.start()
```

### 3.3 SelectionConstraints Enhancement

**File:** `variety/smart_selection/models.py`

```python
@dataclass
class SelectionConstraints:
    # Existing fields...

    # Color filtering
    target_palette: Optional[Dict[str, Any]] = None
    min_color_similarity: Optional[float] = None  # 0.0-1.0

    # NEW: Time-based color preferences
    prefer_warm_colors: Optional[bool] = None     # For evening
    prefer_cool_colors: Optional[bool] = None     # For morning
    target_lightness_range: Optional[Tuple[float, float]] = None  # (min, max)
    target_temperature_range: Optional[Tuple[float, float]] = None
```

---

## 4. Color-Aware Selection Modes

### 4.1 Time-Based Color Selection

```python
# In selector.py

def get_time_based_constraints(self) -> SelectionConstraints:
    """Get color constraints based on time of day."""
    hour = datetime.now().hour

    if 6 <= hour < 12:      # Morning
        return SelectionConstraints(
            target_temperature_range=(-0.5, 0.3),  # Cool to neutral
            target_lightness_range=(0.4, 0.7),     # Medium-bright
        )
    elif 12 <= hour < 18:   # Afternoon
        return SelectionConstraints(
            target_temperature_range=(-0.3, 0.5),  # Neutral
            target_lightness_range=(0.3, 0.6),     # Medium
        )
    elif 18 <= hour < 22:   # Evening
        return SelectionConstraints(
            target_temperature_range=(0.2, 0.8),   # Warm
            target_lightness_range=(0.2, 0.5),     # Darker
        )
    else:                   # Night
        return SelectionConstraints(
            target_temperature_range=(-0.3, 0.3),  # Neutral
            target_lightness_range=(0.1, 0.4),     # Dark
        )
```

### 4.2 Current Wallpaper Similarity

```python
def select_similar_to_current(self, current_wallpaper: str,
                              similarity_threshold: float = 0.7) -> List[str]:
    """Select wallpapers with similar color palette to current."""
    current_palette = self.db.get_palette(current_wallpaper)
    if not current_palette:
        return self.select_images(count=1)  # Fallback

    constraints = SelectionConstraints(
        target_palette={
            'avg_hue': current_palette.avg_hue,
            'avg_saturation': current_palette.avg_saturation,
            'avg_lightness': current_palette.avg_lightness,
            'color_temperature': current_palette.color_temperature,
        },
        min_color_similarity=similarity_threshold,
    )

    return self.select_images(count=1, constraints=constraints)
```

### 4.3 Contrast Mode (Opposite Colors)

```python
def select_contrasting(self, current_wallpaper: str) -> List[str]:
    """Select wallpaper with contrasting colors."""
    current_palette = self.db.get_palette(current_wallpaper)
    if not current_palette:
        return self.select_images(count=1)

    # Opposite hue (180 degrees)
    opposite_hue = (current_palette.avg_hue + 180) % 360

    constraints = SelectionConstraints(
        target_palette={
            'avg_hue': opposite_hue,
            'avg_saturation': current_palette.avg_saturation,
            'avg_lightness': current_palette.avg_lightness,
            'color_temperature': -current_palette.color_temperature,
        },
        min_color_similarity=0.3,  # Lower threshold for contrast
    )

    return self.select_images(count=1, constraints=constraints)
```

---

## 5. Performance Considerations

### 5.1 Lazy Extraction Timing

| Event | Latency Added | Acceptable? |
|-------|---------------|-------------|
| Read wallust cache | ~5ms | Yes |
| Parse JSON | ~1ms | Yes |
| Calculate metrics | ~2ms | Yes |
| Database upsert | ~10ms | Yes |
| **Total** | **~18ms** | **Yes** |

### 5.2 Background Extraction Performance

For large collections (10,000+ images):

```python
# Batch processing with rate limiting
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 0.5  # seconds

def extract_all_palettes_batched(self, progress_callback=None):
    images = self.db.get_images_without_palettes()
    total = len(images)

    for i in range(0, total, BATCH_SIZE):
        batch = images[i:i+BATCH_SIZE]

        for img in batch:
            self._extract_and_store_palette(img.filepath)

        if progress_callback:
            progress_callback(min(i + BATCH_SIZE, total), total)

        time.sleep(SLEEP_BETWEEN_BATCHES)  # Prevent CPU spike
```

### 5.3 Database Query Optimization

```sql
-- Add index for color filtering queries
CREATE INDEX IF NOT EXISTS idx_palettes_color_metrics
ON palettes(avg_hue, avg_saturation, avg_lightness, color_temperature);

-- Query for similar colors (rough filter before Python refinement)
SELECT * FROM palettes
WHERE avg_hue BETWEEN ? AND ?
  AND avg_lightness BETWEEN ? AND ?
ORDER BY indexed_at DESC;
```

---

## 6. Error Handling

### 6.1 Graceful Degradation

```python
class SmartSelector:
    def select_images(self, count, constraints=None):
        # If color filtering requested but no images have palettes
        if constraints and constraints.target_palette:
            palette_count = self.db.count_images_with_palettes()
            if palette_count == 0:
                logger.warning(
                    "Color filtering requested but no palettes extracted. "
                    "Falling back to non-color selection."
                )
                # Remove color constraint, keep others
                constraints = SelectionConstraints(
                    min_width=constraints.min_width,
                    min_height=constraints.min_height,
                    favorites_only=constraints.favorites_only,
                    sources=constraints.sources,
                    # target_palette=None  <- removed
                )

        return self._select_with_weights(count, constraints)
```

### 6.2 Wallust Availability Check

```python
def _check_wallust_integration(self):
    """Check if wallust integration is available and working."""
    if not self._palette_extractor:
        self._palette_extractor = PaletteExtractor()

    if not self._palette_extractor.is_wallust_available():
        logger.info(
            "wallust not available. Color-aware selection disabled. "
            "Install wallust for color features: https://github.com/explosion-mental/wallust"
        )
        self._enable_palette_extraction = False
        return False

    return True
```

### 6.3 Cache Read Failures

```python
def _read_wallust_cache_for_image(self, filepath):
    try:
        # ... cache reading logic ...
    except PermissionError:
        logger.warning(f"Permission denied reading wallust cache")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in wallust cache: {e}")
        return None
    except Exception as e:
        logger.debug(f"Could not read wallust cache: {e}")
        return None
```

---

## 7. Configuration Schema

### 7.1 Options.py Additions

```python
# In variety/Options.py

# Smart Selection - Color Settings
"smart_selection_color_enabled": True,        # Enable color-aware selection
"smart_selection_time_based_colors": False,   # Auto-adjust by time of day
"smart_selection_color_similarity": 0.5,      # Default similarity threshold (0-1)
"smart_selection_prefer_warm_evening": True,  # Warm colors after 6pm
"smart_selection_prefer_cool_morning": True,  # Cool colors before noon
```

### 7.2 variety.conf Format

```ini
[smart_selection]
enabled = True
color_enabled = True
time_based_colors = False
color_similarity_threshold = 0.5
recency_days = 7
new_image_boost = 1.5
favorite_boost = 2.0
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
# tests/smart_selection/test_color_selection.py

class TestColorAwareSelection:
    def test_time_based_constraints_morning(self):
        """Morning should prefer cool, bright colors."""

    def test_time_based_constraints_evening(self):
        """Evening should prefer warm, darker colors."""

    def test_similar_color_selection(self):
        """Similar palette should have high similarity score."""

    def test_contrasting_color_selection(self):
        """Contrasting selection should pick opposite hues."""

    def test_no_palette_excludes_from_color_filter(self):
        """Images without palettes excluded when color filtering."""

    def test_graceful_fallback_no_palettes(self):
        """Falls back to non-color selection if no palettes exist."""
```

### 8.2 Integration Tests

```python
class TestWallustIntegration:
    def test_cache_reading_after_wallust_run(self):
        """After wallust runs, palette readable from cache."""

    def test_record_shown_captures_palette(self):
        """record_shown() stores palette in database."""

    def test_palette_persists_across_sessions(self):
        """Palette data survives app restart."""
```

### 8.3 E2E Tests

```python
class TestColorAwareWorkflow:
    def test_full_workflow_index_extract_select(self):
        """Index images, extract palettes, select by color."""

    def test_time_based_selection_changes_with_hour(self):
        """Selection changes based on mocked time."""
```

---

## 9. Implementation Phases

### Phase 3a: Cache Integration (Week 1)
- [ ] Add `_read_wallust_cache_for_image()` to VarietyWindow
- [ ] Modify `record_shown()` to capture palette after set_wallpaper
- [ ] Add 500ms delay for wallust completion
- [ ] Tests for cache reading

### Phase 3b: Selection Modes (Week 2)
- [ ] Implement `get_time_based_constraints()`
- [ ] Implement `select_similar_to_current()`
- [ ] Implement `select_contrasting()`
- [ ] Add temperature/lightness range filtering
- [ ] Tests for each selection mode

### Phase 3c: UI Integration (Week 3)
- [ ] Add color settings to Preferences dialog
- [ ] Add "Extract All Palettes" button with progress
- [ ] Add palette statistics display
- [ ] Add time-based toggle
- [ ] Add similarity threshold slider

### Phase 3d: Polish & Documentation (Week 4)
- [ ] Performance optimization for large collections
- [ ] Error handling edge cases
- [ ] User documentation
- [ ] Update CLAUDE.md with Phase 3 completion

---

## 10. Reflection Phase: Critical Issues Found

### 10.1 CRITICAL: Race Condition in record_shown Timing

**Current broken flow:**
```
set_wallpaper():
  Line 2088: set_wp_throttled(img)  ← Returns IMMEDIATELY (async)
  Line 2093: record_shown(img)      ← Runs NOW, before wallust!

Background thread:
  do_set_wp() → set_desktop_wallpaper() → subprocess.check_call(script)
  → Script runs wallust (creates cache)
  → But record_shown already happened!
```

**The plan's "500ms delay" assumption is WRONG.** The delay would need to be inside the async flow.

**REQUIRED FIX:**
```python
# In do_set_wp() - AFTER set_desktop_wallpaper() completes
def do_set_wp(self, filename, refresh_level=RefreshLevel.ALL):
    with self.do_set_wp_lock:
        # ... existing code ...
        self.set_desktop_wallpaper(to_set, filename, refresh_level, display_mode_param)
        self.current = filename

        # NEW: Record for Smart Selection AFTER wallpaper script completes
        if hasattr(self, 'smart_selector') and self.smart_selector:
            palette = self._read_wallust_cache_for_image(filename)
            self.smart_selector.record_shown(filename, wallust_palette=palette)
```

**ALSO REMOVE** the existing `record_shown` call from `set_wallpaper()` (line 2091-2095).

### 10.2 UI Issues: No Progress Feedback

**Extract Palettes button:**
- Button stays active during extraction (user can spawn multiple threads)
- No progress bar for 10+ minute operations
- No cancellation mechanism
- Single notification at start, nothing until end

**Required changes:**
```python
def on_smart_extract_palettes_clicked(self, widget=None):
    widget.set_sensitive(False)  # Disable immediately
    self.ui.smart_extract_progress.set_visible(True)
    self.ui.smart_extract_progress.set_fraction(0)

    def progress_callback(current, total):
        def _update():
            self.ui.smart_extract_progress.set_fraction(current / total)
            self.ui.smart_extract_status.set_text(f"{current}/{total}")
        GObject.idle_add(_update)

    def extract():
        try:
            count = self.parent.smart_selector.extract_all_palettes(
                progress_callback=progress_callback
            )
            # ...
        finally:
            GObject.idle_add(lambda: widget.set_sensitive(True))
            GObject.idle_add(lambda: self.ui.smart_extract_progress.set_visible(False))
```

### 10.3 UI Issues: Thumbnail Loading Freezes UI

**Problem:** `_populate_dialog_flowbox()` loads 60 images synchronously on main thread.

**Fix:** Load thumbnails in background thread, add to FlowBox via idle_add:
```python
def _populate_dialog_flowbox_async(self, dialog, candidates):
    def load_thumbnail(candidate):
        # Load in background
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(...)
        GObject.idle_add(self._add_thumbnail_to_flowbox, dialog, candidate, pixbuf)

    for candidate in candidates:
        threading.Thread(target=load_thumbnail, args=(candidate,), daemon=True).start()
```

### 10.4 Hardcoded Palette Type

**Problem:** Code assumes `Dark16` but wallust.toml could specify different palette.

**Fix:** Read palette type from wallust config:
```python
def _get_wallust_palette_type(self) -> str:
    config_path = os.path.expanduser('~/.config/wallust/wallust.toml')
    try:
        with open(config_path) as f:
            for line in f:
                if line.startswith('palette'):
                    # palette = "dark16" → "Dark16"
                    match = re.search(r'"(\w+)"', line)
                    if match:
                        return match.group(1).title()
    except:
        pass
    return 'Dark16'  # Default fallback
```

### 10.5 Missing Wallust Availability Check

**Problem:** User can enable color features without wallust installed → silent failure.

**Fix:** Check wallust on color toggle:
```python
def on_smart_color_enabled_toggled(self, widget=None):
    if widget.get_active():
        if not shutil.which('wallust'):
            widget.set_active(False)
            dialog = Gtk.MessageDialog(
                self, Gtk.DialogFlags.MODAL,
                Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                _("wallust is required for color-aware selection.\n\n"
                  "Install it from: https://github.com/explosion-mental/wallust")
            )
            dialog.run()
            dialog.destroy()
            return
    # ... rest of handler
```

### 10.6 Original Identified Gaps

| Gap | Risk | Mitigation |
|-----|------|------------|
| **Wallust not installed** | Color features fail silently | Check on toggle, show dialog |
| **set_wallpaper script variations** | User may not use wallust | Document requirement, detect wallust in script |
| **Cache race condition** | Read before wallust finishes | Move record_shown into do_set_wp AFTER script |
| **Palette schema changes** | wallust updates break parsing | Version check, defensive parsing |
| **Very dark/light images** | Palette metrics less meaningful | Weight by saturation |

### 10.2 Potential Oversights

1. **Multi-monitor setups**: Different wallpapers per monitor have different palettes. Which one to record?
   - **Solution**: Record palette for the primary/focused monitor's wallpaper.

2. **Wallust palette type**: Code assumes "Dark16" but wallust supports other palettes (light16, etc.)
   - **Solution**: Make palette type configurable, default to match wallust.toml setting.

3. **Cache cleanup**: Old wallust cache entries accumulate.
   - **Solution**: Not Variety's responsibility, but document for users.

4. **Color blindness accessibility**: Color-based selection may not help colorblind users.
   - **Solution**: Focus on lightness/temperature which are more universal.

5. **Wallust version compatibility**: Different wallust versions may have different cache formats.
   - **Solution**: Test with wallust 2.x, add version detection.

6. **Template-only mode**: Some users may want wallust for themes but not color selection.
   - **Solution**: Separate "enable color themes" from "enable color selection" toggles.

### 10.3 Missing Requirements

1. **Preview**: Show palette swatches in thumbs window for color-indexed images.
2. **Manual override**: Let user set preferred palette for specific times.
3. **Color history**: Track which colors have been shown recently to avoid repetition.
4. **Seasonal mode**: Different palettes for seasons (not just time of day).

### 10.4 Testing Blind Spots

1. **Concurrent wallust runs**: What if user manually runs wallust while Variety reads cache?
2. **Symlinked cache directory**: ~/.cache might be on different filesystem.
3. **Wallust stderr parsing**: Current code checks for "Not enough colors" but other errors exist.
4. **Empty palette**: What if wallust produces empty JSON?

### 10.5 Recommendations for Future

1. **Phase 4 consideration**: ML-based palette grouping (cluster similar images)
2. **Integration with night light**: Sync with Redshift/Gammastep for cohesive warm tones
3. **Wallpaper preview**: Show how UI will look before applying (mock waybar colors)
4. **Palette history widget**: Show timeline of recent palettes in preferences

---

## 11. Dependencies & Requirements

### 11.1 Runtime Dependencies

| Dependency | Required | Purpose |
|------------|----------|---------|
| wallust | Yes (for color features) | Palette extraction |
| wallust.toml | Yes | Palette type detection |

### 11.2 Build/Test Dependencies

| Dependency | Purpose |
|------------|---------|
| pytest | Testing |
| pytest-benchmark | Performance tests |
| PIL/Pillow | Test image creation |

---

## 12. Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Palette extraction success rate | >95% | Log failed extractions |
| Cache read latency | <50ms | Benchmark tests |
| Color filter accuracy | User satisfaction | Feedback |
| UI responsiveness during extraction | No freezing | Manual testing |

---

## Appendix A: File Changes Summary

| File | Changes |
|------|---------|
| `variety/VarietyWindow.py` | Add cache reading, delayed record_shown |
| `variety/PreferencesVarietyDialog.py` | Color settings UI |
| `variety/Options.py` | Color config schema |
| `variety/smart_selection/selector.py` | Time-based constraints, selection modes |
| `variety/smart_selection/models.py` | Extended SelectionConstraints |
| `variety/smart_selection/palette.py` | Defensive parsing improvements |
| `data/ui/PreferencesVarietyDialog.ui` | Color settings widgets |

---

## Appendix B: Configuration Examples

### Minimal (Colors Disabled)
```ini
[smart_selection]
enabled = True
color_enabled = False
```

### Time-Based Colors
```ini
[smart_selection]
enabled = True
color_enabled = True
time_based_colors = True
prefer_warm_evening = True
prefer_cool_morning = True
```

### Strict Color Matching
```ini
[smart_selection]
enabled = True
color_enabled = True
color_similarity_threshold = 0.8
```

---

*Document Version: 1.0*
*Created: 2025-12-06*
*Last Updated: 2025-12-06*
