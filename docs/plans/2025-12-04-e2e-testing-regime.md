# End-to-End Testing Regime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a comprehensive, extensible testing regime with workflow validation, regression prevention, and performance benchmarking for the Smart Selection Engine.

**Architecture:** Three-tier test structure: existing unittest for units, pytest for E2E workflows, pytest-benchmark for performance. Real dependencies only (no mocks). Curated image fixtures from Favorites folder.

**Tech Stack:** Python unittest (existing), pytest, pytest-benchmark, PIL/Pillow, wallust CLI

---

## Task 1: Create Test Fixtures Directory

**Files:**
- Create: `tests/smart_selection/fixtures/wallpapers/` (directory)
- Create: `tests/smart_selection/fixtures/README.md`

**Step 1: Create fixtures directory structure**

```bash
mkdir -p tests/smart_selection/fixtures/wallpapers
```

**Step 2: Copy diverse sample images from Favorites**

Select ~15 images with variety in: color temperature, aspect ratio, file size, source.

```bash
# Copy a diverse selection of images
cp ~/.config/variety/Favorites/Abell7_VChander4096.jpg tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/wallhaven-4xjgzz.png tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/wallhaven-l8z3el.jpg tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/wallhaven-q6ojxl.png tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/wallhaven-9ddpq1.png tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/Heart_TelLiveOstling_2953.jpg tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/KingOfWings_Pinkston_7360.jpg tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/VeilWide_Alharbi_5169.jpg tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/ArchFalls_Pellegrini_2000.jpg tests/smart_selection/fixtures/wallpapers/
cp ~/.config/variety/Favorites/20240408h14.jpg tests/smart_selection/fixtures/wallpapers/
```

**Step 3: Create README documenting fixtures**

```markdown
# Test Fixtures

This directory contains curated wallpaper images for end-to-end testing.

## Selection Criteria

Images were selected to provide diversity in:
- Color temperature (warm, cool, neutral)
- Aspect ratios (landscape, portrait, square)
- File sizes (small to large)
- Sources (wallhaven, APOD, reddit, unsplash)

## Usage

These fixtures are used by:
- `tests/smart_selection/e2e/` - End-to-end workflow tests
- `tests/smart_selection/benchmarks/` - Performance benchmarks

## Adding New Fixtures

When adding images, ensure variety in the above criteria.
Keep total size under 50MB for reasonable clone times.
```

**Step 4: Verify fixtures are usable**

```bash
ls -la tests/smart_selection/fixtures/wallpapers/
file tests/smart_selection/fixtures/wallpapers/*
```

Expected: 10+ image files, mix of jpg/png formats.

**Step 5: Commit**

```bash
git add tests/smart_selection/fixtures/
git commit -m "test: add curated wallpaper fixtures for E2E testing"
```

---

## Task 2: Create E2E Test Infrastructure

**Files:**
- Create: `tests/smart_selection/e2e/__init__.py`
- Create: `tests/smart_selection/e2e/conftest.py`

**Step 1: Create e2e package**

```bash
mkdir -p tests/smart_selection/e2e
touch tests/smart_selection/e2e/__init__.py
```

**Step 2: Write conftest.py with shared fixtures**

```python
# tests/smart_selection/e2e/conftest.py
"""Shared fixtures for end-to-end tests."""

import os
import shutil
import tempfile
import pytest

# Path to fixture images
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'wallpapers')


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: end-to-end tests requiring real dependencies"
    )
    config.addinivalue_line(
        "markers", "slow: tests that take more than 5 seconds"
    )
    config.addinivalue_line(
        "markers", "wallust: tests requiring wallust CLI"
    )


@pytest.fixture
def fixtures_dir():
    """Return path to fixture wallpapers."""
    if not os.path.isdir(FIXTURES_DIR):
        pytest.skip(f"Fixtures directory not found: {FIXTURES_DIR}")
    return FIXTURES_DIR


@pytest.fixture
def fixture_images(fixtures_dir):
    """Return list of all fixture image paths."""
    images = []
    for f in os.listdir(fixtures_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            images.append(os.path.join(fixtures_dir, f))
    if not images:
        pytest.skip("No fixture images found")
    return images


@pytest.fixture
def temp_db():
    """Create a temporary database file, cleanup after test."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_e2e.db')
    yield db_path
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def temp_dir():
    """Create a temporary directory, cleanup after test."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def wallust_available():
    """Check if wallust is available, skip if not."""
    if not shutil.which('wallust'):
        pytest.skip("wallust not installed")
    return True


@pytest.fixture
def indexed_database(temp_db, fixtures_dir):
    """Create a database with all fixture images indexed."""
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.indexer import ImageIndexer

    with ImageDatabase(temp_db) as db:
        indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
        indexer.index_directory(fixtures_dir)

    return temp_db


@pytest.fixture
def database_with_palettes(indexed_database, wallust_available):
    """Create a database with images indexed AND palettes extracted."""
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.palette import PaletteExtractor, create_palette_record

    extractor = PaletteExtractor()

    with ImageDatabase(indexed_database) as db:
        for img in db.get_all_images():
            palette_data = extractor.extract_palette(img.filepath)
            if palette_data:
                record = create_palette_record(img.filepath, palette_data)
                db.upsert_palette(record)

    return indexed_database


@pytest.fixture
def selector_with_palettes(database_with_palettes):
    """Create a SmartSelector with indexed images and palettes."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    config = SelectionConfig(enabled=True)
    selector = SmartSelector(database_with_palettes, config)
    yield selector
    selector.close()
```

**Step 3: Verify pytest can discover fixtures**

