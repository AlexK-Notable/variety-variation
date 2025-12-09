# End-to-End Test Suite Design

**Date:** 2025-12-08
**Purpose:** Validate Smart Selection is production-ready

## Test Environment Setup

```python
# tests/smart_selection/e2e/conftest.py

import pytest
import tempfile
import shutil
import os
from pathlib import Path

@pytest.fixture
def test_environment():
    """Create isolated test environment with sample images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = TestEnvironment(tmpdir)
        env.setup()
        yield env
        env.teardown()

class TestEnvironment:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "smart_selection.db"
        self.downloaded_dir = self.base_dir / "Downloaded"
        self.favorites_dir = self.base_dir / "Favorites"
        self.wallust_cache = self.base_dir / ".cache" / "wallust"

    def setup(self):
        # Create directories
        self.downloaded_dir.mkdir(parents=True)
        self.favorites_dir.mkdir(parents=True)
        self.wallust_cache.mkdir(parents=True)

        # Copy sample images (use small test images)
        self._create_test_images()

    def _create_test_images(self):
        """Create minimal valid PNG files for testing."""
        # Use PIL to create simple colored images
        pass

    def create_wallust_cache(self, image_path, palette):
        """Create fake wallust cache file for testing."""
        pass
```

---

## E2E-1: Fresh Install Flow

**Objective:** Verify complete flow from empty database to working selection.

```python
# tests/smart_selection/e2e/test_fresh_install.py

class TestFreshInstallFlow:
    """E2E-1: Fresh install flow validation."""

    def test_empty_database_creates_schema(self, test_environment):
        """Database is created with correct schema on first run."""
        selector = SmartSelector(
            db_path=str(test_environment.db_path),
            config=SelectionConfig()
        )

        # Verify tables exist
        assert selector.db.get_statistics()['images_indexed'] == 0

    def test_favorites_indexed_on_startup(self, test_environment):
        """Favorites are indexed when selector starts."""
        # Add 5 images to favorites
        test_environment.add_favorite_images(5)

        selector = SmartSelector(...)
        selector.index_directory(str(test_environment.favorites_dir))

        stats = selector.get_statistics()
        assert stats['images_indexed'] == 5
        assert stats['favorites_count'] == 5

    def test_selection_works_after_indexing(self, test_environment):
        """Can select images after indexing."""
        test_environment.add_favorite_images(10)
        selector = SmartSelector(...)
        selector.index_directory(str(test_environment.favorites_dir))

        selected = selector.select_images(count=3)

        assert len(selected) == 3
        assert all(os.path.exists(p) for p in selected)

    def test_no_repeats_within_cooldown(self, test_environment):
        """Same image not selected twice within cooldown period."""
        test_environment.add_favorite_images(20)
        selector = SmartSelector(
            db_path=str(test_environment.db_path),
            config=SelectionConfig(image_cooldown_days=7)
        )
        selector.index_directory(str(test_environment.favorites_dir))

        # Select and record 10 images
        shown_images = set()
        for _ in range(10):
            selected = selector.select_images(count=1)
            assert selected[0] not in shown_images, "Image repeated within cooldown!"
            shown_images.add(selected[0])
            selector.record_shown(selected[0])

    def test_source_rotation(self, test_environment):
        """Different sources are rotated fairly."""
        # Add images from multiple sources
        test_environment.add_images_with_source("source_a", 10)
        test_environment.add_images_with_source("source_b", 10)

        selector = SmartSelector(...)
        selector.index_directory(str(test_environment.downloaded_dir))

        # Select 10 images, track sources
        source_counts = {"source_a": 0, "source_b": 0}
        for _ in range(10):
            selected = selector.select_images(count=1)
            source = selector.db.get_image(selected[0]).source_id
            source_counts[source] += 1
            selector.record_shown(selected[0])

        # Both sources should be represented (not all from one)
        assert source_counts["source_a"] >= 3
        assert source_counts["source_b"] >= 3
```

---

## E2E-2: Color-Aware Selection

**Objective:** Verify color preferences affect selection.

