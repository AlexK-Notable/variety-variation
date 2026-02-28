# Performance Analysis - Smart Selection Engine

## Executive Summary

The Smart Selection Engine demonstrates **strong foundational performance design** with proper batch processing, O(log n) weighted random selection using binary search, and effective use of database indexes. Recent optimizations have addressed critical N+1 query patterns. However, opportunities remain for improving memory efficiency in large collections, reducing subprocess overhead in palette extraction, and adding performance regression tests.

## Performance Strengths

### 1. Database Layer (database.py)

**WAL Mode for Concurrency**
- Uses `PRAGMA journal_mode=WAL` for improved concurrent read/write performance
- Better crash recovery characteristics than the default rollback journal
- Reduces lock contention in multi-threaded scenarios

**Thread Safety via RLock**
- `threading.RLock` serializes all database operations
- Reentrant lock allows nested locking within the same thread
- Safe for Variety's GTK main thread + background worker architecture

**Strategic Indexing**
- Index on `source_id` for source-filtered queries - O(log n) vs O(n)
- Index on `last_shown_at` for recency-based sorting
- Index on `is_favorite` for favorites filtering
- Index on palette metrics (`avg_lightness`, `color_temperature`) for color queries

**Batch Operations**
- `batch_upsert_images()` uses `executemany()` for bulk inserts - O(n) vs O(n^2) for individual commits
- `batch_upsert_sources()` similarly optimized
- `batch_delete_images()` handles large deletions in 500-record chunks to avoid SQLite parameter limit (999)

**Chunked Palette Loading**
- `get_palettes_by_filepaths()` processes in 500-record chunks
- Prevents SQLite parameter limit errors
- Memory-efficient for large collections

### 2. Selection Algorithm (selector.py)

**O(log n) Weighted Random Selection**
- Uses `bisect.bisect_left()` for binary search on cumulative weights
- Selection complexity: O(k * log n) for k images from n candidates
- Previous naive implementation was O(k * n)

**Batch Source/Palette Loading**
- `select_images()` loads all sources in a single query via `get_sources_by_ids()`
- Palettes loaded in batch when color constraints are active
- Eliminates N+1 query pattern in the hot path

**File Existence Filtering**
- Filters phantom index entries with `os.path.exists()` before selection
- Prevents returning paths to deleted files
- Minimal overhead: one syscall per candidate (stat is cached by OS)

### 3. Weight Calculation (weights.py)

**Efficient Decay Functions**
- Recency factor uses simple arithmetic for linear/step decay
- Exponential decay uses sigmoid approximation: `1 / (1 + exp(-x))`
- All calculations are O(1) with no allocations

**Guard Against Zero Weights**
- Minimum weight floor of `1e-6` prevents division by zero
- Avoids degenerate selection behavior

### 4. Indexing (indexer.py)

**Memory-Efficient Directory Scanning**
- `_scan_directory_generator()` yields paths lazily using `os.walk()`
- Non-recursive scanning uses `os.scandir()` for better performance than `os.listdir()`
- Avoids loading all paths into memory at once

**Incremental Indexing**
- `index_directory_incremental()` loads existing mtime map for O(1) lookup
- Only processes changed files
- Detects and removes deleted files

**Batch Processing**
- Configurable batch size (default 500)
- Reduces transaction overhead
- Memory bounded by batch size

### 5. Statistics (statistics.py)

**Cache-All-or-Nothing Design**
- Single invalidation flag ensures cache consistency
- All distributions cached together in one pass
- Thread-safe with lock protection

**Efficient Aggregate Queries**
- Uses SQL `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` pattern
- Single table scan per distribution
- No row-by-row processing in Python

## Critical Bottlenecks

### 1. Palette Extraction Subprocess Overhead

**Location:** `palette.py` - `PaletteExtractor.extract_palette()`

**Complexity:** O(1) per image, but with **30ms-500ms wall-clock time** per subprocess

**Issue:**
```python
result = subprocess.run(
    [self.wallust_path, 'run', '-s', '-T', '-q', '-w', '--backend', 'fastresize', image_path],
    capture_output=True,
    timeout=30,
)
```

- Each extraction spawns a new process
- Process creation overhead: ~5-20ms on Linux
- `wallust` itself takes 20-200ms depending on image size
- Cache discovery scans entire `~/.cache/wallust/` directory

**Impact:** For 1000 images, `extract_all_palettes()` takes 30-500 seconds.

**Recommendations:**
1. Consider batch mode if wallust supports it (check for multi-file input)
2. Implement parallel extraction with `concurrent.futures.ThreadPoolExecutor`
3. Use a file watcher or hash-based cache lookup instead of timestamp scanning

### 2. Full Image Load for Dimension Extraction

**Location:** `indexer.py` - `index_image()`

