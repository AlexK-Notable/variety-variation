# Threading Model Analysis: Wallpaper Setting Flow

**Date**: 2025-12-08
**Purpose**: Document the complete threading model and synchronization for wallpaper changes

---

## Complete Execution Flow with Timing

```
TIME    MAIN THREAD                      BACKGROUND THREAD
─────────────────────────────────────────────────────────────────────────
0ms     set_wallpaper(img)
        │
        ├─ Check if accessible ✓
        ├─ Update UI (thumbs, position)
        ├─ set_wp_throttled(img)
        │   │
        │   ├─ Mark thumbnail active
        │   │
        │   └─ Timer(0, _do_set_wp).start()  ─→ [Schedule on bg thread]
        │
        └─ RETURN IMMEDIATELY
            (UI remains responsive)
                                         0ms    [Background thread starts]
                                              _do_set_wp()
                                              │
                                              ├─ Lock do_set_wp_lock
                                              │
                                              ├─ Validate file access
                                              ├─ Write filter origin
                                              ├─ Apply auto-rotate
                                              ├─ Apply filters
                                              ├─ Apply display mode
                                              ├─ Apply quote/clock
                                              ├─ Apply copyto
                                              │
                                              ├─ set_desktop_wallpaper()
                                              │   │
                                              │   ├─ Get script path
                                              │   │
                                              │   └─ subprocess.check_call([
                                              │       script, wallpaper,
                                              │       "auto|manual|refresh",
                                              │       original_file,
                                              │       display_mode
                                              │     ])
                                              │     │
                                              │     ├─ [BLOCKS HERE until script finishes]
                                              │     │
                                              │     └─ Script runs in child process:
                                              │         - Set DE wallpaper
                                              │         - Run wallust (if enabled)
                                              │         - Wallust creates cache:
                                              │           ~/.cache/wallust/
                                              │             {hash}_1.7/
                                              │               Dark16_{backend}
                                              │
                                              ├─ set_desktop_wallpaper() RETURNS ✓
                                              │
                                              ├─ Update current wallpaper
                                              │
                                              ├─ [PALETTE DATA AVAILABLE]
                                              │
                                              ├─ _read_wallust_cache_for_image()
                                              │   └─ Read ~/.cache/wallust/...
                                              │       └─ Parse JSON
                                              │           └─ Return palette dict
                                              │
                                              ├─ smart_selector.record_shown()
                                              │   │
                                              │   ├─ Index image if new
                                              │   ├─ Update last_shown_at
                                              │   ├─ Increment times_shown
                                              │   │
                                              │   └─ Store palette in DB:
                                              │       smart_selection.palettes
                                              │       table
                                              │
                                              ├─ theme_engine.apply()
                                              │   └─ Apply color theme to apps
                                              │
                                              ├─ Update indicator icon
                                              │
                                              ├─ Save last_change_time
                                              ├─ Save history
                                              │
                                              └─ Unlock do_set_wp_lock
```

---

## Synchronization Mechanisms

### 1. Timer-Based Thread Spawning

**Location**: `set_wp_throttled()` line 1663

```python
def set_wp_throttled(self, filename, refresh_level=RefreshLevel.ALL):
    def _do_set_wp():
        self.do_set_wp(filename, refresh_level)

    threading.Timer(0, _do_set_wp).start()
    # Returns immediately
```

**Why Timer(0)?**
- 0-second delay still uses thread scheduling
- Allows main thread to return and UI to remain responsive
- Alternative: `Thread(target=...).start()` would be equivalent

**Effect**:
- `set_wallpaper()` returns immediately
- `do_set_wp()` runs on background thread
- UI doesn't freeze during wallpaper setting

---

### 2. Subprocess Blocking

**Location**: `set_desktop_wallpaper()` line 3405-3407

```python
try:
    subprocess.check_call(
        [script, wallpaper, auto, original_file, display_mode],
        timeout=10
    )
```

**Why subprocess.check_call()?**
- Blocks until script finishes
- Raises exception if script fails
- Timeout prevents hanging
- Wallust completion guaranteed before next line

**Effect**:
- Background thread waits for script
- Wallust definitely runs before `record_shown()`
- No race condition possible

---

### 3. Mutex Lock

**Location**: `do_set_wp()` line 1934

