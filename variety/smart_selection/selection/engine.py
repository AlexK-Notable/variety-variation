# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Weighted random selection algorithm.

Provides the core selection algorithm using weighted random selection
with O(log n) binary search for efficiency.
"""

import bisect
import random
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from variety.smart_selection.weights import calculate_weight

if TYPE_CHECKING:
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.models import ImageRecord, SelectionConstraints, PaletteRecord
    from variety.smart_selection.config import SelectionConfig


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

        # Batch-load palettes if color constraints are active
        palettes: Dict[str, 'PaletteRecord'] = {}
        if target_palette and self.config.color_match_weight:
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

        Uses cumulative weights with binary search for O(log n) lookups.

        Args:
            candidates: List of candidate ImageRecord objects.
            weights: List of weights corresponding to candidates.
            count: Number of images to select.

        Returns:
            List of selected file paths.
        """
        selected = []
        remaining_candidates = list(candidates)
        remaining_weights = list(weights)

        for _ in range(min(count, len(candidates))):
            if not remaining_candidates:
                break

            # Build cumulative weights for binary search
            total_weight = sum(remaining_weights)
            if total_weight <= 0:
                # All weights are zero, fall back to uniform
                idx = random.randrange(len(remaining_candidates))
            else:
                # Build cumulative sum for bisect
                cumulative_weights = []
                cumsum = 0.0
                for w in remaining_weights:
                    cumsum += w
                    cumulative_weights.append(cumsum)

                # Weighted random choice using binary search (O(log n))
                r = random.uniform(0, total_weight)
                idx = bisect.bisect_left(cumulative_weights, r)

                # Clamp to valid range (handles float precision edge cases)
                idx = min(idx, len(remaining_candidates) - 1)

            selected.append(remaining_candidates[idx])
            remaining_candidates.pop(idx)
            remaining_weights.pop(idx)

        return [img.filepath for img in selected]

    def score_candidates(
        self,
        candidates: List['ImageRecord'],
        constraints: Optional['SelectionConstraints'] = None,
    ) -> List[ScoredCandidate]:
        """Score all candidates and return with weights.

        Useful for preview displays showing candidate weights.

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

        # Batch-load palettes if color constraints are active
        palettes: Dict[str, 'PaletteRecord'] = {}
        if target_palette and self.config.color_match_weight:
            filepaths = [img.filepath for img in candidates]
            palettes = self.db.get_palettes_by_filepaths(filepaths)

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
            )
            scored.append(ScoredCandidate(image=img, weight=weight))

        # Sort by weight (highest first)
        scored.sort(key=lambda x: x.weight, reverse=True)

        return scored