```python
# tests/smart_selection/e2e/test_color_selection.py

class TestColorAwareSelection:
    """E2E-2: Color-aware selection validation."""

    def test_warm_preference_selects_warm_images(self, test_environment):
        """Warm temperature preference selects warm-palette images."""
        # Create images with known palettes
        warm_images = test_environment.add_images_with_temperature("warm", 10)
        cool_images = test_environment.add_images_with_temperature("cool", 10)

        selector = SmartSelector(...)
        selector.index_directory(str(test_environment.downloaded_dir))

        # Extract palettes for all images
        for img in warm_images + cool_images:
            palette = test_environment.get_test_palette(img)
            selector.record_shown(img, wallust_palette=palette)

        # Reset shown status but keep palettes
        selector.clear_history()

        # Select with warm constraint
        constraints = SelectionConstraints(
            target_temperature="warm",
            min_similarity=0.5
        )

        selected = selector.select_images(count=5, constraints=constraints)

        # Most should be warm images
        warm_count = sum(1 for s in selected if s in warm_images)
        assert warm_count >= 4, f"Expected mostly warm images, got {warm_count}/5"

    def test_cool_preference_selects_cool_images(self, test_environment):
        """Cool temperature preference selects cool-palette images."""
        # Similar to above but with cool preference
        pass

    def test_adaptive_uses_time_of_day(self, test_environment, monkeypatch):
        """Adaptive mode selects based on time of day."""
        # Mock datetime to control time
        import datetime

        # Morning (6 AM) - should prefer cool/bright
        mock_morning = datetime.datetime(2025, 12, 8, 6, 0, 0)
        monkeypatch.setattr('datetime.datetime', lambda: mock_morning)

        # ... test selection prefers cool palettes

        # Evening (8 PM) - should prefer warm/dark
        mock_evening = datetime.datetime(2025, 12, 8, 20, 0, 0)
        # ... test selection prefers warm palettes
```

---

## E2E-3: Theming Engine

**Objective:** Verify theme templates are applied correctly.

```python
# tests/smart_selection/e2e/test_theming.py

class TestThemingEngine:
    """E2E-3: Theming engine validation."""

    def test_templates_applied_under_20ms(self, test_environment):
        """All templates applied within performance target."""
        import time

        # Setup engine with test templates
        engine = ThemeEngine(
            get_palette_callback=lambda p: test_environment.get_test_palette(p),
            wallust_config_path=str(test_environment.wallust_config)
        )

        # Add test templates
        test_environment.create_test_templates(count=10)
        engine.reload_config()

        # Time the apply
        start = time.perf_counter()
        success = engine.apply(test_environment.test_image, debounce=False)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert success
        assert elapsed_ms < 20, f"Apply took {elapsed_ms:.1f}ms, target <20ms"

    def test_template_variables_substituted(self, test_environment):
        """Template variables are correctly replaced with colors."""
        # Create template with known variables
        template_content = """
        background = "{{background}}"
        foreground = "{{foreground}}"
        color0 = "{{color0}}"
        modified = "{{color1 | darken(0.2)}}"
        """
        test_environment.create_template("test", template_content)

        palette = {
            'background': '#1a1a1a',
            'foreground': '#ffffff',
            'color0': '#ff0000',
            'color1': '#00ff00',
        }

        engine = ThemeEngine(lambda p: palette, ...)
        engine.apply(test_environment.test_image, debounce=False)

        # Read output file
        output = test_environment.read_template_output("test")

        assert '#1a1a1a' in output
        assert '#ffffff' in output
        assert '#ff0000' in output
        # color1 darkened should not be #00ff00
        assert '#00ff00' not in output

    def test_reload_commands_executed(self, test_environment, mocker):
        """Reload commands are called after template apply."""
        mock_run = mocker.patch('subprocess.run')

        engine = ThemeEngine(...)
        engine.apply(test_environment.test_image, debounce=False)

        # Check reload commands were called
        assert mock_run.called
```

---

## E2E-4: Recency Tracking

**Objective:** Verify recency-based selection prevents repeats correctly.