**Issue:**
```python
with Image.open(filepath) as img:
    width, height = img.size
```

- PIL fully parses image headers
- For JPEG: reads entire EXIF metadata
- Memory allocation for image object even though we only need dimensions

**Impact:** ~5-20ms per image, memory pressure for large images

**Recommendations:**
1. Use `PIL.Image.open(filepath).size` without context manager for lazy mode
2. Consider using `imagesize` library (pure Python, header-only parsing)
3. For JPEG: use `struct` to parse dimensions directly from file header (~10 bytes)

### 3. Repeated File Existence Checks

**Location:** `selector.py` - `_get_candidates()`

**Issue:**
```python
candidates = [img for img in candidates if os.path.exists(img.filepath)]
```

**Complexity:** O(n) syscalls for n candidates

**Impact:** For 10,000 images, this is 10,000 stat() calls. While individually fast (~0.1ms), it adds up to ~1 second.

**Mitigation (already documented in code):**
- OS filesystem cache makes repeated checks fast
- TOCTOU race is acknowledged and documented
- Callers should handle FileNotFoundError as final safety net

**Recommendations:**
1. Consider periodic cleanup job to remove stale entries
2. Cache existence checks within a selection session (valid for ~1 second)
3. Use `os.scandir()` batch check if checking files in same directory

### 4. Lock Contention in High-Frequency Operations

**Location:** `database.py` - all operations use `with self._lock:`

**Issue:** Every database operation acquires the global lock, including statistics queries.

**Impact:** In multi-threaded scenarios:
- Background indexer blocks UI statistics refresh
- Concurrent record_shown calls serialize completely

**Recommendations:**
1. Use read-write lock (readers can proceed in parallel)
2. Separate connection pools for read-only and read-write operations
3. Use SQLite's built-in locking (remove Python-level lock for read operations)

## Optimization Opportunities

### 1. Lazy Palette Extraction

**Current:** Palettes extracted synchronously in `record_shown()` when `enable_palette_extraction=True`

**Opportunity:** Queue palette extraction for background processing

```python
# Instead of:
palette_data = self._palette_extractor.extract_palette(filepath)

# Consider:
self._palette_queue.put(filepath)  # Background thread processes
```

**Benefit:** Reduces `record_shown()` latency from ~100ms to ~5ms

### 2. Connection Pool for Read Operations

**Current:** Single connection shared across all operations

**Opportunity:** Separate read-only connection pool

```python
# Read operations could use a pool
self._read_pool = [sqlite3.connect(db_path, check_same_thread=False) for _ in range(3)]
```

**Benefit:** Concurrent statistics queries during indexing

### 3. Prepared Statement Caching

**Current:** SQL strings compiled each query

**Opportunity:** Use `cursor.execute()` with pre-compiled statements

**Benefit:** Minor improvement (~5-10%) for frequently executed queries

### 4. Statistics Distribution Caching at Write Time

**Current:** Statistics calculated on demand by scanning tables

**Opportunity:** Maintain running counts in a `stats` table, updated on insert/update

```sql
CREATE TABLE stats (
    bucket TEXT PRIMARY KEY,
    count INTEGER
);
```

**Benefit:** O(1) statistics retrieval instead of O(n) table scan

### 5. Binary Search for Color Similarity

**Current:** Linear scan of all candidates for color filtering

**Opportunity:** Use k-d tree or ball tree for multidimensional nearest neighbor

**Benefit:** O(log n) for finding similar palettes instead of O(n)

## Memory Analysis

### Current Memory Usage Patterns

| Component | Memory Usage | Growth Pattern |
|-----------|--------------|----------------|
| ImageRecord | ~200 bytes each | O(n) with image count |
| PaletteRecord | ~500 bytes each | O(n) with palette count |
| Selection candidates list | ~8 bytes/ptr + ImageRecord | O(n) during selection |
| Cumulative weights array | ~8 bytes/float | O(n) per selection |
| mtime lookup map | ~50 bytes/entry | O(n) during incremental indexing |

### Memory Concerns

**1. Full Candidate List in Memory**
- `get_all_images()` loads all images at once
- For 50,000 images: ~10MB in ImageRecord objects
- Add weights array: ~400KB
- Total: ~11MB peak during selection

**2. Incremental Index mtime Map**
- `get_indexed_mtime_map()` loads all filepaths and mtimes
- For 50,000 images: ~2.5MB (50 bytes * 50,000)
- Documentation acknowledges: "~20MB memory for 10,000 files"

**3. Failed Files Set in extract_all_palettes()**
```python
failed_files: Set[str] = set()  # Track failures to avoid infinite loop
```
- Grows unbounded if many extractions fail
- For 10,000 failures: ~500KB

### Memory Recommendations

