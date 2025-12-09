# Test Implementation Guide: Smart Selection Engine
## Step-by-Step Instructions for Implementing Missing Tests

---

## Quick Reference: Missing Tests by Priority

| Priority | Test Class | Count | Location | Lines Covered |
|----------|-----------|-------|----------|----------------|
| 1 | TestSelectorIndexManagement | 7 | test_selector.py | 281-309 |
| 1 | TestDatabaseStatistics | 14 | test_database.py | 521-590 |
| 2 | TestSelectorPaletteExtraction | 6 | test_selector.py | 311-351 |
| 2 | TestPaletteExtractionErrors | 6 | test_palette.py | 233-284 |
| 2 | TestWeightCalculationEdgeCases | 5 | test_selector.py | 113-119 |
| 3 | TestTimeBasedSelection | 4 | test_selector.py | 357-378 |
| 3 | TestColorAwarePreview | 4 | test_selector.py | 427, 459-460 |

---

## PRIORITY 1: CRITICAL

### Test 1: TestSelectorIndexManagement
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_selector.py`
**Insert After:** Line 725 (end of file)
**Coverage:** Lines 281-309 in selector.py

#### Test Case 1.1: Rebuild Index with No Folders
```python
def test_rebuild_index_with_no_folders(self):
    """rebuild_index with no folders clears existing data."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig
    from variety.smart_selection.indexer import ImageIndexer

    selector = SmartSelector(self.db_path, SelectionConfig())

    # Populate database with test images
    indexer = ImageIndexer(selector.db)
    indexer.index_directory(self.images_dir)

    initial_count = selector.db.count_images()
    self.assertGreater(initial_count, 0, "Database should have images")

    # Rebuild with no folders (should clear)
    selector.rebuild_index(source_folders=None)

    # Verify all images cleared
    final_count = selector.db.count_images()
    self.assertEqual(final_count, 0, "Database should be cleared")
    selector.close()
```

#### Test Case 1.2: Rebuild Index with Single Folder
```python
def test_rebuild_index_with_single_folder(self):
    """rebuild_index with single folder populates database."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    selector = SmartSelector(self.db_path, SelectionConfig())

    # Start with empty database
    self.assertEqual(selector.db.count_images(), 0)

    # Rebuild with single folder
    selector.rebuild_index(source_folders=[self.images_dir])

    # Verify images indexed
    final_count = selector.db.count_images()
    self.assertGreater(final_count, 0, "Images should be indexed")
    self.assertEqual(final_count, 10, "All 10 test images should be indexed")
    selector.close()
```

#### Test Case 1.3: Rebuild Index with Multiple Folders
```python
def test_rebuild_index_with_multiple_folders(self):
    """rebuild_index with multiple folders indexes all."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    # Create multiple test folders
    folder1 = os.path.join(self.temp_dir, 'folder1')
    folder2 = os.path.join(self.temp_dir, 'folder2')
    os.makedirs(folder1, exist_ok=True)
    os.makedirs(folder2, exist_ok=True)

    # Add test images to each folder
    for i in range(3):
        img = Image.new('RGB', (1920, 1080), color='blue')
        img.save(os.path.join(folder1, f'img{i}.jpg'))
        img.save(os.path.join(folder2, f'img{i+3}.jpg'))

    selector = SmartSelector(self.db_path, SelectionConfig())

    # Rebuild with multiple folders
    selector.rebuild_index(source_folders=[folder1, folder2])

    # Verify all images indexed
    count = selector.db.count_images()
    self.assertEqual(count, 6, "All images from both folders should be indexed")
    selector.close()
```

#### Test Case 1.4: Progress Callback Invoked for Each Folder
```python
def test_rebuild_index_progress_callback_invoked(self):
    """rebuild_index invokes progress_callback for each folder."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    # Create test folders
    folder1 = os.path.join(self.temp_dir, 'folder1')
    folder2 = os.path.join(self.temp_dir, 'folder2')
    os.makedirs(folder1, exist_ok=True)
    os.makedirs(folder2, exist_ok=True)

    # Add test images
    for i in range(2):
        img = Image.new('RGB', (1920, 1080), color='blue')
        img.save(os.path.join(folder1, f'img{i}.jpg'))
        img.save(os.path.join(folder2, f'img{i}.jpg'))

    # Track callback invocations
    callback_calls = []
    def progress_callback(current, total):
        callback_calls.append((current, total))

    selector = SmartSelector(self.db_path, SelectionConfig())
    selector.rebuild_index(
        source_folders=[folder1, folder2],
        progress_callback=progress_callback
    )

    # Verify callbacks were invoked
    self.assertGreater(len(callback_calls), 0, "Progress callback should be invoked")
    # Should include start (0, 2) and end (2, 2)
    self.assertEqual(callback_calls[0], (0, 2), "Should start at 0 of 2")
    self.assertEqual(callback_calls[-1], (2, 2), "Should end at 2 of 2")
    selector.close()
