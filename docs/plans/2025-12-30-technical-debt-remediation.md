# Technical Debt Remediation Plan

**Date:** 2025-12-30
**Target Phase:** Phase 5 (Post-Security Fixes)
**Priority:** High (Architecture), Medium (Performance), Low (Color Science)

---

## Overview

Four technical debt items identified in the Phase 4 Final Review:

| ID | Issue | Severity | Effort | Impact |
|----|-------|----------|--------|--------|
| ARCH-001 | SmartSelector god object (726 lines) | HIGH | Large | Maintainability |
| PERF-001 | Memory pressure loading all candidates | HIGH | Medium | Scalability |
| PERF-002 | Subprocess overhead in palette extraction | MEDIUM | Medium | User experience |
| SCIENCE-001 | HSL color space perceptually incorrect | LOW | Large | Color accuracy |

---

## ARCH-001: SmartSelector Decomposition

### Current State

`selector.py` is 726 lines with SmartSelector handling:
- Configuration management
- Candidate retrieval and filtering
- Weight calculation orchestration
- Constraint application (color, time, source)
- Image selection algorithm
- Recency tracking
- Palette extraction coordination
- Statistics collection

This violates Single Responsibility Principle and makes testing difficult.

### Target Architecture

```
variety/smart_selection/
├── selector.py           # SmartSelector facade (< 200 lines)
├── selection/
│   ├── __init__.py
│   ├── engine.py         # SelectionEngine - core weighted random
│   ├── constraints.py    # ConstraintApplier - filtering logic
│   ├── weights.py        # WeightCalculator - scoring (already exists)
│   └── candidates.py     # CandidateProvider - DB queries
└── [existing files]
```

### Detailed Design

#### 1. CandidateProvider (`selection/candidates.py`)

**Responsibility:** Retrieve and pre-filter candidates from database.

```python
"""Candidate retrieval and basic filtering."""
from dataclasses import dataclass
from typing import List, Optional, Iterator
import os

from variety.smart_selection.database import SmartSelectionDB
from variety.smart_selection.models import ImageRecord


@dataclass
class CandidateQuery:
    """Query parameters for candidate retrieval."""
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    min_width: Optional[int] = None
    min_height: Optional[int] = None
    favorites_only: bool = False
    exclude_filepaths: Optional[List[str]] = None


class CandidateProvider:
    """Provides filtered candidates from the database.

    Responsibilities:
    - Query database for images matching criteria
    - Filter non-existent files
    - Provide streaming iteration for large collections
    """

    def __init__(self, db: SmartSelectionDB):
        self._db = db

    def get_candidates(
        self,
        query: CandidateQuery,
        stream: bool = False
    ) -> Iterator[ImageRecord]:
        """Get candidates matching query.

        Args:
            query: Filter criteria.
            stream: If True, yield one at a time (memory efficient).
                    If False, load all then yield.

        Yields:
            ImageRecord instances that exist on disk.
        """
        if stream:
            yield from self._stream_candidates(query)
        else:
            yield from self._batch_candidates(query)

    def _batch_candidates(self, query: CandidateQuery) -> Iterator[ImageRecord]:
        """Load all candidates, filter, yield."""
        all_images = self._db.get_all_images()
        for img in all_images:
            if self._matches_query(img, query):
                if os.path.exists(img.filepath):
                    yield img

    def _stream_candidates(self, query: CandidateQuery) -> Iterator[ImageRecord]:
        """Stream candidates from database cursor."""
        # Future: Use DB cursor directly for memory efficiency
        # For now, delegate to batch
        yield from self._batch_candidates(query)

    def _matches_query(self, img: ImageRecord, query: CandidateQuery) -> bool:
        """Check if image matches query criteria."""
        if query.source_type and img.source_type != query.source_type:
            return False
        if query.source_id and img.source_id != query.source_id:
            return False
        if query.min_width and img.width and img.width < query.min_width:
            return False
        if query.min_height and img.height and img.height < query.min_height:
            return False
        if query.favorites_only and not img.is_favorite:
            return False
        if query.exclude_filepaths and img.filepath in query.exclude_filepaths:
            return False
        return True
```