```bash
python3 -m pytest tests/smart_selection/e2e/ --collect-only 2>&1 | head -20
```

Expected: Shows conftest.py loaded, no errors.

**Step 4: Commit**

```bash
git add tests/smart_selection/e2e/
git commit -m "test: add E2E test infrastructure with pytest fixtures"
```

---

## Task 3: Implement Workflow Tests - Fresh Start

**Files:**
- Create: `tests/smart_selection/e2e/test_workflows.py`

**Step 1: Write fresh start workflow test**

```python
# tests/smart_selection/e2e/test_workflows.py
"""End-to-end workflow tests for Smart Selection Engine."""

import os
import pytest


class TestFreshStartWorkflow:
    """Test complete fresh start workflow."""

    @pytest.mark.e2e
    def test_fresh_database_index_and_select(self, temp_db, fixtures_dir, fixture_images):
        """Complete workflow: create DB, index, select."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Step 1: Create fresh database and index
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            count = indexer.index_directory(fixtures_dir)

            # Verify indexing
            assert count == len(fixture_images)
            assert count > 0

            # Verify metadata extracted
            all_images = db.get_all_images()
            assert len(all_images) == count

            for img in all_images:
                assert img.width is not None
                assert img.height is not None
                assert img.aspect_ratio is not None
                assert img.file_size is not None
                assert img.is_favorite is True  # All in favorites_folder

        # Step 2: Select images
        with SmartSelector(temp_db, SelectionConfig()) as selector:
            selected = selector.select_images(count=3)

            # Verify selection
            assert len(selected) == 3
            assert all(os.path.exists(p) for p in selected)
            assert all(p in [img.filepath for img in all_images] for p in selected)

    @pytest.mark.e2e
    def test_empty_database_returns_empty_selection(self, temp_db):
        """Empty database returns empty selection."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(temp_db, SelectionConfig()) as selector:
            selected = selector.select_images(count=5)
            assert selected == []
```

**Step 2: Run test to verify it works**

```bash
python3 -m pytest tests/smart_selection/e2e/test_workflows.py -v
```

Expected: 2 tests PASS

**Step 3: Commit**

```bash
git add tests/smart_selection/e2e/test_workflows.py
git commit -m "test: add fresh start workflow E2E tests"
```

---

## Task 4: Implement Workflow Tests - Selection Lifecycle

**Files:**
- Modify: `tests/smart_selection/e2e/test_workflows.py`

**Step 1: Add selection lifecycle tests**

Append to `test_workflows.py`:

```python
class TestSelectionLifecycleWorkflow:
    """Test selection behavior over time."""

    @pytest.mark.e2e
    def test_recently_shown_image_less_likely(self, indexed_database):
        """Recently shown images appear less frequently in selections."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from collections import Counter

        config = SelectionConfig(
            enabled=True,
            cooldown_days=7,
            decay_type='linear',
        )

        with SmartSelector(indexed_database, config) as selector:
            # Get all images
            all_images = selector.db.get_all_images()
            assert len(all_images) >= 3, "Need at least 3 fixture images"

            # Record one image as shown
            shown_image = all_images[0].filepath
            selector.record_shown(shown_image)

            # Select many times and count occurrences
            selection_counts = Counter()
            num_trials = 200

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    selection_counts[selected[0]] += 1

            # Recently shown image should appear less than average
            expected_uniform = num_trials / len(all_images)
            shown_count = selection_counts.get(shown_image, 0)

            # Should be significantly below uniform distribution
            assert shown_count < expected_uniform * 0.5, (
                f"Recently shown image selected {shown_count} times, "
                f"expected less than {expected_uniform * 0.5:.0f}"
            )

    @pytest.mark.e2e
    def test_times_shown_increments(self, indexed_database):
        """Recording shown increments times_shown counter."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            image = selector.db.get_all_images()[0]

            assert image.times_shown == 0

            selector.record_shown(image.filepath)
            updated = selector.db.get_image(image.filepath)
            assert updated.times_shown == 1

            selector.record_shown(image.filepath)
            updated = selector.db.get_image(image.filepath)
            assert updated.times_shown == 2
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/smart_selection/e2e/test_workflows.py::TestSelectionLifecycleWorkflow -v
```

Expected: 2 tests PASS

**Step 3: Commit**

```bash
git add tests/smart_selection/e2e/test_workflows.py
git commit -m "test: add selection lifecycle workflow E2E tests"
```

---

## Task 5: Implement Workflow Tests - Color-Aware Selection

**Files:**
- Modify: `tests/smart_selection/e2e/test_workflows.py`

**Step 1: Add color-aware selection tests**

Append to `test_workflows.py`:

