# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Weighted random selection algorithm.

Provides the core selection algorithm using weighted random selection
with O(n + k·log k) efficiency via weighted reservoir sampling.
"""

import heapq
import logging
import math
import random
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from variety.smart_selection.weights import calculate_weight
from variety.smart_selection.time_adapter import TimeAdapter, PaletteTarget

if TYPE_CHECKING:
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.models import ImageRecord, SelectionConstraints, PaletteRecord
    from variety.smart_selection.config import SelectionConfig

logger = logging.getLogger(__name__)


@dataclass
class ScoredCandidate:
    """A candidate image with its calculated weight.

    Attributes:
        image: The ImageRecord for this candidate.
        weight: Calculated selection weight (higher = more likely).
        weight_breakdown: Optional dict with individual weight factors.
    """
    image: 'ImageRecord'
    weight: float
    weight_breakdown: Optional[Dict[str, float]] = None


class SelectionEngine:
    """Performs weighted random selection of images.

    Uses cumulative weights with binary search (bisect) for O(log n)
    selection performance.
    """

    def __init__(self, db: 'ImageDatabase', config: 'SelectionConfig'):
        """Initialize the selection engine.

        Args:
            db: ImageDatabase instance for source lookups.
            config: SelectionConfig with weight parameters.
        """
        self.db = db
        self.config = config
        self._time_adapter: Optional[TimeAdapter] = None

        # Initialize time adapter if time adaptation is enabled
        if config.time_adaptation_enabled:
            try:
                self._time_adapter = TimeAdapter(config)
                logger.debug("TimeAdapter initialized for time-based selection")
            except Exception as e:
                logger.warning(f"Failed to initialize TimeAdapter: {e}")

    def _get_time_target(self, context: str = "") -> Optional[PaletteTarget]:
        """Get time-based palette target if time adaptation is enabled.

        Args:
            context: Optional context string for logging (e.g., "scoring", "selection").

        Returns:
            PaletteTarget if time adaptation is enabled and successful, None otherwise.
        """
        if not self._time_adapter or not self.config.time_adaptation_enabled:
            return None

        try:
            target = self._time_adapter.get_palette_target()
            period = self._time_adapter.get_current_period()
            logger.debug(f"Time adaptation active: period={period}, "
                        f"target L={target.lightness:.2f}, "
                        f"T={target.temperature:.2f}, "
                        f"S={target.saturation:.2f}")
            return target
        except Exception as e:
            ctx = f" for {context}" if context else ""
            logger.warning(f"Failed to get time target{ctx}: {e}")
            return None

    def select(
        self,
        candidates: List['ImageRecord'],
        count: int,
        constraints: Optional['SelectionConstraints'] = None,
    ) -> List[str]:
        """Select images using weighted random selection.

        Args:
            candidates: List of candidate ImageRecord objects.
            count: Number of images to select.
            constraints: Optional SelectionConstraints for weight calculation.

        Returns:
            List of selected file paths.
        """
        if not candidates:
            return []

        # If disabled, use uniform random
        if not self.config.enabled:
            selected = random.sample(candidates, min(count, len(candidates)))
            return [img.filepath for img in selected]

        # Extract target palette from constraints for color affinity
        target_palette = constraints.target_palette if constraints else None

        # Batch-load all source records for candidates to avoid N+1 queries
        source_ids = list(set(img.source_id for img in candidates if img.source_id))
        sources = self.db.get_sources_by_ids(source_ids) if source_ids else {}

        # Batch-load palettes if color constraints or time adaptation is active
        palettes: Dict[str, 'PaletteRecord'] = {}
        needs_palettes = (
            (target_palette and self.config.color_match_weight) or
            (self._time_adapter and self.config.time_adaptation_enabled)
        )
        if needs_palettes:
            filepaths = [img.filepath for img in candidates]
            palettes = self.db.get_palettes_by_filepaths(filepaths)

        # Calculate weights for each candidate
        weights = self._calculate_weights(
            candidates, sources, palettes, target_palette, constraints
        )

        # Weighted random selection without replacement
        return self._weighted_selection(candidates, weights, count)

    def _calculate_weights(
        self,
        candidates: List['ImageRecord'],
        sources: Dict[str, Any],
        palettes: Dict[str, 'PaletteRecord'],
        target_palette: Optional[Dict[str, Any]],
        constraints: Optional['SelectionConstraints'],
    ) -> List[float]:
        """Calculate weights for all candidates.

        Args:
            candidates: List of candidate ImageRecord objects.
            sources: Dict mapping source_id to SourceRecord.
            palettes: Dict mapping filepath to PaletteRecord.
            target_palette: Optional target palette for color affinity.
            constraints: Optional SelectionConstraints.

        Returns:
            List of weights corresponding to candidates.
        """
        time_target = self._get_time_target("selection")

        weights = []
        for img in candidates:
            source_last_shown = None
            if img.source_id and img.source_id in sources:
                source_last_shown = sources[img.source_id].last_shown_at

            # Get image palette for color affinity calculation
            image_palette = palettes.get(img.filepath) if palettes else None

            weight = calculate_weight(
                img, source_last_shown, self.config,
                image_palette=image_palette,
                target_palette=target_palette,
                constraints=constraints,
                time_target_lightness=time_target.lightness if time_target else None,
                time_target_temperature=time_target.temperature if time_target else None,
                time_target_saturation=time_target.saturation if time_target else None,
            )
            weights.append(weight)

        return weights

    def _weighted_selection(
        self,
        candidates: List['ImageRecord'],
        weights: List[float],
        count: int,
    ) -> List[str]:
        """Perform weighted random selection without replacement.

        Uses A-ES (Algorithm-ES) weighted reservoir sampling for O(n + k·log k)
        time complexity, where n is number of candidates and k is count.

        Algorithm: For each item, compute a random key as log(random())/weight.
        Items with higher weights get higher expected keys. Use a min-heap to
        keep the k items with the highest keys efficiently.

        This replaces the previous O(n·k) algorithm that rebuilt cumulative
        weights for each selection.

        Args:
            candidates: List of candidate ImageRecord objects.
            weights: List of weights corresponding to candidates.
            count: Number of images to select.

        Returns:
            List of selected file paths.
        """
        if not candidates:
            return []

        k = min(count, len(candidates))

        # Check if all weights are zero - fall back to uniform sampling
        total_weight = sum(weights)
        if total_weight <= 0:
            selected = random.sample(candidates, k)
            return [img.filepath for img in selected]

        # A-ES weighted reservoir sampling using min-heap
        # Key = log(random()) / weight - higher weight = higher expected key
        # We keep the k highest keys using a min-heap (heapq)
        heap: List[tuple] = []  # (key, index) tuples

        for i, (img, weight) in enumerate(zip(candidates, weights)):
            if weight <= 0:
                # Zero-weight items get -inf key, will never be selected
                key = float('-inf')
            else:
                # log(U) / w where U ~ Uniform(0,1)
                # This gives weighted sampling without replacement
                r = random.random()
                if r > 0:
                    key = math.log(r) / weight
                else:
                    key = float('-inf')

            if len(heap) < k:
                heapq.heappush(heap, (key, i))
            elif key > heap[0][0]:
                # This key is higher than the smallest in our top-k
                heapq.heapreplace(heap, (key, i))

        # Extract selected candidates (heap gives us indices)
        selected_indices = [idx for _, idx in heap]
        return [candidates[idx].filepath for idx in selected_indices]

    def score_candidates(
        self,
        candidates: List['ImageRecord'],
        constraints: Optional['SelectionConstraints'] = None,
    ) -> List[ScoredCandidate]:
        """Score all candidates and return with weights.

        Useful for preview displays showing candidate weights.
        Includes time-based adaptation when enabled.

        Args:
            candidates: List of candidate ImageRecord objects.
            constraints: Optional SelectionConstraints for weight calculation.

        Returns:
            List of ScoredCandidate objects sorted by weight (descending).
        """
        if not candidates:
            return []

        # Extract target palette from constraints for color affinity
        target_palette = constraints.target_palette if constraints else None

        # Batch-load all source records
        source_ids = list(set(img.source_id for img in candidates if img.source_id))
        sources = self.db.get_sources_by_ids(source_ids) if source_ids else {}

        # Batch-load palettes if color constraints or time adaptation is active
        palettes: Dict[str, 'PaletteRecord'] = {}
        needs_palettes = (
            (target_palette and self.config.color_match_weight) or
            (self._time_adapter and self.config.time_adaptation_enabled)
        )
        if needs_palettes:
            filepaths = [img.filepath for img in candidates]
            palettes = self.db.get_palettes_by_filepaths(filepaths)

        time_target = self._get_time_target("scoring")

        # Calculate weights and create ScoredCandidate objects
        scored = []
        for img in candidates:
            source_last_shown = None
            if img.source_id and img.source_id in sources:
                source_last_shown = sources[img.source_id].last_shown_at

            image_palette = palettes.get(img.filepath) if palettes else None

            weight = calculate_weight(
                img, source_last_shown, self.config,
                image_palette=image_palette,
                target_palette=target_palette,
                constraints=constraints,
                time_target_lightness=time_target.lightness if time_target else None,
                time_target_temperature=time_target.temperature if time_target else None,
                time_target_saturation=time_target.saturation if time_target else None,
            )
            scored.append(ScoredCandidate(image=img, weight=weight))

        # Sort by weight (highest first)
        scored.sort(key=lambda x: x.weight, reverse=True)

        return scored
