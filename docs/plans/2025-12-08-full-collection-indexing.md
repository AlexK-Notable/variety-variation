# Full Collection Indexing - Implementation Plan

**Date:** 2025-12-08
**Status:** Planned
**Agent:** fd9b78d2

---

## Current Indexer Architecture

### Existing Components

**ImageIndexer (`variety/smart_selection/indexer.py`)**
- `scan_directory(directory, recursive)` - Scans for image files, returns list of paths
- `index_image(filepath)` - Extracts metadata using PIL, returns ImageRecord
- `index_directory(directory, recursive, batch_size=100)` - Scans and indexes with batch inserts
- Uses mtime checking to skip unchanged files

**ImageDatabase (`variety/smart_selection/database.py`)**
- Thread-safe via `threading.RLock()`
- WAL mode enabled for concurrent performance
- `batch_upsert_images()` for bulk operations

**Current Startup Indexing (`variety/VarietyWindow.py:367-427`)**
```python
def _index_all_sources():
    indexer = ImageIndexer(self.smart_selector.db, favorites_folder=...)
    folders_to_index = [favorites_folder, download_folder, fetched_folder, user_folders]
    for folder in folders_to_index:
        indexer.index_directory(folder, recursive=True)

index_thread = threading.Thread(target=_index_all_sources, daemon=True)
index_thread.start()
```

### Current Limitations

1. **No progress reporting** - No callback mechanism during indexing
2. **Per-file database queries** - `db.get_image()` called for EVERY file
3. **No bulk mtime checking** - Cannot efficiently determine which files changed
4. **No file deletion tracking** - Deleted files remain in index
5. **Memory unbounded** - `scan_directory()` returns full list in memory

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FULL COLLECTION INDEXER                          │
├─────────────────────────────────────────────────────────────────────┤
│  1. STARTUP SEQUENCE:                                               │
│     _init_smart_selector()                                          │
│        └─ start_background_indexing()                               │
│              └─ Thread: _index_all_sources_with_progress()          │
│                   ├─ Phase 1: Index favorites (high priority)       │
│                   ├─ Phase 2: Index Downloaded folder               │
│                   ├─ Phase 3: Index Fetched folder                  │
│                   └─ Phase 4: Index user source folders             │
│                                                                     │
│  2. INCREMENTAL INDEXING:                                           │
│     a) Load existing index into memory (filepath → mtime mapping)   │
│     b) Scan directory, compare mtimes                               │
│     c) Batch insert NEW files                                       │
│     d) Batch update CHANGED files (mtime changed)                   │
│     e) Batch delete REMOVED files (in index but not on disk)        │
│                                                                     │
│  3. PROGRESS REPORTING:                                             │
│     progress_callback(phase, current, total, message)               │
│                                                                     │
│  4. MEMORY MANAGEMENT:                                              │
│     - Stream file paths using os.scandir() generator                │
│     - Process in batches of 500 files                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### 1. New Database Methods

```python
# In database.py

def get_indexed_mtime_map(self, folder_prefix: str) -> Dict[str, int]:
    """Get filepath→mtime mapping for files under a folder prefix.

    Enables O(1) lookup instead of O(n) queries.
    For 10,000 files: ~20MB memory, saves ~10,000 DB queries.
    """
    with self._lock:
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT filepath, file_mtime FROM images WHERE filepath LIKE ?',
            (folder_prefix + '%',)
        )
        return {row['filepath']: row['file_mtime'] for row in cursor.fetchall()}

def batch_delete_images(self, filepaths: List[str]):
    """Delete multiple images in a single transaction."""
    if not filepaths:
        return
    with self._lock:
        cursor = self.conn.cursor()
        # SQLite has 999 parameter limit, batch in chunks
        for i in range(0, len(filepaths), 500):
            chunk = filepaths[i:i+500]
            placeholders = ','.join('?' * len(chunk))
            cursor.execute(
                f'DELETE FROM images WHERE filepath IN ({placeholders})',
                chunk
            )
        self.conn.commit()
```

### 2. Enhanced ImageIndexer

```python
# In indexer.py

@dataclass
class IndexingResult:
    """Result of an indexing operation."""
    added: int = 0
    updated: int = 0
    removed: int = 0

class ImageIndexer:
    def index_directory_incremental(
        self,
        directory: str,
        recursive: bool = True,
        batch_size: int = 500,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> IndexingResult:
        """Incrementally index a directory with progress reporting."""

        # Step 1: Load existing index for this directory
        indexed_mtime = self.db.get_indexed_mtime_map(directory)
        indexed_paths = set(indexed_mtime.keys())

        # Step 2: Scan directory (generator to save memory)
        disk_paths = set()
        to_index: List[str] = []
        to_update: List[str] = []

        for filepath in self._scan_directory_generator(directory, recursive):
            disk_paths.add(filepath)

            if filepath not in indexed_paths:
                to_index.append(filepath)
            else:
                try:
                    current_mtime = int(os.stat(filepath).st_mtime)
                    if current_mtime != indexed_mtime[filepath]:
                        to_update.append(filepath)
                except OSError:
                    pass

        # Step 3: Find deleted files
        to_delete = indexed_paths - disk_paths

        # Step 4: Process changes in batches
        total_work = len(to_index) + len(to_update) + len(to_delete)
        processed = 0

        # Index new files
        for batch in self._batch(to_index, batch_size):
            records = [self.index_image(f) for f in batch if f]
            records = [r for r in records if r]
            self.db.batch_upsert_images(records)
            processed += len(batch)
            if progress_callback:
                progress_callback(processed, total_work, "Indexing new files...")

        # Update modified files
        for batch in self._batch(to_update, batch_size):
            records = []
            for filepath in batch:
                existing = self.db.get_image(filepath)
                new_record = self.index_image(filepath)
                if new_record and existing:
                    # Preserve selection history
                    new_record.first_indexed_at = existing.first_indexed_at
                    new_record.times_shown = existing.times_shown
                    new_record.last_shown_at = existing.last_shown_at
                    records.append(new_record)
            self.db.batch_upsert_images(records)
            processed += len(batch)
            if progress_callback:
                progress_callback(processed, total_work, "Updating modified files...")

        # Delete removed files
        if to_delete:
            self.db.batch_delete_images(list(to_delete))

        return IndexingResult(
            added=len(to_index),
            updated=len(to_update),
            removed=len(to_delete),
        )

    def _scan_directory_generator(self, directory: str, recursive: bool):
        """Generator that yields file paths without loading all into memory."""
        directory = os.path.normpath(directory)

        if recursive:
            for root, _, files in os.walk(directory):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    if self._is_image_file(filepath):
                        yield filepath
        else:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_file() and self._is_image_file(entry.path):
                        yield entry.path

    @staticmethod
    def _batch(items: List[Any], size: int) -> Iterator[List[Any]]:
        """Yield successive batches from list."""
        for i in range(0, len(items), size):
            yield items[i:i+size]
```