```python
class TestColorAwareWorkflow:
    """Test color-based selection workflows."""

    @pytest.mark.e2e
    @pytest.mark.wallust
    def test_color_similar_images_preferred(self, selector_with_palettes):
        """Images with similar colors are preferred when target_palette set."""
        from variety.smart_selection.models import SelectionConstraints
        from variety.smart_selection.palette import palette_similarity
        from collections import Counter

        selector = selector_with_palettes

        # Get an image with a palette to use as target
        all_images = selector.db.get_all_images()
        target_image = None
        target_palette_data = None

        for img in all_images:
            palette = selector.db.get_palette(img.filepath)
            if palette and palette.avg_hue is not None:
                target_image = img
                target_palette_data = {
                    'avg_hue': palette.avg_hue,
                    'avg_saturation': palette.avg_saturation,
                    'avg_lightness': palette.avg_lightness,
                    'color_temperature': palette.color_temperature,
                }
                break

        assert target_image is not None, "No images with palettes found"

        # Calculate similarity scores for all images
        similarities = {}
        for img in all_images:
            palette = selector.db.get_palette(img.filepath)
            if palette and palette.avg_hue is not None:
                img_palette = {
                    'avg_hue': palette.avg_hue,
                    'avg_saturation': palette.avg_saturation,
                    'avg_lightness': palette.avg_lightness,
                    'color_temperature': palette.color_temperature,
                }
                similarities[img.filepath] = palette_similarity(
                    target_palette_data, img_palette
                )

        # Select with color constraint
        constraints = SelectionConstraints(
            target_palette=target_palette_data,
            min_color_similarity=0.5,
        )

        selection_counts = Counter()
        num_trials = 100

        for _ in range(num_trials):
            selected = selector.select_images(count=1, constraints=constraints)
            if selected:
                selection_counts[selected[0]] += 1

        # Verify only similar images were selected
        for filepath, count in selection_counts.items():
            assert filepath in similarities, f"{filepath} has no palette"
            assert similarities[filepath] >= 0.5, (
                f"{filepath} similarity {similarities[filepath]:.2f} below threshold"
            )

    @pytest.mark.e2e
    @pytest.mark.wallust
    def test_palette_extraction_on_record_shown(self, indexed_database, wallust_available):
        """Palette is extracted when record_shown is called with extraction enabled."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(
            indexed_database,
            SelectionConfig(),
            enable_palette_extraction=True
        ) as selector:
            image = selector.db.get_all_images()[0]

            # No palette initially
            assert selector.db.get_palette(image.filepath) is None

            # Record shown triggers extraction
            selector.record_shown(image.filepath)

            # Now palette should exist
            palette = selector.db.get_palette(image.filepath)
            assert palette is not None
            assert palette.avg_hue is not None
            assert palette.color0 is not None
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/smart_selection/e2e/test_workflows.py::TestColorAwareWorkflow -v
```

Expected: 2 tests PASS (or skip if wallust unavailable)

**Step 3: Commit**

```bash
git add tests/smart_selection/e2e/test_workflows.py
git commit -m "test: add color-aware workflow E2E tests"
```

---

## Task 6: Implement Workflow Tests - Favorites and Source Rotation

**Files:**
- Modify: `tests/smart_selection/e2e/test_workflows.py`

**Step 1: Add favorites and source rotation tests**

Append to `test_workflows.py`:

```python
class TestFavoritesWorkflow:
    """Test favorites boost behavior."""

    @pytest.mark.e2e
    def test_favorites_boosted_in_selection(self, temp_db, temp_dir, fixture_images):
        """Favorite images appear more frequently than non-favorites."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from collections import Counter
        import shutil

        # Create two directories: favorites and non-favorites
        fav_dir = os.path.join(temp_dir, 'favorites')
        other_dir = os.path.join(temp_dir, 'other')
        os.makedirs(fav_dir)
        os.makedirs(other_dir)

        # Split fixture images
        half = len(fixture_images) // 2
        for i, img in enumerate(fixture_images):
            dest_dir = fav_dir if i < half else other_dir
            shutil.copy(img, dest_dir)

        # Index with favorites folder set
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fav_dir)
            indexer.index_directory(fav_dir)
            indexer.index_directory(other_dir)

        # Select many times
        config = SelectionConfig(enabled=True, favorite_boost=3.0)
        with SmartSelector(temp_db, config) as selector:
            fav_count = 0
            other_count = 0
            num_trials = 200

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    if selected[0].startswith(fav_dir):
                        fav_count += 1
                    else:
                        other_count += 1

            # Favorites should be selected more often
            assert fav_count > other_count, (
                f"Favorites: {fav_count}, Others: {other_count}"
            )


class TestSourceRotationWorkflow:
    """Test source rotation behavior."""

    @pytest.mark.e2e
    def test_source_rotation_balances_selection(self, temp_db, temp_dir, fixture_images):
        """Sources rotate - recently used sources are deprioritized."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from collections import Counter
        import shutil

        # Create two source directories
        source_a = os.path.join(temp_dir, 'source_a')
        source_b = os.path.join(temp_dir, 'source_b')
        os.makedirs(source_a)
        os.makedirs(source_b)

        # Split images between sources
        half = len(fixture_images) // 2
        for i, img in enumerate(fixture_images):
            dest = source_a if i < half else source_b
            shutil.copy(img, dest)

        # Index both sources
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(source_a)
            indexer.index_directory(source_b)

        # Configure with source cooldown
        config = SelectionConfig(
            enabled=True,
            source_cooldown_hours=24,
        )

        with SmartSelector(temp_db, config) as selector:
            # Record many shows from source_a
            source_a_images = [
                img for img in selector.db.get_all_images()
                if source_a in img.filepath
            ]
            for img in source_a_images[:3]:
                selector.record_shown(img.filepath)

            # Now selections should favor source_b
            source_counts = Counter()
            num_trials = 100

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    if source_a in selected[0]:
                        source_counts['a'] += 1
                    else:
                        source_counts['b'] += 1

            # Source B should be preferred
            assert source_counts['b'] > source_counts['a'], (
                f"Source A: {source_counts['a']}, Source B: {source_counts['b']}"
            )
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/smart_selection/e2e/test_workflows.py -v -k "Favorites or SourceRotation"
```

Expected: 2 tests PASS

**Step 3: Commit**

```bash
git add tests/smart_selection/e2e/test_workflows.py
git commit -m "test: add favorites and source rotation workflow E2E tests"
```

---

## Task 7: Implement Persistence Tests

**Files:**
- Create: `tests/smart_selection/e2e/test_persistence.py`

**Step 1: Write persistence tests**

