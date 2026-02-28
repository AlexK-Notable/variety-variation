# Code Quality Review - Smart Selection Engine

## Executive Summary

The Smart Selection Engine demonstrates solid architecture with good separation of concerns, comprehensive documentation, and thoughtful error handling. The codebase follows Python best practices with consistent naming conventions, proper type hints, and appropriate use of dataclasses. Key areas for improvement include reducing code duplication in row-to-record conversions, addressing potential thread-safety edge cases, and adding missing validation in a few critical paths.

## Critical Issues

### 1. Duplicate Method Definition in indexer.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/indexer.py`
**Lines:** 79-89 and 422-432

The `_is_image_file` method is defined twice in the `ImageIndexer` class with identical implementations:

```python
# Lines 79-89
def _is_image_file(self, filepath: str) -> bool:
    """Check if a file is a supported image format."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in IMAGE_EXTENSIONS

# Lines 422-432
def _is_image_file(self, filepath: str) -> bool:
    """Check if a file is a supported image format."""
    _, ext = os.path.splitext(filepath)
    return ext.lower() in IMAGE_EXTENSIONS
```

**Impact:** The second definition shadows the first, potentially causing confusion during maintenance. While both are functionally equivalent, this is a code smell indicating incomplete refactoring.

**Recommendation:** Remove the duplicate method definition at lines 422-432.

---

### 2. Missing Thread-Safety in WallustConfigManager

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/wallust_config.py`
**Lines:** 102-153

The `WallustConfigManager` class caches configuration but lacks thread-safety for cache access:

```python
def _get_config(self) -> Dict[str, str]:
    """Get wallust config, re-parsing if file changed."""
    # ...
    if self._config_cache is None or self._config_mtime != current_mtime:
        self._config_cache = parse_wallust_config()  # Not atomic!
        self._config_mtime = current_mtime
    return self._config_cache
```

**Impact:** In multi-threaded contexts, race conditions could cause:
- Multiple threads to parse config simultaneously (wasteful)
- One thread reading partially-updated cache state

**Recommendation:** Add a threading.Lock to protect cache reads/writes, similar to the pattern used in `ThemeEngine._template_cache_lock`.

---

## Major Issues

### 1. SQL Query Using String Interpolation for LIMIT/OFFSET

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/database.py`
**Lines:** 683-689

```python
query = '''
    SELECT i.* FROM images i
    LEFT JOIN palettes p ON i.filepath = p.filepath
    WHERE p.filepath IS NULL
'''
if limit:
    query += f' LIMIT {limit} OFFSET {offset}'
```

**Impact:** While `limit` and `offset` are integers (not user input), using f-string interpolation in SQL queries is a code smell that could lead to SQL injection if the pattern is copied elsewhere.

**Recommendation:** Use parameterized queries consistently:
```python
if limit:
    query += ' LIMIT ? OFFSET ?'
    cursor.execute(query, (limit, offset))
```

---

### 2. Broad Exception Handling in palette.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/palette.py`
**Lines:** 291-298

```python
try:
    result = subprocess.run(
        [self.wallust_path, '--version'],
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0
except Exception:
    return False
```

**Impact:** Catching bare `Exception` swallows all errors including `KeyboardInterrupt` and `SystemExit`, making debugging difficult.

**Recommendation:** Catch specific exceptions: `subprocess.SubprocessError`, `OSError`, `FileNotFoundError`.

---

### 3. Potential Resource Leak in theming.py Timer Handling

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/theming.py`
**Lines:** 806-824

```python
def _apply_debounced(self, image_path: str) -> bool:
    with self._debounce_lock:
        self._pending_image = image_path
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            # Don't join here - it could block if timer is executing
            self._debounce_timer = None
        self._debounce_timer = threading.Timer(...)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()
    return True