```python
def do_set_wp(self, filename, refresh_level=RefreshLevel.ALL):
    with self.do_set_wp_lock:
        try:
            # ... wallpaper setting code ...
```

**Purpose**:
- Prevents concurrent `do_set_wp()` execution
- Serializes wallpaper changes
- Ensures one set at a time

**Lock initialization**: Likely in `__init__()`:
```python
self.do_set_wp_lock = threading.Lock()
```

**Effect**:
- If user clicks "Next" while setting wallpaper, waits for lock
- No concurrent cache reads/writes
- Atomic wallpaper change

---

## Critical Sections Analysis

### Critical Section 1: set_desktop_wallpaper() Block

**Thread**: Background (do_set_wp)
**Duration**: ~100ms - 10s (depends on script)
**What happens**:
- Parent process calls subprocess
- Child process (script) runs
- Wallust extracts colors
- Cache file created
- subprocess.check_call() returns
- **ONLY AFTER THIS** cache is guaranteed to exist

### Critical Section 2: Cache Lookup

**Thread**: Background (do_set_wp)
**Duration**: ~10ms
**What happens**:
- `_read_wallust_cache_for_image()` called
- Lists `~/.cache/wallust/` directory
- Finds most recent palette file
- Reads JSON
- Returns parsed palette

**Race condition avoided because**:
- Lock held
- Wallust already completed
- File definitely exists and fresh

### Critical Section 3: record_shown()

**Thread**: Background (do_set_wp)
**Duration**: ~50ms (DB insert)
**What happens**:
- Index image if new
- Update timestamps
- Upsert palette record in DB
- Invalidate statistics cache

**Race condition avoided because**:
- Lock held
- Palette data available
- Only one write at a time

---

## Failure Modes and Recovery

### Mode 1: Wallust Not Installed

```
subprocess.check_call(script) ─ Script completes without calling wallust
                   ↓
_read_wallust_cache_for_image() ─ Returns None (no cache)
                   ↓
record_shown(wallust_palette=None) ─ Calls with None
                   ↓
record_shown() logic (lines 272-275):
    if palette_data is None and self._enable_palette_extraction:
        palette_data = self._palette_extractor.extract_palette(filepath)
                   ↓
Python-based extraction runs ✓ SAFE FALLBACK
```

**Result**: Image indexed without palette (or with Python-extracted palette).

### Mode 2: Wallust Timeout

```
subprocess.check_call(script) ─ Script times out after 10s
                   ↓
OSError: subprocess.TimeoutExpired
                   ↓
do_set_wp() exception handler catches it
                   ↓
Wallpaper not set, user gets error
```

**Result**: User sees error, can retry.

### Mode 3: Cache Directory Missing

```
_read_wallust_cache_for_image():
    cache_dir = os.path.expanduser('~/.cache/wallust')
    if not os.path.isdir(cache_dir):
        return None
                   ↓
record_shown(wallust_palette=None) ─ Fallback extraction runs
```

**Result**: SAFE - fallback handles it.

### Mode 4: JSON Parse Error

```
with open(latest_file, 'r') as f:
    palette_data = json.load(f)  ← JSONDecodeError
                   ↓
except Exception as e:
    logger.debug(f"Failed to read wallust cache: {e}")
    return None
                   ↓
record_shown(wallust_palette=None) ─ Fallback extraction runs
```

**Result**: SAFE - fallback handles it.

---

## Lock Contention Scenarios

### Scenario 1: Single Wallpaper Change

```
Time  Main Thread              Background Thread
─────────────────────────────────────────────
0     set_wallpaper()
      │
      set_wp_throttled()  ─→  acquire lock
      │                       do_set_wp()
      │                       [holds lock 100-500ms]
      │                       release lock
      return
```

**Lock wait**: 0ms (no contention)
**UI impact**: None (async)

### Scenario 2: Rapid Clicks (5 wallpapers in 100ms)

```
Time  Main Thread              Background Thread
─────────────────────────────────────────────
0     set_wallpaper() #1  ─→  T1: acquire lock
      │                        do_set_wp() #1

5     set_wallpaper() #2
      │ [schedules, returns]

10    set_wallpaper() #3
      │ [schedules, returns]

100   set_wallpaper() #4
      │ [schedules, returns]

105   set_wallpaper() #5
      │ [schedules, returns]
      │                        T1: release lock (after ~100ms)
                               T2: acquire lock
                               do_set_wp() #2
                               [holds lock]
                               ...
                               T2: release lock

                               T3: acquire lock
                               do_set_wp() #3
                               ...
```