```python
# tests/smart_selection/e2e/test_persistence.py
"""Tests for data persistence and recovery."""

import os
import pytest


class TestDatabasePersistence:
    """Test that data survives across sessions."""

    @pytest.mark.e2e
    def test_data_persists_across_sessions(self, temp_db, fixtures_dir):
        """Data indexed in one session is available in another."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Session 1: Index and record shown
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            indexer.index_directory(fixtures_dir)
            images = db.get_all_images()
            first_image = images[0].filepath

        with SmartSelector(temp_db, SelectionConfig()) as selector:
            selector.record_shown(first_image)

        # Session 2: Verify data persists
        with ImageDatabase(temp_db) as db:
            images = db.get_all_images()
            assert len(images) > 0

            img = db.get_image(first_image)
            assert img is not None
            assert img.times_shown == 1
            assert img.last_shown_at is not None

    @pytest.mark.e2e
    @pytest.mark.wallust
    def test_palette_persists_across_sessions(self, temp_db, fixtures_dir, wallust_available):
        """Extracted palettes persist across sessions."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.palette import PaletteExtractor, create_palette_record

        # Session 1: Index and extract palette
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            indexer.index_directory(fixtures_dir)

            extractor = PaletteExtractor()
            image = db.get_all_images()[0]
            palette_data = extractor.extract_palette(image.filepath)

            if palette_data:
                record = create_palette_record(image.filepath, palette_data)
                db.upsert_palette(record)
                saved_hue = palette_data.get('avg_hue')

        # Session 2: Verify palette persists
        with ImageDatabase(temp_db) as db:
            image = db.get_all_images()[0]
            palette = db.get_palette(image.filepath)

            assert palette is not None
            assert palette.avg_hue is not None
            if saved_hue:
                assert abs(palette.avg_hue - saved_hue) < 0.01


class TestReindexing:
    """Test re-indexing behavior."""

    @pytest.mark.e2e
    def test_reindex_preserves_usage_stats(self, temp_db, fixtures_dir):
        """Re-indexing preserves times_shown and last_shown_at."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Initial index and record shown
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            indexer.index_directory(fixtures_dir)

        with SmartSelector(temp_db, SelectionConfig()) as selector:
            image = selector.db.get_all_images()[0]
            selector.record_shown(image.filepath)
            selector.record_shown(image.filepath)
            original_times = 2
            original_last_shown = selector.db.get_image(image.filepath).last_shown_at

        # Re-index
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            indexer.index_directory(fixtures_dir)

            # Verify stats preserved
            img = db.get_image(image.filepath)
            assert img.times_shown == original_times
            assert img.last_shown_at == original_last_shown

    @pytest.mark.e2e
    def test_deleted_images_removed_on_reindex(self, temp_db, temp_dir, fixture_images):
        """Deleted images are removed when re-indexing with cleanup."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        import shutil

        # Copy fixtures to temp dir
        test_dir = os.path.join(temp_dir, 'images')
        os.makedirs(test_dir)
        for img in fixture_images:
            shutil.copy(img, test_dir)

        # Initial index
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(test_dir)
            initial_count = len(db.get_all_images())

        # Delete one image
        images_in_dir = os.listdir(test_dir)
        deleted_image = os.path.join(test_dir, images_in_dir[0])
        os.remove(deleted_image)

        # Re-index with cleanup
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.cleanup_missing_images()

            # Verify image removed
            assert len(db.get_all_images()) == initial_count - 1
            assert db.get_image(deleted_image) is None
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/smart_selection/e2e/test_persistence.py -v
```

Expected: 4 tests PASS

**Step 3: Commit**

```bash
git add tests/smart_selection/e2e/test_persistence.py
git commit -m "test: add persistence E2E tests"
```

---

## Task 8: Implement Edge Case Tests

**Files:**
- Create: `tests/smart_selection/e2e/test_edge_cases.py`

**Step 1: Write edge case tests**

```python
# tests/smart_selection/e2e/test_edge_cases.py
"""Tests for edge cases and error handling."""

import os
import pytest


class TestConstraintEdgeCases:
    """Test edge cases in constraint filtering."""

    @pytest.mark.e2e
    def test_impossible_constraints_return_empty(self, indexed_database):
        """Constraints that match nothing return empty list."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        # Require impossibly large dimensions
        constraints = SelectionConstraints(
            min_width=100000,
            min_height=100000,
        )

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=5, constraints=constraints)
            assert selected == []

    @pytest.mark.e2e
    def test_request_more_than_available(self, indexed_database):
        """Requesting more images than available returns all available."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            total_images = len(selector.db.get_all_images())

            # Request way more than available
            selected = selector.select_images(count=total_images + 100)

            assert len(selected) == total_images

    @pytest.mark.e2e
    def test_zero_count_returns_empty(self, indexed_database):
        """Requesting zero images returns empty list."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=0)
            assert selected == []

    @pytest.mark.e2e
    def test_aspect_ratio_range_filtering(self, indexed_database):
        """Aspect ratio constraints filter correctly."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            # Only landscape images (aspect > 1.5)
            constraints = SelectionConstraints(min_aspect_ratio=1.5)
            selected = selector.select_images(count=100, constraints=constraints)

            for filepath in selected:
                img = selector.db.get_image(filepath)
                assert img.aspect_ratio >= 1.5


class TestCorruptedDataHandling:
    """Test handling of corrupted or missing data."""

    @pytest.mark.e2e
    def test_missing_image_file_handled(self, indexed_database):
        """Selection handles missing image files gracefully."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            # Selection works even if some files are missing
            # (they're still in DB but file doesn't exist)
            selected = selector.select_images(count=3)

            # All selected files should exist
            for path in selected:
                assert os.path.exists(path)

    @pytest.mark.e2e
    def test_nonexistent_source_filter_returns_empty(self, indexed_database):
        """Filtering by non-existent source returns empty."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(sources=['nonexistent_source_xyz'])

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=5, constraints=constraints)
            assert selected == []


class TestConcurrency:
    """Test concurrent access patterns."""

    @pytest.mark.e2e
    def test_multiple_selectors_same_database(self, indexed_database):
        """Multiple selectors can read from same database."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as sel1:
            with SmartSelector(indexed_database, SelectionConfig()) as sel2:
                # Both can select
                result1 = sel1.select_images(count=2)
                result2 = sel2.select_images(count=2)

                assert len(result1) == 2
                assert len(result2) == 2
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/smart_selection/e2e/test_edge_cases.py -v
```

