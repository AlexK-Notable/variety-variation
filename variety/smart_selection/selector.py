# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Smart wallpaper selection orchestrator.

Provides weighted selection based on recency, source rotation,
favorites boost, and optional constraints.
"""

import bisect
import os
import random
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable, TYPE_CHECKING

from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.config import SelectionConfig
from variety.smart_selection.models import ImageRecord, SelectionConstraints
from variety.smart_selection.weights import calculate_weight
from variety.smart_selection.palette import (
    PaletteExtractor,
    create_palette_record,
    palette_similarity,
)

if TYPE_CHECKING:
    from variety.smart_selection.statistics import CollectionStatistics

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
        self._statistics: Optional['CollectionStatistics'] = None
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
        # Use cumulative weights with binary search for O(log n) lookups
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

        # Always filter out non-existent files (phantom index protection)
        candidates = [img for img in candidates if os.path.exists(img.filepath)]

        if not constraints:
            return candidates

        # Apply constraint filters
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

        If the image is not in the database, it will be indexed first.

        Updates the image's last_shown_at, times_shown, and
        optionally stores the wallust palette.

        Args:
            filepath: Path to the image that was shown.
            wallust_palette: Optional pre-extracted wallust color palette dict.
                            If None and palette extraction is enabled, will extract automatically.
        """
        # Check if image exists in database, if not index it first
        existing = self.db.get_image(filepath)
        if not existing and os.path.exists(filepath):
            from variety.smart_selection.indexer import ImageIndexer
            indexer = ImageIndexer(self.db)
            record = indexer.index_image(filepath)
            if record:
                self.db.upsert_image(record)
                logger.debug(f"Smart Selection: Indexed new image on show: {filepath}")

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

        # Invalidate statistics cache
        if self._statistics:
            self._statistics.invalidate()

    # =========================================================================
    # Statistics and Management Methods
    # =========================================================================

    def get_statistics_analyzer(self) -> 'CollectionStatistics':
        """Get the collection statistics analyzer (lazy initialization).

        Returns:
            CollectionStatistics instance for analyzing collection distributions.
        """
        if self._statistics is None:
            from variety.smart_selection.statistics import CollectionStatistics
            self._statistics = CollectionStatistics(self.db)
        return self._statistics

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics for preferences display.

        Returns:
            Dictionary with selection statistics:
            - images_indexed: Total number of indexed images
            - sources_count: Number of sources
            - images_with_palettes: Images with extracted color palettes
            - total_selections: Total times any image has been shown
            - unique_shown: Number of unique images shown at least once
        """
        return {
            'images_indexed': self.db.count_images(),
            'sources_count': self.db.count_sources(),
            'images_with_palettes': self.db.count_images_with_palettes(),
            'total_selections': self.db.sum_times_shown(),
            'unique_shown': self.db.count_shown_images(),
        }

    def clear_history(self):
        """Clear selection history (reset times_shown and last_shown_at).

        This keeps all indexed images but resets their selection tracking,
        giving all images an equal chance of being selected again.
        """
        self.db.clear_history()
        logger.info("Cleared selection history")

        # Invalidate statistics cache (freshness distribution changes)
        if self._statistics:
            self._statistics.invalidate()

    def rebuild_index(self, source_folders: List[str] = None,
                      favorites_folder: str = None,
                      progress_callback: Callable[[int, int], None] = None):
        """Rebuild the image index from scratch.

        Clears all existing index data and re-scans source folders.
        Creates a backup of the database before clearing.

        Args:
            source_folders: List of folder paths to index.
                           If None, clears index without re-populating.
            favorites_folder: Path to favorites folder for marking favorites.
            progress_callback: Optional callback(current, total) for progress updates.
        """
        from variety.smart_selection.indexer import ImageIndexer

        # Backup before destructive operation
        backup_path = self.db.db_path + '.backup'
        if self.db.backup(backup_path):
            logger.info(f"Created database backup at {backup_path}")
        else:
            logger.warning("Failed to create database backup before rebuild")

        self.db.delete_all_images()
        logger.info("Cleared image index")

        if source_folders:
            indexer = ImageIndexer(self.db, favorites_folder=favorites_folder)
            total = len(source_folders)
            for i, folder in enumerate(source_folders):
                if progress_callback:
                    progress_callback(i, total)
                try:
                    indexer.index_directory(folder, recursive=True)
                except Exception as e:
                    logger.warning(f"Failed to index folder {folder}: {e}")
            if progress_callback:
                progress_callback(total, total)
            logger.info(f"Rebuilt index with {self.db.count_images()} images")

        # Invalidate statistics cache
        if self._statistics:
            self._statistics.invalidate()

    def extract_all_palettes(self, progress_callback: Callable[[int, int], None] = None):
        """Extract color palettes for all indexed images without palettes.

        Uses wallust to extract color palettes for images that don't have
        palette data yet.

        Args:
            progress_callback: Optional callback(current, total) for progress updates.

        Returns:
            Number of palettes extracted.
        """
        if not self._palette_extractor:
            self._palette_extractor = PaletteExtractor()

        if not self._palette_extractor.is_wallust_available():
            logger.warning("wallust is not available for palette extraction")
            return 0

        images = self.db.get_images_without_palettes()
        total = len(images)
        extracted = 0

        for i, image in enumerate(images):
            if progress_callback:
                progress_callback(i, total)

            try:
                palette_data = self._palette_extractor.extract_palette(image.filepath)
                if palette_data:
                    palette_record = create_palette_record(image.filepath, palette_data)
                    self.db.upsert_palette(palette_record)
                    extracted += 1
            except Exception as e:
                logger.warning(f"Failed to extract palette for {image.filepath}: {e}")

        if progress_callback:
            progress_callback(total, total)

        logger.info(f"Extracted {extracted} palettes out of {total} images")

        # Invalidate statistics cache (color distributions change)
        if extracted > 0 and self._statistics:
            self._statistics.invalidate()

        return extracted

    # =========================================================================
    # Time-Based Selection Methods
    # =========================================================================

    def get_time_based_temperature(self) -> float:
        """Get target color temperature based on current time.

        Returns a value indicating preferred color temperature:
        - Lower values (0.3) = cool/bright (morning)
        - 0.5 = neutral (afternoon)
        - Higher values (0.7) = warm/cozy (evening)
        - 0.4 = neutral-dark (night)

        Returns:
            Target color temperature value between 0.0 and 1.0.
        """
        hour = datetime.now().hour

        if 6 <= hour < 12:      # Morning
            return 0.3  # Cool/bright
        elif 12 <= hour < 18:   # Afternoon
            return 0.5  # Neutral
        elif 18 <= hour < 22:   # Evening
            return 0.7  # Warm/cozy
        else:                   # Night (22-6)
            return 0.4  # Neutral-dark

    def get_time_period(self) -> str:
        """Get the current time period name.

        Returns:
            One of: 'morning', 'afternoon', 'evening', 'night'
        """
        hour = datetime.now().hour

        if 6 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 18:
            return 'afternoon'
        elif 18 <= hour < 22:
            return 'evening'
        else:
            return 'night'

    # =========================================================================
    # Preview Methods
    # =========================================================================

    def get_preview_candidates(
        self,
        count: int = 20,
        constraints: Optional[SelectionConstraints] = None,
    ) -> List[Dict[str, Any]]:
        """Get preview candidates with their calculated weights.

        Returns top candidates sorted by weight for preview display.
        Each result includes the image path and its calculated weight.

        Args:
            count: Maximum number of candidates to return.
            constraints: Optional filtering constraints.

        Returns:
            List of dicts with keys:
            - filepath: Path to the image
            - filename: Image filename
            - weight: Calculated selection weight (0.0-1.0 normalized)
            - is_favorite: Whether image is marked as favorite
            - times_shown: Number of times image has been shown
            - source_id: Source identifier
        """
        candidates = self._get_candidates(constraints)

        if not candidates:
            return []

        # Calculate weights for each candidate
        weighted_candidates = []
        for img in candidates:
            source_last_shown = None
            if img.source_id:
                source = self.db.get_source(img.source_id)
                if source:
                    source_last_shown = source.last_shown_at

            weight = calculate_weight(img, source_last_shown, self.config)
            weighted_candidates.append({
                'filepath': img.filepath,
                'filename': img.filename,
                'weight': weight,
                'is_favorite': img.is_favorite,
                'times_shown': img.times_shown,
                'source_id': img.source_id,
            })

        # Sort by weight (highest first) and take top N
        weighted_candidates.sort(key=lambda x: x['weight'], reverse=True)
        top_candidates = weighted_candidates[:count]

        # Normalize weights to 0-1 range for display
        if top_candidates:
            max_weight = max(c['weight'] for c in top_candidates)
            if max_weight > 0:
                for c in top_candidates:
                    c['normalized_weight'] = c['weight'] / max_weight
            else:
                for c in top_candidates:
                    c['normalized_weight'] = 1.0

        return top_candidates

    # =========================================================================
    # Database Maintenance Methods
    # =========================================================================

    def vacuum_database(self) -> bool:
        """Optimize and compact the database.

        Reclaims space from deleted records and optimizes storage.
        Should be called periodically for long-running installations.

        Returns:
            True if vacuum succeeded, False otherwise.
        """
        if self.db.vacuum():
            logger.info("Database vacuum completed successfully")
            return True
        else:
            logger.warning("Database vacuum failed")
            return False

    def verify_index(self) -> Dict[str, Any]:
        """Verify database integrity and check for issues.

        Checks for:
        - SQLite integrity errors
        - Orphaned palette records (no matching image)
        - Missing files (indexed but no longer on disk)

        Returns:
            Dictionary with verification results:
            - is_valid: Overall integrity status
            - integrity_result: SQLite integrity check result
            - orphaned_palettes: Number of orphaned palette records
            - missing_files: Number of indexed files not on disk
            - total_images: Total indexed images
            - total_palettes: Total palette records
        """
        return self.db.verify_integrity()

    def cleanup_index(self, remove_orphans: bool = True,
                      remove_missing: bool = True) -> Dict[str, int]:
        """Clean up the index by removing invalid entries.

        Args:
            remove_orphans: If True, remove orphaned palette records.
            remove_missing: If True, remove entries for files that no longer exist.

        Returns:
            Dictionary with cleanup results:
            - orphans_removed: Number of orphaned palettes removed
            - missing_removed: Number of missing file entries removed
        """
        results = {'orphans_removed': 0, 'missing_removed': 0}

        if remove_orphans:
            count = self.db.cleanup_orphans()
            results['orphans_removed'] = count
            if count > 0:
                logger.info(f"Removed {count} orphaned palette records")

        if remove_missing:
            count = self.db.remove_missing_files()
            results['missing_removed'] = count
            if count > 0:
                logger.info(f"Removed {count} entries for missing files")

        return results

    def backup_database(self, backup_path: str = None) -> bool:
        """Create a backup of the database.

        Args:
            backup_path: Path for backup file. If None, uses db_path + '.backup'.

        Returns:
            True if backup succeeded, False otherwise.
        """
        if backup_path is None:
            backup_path = self.db.db_path + '.backup'

        if self.db.backup(backup_path):
            logger.info(f"Database backup created at {backup_path}")
            return True
        else:
            logger.warning(f"Failed to create database backup at {backup_path}")
            return False