```

**Impact:** While daemon threads won't prevent exit, cancelled timers may accumulate if not properly cleaned up. The comment acknowledges this but the cleanup in `cleanup()` only cancels the current timer.

**Recommendation:** Consider using a single persistent worker thread with a queue instead of creating/destroying timers repeatedly.

---

### 4. Incomplete Error Handling in selector.py record_shown

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/selector.py`
**Lines:** 320-338

```python
def record_shown(self, filepath: str, wallust_palette: Dict[str, Any] = None):
    existing = self.db.get_image(filepath)
    if not existing and os.path.exists(filepath):
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(self.db)
        record = indexer.index_image(filepath)
        if record:
            self.db.upsert_image(record)
```

**Impact:** If `index_image` fails (returns None), the method continues to call `record_image_shown` which may fail silently or cause a database error if the image doesn't exist.

**Recommendation:** Add explicit handling when indexing fails:
```python
if not record:
    logger.warning(f"Failed to index image for recording: {filepath}")
    return
```

---

### 5. Magic Numbers in statistics.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/statistics.py`
**Lines:** 179, 187-188, 237, 262

```python
threshold = total_with_palettes * 0.05  # Magic number
percentage = int(count / total_with_palettes * 100)
if percentage >= 40:  # Another magic number
```

**Impact:** Magic numbers make the code harder to maintain and tune. The 5% threshold and 40% "dominance" threshold are business logic that should be configurable or at least named constants.

**Recommendation:** Define constants at class or module level:
```python
GAP_THRESHOLD_PERCENT = 0.05
DOMINANCE_THRESHOLD_PERCENT = 0.40
```

---

## Minor Issues

### 1. Repetitive Row-to-Record Conversion Code

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/database.py`
**Lines:** 430-453, 497-502, 513-521, 635-651, 725-743

The database class has multiple nearly-identical row conversion methods:

- `_row_to_image_record` (lines 430-453)
- `_row_to_palette_record` (lines 725-743)
- Inline SourceRecord construction (lines 497-502, 513-521, 565-571)

**Recommendation:** Create a private `_row_to_source_record` method for consistency, or use a generic factory pattern.

---

### 2. Inconsistent Naming: `color_affinity` vs `color_match_weight`

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/weights.py`
**Lines:** 115-178

The function is named `color_affinity_factor` but uses `config.color_match_weight`:

```python
def color_affinity_factor(..., config: SelectionConfig, ...):
    if not config.color_match_weight or not target_palette:
        return 1.0
```

**Impact:** Minor naming inconsistency may cause confusion.

**Recommendation:** Consider renaming for consistency (either both use "affinity" or both use "match_weight").

---

### 3. Unused Import in indexer.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/indexer.py`
**Line:** 11

```python
from typing import Optional, List, Dict, Any, Set, Callable, Iterator
```

`Dict` and `Any` are imported but only used in `get_index_stats` return type annotation. The return type could be simplified or the imports cleaned up.

---

### 4. Long Method: `extract_palette` in palette.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/palette.py`
**Lines:** 311-435

The `extract_palette` method is 124 lines long, handling subprocess execution, cache searching, JSON parsing, and error handling.

**Recommendation:** Extract the cache-searching logic into a separate `_find_cache_file` method.

---

### 5. Inconsistent Docstring Format in theming.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/theming.py`

Some methods have full Google-style docstrings while others are minimal:

```python
# Full docstring (lines 86-96)
def strip(self, color: str) -> str:
    """Remove # prefix from color.

    Args:
        color: Hex color string.

    Returns:
        Color without # prefix.
    """

# Minimal docstring (lines 922-929)
def get_enabled_templates(self) -> List[TemplateConfig]:
    """Get list of enabled templates."""
```

**Recommendation:** Standardize on full docstrings for all public methods.

---

### 6. Potential Division by Zero in weights.py

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/weights.py`
**Lines:** 51-54

```python
if elapsed_seconds >= cooldown_seconds:
    return 1.0