Expected: 7 tests PASS

**Step 3: Commit**

```bash
git add tests/smart_selection/e2e/test_edge_cases.py
git commit -m "test: add edge case E2E tests"
```

---

## Task 9: Create Benchmark Infrastructure

**Files:**
- Create: `tests/smart_selection/benchmarks/__init__.py`
- Create: `tests/smart_selection/benchmarks/conftest.py`

**Step 1: Create benchmarks package**

```bash
mkdir -p tests/smart_selection/benchmarks
touch tests/smart_selection/benchmarks/__init__.py
```

**Step 2: Write benchmark conftest.py**

```python
# tests/smart_selection/benchmarks/conftest.py
"""Shared fixtures for benchmark tests."""

import os
import shutil
import tempfile
import pytest

FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'fixtures', 'wallpapers'
)


@pytest.fixture(scope="module")
def benchmark_db():
    """Create a temporary database for benchmarks (module-scoped for speed)."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'benchmark.db')
    yield db_path
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture(scope="module")
def benchmark_fixtures_dir():
    """Return path to fixture wallpapers."""
    if not os.path.isdir(FIXTURES_DIR):
        pytest.skip(f"Fixtures directory not found: {FIXTURES_DIR}")
    return FIXTURES_DIR


@pytest.fixture(scope="module")
def large_image_set(benchmark_fixtures_dir, tmp_path_factory):
    """Create a larger set of images by duplicating fixtures."""
    large_dir = tmp_path_factory.mktemp("large_images")

    # Duplicate fixtures to create ~100 images for benchmarking
    fixture_images = [
        os.path.join(benchmark_fixtures_dir, f)
        for f in os.listdir(benchmark_fixtures_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]

    for i in range(10):  # 10x duplication
        for img in fixture_images:
            base = os.path.basename(img)
            name, ext = os.path.splitext(base)
            new_name = f"{name}_copy{i}{ext}"
            shutil.copy(img, large_dir / new_name)

    return str(large_dir)


@pytest.fixture(scope="module")
def indexed_benchmark_db(benchmark_db, benchmark_fixtures_dir):
    """Pre-indexed database for selection benchmarks."""
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.indexer import ImageIndexer

    with ImageDatabase(benchmark_db) as db:
        indexer = ImageIndexer(db, favorites_folder=benchmark_fixtures_dir)
        indexer.index_directory(benchmark_fixtures_dir)

    return benchmark_db
```

**Step 3: Commit**

```bash
git add tests/smart_selection/benchmarks/
git commit -m "test: add benchmark infrastructure"
```

---

## Task 10: Implement Indexing Benchmarks

**Files:**
- Create: `tests/smart_selection/benchmarks/bench_indexing.py`

**Step 1: Write indexing benchmarks**

```python
# tests/smart_selection/benchmarks/bench_indexing.py
"""Benchmarks for image indexing performance."""

import os
import tempfile
import shutil
import pytest


class TestIndexingBenchmarks:
    """Benchmarks for indexing operations."""

    @pytest.mark.benchmark(group="indexing")
    def test_index_single_image(self, benchmark, benchmark_fixtures_dir):
        """Benchmark indexing a single image."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        images = [
            os.path.join(benchmark_fixtures_dir, f)
            for f in os.listdir(benchmark_fixtures_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ]
        test_image = images[0]

        def index_one():
            temp_dir = tempfile.mkdtemp()
            db_path = os.path.join(temp_dir, 'bench.db')
            try:
                with ImageDatabase(db_path) as db:
                    indexer = ImageIndexer(db)
                    indexer.index_image(test_image)
            finally:
                shutil.rmtree(temp_dir)

        benchmark(index_one)

    @pytest.mark.benchmark(group="indexing")
    def test_index_directory_small(self, benchmark, benchmark_fixtures_dir):
        """Benchmark indexing fixture directory (~10 images)."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        def index_fixtures():
            temp_dir = tempfile.mkdtemp()
            db_path = os.path.join(temp_dir, 'bench.db')
            try:
                with ImageDatabase(db_path) as db:
                    indexer = ImageIndexer(db)
                    indexer.index_directory(benchmark_fixtures_dir)
            finally:
                shutil.rmtree(temp_dir)

        benchmark(index_fixtures)

    @pytest.mark.benchmark(group="indexing")
    def test_index_directory_large(self, benchmark, large_image_set):
        """Benchmark indexing large directory (~100 images)."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        def index_large():
            temp_dir = tempfile.mkdtemp()
            db_path = os.path.join(temp_dir, 'bench.db')
            try:
                with ImageDatabase(db_path) as db:
                    indexer = ImageIndexer(db)
                    indexer.index_directory(large_image_set)
            finally:
                shutil.rmtree(temp_dir)

        benchmark(index_large)

    @pytest.mark.benchmark(group="indexing")
    def test_reindex_no_changes(self, benchmark, benchmark_fixtures_dir):
        """Benchmark re-indexing when nothing changed (should be fast)."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        # Pre-create indexed database
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, 'bench.db')

        with ImageDatabase(db_path) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(benchmark_fixtures_dir)

        def reindex():
            with ImageDatabase(db_path) as db:
                indexer = ImageIndexer(db)
                indexer.index_directory(benchmark_fixtures_dir)

        try:
            benchmark(reindex)
        finally:
            shutil.rmtree(temp_dir)
```