#### 2. ConstraintApplier (`selection/constraints.py`)

**Responsibility:** Apply color and palette constraints.

```python
"""Constraint application for candidate filtering."""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import logging

from variety.smart_selection.models import ImageRecord, PaletteRecord
from variety.smart_selection.database import SmartSelectionDB

logger = logging.getLogger(__name__)


@dataclass
class ColorConstraints:
    """Color-based selection constraints."""
    target_palette: Optional[Dict[str, Any]] = None
    min_lightness: Optional[float] = None
    max_lightness: Optional[float] = None
    min_saturation: Optional[float] = None
    max_saturation: Optional[float] = None
    temperature: Optional[str] = None  # 'warm', 'cool', 'neutral'
    similarity_threshold: float = 0.7


class ConstraintApplier:
    """Applies constraints to filter candidates.

    Responsibilities:
    - Color/palette filtering
    - Similarity scoring
    - Lightness/saturation/temperature constraints
    """

    def __init__(self, db: SmartSelectionDB):
        self._db = db

    def apply(
        self,
        candidates: List[ImageRecord],
        constraints: ColorConstraints
    ) -> List[ImageRecord]:
        """Apply color constraints to candidates.

        Args:
            candidates: List of candidate images.
            constraints: Color constraints to apply.

        Returns:
            Filtered list of candidates meeting constraints.
        """
        if not self._has_active_constraints(constraints):
            return candidates

        # Batch load palettes for efficiency
        filepaths = [c.filepath for c in candidates]
        palettes = self._db.get_palettes_by_filepaths(filepaths)
        palette_map = {p.filepath: p for p in palettes}

        filtered = []
        for candidate in candidates:
            palette = palette_map.get(candidate.filepath)
            if self._meets_constraints(palette, constraints):
                filtered.append(candidate)

        logger.debug(
            f"Color constraints: {len(candidates)} -> {len(filtered)} candidates"
        )
        return filtered

    def _has_active_constraints(self, c: ColorConstraints) -> bool:
        """Check if any constraints are active."""
        return any([
            c.target_palette,
            c.min_lightness is not None,
            c.max_lightness is not None,
            c.min_saturation is not None,
            c.max_saturation is not None,
            c.temperature,
        ])

    def _meets_constraints(
        self,
        palette: Optional[PaletteRecord],
        constraints: ColorConstraints
    ) -> bool:
        """Check if palette meets all constraints."""
        if palette is None:
            # No palette data - include if no strict constraints
            return not constraints.target_palette

        # Lightness constraints
        if constraints.min_lightness is not None:
            if palette.avg_lightness < constraints.min_lightness:
                return False
        if constraints.max_lightness is not None:
            if palette.avg_lightness > constraints.max_lightness:
                return False

        # Saturation constraints
        if constraints.min_saturation is not None:
            if palette.avg_saturation < constraints.min_saturation:
                return False
        if constraints.max_saturation is not None:
            if palette.avg_saturation > constraints.max_saturation:
                return False

        # Temperature constraints
        if constraints.temperature:
            if not self._matches_temperature(palette, constraints.temperature):
                return False

        # Similarity constraints
        if constraints.target_palette:
            similarity = self._calculate_similarity(
                palette, constraints.target_palette
            )
            if similarity < constraints.similarity_threshold:
                return False

        return True

    def _matches_temperature(
        self,
        palette: PaletteRecord,
        temperature: str
    ) -> bool:
        """Check if palette matches temperature preference."""
        if temperature == 'warm':
            return palette.color_temperature > 0.3
        elif temperature == 'cool':
            return palette.color_temperature < -0.3
        elif temperature == 'neutral':
            return -0.3 <= palette.color_temperature <= 0.3
        return True

    def _calculate_similarity(
        self,
        palette: PaletteRecord,
        target: Dict[str, Any]
    ) -> float:
        """Calculate similarity score between palettes."""
        # Implement HSL distance calculation
        # (Extract from current selector.py implementation)
        return 0.5  # Placeholder
```

#### 3. SelectionEngine (`selection/engine.py`)

**Responsibility:** Core weighted random selection algorithm.