### 3. VarietyWindow Integration

```python
# In VarietyWindow.py

def _start_background_indexing(self):
    """Start background indexing with progress reporting."""

    def _index_with_progress():
        try:
            indexer = ImageIndexer(
                self.smart_selector.db,
                favorites_folder=self.options.favorites_folder
            )

            folders = []

            # Priority 1: Favorites
            if self.options.favorites_folder and os.path.exists(self.options.favorites_folder):
                folders.append(('Favorites', self.options.favorites_folder))

            # Priority 2: Downloaded
            download_folder = self.real_download_folder or self.options.download_folder
            if download_folder and os.path.exists(download_folder):
                folders.append(('Downloaded', download_folder))

            # Priority 3: Fetched
            if self.options.fetched_folder and os.path.exists(self.options.fetched_folder):
                folders.append(('Fetched', self.options.fetched_folder))

            # Priority 4: User source folders
            for source in self.options.sources:
                enabled, source_type, location = source
                if enabled and source_type == Options.SourceType.FOLDER:
                    folder = os.path.expanduser(location)
                    if os.path.exists(folder):
                        folders.append(('Source', folder))

            total_phases = len(folders)
            for phase_idx, (phase_name, folder) in enumerate(folders):
                def progress_callback(current, total, message):
                    self._on_indexing_progress(
                        phase_idx + 1, total_phases,
                        phase_name, current, total, message
                    )

                result = indexer.index_directory_incremental(
                    folder,
                    recursive=True,
                    progress_callback=progress_callback
                )

                logger.info(
                    f"Smart Selection: {phase_name} indexed - "
                    f"added={result.added}, updated={result.updated}, removed={result.removed}"
                )

            self._on_indexing_complete()

        except Exception as e:
            logger.warning(f"Smart Selection: Background indexing failed: {e}")

    self._indexing_thread = threading.Thread(target=_index_with_progress, daemon=True)
    self._indexing_thread.start()
```

---

## Memory Budget (10,000 images)

| Component | Memory Usage | Notes |
|-----------|--------------|-------|
| `indexed_mtime` dict | ~2 MB | 10K entries x 200 bytes |
| `disk_paths` set | ~2 MB | 10K paths |
| `to_index/to_update/to_delete` | ~1 MB | Path strings |
| Batch of ImageRecords | ~5 MB | 500 records x 10KB |
| PIL image (single) | ~50 MB | 4K image, released per file |
| **Peak usage** | **~60 MB** | Well under 100MB target |

---

## Performance Targets

| Metric | Target | Implementation |
|--------|--------|----------------|
| Index 10,000 images | <30 seconds | Batch inserts, skip unchanged |
| Re-index (no changes) | <5 seconds | Bulk mtime comparison |
| Memory usage | <100 MB | Generator scanning, batch processing |
| UI responsiveness | No blocking | Background thread, throttled progress |

---

## Test Cases

### Unit Tests
```python
def test_empty_directory_returns_zero_counts():
def test_new_files_indexed_on_first_run():
def test_unchanged_files_not_reindexed():
def test_modified_files_reindexed():
def test_deleted_files_removed_from_index():
def test_new_files_added_to_existing_index():
def test_progress_callback_called():
def test_batch_size_respected():
def test_selection_history_preserved_on_update():
```

### Performance Tests
```python
@pytest.mark.benchmark
def test_index_100_images_performance():
@pytest.mark.benchmark
@pytest.mark.slow
def test_index_10000_images_under_30_seconds():
@pytest.mark.benchmark
def test_reindex_10000_unchanged_under_5_seconds():
def test_memory_usage_under_100mb():
```

### Database Tests
```python
def test_get_indexed_mtime_map_returns_dict():
def test_get_indexed_mtime_map_filters_by_prefix():
def test_batch_delete_images_removes_files():
def test_batch_delete_handles_large_lists():
```

---

## Files to Modify

1. **`variety/smart_selection/database.py`** - Add `get_indexed_mtime_map()`, `batch_delete_images()`
2. **`variety/smart_selection/indexer.py`** - Add `index_directory_incremental()`, `IndexingResult`
3. **`variety/smart_selection/models.py`** - Add `IndexingResult` dataclass
4. **`variety/VarietyWindow.py`** - Add `_start_background_indexing()`, progress callbacks
5. **`tests/smart_selection/test_indexer.py`** - Add incremental indexing tests