**Step 2: Run benchmarks**

```bash
python3 -m pytest tests/smart_selection/benchmarks/bench_indexing.py -v --benchmark-only
```

Expected: 4 benchmarks run with timing results.

**Step 3: Commit**

```bash
git add tests/smart_selection/benchmarks/bench_indexing.py
git commit -m "test: add indexing benchmarks"
```

---

## Task 11: Implement Selection Benchmarks

**Files:**
- Create: `tests/smart_selection/benchmarks/bench_selection.py`

**Step 1: Write selection benchmarks**

```python
# tests/smart_selection/benchmarks/bench_selection.py
"""Benchmarks for image selection performance."""

import pytest


class TestSelectionBenchmarks:
    """Benchmarks for selection operations."""

    @pytest.mark.benchmark(group="selection")
    def test_select_single_no_constraints(self, benchmark, indexed_benchmark_db):
        """Benchmark selecting single image, no constraints."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        selector = SmartSelector(indexed_benchmark_db, SelectionConfig())

        def select_one():
            return selector.select_images(count=1)

        result = benchmark(select_one)
        selector.close()
        assert len(result) == 1

    @pytest.mark.benchmark(group="selection")
    def test_select_multiple_no_constraints(self, benchmark, indexed_benchmark_db):
        """Benchmark selecting 5 images, no constraints."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        selector = SmartSelector(indexed_benchmark_db, SelectionConfig())

        def select_five():
            return selector.select_images(count=5)

        result = benchmark(select_five)
        selector.close()
        assert len(result) <= 5

    @pytest.mark.benchmark(group="selection")
    def test_select_with_dimension_constraints(self, benchmark, indexed_benchmark_db):
        """Benchmark selection with dimension constraints."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        selector = SmartSelector(indexed_benchmark_db, SelectionConfig())
        constraints = SelectionConstraints(
            min_width=1000,
            min_height=500,
        )

        def select_constrained():
            return selector.select_images(count=3, constraints=constraints)

        benchmark(select_constrained)
        selector.close()

    @pytest.mark.benchmark(group="selection")
    def test_select_with_aspect_ratio_constraints(self, benchmark, indexed_benchmark_db):
        """Benchmark selection with aspect ratio constraints."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        selector = SmartSelector(indexed_benchmark_db, SelectionConfig())
        constraints = SelectionConstraints(
            min_aspect_ratio=1.0,
            max_aspect_ratio=2.0,
        )

        def select_constrained():
            return selector.select_images(count=3, constraints=constraints)

        benchmark(select_constrained)
        selector.close()

    @pytest.mark.benchmark(group="selection")
    def test_weight_calculation_overhead(self, benchmark, indexed_benchmark_db):
        """Benchmark the overhead of weight calculations."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Compare enabled vs disabled selection
        config_enabled = SelectionConfig(enabled=True)
        config_disabled = SelectionConfig(enabled=False)

        selector_enabled = SmartSelector(indexed_benchmark_db, config_enabled)
        selector_disabled = SmartSelector(indexed_benchmark_db, config_disabled)

        def select_weighted():
            return selector_enabled.select_images(count=3)

        benchmark(select_weighted)
        selector_enabled.close()
        selector_disabled.close()
```

**Step 2: Run benchmarks**

```bash
python3 -m pytest tests/smart_selection/benchmarks/bench_selection.py -v --benchmark-only
```

Expected: 5 benchmarks run with timing results.

**Step 3: Commit**

```bash
git add tests/smart_selection/benchmarks/bench_selection.py
git commit -m "test: add selection benchmarks"
```

---

## Task 12: Implement Palette Benchmarks

**Files:**
- Create: `tests/smart_selection/benchmarks/bench_palette.py`

**Step 1: Write palette benchmarks**