```python
"""Core selection engine with weighted random algorithm."""
import bisect
import random
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging

from variety.smart_selection.models import ImageRecord, SourceRecord
from variety.smart_selection.weights import (
    recency_factor,
    source_recency_factor,
    SelectionConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class ScoredCandidate:
    """Candidate with calculated weight."""
    image: ImageRecord
    weight: float
    weight_breakdown: Optional[dict] = None


class SelectionEngine:
    """Core weighted random selection.

    Responsibilities:
    - Calculate weights for candidates
    - Perform O(log n) weighted random selection
    - Track selection reasoning for debugging
    """

    MIN_WEIGHT = 1e-6  # Prevent division by zero

    def __init__(self, config: SelectionConfig):
        self._config = config

    def select(
        self,
        candidates: List[ImageRecord],
        sources: dict,  # source_id -> SourceRecord
        count: int = 1,
        current_time: Optional[int] = None
    ) -> List[ImageRecord]:
        """Select images using weighted random algorithm.

        Args:
            candidates: Pool of candidate images.
            sources: Map of source_id to SourceRecord for source weights.
            count: Number of images to select.
            current_time: Unix timestamp (defaults to now).

        Returns:
            List of selected images.
        """
        if not candidates:
            return []

        current_time = current_time or int(time.time())

        # Score all candidates
        scored = [
            self._score_candidate(c, sources, current_time)
            for c in candidates
        ]

        # Build cumulative weights for binary search
        cumulative = []
        total = 0.0
        for sc in scored:
            total += sc.weight
            cumulative.append(total)

        if total == 0:
            # All weights zero - fall back to uniform random
            logger.warning("All weights zero, using uniform random")
            return random.sample(candidates, min(count, len(candidates)))

        # Select using binary search
        selected = []
        selected_indices = set()

        for _ in range(min(count, len(candidates))):
            # Find candidate at random point in weight distribution
            point = random.uniform(0, total)
            idx = bisect.bisect_left(cumulative, point)
            idx = min(idx, len(scored) - 1)

            # Avoid duplicates
            attempts = 0
            while idx in selected_indices and attempts < len(candidates):
                point = random.uniform(0, total)
                idx = bisect.bisect_left(cumulative, point)
                idx = min(idx, len(scored) - 1)
                attempts += 1

            if idx not in selected_indices:
                selected_indices.add(idx)
                selected.append(scored[idx].image)

        return selected

    def _score_candidate(
        self,
        candidate: ImageRecord,
        sources: dict,
        current_time: int
    ) -> ScoredCandidate:
        """Calculate weight for a candidate."""
        weight = 1.0
        breakdown = {}

        # Recency factor
        if candidate.last_shown_at:
            rf = recency_factor(
                candidate.last_shown_at,
                current_time,
                self._config.image_cooldown_days,
                self._config.recency_decay
            )
            weight *= rf
            breakdown['recency'] = rf
        else:
            # Never shown - apply new image boost
            weight *= self._config.new_image_boost
            breakdown['new_boost'] = self._config.new_image_boost

        # Source recency factor
        source = sources.get(candidate.source_id)
        if source and source.last_used_at:
            sf = source_recency_factor(
                source.last_used_at,
                current_time,
                self._config.source_cooldown_days
            )
            weight *= sf
            breakdown['source_recency'] = sf

        # Favorite boost
        if candidate.is_favorite:
            weight *= self._config.favorite_boost
            breakdown['favorite'] = self._config.favorite_boost

        # Ensure minimum weight
        weight = max(weight, self.MIN_WEIGHT)
        breakdown['final'] = weight

        return ScoredCandidate(
            image=candidate,
            weight=weight,
            weight_breakdown=breakdown
        )
```

#### 4. SmartSelector Facade (`selector.py` refactored)

**Responsibility:** Coordinate components, maintain backward compatibility.