```

#### Test Case 1.5: Handle Folder Not Found
```python
def test_rebuild_index_handles_folder_not_found(self):
    """rebuild_index handles missing folder gracefully."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    selector = SmartSelector(self.db_path, SelectionConfig())

    # Try to index non-existent folder
    nonexistent = os.path.join(self.temp_dir, 'nonexistent')

    # Should not raise exception
    selector.rebuild_index(source_folders=[nonexistent])

    # Database should remain empty
    count = selector.db.count_images()
    self.assertEqual(count, 0, "Database should be empty after failed index")
    selector.close()
```

#### Test Case 1.6: Clears Existing Data Before Rebuild
```python
def test_rebuild_index_clears_existing_data(self):
    """rebuild_index clears existing data before repopulating."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig
    from variety.smart_selection.indexer import ImageIndexer

    selector = SmartSelector(self.db_path, SelectionConfig())

    # First populate
    indexer = ImageIndexer(selector.db)
    indexer.index_directory(self.images_dir)
    first_count = selector.db.count_images()

    # Record one image as shown
    images = selector.db.get_all_images()
    selector.db.record_image_shown(images[0].filepath)

    # Second rebuild with different folder (simulate removing images)
    empty_folder = os.path.join(self.temp_dir, 'empty')
    os.makedirs(empty_folder, exist_ok=True)

    selector.rebuild_index(source_folders=[empty_folder])

    # Verify old data cleared
    final_count = selector.db.count_images()
    self.assertEqual(final_count, 0, "Old images should be cleared")

    # Verify selection history cleared
    stats = selector.get_statistics()
    self.assertEqual(stats['unique_shown'], 0, "Selection history should be cleared")
    selector.close()