progress = elapsed_seconds / cooldown_seconds
```

**Impact:** If `cooldown_seconds` is 0 (which shouldn't happen given the check at line 37), this would raise `ZeroDivisionError`. The early return at line 37 protects this, but the logic is fragile.

**Recommendation:** Add an explicit guard or assertion.

---

### 7. Hardcoded Template Directory Path

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/theming.py`
**Lines:** 445-447

```python
WALLUST_CONFIG = os.path.expanduser('~/.config/wallust/wallust.toml')
WALLUST_TEMPLATES_DIR = os.path.expanduser('~/.config/wallust/templates')
VARIETY_CONFIG = os.path.expanduser('~/.config/variety/theming.json')
```

**Impact:** These paths are hardcoded at class level but can be overridden in `__init__`. The `WALLUST_TEMPLATES_DIR` is not overridable.

**Recommendation:** Make `templates_dir` configurable via `__init__` for testing flexibility.

---

### 8. Missing Type Hints in Some Callback Parameters

**File:** `/home/komi/repos/variety-variation/variety/smart_selection/selector.py`
**Lines:** 290, 404-406

```python
def record_shown(self, filepath: str, wallust_palette: Dict[str, Any] = None):
    # wallust_palette should be Optional[Dict[str, Any]]

def rebuild_index(self, source_folders: List[str] = None, ...):
    # source_folders should be Optional[List[str]]
```

**Recommendation:** Use `Optional[...]` explicitly for parameters with `None` defaults.

---

## Observations

### Positive Patterns

1. **Excellent Documentation**: Almost every class and method has comprehensive docstrings explaining purpose, arguments, return values, and edge cases.

2. **Thread-Safety Awareness**: The codebase shows consistent awareness of thread-safety with locks in `ImageDatabase`, `CollectionStatistics`, and `ThemeEngine`.

3. **Context Manager Support**: Classes that manage resources (`ImageDatabase`, `SmartSelector`) properly implement `__enter__` and `__exit__`.

4. **Defensive Programming**: Good use of early returns, input validation, and fallback values throughout.

5. **Batch Operations**: Database operations are batched for performance (`batch_upsert_images`, `batch_delete_images`).

6. **Comprehensive Error Handling**: Most external operations (subprocess calls, file I/O, database operations) have appropriate exception handling.

7. **Clean Separation of Concerns**:
   - `models.py` - Data structures only
   - `config.py` - Configuration only
   - `database.py` - Persistence only
   - `weights.py` - Pure calculation functions
   - `selector.py` - Orchestration

8. **Consistent Coding Style**: Files follow the same header format, indentation, and naming conventions.

### Architectural Notes

1. **Database Design**: The SQLite schema with WAL mode is appropriate for this use case (single writer, multiple readers).

2. **Caching Strategy**: Statistics caching with invalidation is well-designed for the expected usage patterns.

3. **Plugin Architecture**: The `PaletteExtractor` is cleanly separated from the wallust dependency, allowing for alternative implementations.

---

## Recommendations

### High Priority

1. **Fix the duplicate `_is_image_file` method** in `indexer.py` - this is a clear bug that should be addressed immediately.

2. **Add thread-safety to `WallustConfigManager`** - this is called from multiple places and could cause subtle race conditions.

3. **Parameterize SQL queries consistently** - even when values are known-safe, using string interpolation sets a bad precedent.

### Medium Priority

4. **Extract cache-searching logic** from `PaletteExtractor.extract_palette` into a separate method for testability.

5. **Define named constants** for magic numbers in `statistics.py`.

6. **Create `_row_to_source_record`** method for consistency with other row conversion methods.

### Low Priority

7. **Standardize docstring format** across all modules.

8. **Consider a persistent worker thread** instead of timer creation/destruction in `ThemeEngine`.

9. **Add `Optional[...]` type hints** for parameters with `None` defaults.

### Testing Recommendations

1. Add tests for concurrent access to `WallustConfigManager`.
2. Add tests for edge cases in `recency_factor` (negative elapsed time, zero cooldown).
3. Add integration tests for `ThemeEngine` template processing with various wallust configurations.