```python
"""SmartSelector - Facade for intelligent wallpaper selection.

This module provides the main entry point for the smart selection system.
Internally delegates to specialized components:
- CandidateProvider: Database queries
- ConstraintApplier: Color filtering
- SelectionEngine: Weighted random selection
"""
from typing import List, Optional

from variety.smart_selection.database import SmartSelectionDB
from variety.smart_selection.selection.candidates import (
    CandidateProvider, CandidateQuery
)
from variety.smart_selection.selection.constraints import (
    ConstraintApplier, ColorConstraints
)
from variety.smart_selection.selection.engine import SelectionEngine
from variety.smart_selection.weights import SelectionConfig
from variety.smart_selection.models import ImageRecord


class SmartSelector:
    """Intelligent wallpaper selection with weighted random algorithm.

    Facade pattern: Provides simple interface while delegating to
    specialized components for maintainability.
    """

    def __init__(
        self,
        db: SmartSelectionDB,
        config: Optional[SelectionConfig] = None
    ):
        self._db = db
        self._config = config or SelectionConfig()

        # Initialize components
        self._candidates = CandidateProvider(db)
        self._constraints = ConstraintApplier(db)
        self._engine = SelectionEngine(self._config)

    def select_images(
        self,
        count: int = 1,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        color_constraints: Optional[ColorConstraints] = None,
        exclude_recent: bool = True
    ) -> List[ImageRecord]:
        """Select images using intelligent weighted algorithm.

        Args:
            count: Number of images to select.
            source_type: Filter by source type.
            source_id: Filter by specific source.
            color_constraints: Color-based filtering.
            exclude_recent: Exclude recently shown images.

        Returns:
            List of selected ImageRecord instances.
        """
        # Build candidate query
        query = CandidateQuery(
            source_type=source_type,
            source_id=source_id,
        )

        # Get candidates
        candidates = list(self._candidates.get_candidates(query))

        if not candidates:
            return []

        # Apply color constraints if provided
        if color_constraints:
            candidates = self._constraints.apply(candidates, color_constraints)

        if not candidates:
            return []

        # Load source data for weighting
        source_ids = {c.source_id for c in candidates if c.source_id}
        sources = {}
        if source_ids:
            source_records = self._db.get_sources_by_ids(list(source_ids))
            sources = {s.id: s for s in source_records}

        # Select using weighted random
        return self._engine.select(candidates, sources, count)

    # ... remaining methods for backward compatibility ...
```

### Migration Strategy

1. **Phase 1:** Create `selection/` package with new components
2. **Phase 2:** Add comprehensive tests for new components
3. **Phase 3:** Refactor SmartSelector to use new components internally
4. **Phase 4:** Verify all existing tests pass
5. **Phase 5:** Remove duplicated code from SmartSelector

### Test Requirements

```python
# tests/smart_selection/test_candidate_provider.py
class TestCandidateProvider:
    def test_basic_query(self, provider, sample_images): ...
    def test_source_filtering(self, provider): ...
    def test_favorites_only(self, provider): ...
    def test_nonexistent_files_filtered(self, provider, tmp_path): ...
    def test_streaming_vs_batch_equivalent(self, provider): ...

# tests/smart_selection/test_constraint_applier.py
class TestConstraintApplier:
    def test_no_constraints_passes_all(self, applier): ...
    def test_lightness_range(self, applier): ...
    def test_temperature_filtering(self, applier): ...
    def test_batch_palette_loading(self, applier): ...

# tests/smart_selection/test_selection_engine.py
class TestSelectionEngine:
    def test_weighted_distribution(self, engine): ...
    def test_binary_search_correctness(self, engine): ...
    def test_favorite_boost_effect(self, engine): ...
    def test_recency_penalty_effect(self, engine): ...
    def test_zero_weights_fallback(self, engine): ...
```

### Effort Estimate

- Design: 2-3 hours (done above)
- Implementation: 8-12 hours
- Testing: 4-6 hours
- Migration/refactoring: 4-6 hours
- **Total: 18-27 hours**

---

## PERF-001: Memory-Efficient Candidate Streaming

### Current State

`selector.py:197`:
```python
candidates = self.db.get_all_images()  # Loads ALL images into memory
```

For 50,000 images at ~200 bytes each = 10MB peak memory.

### Target State

Stream candidates from database cursor, process in batches.

### Implementation

#### 1. Database Layer Changes