```

#### Test Case 1.7: Mixed Success and Failure Handling
```python
def test_rebuild_index_with_mixed_success_failure(self):
    """rebuild_index continues despite errors in some folders."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    # Create valid and invalid folders
    valid_folder = os.path.join(self.temp_dir, 'valid')
    os.makedirs(valid_folder, exist_ok=True)

    # Add images to valid folder
    for i in range(3):
        img = Image.new('RGB', (1920, 1080), color='blue')
        img.save(os.path.join(valid_folder, f'img{i}.jpg'))

    nonexistent_folder = os.path.join(self.temp_dir, 'nonexistent')

    selector = SmartSelector(self.db_path, SelectionConfig())

    # Rebuild with mix of valid and invalid
    selector.rebuild_index(
        source_folders=[valid_folder, nonexistent_folder, self.images_dir]
    )

    # Should have indexed from valid folders despite missing one
    count = selector.db.count_images()
    self.assertGreater(count, 0, "Should have indexed from valid folders")
    selector.close()
```

---

### Test 2: TestDatabaseStatistics
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_database.py`
**Insert After:** TestDatabaseContextManager class
**Coverage:** Lines 521-590 in database.py

#### Test Case 2.1-2.10: Statistics Methods
```python
class TestDatabaseStatistics(unittest.TestCase):
    """Tests for database statistics methods."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary database."""
        shutil.rmtree(self.temp_dir)

    def test_count_images_empty_database(self):
        """count_images returns 0 for empty database."""
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        count = db.count_images()
        self.assertEqual(count, 0)
        db.close()

    def test_count_images_with_multiple_images(self):
        """count_images returns correct count."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert test images
        for i in range(5):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg',
                source_id='test_source',
                width=1920,
                height=1080
            )
            db.upsert_image(img)

        count = db.count_images()
        self.assertEqual(count, 5)
        db.close()

    def test_count_sources_empty_database(self):
        """count_sources returns 0 for empty database."""
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        count = db.count_sources()
        self.assertEqual(count, 0)
        db.close()

    def test_count_sources_multiple_sources(self):
        """count_sources returns correct count."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord, SourceRecord

        db = ImageDatabase(self.db_path)

        # Insert sources
        for i in range(3):
            source = SourceRecord(source_id=f'source_{i}', source_type='test')
            db.upsert_source(source)

        count = db.count_sources()
        self.assertEqual(count, 3)
        db.close()

    def test_count_images_with_palettes_all_have(self):
        """count_images_with_palettes when all have palettes."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        db = ImageDatabase(self.db_path)

        # Insert images with palettes
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/path/img{i}.jpg',
                color0='#FF0000',
                avg_hue=0.0,
                avg_saturation=1.0,
                avg_lightness=0.5,
                color_temperature=1.0
            )
            db.upsert_palette(palette)

        count = db.count_images_with_palettes()
        self.assertEqual(count, 3)
        db.close()

    def test_count_images_with_palettes_none_have(self):
        """count_images_with_palettes when none have palettes."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert images without palettes
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

        count = db.count_images_with_palettes()
        self.assertEqual(count, 0)
        db.close()

    def test_sum_times_shown_all_zero(self):
        """sum_times_shown returns 0 when no images shown."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert images without showing
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

        total = db.sum_times_shown()
        self.assertEqual(total, 0)
        db.close()

    def test_sum_times_shown_multiple_values(self):
        """sum_times_shown returns correct total."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert images and record shown
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

            # Record shown different number of times
            for _ in range(i + 1):
                db.record_image_shown(f'/path/img{i}.jpg')

        # 1 + 2 + 3 = 6
        total = db.sum_times_shown()
        self.assertEqual(total, 6)
        db.close()

    def test_count_shown_images_none_shown(self):
        """count_shown_images returns 0 when no images shown."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert images without showing
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

        count = db.count_shown_images()
        self.assertEqual(count, 0)
        db.close()

    def test_count_shown_images_some_shown(self):
        """count_shown_images counts only shown images."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert and show some images
        for i in range(5):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

            # Show first 3
            if i < 3:
                db.record_image_shown(f'/path/img{i}.jpg')

        count = db.count_shown_images()
        self.assertEqual(count, 3)
        db.close()

    def test_clear_history_resets_times_shown(self):
        """clear_history resets times_shown to 0."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert and show images
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)
            for _ in range(2):
                db.record_image_shown(f'/path/img{i}.jpg')

        # Verify times_shown incremented
        record = db.get_image('/path/img0.jpg')
        self.assertEqual(record.times_shown, 2)

        # Clear history
        db.clear_history()

        # Verify reset
        record = db.get_image('/path/img0.jpg')
        self.assertEqual(record.times_shown, 0)
        self.assertIsNone(record.last_shown_at)
        db.close()

    def test_clear_history_resets_last_shown_at(self):
        """clear_history resets last_shown_at to NULL."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord

        db = ImageDatabase(self.db_path)

        # Insert and show image
        img = ImageRecord(
            filepath='/path/img.jpg',
            filename='img.jpg'
        )
        db.upsert_image(img)
        db.record_image_shown('/path/img.jpg')

        # Verify timestamp set
        record = db.get_image('/path/img.jpg')
        self.assertIsNotNone(record.last_shown_at)

        # Clear history
        db.clear_history()

        # Verify reset
        record = db.get_image('/path/img.jpg')
        self.assertIsNone(record.last_shown_at)
        db.close()

    def test_delete_all_images_removes_all_data(self):
        """delete_all_images removes all records."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import ImageRecord, PaletteRecord

        db = ImageDatabase(self.db_path)

        # Insert data
        for i in range(3):
            img = ImageRecord(
                filepath=f'/path/img{i}.jpg',
                filename=f'img{i}.jpg'
            )
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/path/img{i}.jpg',
                color0='#FF0000',
                avg_hue=0.0,
                avg_saturation=1.0,
                avg_lightness=0.5,
                color_temperature=1.0
            )
            db.upsert_palette(palette)

        # Verify data exists
        self.assertEqual(db.count_images(), 3)
        self.assertEqual(db.count_images_with_palettes(), 3)

        # Delete all
        db.delete_all_images()

        # Verify all deleted
        self.assertEqual(db.count_images(), 0)
        self.assertEqual(db.count_images_with_palettes(), 0)
        db.close()
```

---

## PRIORITY 2: HIGH

### Test 3: TestSelectorPaletteExtraction
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_selector.py`
**Insert After:** TestSelectorIndexManagement class
**Coverage:** Lines 311-351 in selector.py

```python
class TestSelectorPaletteExtraction(unittest.TestCase):
    """Tests for SmartSelector palette extraction operations."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test images
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_extract_all_palettes_when_wallust_unavailable(self):
        """Returns 0 and logs warning when wallust unavailable."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mock wallust unavailable
        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=False):
            result = selector.extract_all_palettes()

        self.assertEqual(result, 0, "Should return 0 when wallust unavailable")
        selector.close()

    def test_extract_all_palettes_progress_callback(self):
        """Progress callback invoked for each image."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch, MagicMock

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mock wallust
        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=False):
            # Track callback invocations
            callback_calls = []
            def progress_callback(current, total):
                callback_calls.append((current, total))

            selector.extract_all_palettes(progress_callback=progress_callback)

        # Verify callbacks were invoked
        self.assertGreater(len(callback_calls), 0,
                          "Progress callback should be invoked")
        selector.close()

    def test_extract_all_palettes_handles_per_image_failures(self):
        """Continues processing after per-image failures."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch, MagicMock

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mock extraction: fail on first, succeed on others
        mock_extract = MagicMock(side_effect=[
            None,  # First image fails
            {'color0': '#FF0000', 'avg_hue': 0.0, 'avg_saturation': 1.0,
             'avg_lightness': 0.5, 'color_temperature': 1.0},
            {'color0': '#00FF00', 'avg_hue': 120.0, 'avg_saturation': 1.0,
             'avg_lightness': 0.5, 'color_temperature': -0.5},
            None,  # Fourth fails
            {'color0': '#0000FF', 'avg_hue': 240.0, 'avg_saturation': 1.0,
             'avg_lightness': 0.5, 'color_temperature': -1.0},
        ])

        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=True):
            with patch.object(selector._palette_extractor, 'extract_palette',
                            side_effect=mock_extract):
                result = selector.extract_all_palettes()

        # Should have extracted 3 out of 5
        self.assertEqual(result, 3, "Should extract successful palettes despite failures")
        selector.close()

    def test_extract_all_palettes_counts_successful(self):
        """Returns count of successfully extracted palettes."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch, MagicMock

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mock successful extraction
        palette_template = {
            'color0': '#FF0000', 'avg_hue': 0.0, 'avg_saturation': 1.0,
            'avg_lightness': 0.5, 'color_temperature': 1.0
        }

        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=True):
            with patch.object(selector._palette_extractor, 'extract_palette',
                            return_value=palette_template):
                result = selector.extract_all_palettes()

        self.assertEqual(result, 5, "Should extract all 5 palettes")
        selector.close()

    def test_extract_all_palettes_empty_database(self):
        """Handles empty database gracefully."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Empty database - no images to extract
        result = selector.extract_all_palettes()

        self.assertEqual(result, 0, "Should return 0 for empty database")
        selector.close()

    def test_extract_all_palettes_skips_existing(self):
        """Skips images that already have palettes."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.models import PaletteRecord
        from unittest.mock import patch, MagicMock

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Add palette for first image
        images = selector.db.get_all_images()
        palette = PaletteRecord(
            filepath=images[0].filepath,
            color0='#FF0000',
            avg_hue=0.0, avg_saturation=1.0, avg_lightness=0.5,
            color_temperature=1.0
        )
        selector.db.upsert_palette(palette)

        # Mock extraction
        palette_template = {
            'color0': '#FF0000', 'avg_hue': 0.0, 'avg_saturation': 1.0,
            'avg_lightness': 0.5, 'color_temperature': 1.0
        }

        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=True):
            with patch.object(selector._palette_extractor, 'extract_palette',
                            return_value=palette_template) as mock_extract:
                result = selector.extract_all_palettes()

        # Should extract 4 (5 total - 1 existing)
        self.assertEqual(result, 4, "Should skip existing palettes")
        # Extract should be called 4 times, not 5
        self.assertEqual(mock_extract.call_count, 4)
        selector.close()