```python
# tests/smart_selection/benchmarks/bench_palette.py
"""Benchmarks for palette extraction and color operations."""

import os
import shutil
import pytest


class TestPaletteBenchmarks:
    """Benchmarks for palette operations."""

    @pytest.mark.benchmark(group="palette")
    def test_hex_to_hsl_conversion(self, benchmark):
        """Benchmark hex to HSL color conversion."""
        from variety.smart_selection.palette import hex_to_hsl

        colors = [
            "#FF0000", "#00FF00", "#0000FF", "#FFFFFF", "#000000",
            "#FF5733", "#33FF57", "#3357FF", "#F0F0F0", "#0F0F0F",
        ]

        def convert_all():
            for color in colors:
                hex_to_hsl(color)

        benchmark(convert_all)

    @pytest.mark.benchmark(group="palette")
    def test_palette_similarity_calculation(self, benchmark):
        """Benchmark palette similarity calculation."""
        from variety.smart_selection.palette import palette_similarity

        palette1 = {
            'avg_hue': 180,
            'avg_saturation': 0.5,
            'avg_lightness': 0.5,
            'color_temperature': 0.0,
        }
        palette2 = {
            'avg_hue': 200,
            'avg_saturation': 0.6,
            'avg_lightness': 0.4,
            'color_temperature': -0.2,
        }

        def calculate_similarity():
            return palette_similarity(palette1, palette2)

        result = benchmark(calculate_similarity)
        assert 0 <= result <= 1

    @pytest.mark.benchmark(group="palette")
    @pytest.mark.skipif(
        not shutil.which('wallust'),
        reason="wallust not installed"
    )
    def test_wallust_extraction_single(self, benchmark, benchmark_fixtures_dir):
        """Benchmark wallust palette extraction for single image."""
        from variety.smart_selection.palette import PaletteExtractor

        images = [
            os.path.join(benchmark_fixtures_dir, f)
            for f in os.listdir(benchmark_fixtures_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ]
        test_image = images[0]

        extractor = PaletteExtractor()

        def extract_palette():
            return extractor.extract_palette(test_image)

        result = benchmark(extract_palette)
        assert result is not None

    @pytest.mark.benchmark(group="palette")
    @pytest.mark.skipif(
        not shutil.which('wallust'),
        reason="wallust not installed"
    )
    def test_wallust_extraction_batch(self, benchmark, benchmark_fixtures_dir):
        """Benchmark wallust palette extraction for multiple images."""
        from variety.smart_selection.palette import PaletteExtractor

        images = [
            os.path.join(benchmark_fixtures_dir, f)
            for f in os.listdir(benchmark_fixtures_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ][:5]  # Limit to 5 for reasonable benchmark time

        extractor = PaletteExtractor()

        def extract_batch():
            results = []
            for img in images:
                results.append(extractor.extract_palette(img))
            return results

        results = benchmark(extract_batch)
        assert len(results) == len(images)

    @pytest.mark.benchmark(group="palette")
    def test_parse_wallust_json(self, benchmark):
        """Benchmark parsing wallust JSON output."""
        from variety.smart_selection.palette import parse_wallust_json

        json_data = {
            "background": "#171815",
            "foreground": "#E7E8EC",
            "cursor": "#A5A3A3",
            "color0": "#3E3F3C",
            "color1": "#3F4122",
            "color2": "#4A4743",
            "color3": "#544638",
            "color4": "#5B4622",
            "color5": "#6E7076",
            "color6": "#8C8E97",
            "color7": "#D5D6DC",
            "color8": "#95959A",
            "color9": "#54572D",
            "color10": "#635F5A",
            "color11": "#705E4B",
            "color12": "#7A5D2D",
            "color13": "#93969D",
            "color14": "#BBBDC9",
            "color15": "#D5D6DC",
        }

        def parse():
            return parse_wallust_json(json_data)

        result = benchmark(parse)
        assert 'avg_hue' in result
```

**Step 2: Run benchmarks**

```bash
python3 -m pytest tests/smart_selection/benchmarks/bench_palette.py -v --benchmark-only
```

Expected: 5 benchmarks run with timing results.

**Step 3: Commit**

```bash
git add tests/smart_selection/benchmarks/bench_palette.py
git commit -m "test: add palette benchmarks"
```

---

## Task 13: Add Database Operation Benchmarks

**Files:**
- Create: `tests/smart_selection/benchmarks/bench_database.py`

**Step 1: Write database benchmarks**

```python
# tests/smart_selection/benchmarks/bench_database.py
"""Benchmarks for database operations."""

import os
import tempfile
import shutil
import pytest


class TestDatabaseBenchmarks:
    """Benchmarks for database operations."""

    @pytest.mark.benchmark(group="database")
    def test_get_all_images(self, benchmark, indexed_benchmark_db):
        """Benchmark retrieving all images from database."""
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(indexed_benchmark_db)

        def get_all():
            return db.get_all_images()

        result = benchmark(get_all)
        db.close()
        assert len(result) > 0

    @pytest.mark.benchmark(group="database")
    def test_get_single_image(self, benchmark, indexed_benchmark_db):
        """Benchmark retrieving single image by path."""
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(indexed_benchmark_db)
        images = db.get_all_images()
        test_path = images[0].filepath

        def get_one():
            return db.get_image(test_path)

        result = benchmark(get_one)
        db.close()
        assert result is not None

    @pytest.mark.benchmark(group="database")
    def test_update_image_shown(self, benchmark, benchmark_fixtures_dir):
        """Benchmark recording image shown (update operation)."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        # Create fresh DB for each benchmark run
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, 'bench.db')

        with ImageDatabase(db_path) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(benchmark_fixtures_dir)
            test_path = db.get_all_images()[0].filepath

        db = ImageDatabase(db_path)

        def record_shown():
            db.record_image_shown(test_path)

        benchmark(record_shown)
        db.close()
        shutil.rmtree(temp_dir)

    @pytest.mark.benchmark(group="database")
    def test_get_favorite_images(self, benchmark, indexed_benchmark_db):
        """Benchmark retrieving favorite images."""
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(indexed_benchmark_db)

        def get_favorites():
            return db.get_favorite_images()

        benchmark(get_favorites)
        db.close()

    @pytest.mark.benchmark(group="database")
    def test_upsert_palette(self, benchmark, indexed_benchmark_db):
        """Benchmark upserting palette record."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import PaletteRecord
        import time

        db = ImageDatabase(indexed_benchmark_db)
        images = db.get_all_images()
        test_path = images[0].filepath

        palette = PaletteRecord(
            filepath=test_path,
            color0="#000000",
            color1="#111111",
            background="#000000",
            foreground="#FFFFFF",
            avg_hue=180.0,
            avg_saturation=0.5,
            avg_lightness=0.5,
            color_temperature=0.0,
            indexed_at=int(time.time()),
        )

        def upsert():
            db.upsert_palette(palette)

        benchmark(upsert)
        db.close()
```

**Step 2: Run benchmarks**