1. **Stream candidates instead of loading all:**
   ```python
   def get_candidates_cursor(self, constraints):
       cursor.execute('SELECT * FROM images ...')
       for row in cursor:  # Streams rows
           yield self._row_to_image_record(row)
   ```

2. **Limit failed_files set size:**
   ```python
   if len(failed_files) > 10000:
       failed_files.clear()  # Or use LRU cache
   ```

3. **Use `__slots__` in dataclasses:**
   ```python
   @dataclass(slots=True)
   class ImageRecord:
       ...
   ```
   Benefit: ~40% memory reduction per instance

## Benchmark Coverage

### Existing Test Coverage

| Category | Coverage | Notes |
|----------|----------|-------|
| CRUD Operations | Good | test_database.py covers all basic operations |
| Thread Safety | Good | Concurrent insert/read/update tests |
| Weighted Selection | Good | Float precision edge cases covered |
| Batch Operations | Partial | Batch upsert tested, batch palette loading tested |
| Large Collections | Missing | No 10K+ image performance tests |
| Memory Usage | Missing | No memory profiling tests |
| Selection Latency | Missing | No timing assertions |
| Indexing Performance | Missing | No benchmarks for incremental indexing |

### Missing Benchmarks

**1. Selection Latency Under Load**
```python
def test_selection_latency_10k_images(self):
    """Selection should complete in <100ms for 10K images."""
    # Insert 10K images
    # Time selector.select_images(count=10)
    # Assert latency < 100ms
```

**2. Indexing Throughput**
```python
def test_indexing_throughput(self):
    """Incremental indexing should process 1000 images/second."""
    # Create 1000 test images
    # Time indexer.index_directory_incremental()
    # Assert throughput > 1000/s
```

**3. Memory Regression**
```python
def test_memory_usage_scaling(self):
    """Memory should scale linearly with image count."""
    # Use tracemalloc to measure memory
    # Insert 1K, 5K, 10K images
    # Assert linear growth (no leaks)
```

**4. Database Size**
```python
def test_database_size_per_image(self):
    """Database should use <1KB per image."""
    # Insert 10K images with palettes
    # Check file size
    # Assert size < 10MB
```

## Recommendations

### Priority 1: Critical (Should Fix)

1. **Add performance regression tests**
   - Selection latency: <100ms for 10K images
   - Indexing throughput: >500 images/second
   - Memory: <50MB for 50K images

2. **Implement parallel palette extraction**
   - Use `ThreadPoolExecutor(max_workers=4)`
   - Queue-based architecture for background processing
   - Expected improvement: 3-4x faster batch extraction

### Priority 2: High (Should Consider)

3. **Use imagesize library for dimension extraction**
   - Drop-in replacement for PIL dimension reading
   - 10-50x faster for JPEG/PNG
   - No full image header parsing

4. **Add periodic stale entry cleanup**
   - Remove entries for missing files during idle time
   - Reduces `os.path.exists()` checks in hot path

### Priority 3: Medium (Nice to Have)

5. **Implement read-write lock or remove Python lock for reads**
   - SQLite handles read concurrency well
   - Python lock only needed for writes

6. **Add `__slots__` to model dataclasses**
   - Python 3.10+ supports `@dataclass(slots=True)`
   - ~40% memory reduction

7. **Consider k-d tree for color similarity**
   - Only worthwhile if color filtering is common
   - Libraries: `scipy.spatial.KDTree` or `sklearn.neighbors.BallTree`

### Priority 4: Low (Future Enhancement)

8. **Streaming candidate iteration**
   - Replace `get_all_images()` with generator
   - Reduces peak memory

9. **Prepared statement caching**
   - Minor improvement for high-frequency queries

10. **Statistics table for O(1) distribution queries**
    - Maintain running counts updated on insert/delete

## Appendix: Big-O Complexity Summary

| Operation | Time | Space | Notes |
|-----------|------|-------|-------|
| `select_images(k)` | O(n + k log n) | O(n) | n=candidates, k=count |
| `calculate_weight()` | O(1) | O(1) | Pure calculation |
| `record_shown()` | O(1) | O(1) | Single row update |
| `index_image()` | O(1) | O(1) | Single file processing |
| `index_directory()` | O(n) | O(n) | n=files in directory |
| `get_all_images()` | O(n) | O(n) | Full table scan |
| `get_sources_by_ids(k)` | O(k) | O(k) | Indexed lookup |
| `get_palettes_by_filepaths(k)` | O(k) | O(k) | Chunked query |
| `get_lightness_counts()` | O(n) | O(1) | Single aggregate query |
| `extract_palette()` | O(1)* | O(1) | *Wall-clock: 30-500ms |
| `extract_all_palettes()` | O(n) | O(n) | n=images without palettes |