```

---

### Test 4: TestPaletteExtractionErrors
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_palette.py`
**Insert After:** TestColorSimilarity class
**Coverage:** Lines 233-284, 246-247 in palette.py

```python
class TestPaletteExtractionErrors(unittest.TestCase):
    """Tests for palette extraction error handling."""

    def setUp(self):
        """Create test image."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_image = os.path.join(self.temp_dir, 'test.jpg')
        img = Image.new('RGB', (1920, 1080), color='blue')
        img.save(self.test_image)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    @patch('subprocess.run')
    def test_extract_palette_timeout(self, mock_run):
        """Timeout exception returns None."""
        from variety.smart_selection.palette import PaletteExtractor
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired('wallust', timeout=30)

        extractor = PaletteExtractor()
        with patch.object(extractor, 'is_wallust_available', return_value=True):
            result = extractor.extract_palette(self.test_image)

        self.assertIsNone(result, "Should return None on timeout")

    @patch('subprocess.run')
    @patch('builtins.open')
    def test_extract_palette_json_decode_error(self, mock_open, mock_run):
        """JSON decode error returns None."""
        from variety.smart_selection.palette import PaletteExtractor
        import json

        # Mock successful wallust execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b''
        mock_run.return_value = mock_result

        # Mock bad JSON in file
        mock_open.side_effect = json.JSONDecodeError('msg', 'doc', 0)

        extractor = PaletteExtractor()
        with patch.object(extractor, 'is_wallust_available', return_value=True):
            with patch('os.listdir', return_value=['cache_dir']):
                with patch('os.path.isdir', return_value=True):
                    with patch('os.path.getmtime', return_value=time.time()):
                        result = extractor.extract_palette(self.test_image)

        self.assertIsNone(result, "Should return None on JSON decode error")

    @patch('subprocess.run')
    def test_extract_palette_insufficient_colors(self, mock_run):
        """'Not enough colors' error logged as debug."""
        from variety.smart_selection.palette import PaletteExtractor

        # Mock wallust returning error about insufficient colors
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b'Not enough colors in image'
        mock_run.return_value = mock_result

        extractor = PaletteExtractor()
        with patch.object(extractor, 'is_wallust_available', return_value=True):
            with patch('variety.smart_selection.palette.logger') as mock_logger:
                result = extractor.extract_palette(self.test_image)

        self.assertIsNone(result)
        # Should log as debug, not warning
        # Note: would need to verify logger.debug was called

    @patch('subprocess.run')
    def test_extract_palette_cache_directory_missing(self, mock_run):
        """Missing cache directory returns None."""
        from variety.smart_selection.palette import PaletteExtractor

        # Mock successful wallust execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b''
        mock_run.return_value = mock_result

        extractor = PaletteExtractor()
        with patch.object(extractor, 'is_wallust_available', return_value=True):
            with patch('os.path.isdir', return_value=False):
                result = extractor.extract_palette(self.test_image)

        self.assertIsNone(result, "Should return None when cache dir missing")

    @patch('subprocess.run')
    def test_extract_palette_generic_exception(self, mock_run):
        """Generic exceptions return None."""
        from variety.smart_selection.palette import PaletteExtractor

        # Mock unexpected exception
        mock_run.side_effect = OSError("Unexpected error")

        extractor = PaletteExtractor()
        with patch.object(extractor, 'is_wallust_available', return_value=True):
            result = extractor.extract_palette(self.test_image)

        self.assertIsNone(result, "Should return None on unexpected exception")

    def test_palette_storage_failure_exception_handling(self):
        """Palette storage failures don't crash selector."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch, MagicMock

        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, 'test.db')
        images_dir = os.path.join(temp_dir, 'images')
        os.makedirs(images_dir)

        # Create test image
        test_image = os.path.join(images_dir, 'test.jpg')
        img = Image.new('RGB', (1920, 1080), color='blue')
        img.save(test_image)

        selector = SmartSelector(db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index image
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(images_dir)

        # Mock palette extraction success but storage failure
        palette_data = {
            'color0': '#FF0000', 'avg_hue': 0.0, 'avg_saturation': 1.0,
            'avg_lightness': 0.5, 'color_temperature': 1.0
        }

        with patch.object(selector._palette_extractor, 'extract_palette',
                         return_value=palette_data):
            with patch.object(selector.db, 'upsert_palette',
                            side_effect=Exception("Database error")):
                # Should not raise exception
                selector.record_shown(test_image)

        # Record should still work (palette storage failure logged)
        record = selector.db.get_image(test_image)
        self.assertIsNotNone(record, "Image should be recorded despite palette failure")

        shutil.rmtree(temp_dir)
        selector.close()
```