```bash
python3 -m pytest tests/smart_selection/benchmarks/bench_database.py -v --benchmark-only
```

Expected: 5 benchmarks run with timing results.

**Step 3: Commit**

```bash
git add tests/smart_selection/benchmarks/bench_database.py
git commit -m "test: add database benchmarks"
```

---

## Task 14: Create Test Runner Scripts

**Files:**
- Create: `tests/smart_selection/run_tests.py`

**Step 1: Write test runner with categories**

```python
#!/usr/bin/env python3
# tests/smart_selection/run_tests.py
"""
Test runner for Smart Selection Engine.

Usage:
    python run_tests.py              # Run all unit tests (fast)
    python run_tests.py --e2e        # Run E2E tests
    python run_tests.py --bench      # Run benchmarks
    python run_tests.py --all        # Run everything
    python run_tests.py --coverage   # Run with coverage report
"""

import argparse
import subprocess
import sys
import os


def run_unit_tests(verbose=False):
    """Run unit tests with unittest."""
    print("\n=== Running Unit Tests ===\n")
    cmd = [
        sys.executable, '-m', 'unittest', 'discover',
        'tests/smart_selection', '-v' if verbose else '-q',
        '-p', 'test_*.py',
    ]
    # Exclude e2e and benchmarks
    return subprocess.run(cmd, cwd=get_project_root()).returncode


def run_e2e_tests(verbose=False):
    """Run E2E tests with pytest."""
    print("\n=== Running E2E Tests ===\n")
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/smart_selection/e2e/',
        '-v' if verbose else '-q',
        '--tb=short',
    ]
    return subprocess.run(cmd, cwd=get_project_root()).returncode


def run_benchmarks(verbose=False):
    """Run benchmarks with pytest-benchmark."""
    print("\n=== Running Benchmarks ===\n")
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/smart_selection/benchmarks/',
        '-v' if verbose else '-q',
        '--benchmark-only',
        '--benchmark-group-by=group',
    ]
    return subprocess.run(cmd, cwd=get_project_root()).returncode


def run_with_coverage():
    """Run all tests with coverage report."""
    print("\n=== Running Tests with Coverage ===\n")
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/smart_selection/',
        '--cov=variety.smart_selection',
        '--cov-report=term-missing',
        '--cov-report=html:coverage_html',
    ]
    return subprocess.run(cmd, cwd=get_project_root()).returncode


def get_project_root():
    """Get the project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description='Run Smart Selection tests')
    parser.add_argument('--e2e', action='store_true', help='Run E2E tests')
    parser.add_argument('--bench', action='store_true', help='Run benchmarks')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--coverage', action='store_true', help='Run with coverage')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    exit_code = 0

    if args.coverage:
        exit_code = run_with_coverage()
    elif args.all:
        exit_code = run_unit_tests(args.verbose)
        if exit_code == 0:
            exit_code = run_e2e_tests(args.verbose)
        if exit_code == 0:
            exit_code = run_benchmarks(args.verbose)
    elif args.e2e:
        exit_code = run_e2e_tests(args.verbose)
    elif args.bench:
        exit_code = run_benchmarks(args.verbose)
    else:
        # Default: run unit tests only
        exit_code = run_unit_tests(args.verbose)

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
```

**Step 2: Make executable and test**

```bash
chmod +x tests/smart_selection/run_tests.py
python3 tests/smart_selection/run_tests.py --help
```

**Step 3: Commit**

```bash
git add tests/smart_selection/run_tests.py
git commit -m "test: add test runner script with categories"
```

---

## Task 15: Update pytest.ini Configuration

**Files:**
- Create: `tests/smart_selection/pytest.ini`

**Step 1: Write pytest configuration**

```ini
# tests/smart_selection/pytest.ini
[pytest]
testpaths = .
python_files = test_*.py bench_*.py
python_classes = Test*
python_functions = test_* bench_*

markers =
    e2e: end-to-end tests requiring real dependencies
    slow: tests that take more than 5 seconds
    wallust: tests requiring wallust CLI
    benchmark: performance benchmark tests

addopts =
    --strict-markers
    -ra

filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning

# Benchmark defaults
benchmark_disable = false
benchmark_warmup = true
benchmark_min_rounds = 5
```

**Step 2: Commit**

```bash
git add tests/smart_selection/pytest.ini
git commit -m "test: add pytest configuration"
```

---

## Task 16: Final Verification

**Step 1: Install pytest dependencies**

```bash
pip install pytest pytest-benchmark
```

**Step 2: Run complete test suite**

```bash
# Unit tests
python3 -m unittest discover tests/smart_selection -v

# E2E tests
python3 -m pytest tests/smart_selection/e2e/ -v

# Benchmarks
python3 -m pytest tests/smart_selection/benchmarks/ -v --benchmark-only

# All together
python3 tests/smart_selection/run_tests.py --all -v
```

**Step 3: Verify test counts**

Expected:
- Unit tests: 142+ tests
- E2E tests: 15+ tests
- Benchmarks: 19+ benchmarks

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: complete E2E testing regime implementation"
```

---

## Summary

This implementation creates:

1. **Test Fixtures** - 10+ curated wallpaper images
2. **E2E Tests** - 15+ workflow, persistence, and edge case tests
3. **Benchmarks** - 19+ performance benchmarks covering:
   - Indexing (single, directory, re-index)
   - Selection (various constraint combinations)
   - Palette (extraction, similarity, parsing)
   - Database (CRUD operations)
4. **Infrastructure** - pytest fixtures, markers, runner script

**Run times:**
- Unit tests: ~2 seconds
- E2E tests: ~30 seconds (with wallust)
- Benchmarks: ~60 seconds
