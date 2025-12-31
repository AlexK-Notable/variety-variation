# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Color and dimension constraint filtering.

Provides filtering logic for applying color and dimension constraints
to candidate images.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from variety.smart_selection.palette import palette_similarity

if TYPE_CHECKING:
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.models import ImageRecord, SelectionConstraints, PaletteRecord

logger = logging.getLogger(__name__)


@dataclass
class ColorConstraints:
    """Color-based constraints for filtering images.

    Attributes:
        target_palette: Target palette for color similarity matching.
        min_lightness: Minimum average lightness (0-1).
        max_lightness: Maximum average lightness (0-1).
        min_saturation: Minimum average saturation (0-1).
        max_saturation: Maximum average saturation (0-1).
        temperature: Target color temperature (-1=cool, +1=warm).
        similarity_threshold: Minimum color similarity (0-1).
    """
    target_palette: Optional[Dict[str, Any]] = None
    min_lightness: Optional[float] = None
    max_lightness: Optional[float] = None
    min_saturation: Optional[float] = None
    max_saturation: Optional[float] = None
    temperature: Optional[float] = None
    similarity_threshold: float = 0.5


class ConstraintApplier:
    """Applies constraints to filter candidate images.

    Filters images based on color similarity, lightness, saturation,
    temperature, and dimension constraints.
    """

    def __init__(self, db: 'ImageDatabase'):
        """Initialize the constraint applier.

        Args:
            db: ImageDatabase instance for palette lookups.
        """
        self.db = db

    def apply(
        self,
        candidates: List['ImageRecord'],
        constraints: Optional['SelectionConstraints'],
    ) -> List['ImageRecord']:
        """Apply constraints to filter candidate images.

        Args:
            candidates: List of candidate ImageRecord objects.
            constraints: SelectionConstraints to apply, or None for no filtering.

        Returns:
            Filtered list of ImageRecord objects.
        """
        if not constraints:
            return candidates

        # Batch-load palettes if color filtering is active
        palettes: Dict[str, 'PaletteRecord'] = {}
        if constraints.target_palette:
            filepaths = [img.filepath for img in candidates]
            palettes = self.db.get_palettes_by_filepaths(filepaths)

        # Apply constraint filters
        filtered = []
        for img in candidates:
            if not self._passes_dimension_constraints(img, constraints):
                continue

            if not self._passes_favorites_constraint(img, constraints):
                continue

            if not self._passes_color_constraints(img, constraints, palettes):
                continue

            filtered.append(img)

        # Log color filtering results
        if constraints.target_palette:
            before_count = len(candidates)
            after_count = len(filtered)
            excluded = before_count - after_count
            threshold = constraints.min_color_similarity or 0.5
            logger.debug(
                f"Color filter: {after_count}/{before_count} candidates passed "
                f"(excluded {excluded}, threshold={threshold:.0%})"
            )

        return filtered

    def _passes_dimension_constraints(
        self,
        img: 'ImageRecord',
        constraints: 'SelectionConstraints',
    ) -> bool:
        """Check if image passes dimension constraints.

        Args:
            img: ImageRecord to check.
            constraints: SelectionConstraints with dimension limits.

        Returns:
            True if image passes all dimension constraints.
        """
        # Min width
        if constraints.min_width and img.width:
            if img.width < constraints.min_width:
                return False

        # Min height
        if constraints.min_height and img.height:
            if img.height < constraints.min_height:
                return False

        # Aspect ratio range
        if img.aspect_ratio:
            if constraints.min_aspect_ratio:
                if img.aspect_ratio < constraints.min_aspect_ratio:
                    return False
            if constraints.max_aspect_ratio:
                if img.aspect_ratio > constraints.max_aspect_ratio:
                    return False

        return True

    def _passes_favorites_constraint(
        self,
        img: 'ImageRecord',
        constraints: 'SelectionConstraints',
    ) -> bool:
        """Check if image passes favorites constraint.

        Args:
            img: ImageRecord to check.
            constraints: SelectionConstraints with favorites_only flag.

        Returns:
            True if image passes favorites constraint.
        """
        if constraints.favorites_only and not img.is_favorite:
            return False
        return True

    def _passes_color_constraints(
        self,
        img: 'ImageRecord',
        constraints: 'SelectionConstraints',
        palettes: Dict[str, 'PaletteRecord'],
    ) -> bool:
        """Check if image passes color similarity constraints.

        Args:
            img: ImageRecord to check.
            constraints: SelectionConstraints with color settings.
            palettes: Dict mapping filepaths to PaletteRecord.

        Returns:
            True if image passes color constraints.
        """
        if not constraints.target_palette:
            return True

        # Get image's palette from batch-loaded dict
        palette_record = palettes.get(img.filepath)
        if not palette_record:
            # No palette data - exclude when color filtering
            return False

        # Convert palette record to dict for similarity calculation
        img_palette = {
            'avg_hue': palette_record.avg_hue,
            'avg_saturation': palette_record.avg_saturation,
            'avg_lightness': palette_record.avg_lightness,
            'color_temperature': palette_record.color_temperature,
        }

        # Calculate similarity
        similarity = palette_similarity(constraints.target_palette, img_palette)

        # Check threshold (default 0.5 if not specified)
        min_similarity = constraints.min_color_similarity or 0.5
        if similarity < min_similarity:
            return False

        return True