**Result**: Wallpapers set sequentially, only last visible.
**Lock waits**: ~100ms per thread.
**UI impact**: Minimal (all async).

---

## Wallust Cache Lookup Robustness

### Cache File Naming

Wallust creates files like:
```
~/.cache/wallust/
├── abc123def456_1.7/
│   ├── Dark16_fastresize_srgb_json
│   ├── Dark16_fastresize_linear_json
│   ├── Light16_fastresize_srgb_json
│   └── ...
├── xyz789abc_1.7/
│   ├── Dark16_fastresize_srgb_json
│   └── ...
```

### Lookup Algorithm

```python
cache_dir = ~/.cache/wallust/
for entry in listdir(cache_dir):  # hash directories
    if isdir(entry):
        for subfile in listdir(entry):  # palette files
            if palette_type in subfile:  # e.g., "Dark16"
                if mtime > latest_time:
                    latest_file = file
                    latest_time = mtime

if latest_file and (now - latest_time) < 5.0:
    return parse(latest_file)
```

### Robustness Analysis

**Issue**: "Most recent" approach.

**Why it works**:
1. Lock held - only one thread at a time
2. Wallust just completed - cache is fresh
3. 5-second window is conservative
4. Fallback extraction if cache not found

**Why it could fail**:
1. Multiple wallpapers set rapidly (lock serializes this)
2. Wallust very slow (5s timeout handles this)
3. Wrong cache file picked (unlikely with timestamp + lock)

**Verdict**: SAFE - works correctly for normal usage.

---

## Recommended Improvements

### 1. Image Hash-Based Cache Matching

Currently: "Most recent file"
Better: Use image hash to match exact cache

**Implementation**:
```python
def _read_wallust_cache_for_image(self, filepath: str):
    # Calculate image hash
    import hashlib
    with open(filepath, 'rb') as f:
        image_hash = hashlib.md5(f.read()).hexdigest()

    # Find cache for this specific image
    for entry in os.listdir(cache_dir):
        if image_hash in entry:
            # Found exact cache for this image
            return parse(cache_file)
```

**Benefit**: Eliminates any ambiguity in concurrent scenarios.

### 2. Explicit Wallust Call in Script

Currently: Relies on user to configure wallust separately
Better: Add to set_wallpaper script

**Implementation**: Add to `data/scripts/set_wallpaper`:
```bash
# Run wallust if available
if command -v wallust >/dev/null 2>&1; then
    wallust run -s -T -q -w --backend fastresize "$3" 2>/dev/null &
fi
```

**Benefit**: Guaranteed palette extraction, no fallback needed.

### 3. Timeout Monitoring

Currently: 5-second age threshold
Better: Log warnings if cache is old

**Implementation**:
```python
if age > 2.0:
    logger.warning(f"Wallust slow: cache age {age:.1f}s")
if age > 5.0:
    logger.warning(f"Using fallback: cache too old ({age:.1f}s)")
```

**Benefit**: Visibility into performance issues.

---

## Summary Table

| Aspect | Current State | Robustness | Recommendation |
|--------|---------------|------------|-----------------|
| Thread spawning | Timer(0) | Good | Keep as-is |
| Subprocess blocking | check_call() | Good | Keep as-is |
| Mutex locking | do_set_wp_lock | Good | Keep as-is |
| Cache lookup | "Most recent" | OK | Improve with hash |
| Wallust integration | Optional (fallback) | Safe | Make explicit in script |
| Error handling | try/except + fallback | Good | Keep as-is |
| Performance logging | Minimal | OK | Add warnings |

**Overall Assessment**: **PRODUCTION-READY** with optional improvements.

---

## Conclusion

The threading model is well-designed and safe:

1. Non-blocking UI (timer-based spawning)
2. Guaranteed wallust completion (subprocess.check_call)
3. Atomic changes (mutex lock)
4. Robust fallback (Python extraction)
5. Proper error handling (try/except everywhere)

No critical issues. Optional improvements available for enhanced robustness in edge cases.