Add to `database.py`:

```python
def get_images_cursor(
    self,
    batch_size: int = 1000
) -> Iterator[List[ImageRecord]]:
    """Stream images in batches from database.

    Memory efficient alternative to get_all_images().

    Args:
        batch_size: Number of records per batch.

    Yields:
        Lists of ImageRecord, up to batch_size each.
    """
    with self._lock:
        cursor = self.conn.execute(
            'SELECT * FROM images ORDER BY filepath'
        )

        batch = []
        for row in cursor:
            batch.append(self._row_to_image_record(row))
            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:  # Remaining records
            yield batch
```

#### 2. CandidateProvider Enhancement

```python
def get_candidates_streaming(
    self,
    query: CandidateQuery,
    batch_size: int = 1000
) -> Iterator[List[ImageRecord]]:
    """Stream candidates in memory-efficient batches.

    For large collections (>10K images), this prevents memory spikes.

    Args:
        query: Filter criteria.
        batch_size: Records per batch.

    Yields:
        Batches of matching candidates.
    """
    for batch in self._db.get_images_cursor(batch_size):
        filtered = [
            img for img in batch
            if self._matches_query(img, query)
            and os.path.exists(img.filepath)
        ]
        if filtered:
            yield filtered
```

#### 3. Selection Engine Adaptation

```python
def select_streaming(
    self,
    candidate_batches: Iterator[List[ImageRecord]],
    sources: dict,
    count: int = 1
) -> List[ImageRecord]:
    """Select from streaming candidate batches.

    Uses reservoir sampling for memory efficiency with large collections.

    Args:
        candidate_batches: Iterator of candidate batches.
        sources: Source records for weighting.
        count: Number to select.

    Returns:
        Selected images.
    """
    # Reservoir sampling with weights
    reservoir = []
    total_weight = 0.0
    current_time = int(time.time())

    for batch in candidate_batches:
        for candidate in batch:
            scored = self._score_candidate(candidate, sources, current_time)
            total_weight += scored.weight

            if len(reservoir) < count:
                reservoir.append(scored)
            else:
                # Replace with probability proportional to weight
                p = scored.weight / total_weight
                if random.random() < p * count:
                    idx = random.randrange(count)
                    reservoir[idx] = scored

    return [sc.image for sc in reservoir]
```

### Test Requirements

```python
class TestStreamingSelection:
    def test_streaming_equivalent_to_batch(self, selector):
        """Streaming and batch should produce similar distributions."""
        # Run both methods many times, compare distributions

    def test_memory_bounded(self, selector, large_collection):
        """Memory should not exceed threshold with streaming."""
        import tracemalloc
        tracemalloc.start()

        results = selector.select_streaming(...)

        current, peak = tracemalloc.get_traced_memory()
        assert peak < 50_000_000  # 50MB limit

    def test_handles_empty_batches(self, selector):
        """Should handle batches where all candidates are filtered."""
```

### Effort Estimate

- Implementation: 4-6 hours
- Testing: 2-3 hours
- Integration: 2-3 hours
- **Total: 8-12 hours**

---

## PERF-002: Parallel Palette Extraction

### Current State

`palette.py` - `extract_all_palettes()`:
- Spawns wallust subprocess for each image sequentially
- 30-500ms per image
- 50K images = 2.7 hours

### Target State

Parallel extraction using ThreadPoolExecutor.

### Implementation

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
import threading