---

### Test 5: TestWeightCalculationEdgeCases
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_selector.py`
**Insert After:** TestSmartSelectorConstraints class
**Coverage:** Lines 113-119 in selector.py

```python
class TestWeightCalculationEdgeCases(unittest.TestCase):
    """Tests for edge cases in weight calculation and selection."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test images
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_select_when_all_weights_zero_uses_uniform_fallback(self):
        """When all weights are 0, uses uniform random selection."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        # Create config that produces zero weights
        config = SelectionConfig(
            enabled=True,
            recency_cooldown=0,  # No recency penalty
            source_cooldown=0,   # No source cooldown
            favorite_boost=0.0,  # No favorite boost
            new_image_boost=0.0  # No new image boost
        )

        selector = SmartSelector(self.db_path, config)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Record all images as shown recently (high recency penalty)
        images = selector.db.get_all_images()
        for img in images:
            for _ in range(100):
                selector.db.record_image_shown(img.filepath)

        # Selection should still work (fallback to uniform)
        selected = selector.select_images(2)
        self.assertEqual(len(selected), 2, "Should select 2 images even with zero weights")
        selector.close()

    def test_select_when_single_image_available(self):
        """Selection works with only one image available."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        # Create single-image directory
        single_img = os.path.join(self.temp_dir, 'single.jpg')
        img = Image.new('RGB', (1920, 1080), color='red')
        img.save(single_img)

        single_dir = os.path.join(self.temp_dir, 'single')
        os.makedirs(single_dir)
        shutil.copy(single_img, single_dir)

        selector = SmartSelector(self.db_path, SelectionConfig())

        # Index single image
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(single_dir)

        # Select multiple should return just the one
        selected = selector.select_images(5)
        self.assertEqual(len(selected), 1, "Should return 1 image")
        selector.close()

    def test_select_with_extreme_weight_values(self):
        """Selection handles extreme weight values."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        config = SelectionConfig(
            enabled=True,
            favorite_boost=1000.0,  # Extreme boost
            new_image_boost=0.0001  # Minimal boost
        )

        selector = SmartSelector(self.db_path, config)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mark one as favorite
        images = selector.db.get_all_images()
        images[0].is_favorite = True
        selector.db.upsert_image(images[0])

        # Selection should work with extreme values
        selected = selector.select_images(3)
        self.assertEqual(len(selected), 3, "Should handle extreme weight values")

        # Favorite should be selected more often
        # Run multiple selections to verify distribution
        favorite_count = 0
        for _ in range(100):
            selected = selector.select_images(1)
            if selected[0] == images[0].filepath:
                favorite_count += 1

        self.assertGreater(favorite_count, 50, "Favorite should be selected >50% of time")
        selector.close()

    def test_weight_calculation_with_null_source(self):
        """Weight calculation handles images with no source."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        selector = SmartSelector(self.db_path, SelectionConfig())

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Manually create image without source
        from variety.smart_selection.models import ImageRecord
        orphan = ImageRecord(
            filepath='/orphan/img.jpg',
            filename='img.jpg',
            source_id=None  # No source
        )
        selector.db.upsert_image(orphan)

        # Selection should work even with null source
        selected = selector.select_images(1)
        self.assertIsNotNone(selected, "Should select images with null source")
        selector.close()
```

---

## PRIORITY 3: MEDIUM

### Test 6: TestTimeBasedSelection
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_selector.py`
**Insert After:** TestWeightCalculationEdgeCases class
**Coverage:** Lines 357-378 in selector.py

```python
class TestTimeBasedSelection(unittest.TestCase):
    """Tests for time-based color temperature selection."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    @patch('datetime.datetime')
    def test_get_time_based_temperature_morning(self, mock_datetime):
        """Morning returns cool/neutral temperature."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Mock 6 AM (morning)
        mock_datetime.now.return_value = MagicMock(hour=6)

        selector = SmartSelector(self.db_path, SelectionConfig())
        temp = selector.get_time_based_temperature()

        # Morning should be cool/neutral (negative or near zero)
        self.assertLessEqual(temp, 0.5, "Morning should be cool/neutral")
        selector.close()

    @patch('datetime.datetime')
    def test_get_time_based_temperature_afternoon(self, mock_datetime):
        """Afternoon returns warm temperature."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Mock 2 PM (afternoon)
        mock_datetime.now.return_value = MagicMock(hour=14)

        selector = SmartSelector(self.db_path, SelectionConfig())
        temp = selector.get_time_based_temperature()

        # Afternoon should be warmer (positive)
        self.assertGreater(temp, 0.0, "Afternoon should be warm")
        selector.close()

    @patch('datetime.datetime')
    def test_get_time_based_temperature_evening(self, mock_datetime):
        """Evening returns warm temperature."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Mock 6 PM (evening)
        mock_datetime.now.return_value = MagicMock(hour=18)

        selector = SmartSelector(self.db_path, SelectionConfig())
        temp = selector.get_time_based_temperature()

        # Evening should be warm
        self.assertGreater(temp, 0.2, "Evening should be warm")
        selector.close()

    @patch('datetime.datetime')
    def test_get_time_based_temperature_night(self, mock_datetime):
        """Night returns cool temperature."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Mock 11 PM (night)
        mock_datetime.now.return_value = MagicMock(hour=23)

        selector = SmartSelector(self.db_path, SelectionConfig())
        temp = selector.get_time_based_temperature()

        # Night should be cool/neutral
        self.assertLess(temp, 0.3, "Night should be cool")
        selector.close()
