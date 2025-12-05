# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Smart wallpaper selection orchestrator.

Provides weighted selection based on recency, source rotation,
favorites boost, and optional constraints.
"""

import random
import logging
from typing import List, Optional, Dict, Any

from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.config import SelectionConfig
from variety.smart_selection.models import ImageRecord, SelectionConstraints
from variety.smart_selection.weights import calculate_weight
from variety.smart_selection.palette import (
    PaletteExtractor,
    create_palette_record,
    palette_similarity,
)

logger = logging.getLogger(__name__)


class SmartSelector:
    """Orchestrates intelligent wallpaper selection.

    Uses weighted random selection based on:
    - Image recency (recently shown images have lower weight)
    - Source rotation (balance across wallpaper sources)
    - Favorites boost
    - New image boost (never-shown images)
    - Optional constraints (dimensions, favorites only, sources)
    """

    def __init__(self, db_path: str, config: SelectionConfig,
                 enable_palette_extraction: bool = False):
        """Initialize the smart selector.

        Args:
            db_path: Path to SQLite database file.
            config: SelectionConfig with weight parameters.
            enable_palette_extraction: If True, extract color palettes when images are shown.
        """
        self.db = ImageDatabase(db_path)
        self.config = config
        self._owns_db = True
        self._enable_palette_extraction = enable_palette_extraction
        self._palette_extractor = None
        if enable_palette_extraction:
            self._palette_extractor = PaletteExtractor()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close database."""
        self.close()
        return False

    def close(self):
        """Close the database connection."""
        if self._owns_db and self.db:
            self.db.close()
            self.db = None

    def select_images(
        self,
        count: int,
        constraints: Optional[SelectionConstraints] = None,
    ) -> List[str]:
        """Select images using weighted random selection.

        Args:
            count: Number of images to select.
            constraints: Optional filtering constraints.

        Returns:
            List of file paths for selected images.
        """
        # Get candidate images
        candidates = self._get_candidates(constraints)

        if not candidates:
            return []

        # If disabled, use uniform random
        if not self.config.enabled:
            selected = random.sample(candidates, min(count, len(candidates)))
            return [img.filepath for img in selected]

        # Calculate weights for each candidate
        weights = []
        for img in candidates:
            source_last_shown = None
            if img.source_id:
                source = self.db.get_source(img.source_id)
                if source:
                    source_last_shown = source.last_shown_at

            weight = calculate_weight(img, source_last_shown, self.config)
            weights.append(weight)

        # Weighted random selection without replacement
        selected = []
        remaining_candidates = list(candidates)
        remaining_weights = list(weights)

        for _ in range(min(count, len(candidates))):
            if not remaining_candidates:
                break

            # Normalize weights
            total_weight = sum(remaining_weights)
            if total_weight <= 0:
                # All weights are zero, fall back to uniform
                idx = random.randrange(len(remaining_candidates))
            else:
                # Weighted random choice
                r = random.uniform(0, total_weight)
                cumulative = 0
                idx = 0
                for i, w in enumerate(remaining_weights):
                    cumulative += w
                    if r <= cumulative:
                        idx = i
                        break

            selected.append(remaining_candidates[idx])
            remaining_candidates.pop(idx)
            remaining_weights.pop(idx)

        return [img.filepath for img in selected]

    def _get_candidates(
        self,
        constraints: Optional[SelectionConstraints],
    ) -> List[ImageRecord]:
        """Get candidate images matching constraints.

        Args:
            constraints: Optional filtering constraints.

        Returns:
            List of ImageRecord objects matching constraints.
        """
        # Start with all images or filtered by source
        if constraints and constraints.sources:
            candidates = []
            for source_id in constraints.sources:
                candidates.extend(self.db.get_images_by_source(source_id))
        elif constraints and constraints.favorites_only:
            candidates = self.db.get_favorite_images()
        else:
            candidates = self.db.get_all_images()

        if not constraints:
            return candidates

        # Apply filters
        filtered = []
        for img in candidates:
            # Min width
            if constraints.min_width and img.width:
                if img.width < constraints.min_width:
                    continue

            # Min height
            if constraints.min_height and img.height:
                if img.height < constraints.min_height:
                    continue

            # Aspect ratio range
            if img.aspect_ratio:
                if constraints.min_aspect_ratio:
                    if img.aspect_ratio < constraints.min_aspect_ratio:
                        continue
                if constraints.max_aspect_ratio:
                    if img.aspect_ratio > constraints.max_aspect_ratio:
                        continue

            # Favorites only (already handled above, but double-check)
            if constraints.favorites_only and not img.is_favorite:
                continue

            # Color similarity filter
            if constraints.target_palette:
                # Get image's palette
                palette_record = self.db.get_palette(img.filepath)
                if not palette_record:
                    # No palette data - exclude when color filtering
                    continue

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
                    continue

            filtered.append(img)

        return filtered

    def record_shown(self, filepath: str, wallust_palette: Dict[str, Any] = None):
        """Record that an image was shown.

        Updates the image's last_shown_at, times_shown, and
        optionally stores the wallust palette.

        Args:
            filepath: Path to the image that was shown.
            wallust_palette: Optional pre-extracted wallust color palette dict.
                            If None and palette extraction is enabled, will extract automatically.
        """
        # Update image record
        self.db.record_image_shown(filepath)

        # Update source record
        image = self.db.get_image(filepath)
        if image and image.source_id:
            self.db.record_source_shown(image.source_id)

        # Store wallust palette if provided or extract if enabled
        palette_data = wallust_palette
        if palette_data is None and self._enable_palette_extraction and self._palette_extractor:
            if self._palette_extractor.is_wallust_available():
                palette_data = self._palette_extractor.extract_palette(filepath)

        if palette_data:
            try:
                palette_record = create_palette_record(filepath, palette_data)
                self.db.upsert_palette(palette_record)
                logger.debug(f"Stored palette for {filepath}")
            except Exception as e:
                logger.warning(f"Failed to store palette for {filepath}: {e}")