class PaletteExtractor:
    """Palette extraction with parallel processing support."""

    DEFAULT_WORKERS = 4

    def __init__(self, ...):
        self._executor: Optional[ThreadPoolExecutor] = None
        self._shutdown_event = threading.Event()

    def extract_all_palettes_parallel(
        self,
        images: List[str],
        max_workers: int = DEFAULT_WORKERS,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Extract palettes in parallel.

        Args:
            images: List of image paths.
            max_workers: Number of parallel workers.
            progress_callback: Called with (completed, total).

        Returns:
            Dict mapping filepath to palette data (or None if failed).
        """
        results = {}
        total = len(images)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            self._executor = executor

            # Submit all tasks
            futures = {
                executor.submit(self._extract_single, path): path
                for path in images
            }

            # Collect results as they complete
            for future in as_completed(futures):
                if self._shutdown_event.is_set():
                    break

                path = futures[future]
                try:
                    palette = future.result(timeout=60)
                    results[path] = palette
                except Exception as e:
                    logger.warning(f"Palette extraction failed for {path}: {e}")
                    results[path] = None

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        self._executor = None
        return results

    def _extract_single(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Extract palette for single image (thread-safe)."""
        if self._shutdown_event.is_set():
            return None
        return self.extract_palette(image_path)

    def shutdown(self):
        """Signal shutdown and wait for workers."""
        self._shutdown_event.set()
        if self._executor:
            self._executor.shutdown(wait=True)
```

### Test Requirements

```python
class TestParallelExtraction:
    def test_parallel_faster_than_sequential(self, extractor, sample_images):
        """Parallel should be significantly faster."""
        import time

        start = time.time()
        seq_results = extractor.extract_all_palettes(sample_images)
        seq_time = time.time() - start

        start = time.time()
        par_results = extractor.extract_all_palettes_parallel(
            sample_images, max_workers=4
        )
        par_time = time.time() - start

        assert par_time < seq_time * 0.5  # At least 2x faster

    def test_results_equivalent(self, extractor, sample_images):
        """Sequential and parallel should produce same results."""
        seq = extractor.extract_all_palettes(sample_images)
        par = extractor.extract_all_palettes_parallel(sample_images)
        assert seq == par

    def test_graceful_shutdown(self, extractor, many_images):
        """Shutdown should stop processing gracefully."""
        # Start parallel extraction in thread
        # Call shutdown() after short delay
        # Verify no crash, partial results returned

    def test_progress_callback(self, extractor, sample_images):
        """Progress callback should be called correctly."""
        progress = []
        extractor.extract_all_palettes_parallel(
            sample_images,
            progress_callback=lambda c, t: progress.append((c, t))
        )
        assert len(progress) == len(sample_images)
        assert progress[-1] == (len(sample_images), len(sample_images))
```

### Effort Estimate

- Implementation: 3-4 hours
- Testing: 2-3 hours
- Integration: 1-2 hours
- **Total: 6-9 hours**

---

## SCIENCE-001: Perceptual Color Space (OKLAB)

### Current State

Color similarity uses HSL space:
- HSL has non-uniform perceptual properties
- "Green" spans huge perceptual range
- "Cyan" is tiny perceptual slice
- Similarity scores don't match human perception

### Target State

Use OKLAB color space for perceptually uniform similarity.

### Background

OKLAB (2020) is designed for:
- Perceptual uniformity (equal distances = equal perceived differences)
- Hue linearity (interpolation doesn't shift hue)
- Better than CIELAB for practical applications

### Implementation

```python
# variety/smart_selection/color_science.py
"""Perceptual color science utilities using OKLAB color space."""

import math
from typing import Tuple


def srgb_to_linear(c: float) -> float:
    """Convert sRGB component to linear RGB."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    """Convert linear RGB component to sRGB."""
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1/2.4)) - 0.055


def rgb_to_oklab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Convert RGB (0-255) to OKLAB (L: 0-1, a: ~-0.4-0.4, b: ~-0.4-0.4).

    Args:
        r, g, b: RGB values 0-255.

    Returns:
        Tuple of (L, a, b) in OKLAB space.
    """
    # Normalize to 0-1
    r_lin = srgb_to_linear(r / 255)
    g_lin = srgb_to_linear(g / 255)
    b_lin = srgb_to_linear(b / 255)

    # Linear RGB to LMS (cone response)
    l = 0.4122214708 * r_lin + 0.5363325363 * g_lin + 0.0514459929 * b_lin
    m = 0.2119034982 * r_lin + 0.6806995451 * g_lin + 0.1073969566 * b_lin
    s = 0.0883024619 * r_lin + 0.2817188376 * g_lin + 0.6299787005 * b_lin

    # Cube root
    l_ = l ** (1/3) if l >= 0 else -((-l) ** (1/3))
    m_ = m ** (1/3) if m >= 0 else -((-m) ** (1/3))
    s_ = s ** (1/3) if s >= 0 else -((-s) ** (1/3))

    # LMS to OKLAB
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    return (L, a, b)


def oklab_distance(
    lab1: Tuple[float, float, float],
    lab2: Tuple[float, float, float]
) -> float:
    """Calculate perceptual distance between two OKLAB colors.

    Returns:
        Distance (0 = identical, ~1 = maximum difference).
    """
    dL = lab1[0] - lab2[0]
    da = lab1[1] - lab2[1]
    db = lab1[2] - lab2[2]
    return math.sqrt(dL*dL + da*da + db*db)


def palette_similarity_oklab(
    palette1: dict,
    palette2: dict
) -> float:
    """Calculate similarity between palettes using OKLAB.

    Args:
        palette1, palette2: Palette dicts with 'colors' list of hex values.

    Returns:
        Similarity score 0-1 (1 = identical).
    """
    colors1 = palette1.get('colors', [])
    colors2 = palette2.get('colors', [])

    if not colors1 or not colors2:
        return 0.0

    # Convert to OKLAB
    def hex_to_oklab(hex_color: str) -> Tuple[float, float, float]:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return rgb_to_oklab(r, g, b)

    labs1 = [hex_to_oklab(c) for c in colors1]
    labs2 = [hex_to_oklab(c) for c in colors2]

    # Calculate average minimum distance
    total_dist = 0.0
    for lab1 in labs1:
        min_dist = min(oklab_distance(lab1, lab2) for lab2 in labs2)
        total_dist += min_dist

    avg_dist = total_dist / len(labs1)

    # Convert distance to similarity (max distance ~1.4 for black-white)
    similarity = max(0, 1 - avg_dist / 1.4)
    return similarity
```

### Migration Path

1. Add `color_science.py` module
2. Create `palette_similarity_oklab()` function
3. Add config flag: `use_oklab_similarity: bool = True`
4. Deprecate HSL similarity (keep for backward compatibility)
5. Default to OKLAB in new installations

### Test Requirements

```python
class TestOKLAB:
    def test_black_white_maximum_distance(self):
        """Black and white should have maximum distance."""
        black = rgb_to_oklab(0, 0, 0)
        white = rgb_to_oklab(255, 255, 255)
        dist = oklab_distance(black, white)
        assert dist > 0.9

    def test_similar_greens_close(self):
        """Similar greens should have small distance."""
        green1 = rgb_to_oklab(0, 200, 0)
        green2 = rgb_to_oklab(0, 210, 0)
        dist = oklab_distance(green1, green2)
        assert dist < 0.1

    def test_perceptual_uniformity(self):
        """Equal RGB steps should give roughly equal OKLAB distances."""
        # This tests the perceptual uniformity property

    def test_similarity_symmetric(self):
        """similarity(a,b) == similarity(b,a)"""

    def test_identical_palettes_similarity_one(self):
        """Identical palettes should have similarity 1.0."""
```

### Effort Estimate

- Research: 2 hours (done above)
- Implementation: 3-4 hours
- Testing: 2-3 hours
- Migration: 2-3 hours
- **Total: 9-12 hours**

---

## Summary and Prioritization

| ID | Issue | Effort | Value | Priority |
|----|-------|--------|-------|----------|
| ARCH-001 | SmartSelector decomposition | 18-27h | High (maintainability) | 1 |
| PERF-002 | Parallel palette extraction | 6-9h | High (UX) | 2 |
| PERF-001 | Streaming candidates | 8-12h | Medium (scalability) | 3 |
| SCIENCE-001 | OKLAB color space | 9-12h | Low (accuracy) | 4 |

### Recommended Execution Order

1. **PERF-002** first - Highest value/effort ratio, immediate user impact
2. **ARCH-001** second - Enables easier future work
3. **PERF-001** third - Benefits large collections
4. **SCIENCE-001** last - Nice-to-have, lower priority

### Total Effort

- Minimum: 41 hours
- Maximum: 60 hours
- **Realistic: ~50 hours (1-2 weeks)**

---

*Technical debt plan created: 2025-12-30*