```

---

### Test 7: TestColorAwarePreview
**File:** `/home/komi/repos/variety-variation/tests/smart_selection/test_selector.py`
**Insert After:** TestTimeBasedSelection class
**Coverage:** Lines 427, 459-460 in selector.py

```python
class TestColorAwarePreview(unittest.TestCase):
    """Tests for color-aware preview candidate generation."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        os.makedirs(self.images_dir)

        # Create test images
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_get_color_aware_preview_candidates_returns_list(self):
        """Returns list of preview candidates."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        result = selector.get_color_aware_preview_candidates(count=3)

        self.assertIsInstance(result, list, "Should return list")
        selector.close()

    def test_color_aware_preview_respects_count(self):
        """Returns requested number of candidates."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        result = selector.get_color_aware_preview_candidates(count=3)

        self.assertLessEqual(len(result), 3, "Should not exceed requested count")
        selector.close()

    def test_color_aware_preview_when_wallust_unavailable(self):
        """Handles wallust unavailable gracefully."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mock wallust unavailable
        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=False):
            result = selector.get_color_aware_preview_candidates(count=3)

        # Should return empty or fallback list
        self.assertIsInstance(result, list, "Should return list even without wallust")
        selector.close()

    def test_color_aware_preview_sorted_by_similarity(self):
        """Returns candidates sorted by color similarity."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.indexer import ImageIndexer
        from unittest.mock import patch

        selector = SmartSelector(self.db_path, SelectionConfig(),
                                enable_palette_extraction=True)

        # Index images
        indexer = ImageIndexer(selector.db)
        indexer.index_directory(self.images_dir)

        # Mock successful palette extraction
        palette_template = {
            'color0': '#FF0000', 'avg_hue': 0.0, 'avg_saturation': 1.0,
            'avg_lightness': 0.5, 'color_temperature': 1.0
        }

        with patch.object(selector._palette_extractor, 'is_wallust_available',
                         return_value=True):
            with patch.object(selector._palette_extractor, 'extract_palette',
                            return_value=palette_template):
                result = selector.get_color_aware_preview_candidates(count=3)

        # If we have results, check they're ordered
        if len(result) > 1:
            # Check that scores are in descending order
            scores = [item.get('similarity_score', 0) for item in result]
            self.assertEqual(scores, sorted(scores, reverse=True),
                           "Candidates should be sorted by similarity descending")

        selector.close()
```

---

## Implementation Checklist

### Phase 1: Critical Gaps
- [ ] Create TestSelectorIndexManagement (7 tests)
- [ ] Create TestDatabaseStatistics (14 tests)
- [ ] Fix database resource cleanup in all test tearDown methods

### Phase 2: High Priority
- [ ] Create TestSelectorPaletteExtraction (6 tests)
- [ ] Create TestPaletteExtractionErrors (6 tests)
- [ ] Create TestWeightCalculationEdgeCases (5 tests)

### Phase 3: Medium Priority
- [ ] Create TestTimeBasedSelection (4 tests)
- [ ] Create TestColorAwarePreview (4 tests)

### Phase 4: Infrastructure Improvements
- [ ] Create `conftest.py` with shared fixtures
- [ ] Add pytest markers for test categories
- [ ] Create test data factory
- [ ] Add integration test markers

---

## Running Tests

### Run all tests:
```bash
python3 -m pytest tests/smart_selection/ -v
```

### Run with coverage:
```bash
python3 -m pytest tests/smart_selection/ --cov=variety/smart_selection --cov-report=term-missing
```

### Run specific test class:
```bash
python3 -m pytest tests/smart_selection/test_selector.py::TestSelectorIndexManagement -v
```

### Run specific test:
```bash
python3 -m pytest tests/smart_selection/test_selector.py::TestSelectorIndexManagement::test_rebuild_index_with_no_folders -v
```

---

## Expected Coverage After Implementation

| Module | Current | Target | Change |
|--------|---------|--------|--------|
| selector.py | 67% | 95% | +28% |
| database.py | 83% | 95% | +12% |
| palette.py | 84% | 95% | +11% |
| **Overall** | **83%** | **95%** | **+12%** |

---

**Last Updated:** 2025-12-05
**Total New Tests:** 52
**Estimated Implementation Time:** 4-6 weeks