```python
# tests/smart_selection/e2e/test_recency.py

class TestRecencyTracking:
    """E2E-4: Recency tracking validation."""

    def test_shown_image_excluded_during_cooldown(self, test_environment):
        """Recently shown image never selected during cooldown."""
        test_environment.add_favorite_images(100)

        selector = SmartSelector(
            config=SelectionConfig(image_cooldown_days=7)
        )
        selector.index_directory(...)

        # Show image A
        image_a = selector.select_images(count=1)[0]
        selector.record_shown(image_a)

        # Select 99 more times - A should never appear
        for _ in range(99):
            selected = selector.select_images(count=1)
            assert selected[0] != image_a, "Image appeared during cooldown!"
            selector.record_shown(selected[0])

    def test_image_available_after_cooldown_expires(self, test_environment):
        """Image becomes available again after cooldown expires."""
        test_environment.add_favorite_images(5)

        selector = SmartSelector(
            config=SelectionConfig(image_cooldown_days=1)
        )
        selector.index_directory(...)

        # Show all 5 images
        all_images = []
        for _ in range(5):
            selected = selector.select_images(count=1)[0]
            all_images.append(selected)
            selector.record_shown(selected)

        # Manually advance the "last_shown_at" timestamp by 2 days
        for img in all_images:
            selector.db._advance_shown_time(img, days=-2)

        # Now all images should be available again
        selected = selector.select_images(count=5)
        assert len(selected) == 5
```

---

## E2E-5: Performance Under Load

**Objective:** Verify performance with large collections.

```python
# tests/smart_selection/e2e/test_performance.py

import time
import psutil
import pytest

class TestPerformanceUnderLoad:
    """E2E-5: Performance validation with large collections."""

    @pytest.mark.slow
    def test_index_10k_images_under_30s(self, test_environment):
        """10,000 images indexed in under 30 seconds."""
        test_environment.add_test_images(10000)

        selector = SmartSelector(...)

        start = time.perf_counter()
        selector.index_directory(str(test_environment.downloaded_dir))
        elapsed = time.perf_counter() - start

        assert elapsed < 30, f"Indexing took {elapsed:.1f}s, target <30s"

        stats = selector.get_statistics()
        assert stats['images_indexed'] == 10000

    @pytest.mark.slow
    def test_select_100_images_under_1s(self, test_environment):
        """Selecting 100 images from 10K collection in under 1 second."""
        test_environment.add_test_images(10000)

        selector = SmartSelector(...)
        selector.index_directory(...)

        start = time.perf_counter()
        selected = selector.select_images(count=100)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Selection took {elapsed:.1f}s, target <1s"
        assert len(selected) == 100

    @pytest.mark.slow
    def test_memory_under_200mb_during_indexing(self, test_environment):
        """Memory stays under 200MB during large indexing operation."""
        test_environment.add_test_images(10000)

        process = psutil.Process()
        baseline_mem = process.memory_info().rss / 1024 / 1024  # MB

        selector = SmartSelector(...)
        selector.index_directory(...)

        peak_mem = process.memory_info().rss / 1024 / 1024  # MB
        mem_increase = peak_mem - baseline_mem

        assert mem_increase < 200, f"Memory increased by {mem_increase:.1f}MB, target <200MB"
```

---

## Test Execution

### Run All E2E Tests
```bash
python -m pytest tests/smart_selection/e2e/ -v --tb=long 2>&1 | tee docs/validation/e2e-results-$(date +%Y-%m-%d).md
```

### Run Performance Tests Only
```bash
python -m pytest tests/smart_selection/e2e/ -v -m slow --benchmark-only
```

### Generate Coverage Report
```bash
python -m pytest tests/smart_selection/ --cov=variety/smart_selection --cov-report=html:docs/validation/coverage
```

---

## Success Criteria

All E2E tests must pass before the feature is considered shippable:

| Test Suite | Required Pass Rate |
|------------|-------------------|
| E2E-1: Fresh Install | 100% |
| E2E-2: Color Selection | 100% |
| E2E-3: Theming Engine | 100% |
| E2E-4: Recency Tracking | 100% |
| E2E-5: Performance | 100% |

Performance targets:
- Index 10K images: <30s
- Select 100 images: <1s
- Theme apply: <20ms
- Memory during indexing: <200MB
