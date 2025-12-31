# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Smart wallpaper selection orchestrator.

Provides weighted selection based on recency, source rotation,
favorites boost, and optional constraints.

This is a facade that orchestrates the selection components:
- CandidateProvider: Database queries for candidate images
- ConstraintApplier: Color and dimension filtering
- SelectionEngine: Weighted random selection algorithm
"""

import heapq
import math
import os
import random
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable, Set, TYPE_CHECKING

from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.config import SelectionConfig
from variety.smart_selection.models import ImageRecord, SelectionConstraints
from variety.smart_selection.palette import (
    PaletteExtractor,
    create_palette_record,
)
from variety.smart_selection.weights import calculate_weight
from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
from variety.smart_selection.selection.constraints import ConstraintApplier
from variety.smart_selection.selection.engine import SelectionEngine

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

    This class is a facade that delegates to focused components:
    - CandidateProvider for database queries
    - ConstraintApplier for filtering
    - SelectionEngine for weighted selection
    """

    def __init__(self, db_path: str, config: SelectionConfig,
                 enable_palette_extraction: bool = False):
        """Initialize the smart selector.

        Args:
            db_path: Path to SQLite database file.
            config: SelectionConfig with weight parameters.
            enable_palette_extraction: If True, extract color palettes when images are shown.

        Raises:
            Exception: If initialization fails. Database is closed on failure.
        """
        self.db = ImageDatabase(db_path)
        self._owns_db = True

        try:
            self.config = config
            self._enable_palette_extraction = enable_palette_extraction
            self._palette_extractor = None
            self._statistics: Optional['CollectionStatistics'] = None

            # Initialize selection components
            self._candidate_provider = CandidateProvider(self.db)
            self._constraint_applier = ConstraintApplier(self.db)
            self._selection_engine = SelectionEngine(self.db, config)

            if enable_palette_extraction:
                self._palette_extractor = PaletteExtractor()
        except Exception:
            # Clean up database on any initialization failure
            self.db.close()
            self.db = None
            raise

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
        # Get candidate images using the component pipeline
        candidates = self._get_candidates(constraints)

        if not candidates:
            return []

        # Delegate selection to SelectionEngine
        return self._selection_engine.select(candidates, count, constraints)

    def select_images_streaming(
        self,
        count: int,
        batch_size: int = 1000,
        constraints: Optional[SelectionConstraints] = None,
    ) -> List[str]:
        """Select images using streaming weighted reservoir sampling.

        Memory-efficient alternative to select_images() for large collections.
        Uses weighted reservoir sampling to select without loading all
        candidates into memory.

        Algorithm: Weighted Reservoir Sampling (A-ES algorithm)
        - Assign each item a key: random()^(1/weight)
        - Keep the top-k items by key

        Time Complexity: O(n log k) where n = total candidates, k = count
        Space Complexity: O(k + batch_size) instead of O(n)

        Args:
            count: Number of images to select.
            batch_size: Number of records to fetch per database batch.
            constraints: Optional filtering constraints.

        Returns:
            List of file paths for selected images.
        """
        # Reservoir: min-heap of (key, filepath) tuples
        reservoir: List[tuple] = []

        # Track source records for weight calculation (lazy loading)
        sources_cache: Dict[str, Any] = {}
        palettes_cache: Dict[str, Any] = {}

        # Extract target palette from constraints
        target_palette = constraints.target_palette if constraints else None
        use_color_matching = target_palette and self.config.color_match_weight

        # Determine source filter for cursor
        source_filter = None
        if constraints and constraints.sources and len(constraints.sources) == 1:
            source_filter = constraints.sources[0]

        # If favorites_only, we can't use cursor efficiently - fall back to batch
        if constraints and constraints.favorites_only:
            return self.select_images(count, constraints)

        # If multiple sources specified, fall back to batch method
        if constraints and constraints.sources and len(constraints.sources) > 1:
            return self.select_images(count, constraints)

        for batch in self.db.get_images_cursor(batch_size=batch_size, source_id=source_filter):
            # Filter batch for file existence and constraints
            filtered_batch = self._filter_batch(batch, constraints)

            if not filtered_batch:
                continue

            # Batch-load sources for weight calculation
            batch_source_ids = list(set(
                img.source_id for img in filtered_batch
                if img.source_id and img.source_id not in sources_cache
            ))
            if batch_source_ids:
                new_sources = self.db.get_sources_by_ids(batch_source_ids)
                sources_cache.update(new_sources)

            # Batch-load palettes if color matching is active
            if use_color_matching:
                batch_filepaths = [
                    img.filepath for img in filtered_batch
                    if img.filepath not in palettes_cache
                ]
                if batch_filepaths:
                    new_palettes = self.db.get_palettes_by_filepaths(batch_filepaths)
                    palettes_cache.update(new_palettes)

            # Process each image in batch
            for img in filtered_batch:
                # Calculate weight
                source_last_shown = None
                if img.source_id and img.source_id in sources_cache:
                    source_last_shown = sources_cache[img.source_id].last_shown_at

                image_palette = palettes_cache.get(img.filepath) if use_color_matching else None

                if self.config.enabled:
                    weight = calculate_weight(
                        img, source_last_shown, self.config,
                        image_palette=image_palette,
                        target_palette=target_palette,
                        constraints=constraints,
                    )
                else:
                    weight = 1.0

                # Weighted reservoir sampling key: random()^(1/weight)
                # Using log transform for numerical stability: log(random()) / weight
                r = random.random()
                if r > 0 and weight > 0:
                    key = math.log(r) / weight
                else:
                    key = float('-inf')

                if len(reservoir) < count:
                    heapq.heappush(reservoir, (key, img.filepath))
                elif key > reservoir[0][0]:
                    heapq.heapreplace(reservoir, (key, img.filepath))

        return [filepath for _, filepath in reservoir]

    def _filter_batch(
        self,
        batch: List[ImageRecord],
        constraints: Optional[SelectionConstraints],
    ) -> List[ImageRecord]:
        """Filter a batch of images for existence and constraints.

        Args:
            batch: List of ImageRecords to filter.
            constraints: Optional filtering constraints.

        Returns:
            Filtered list of ImageRecords.
        """
        # Filter out non-existent files
        filtered = [img for img in batch if os.path.exists(img.filepath)]

        if not constraints:
            return filtered

        # Use ConstraintApplier for dimension and color filtering
        return self._constraint_applier.apply(filtered, constraints)

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
        # Build query from constraints
        query = CandidateQuery.from_constraints(constraints)

        # Get candidates from database (with file existence check)
        candidates = self._candidate_provider.get_candidates(query)

        # Apply constraint filters (dimensions, colors, etc.)
        return self._constraint_applier.apply(candidates, constraints)

    def record_shown(self, filepath: str, wallust_palette: Dict[str, Any] = None):
        """Record that an image was shown.

        If the image is not in the database, it will be indexed first.

        Args:
            filepath: Path to the image that was shown.
            wallust_palette: Optional pre-extracted wallust color palette dict.
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
        """Get the collection statistics analyzer (lazy initialization)."""
        if self._statistics is None:
            from variety.smart_selection.statistics import CollectionStatistics
            self._statistics = CollectionStatistics(self.db)
        return self._statistics

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics for preferences display."""
        return {
            'images_indexed': self.db.count_images(),
            'sources_count': self.db.count_sources(),
            'images_with_palettes': self.db.count_images_with_palettes(),
            'total_selections': self.db.sum_times_shown(),
            'unique_shown': self.db.count_shown_images(),
        }

    def clear_history(self):
        """Clear selection history (reset times_shown and last_shown_at)."""
        self.db.clear_history()
        logger.info("Cleared selection history")

        if self._statistics:
            self._statistics.invalidate()

    def rebuild_index(self, source_folders: List[str] = None,
                      favorites_folder: str = None,
                      progress_callback: Callable[[int, int], None] = None):
        """Rebuild the image index from scratch."""
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

        if self._statistics:
            self._statistics.invalidate()

    def extract_all_palettes(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        batch_size: int = 500,
    ) -> int:
        """Extract palettes for all images that don't have them."""
        if not self._palette_extractor:
            self._palette_extractor = PaletteExtractor()

        if not self._palette_extractor.is_wallust_available():
            logger.warning("wallust is not available for palette extraction")
            return 0

        extracted_count = 0
        failed_files: Set[str] = set()

        while True:
            images = self.db.get_images_without_palettes(limit=batch_size, offset=0)
            images = [img for img in images if img.filepath not in failed_files]

            if not images:
                break

            for image in images:
                palette_data = self._palette_extractor.extract_palette(image.filepath)
                if palette_data:
                    try:
                        palette_record = create_palette_record(image.filepath, palette_data)
                        self.db.upsert_palette(palette_record)
                        extracted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to store palette for {image.filepath}: {e}")
                        failed_files.add(image.filepath)
                else:
                    failed_files.add(image.filepath)

                if progress_callback:
                    progress_callback(extracted_count, -1)

        logger.info(f"Extracted {extracted_count} palettes")

        if extracted_count > 0 and self._statistics:
            self._statistics.invalidate()

        return extracted_count

    # =========================================================================
    # Time-Based Selection Methods
    # =========================================================================

    def get_time_based_temperature(self) -> float:
        """Get target color temperature based on current time."""
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
        """Get the current time period name."""
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
        """Get preview candidates with their calculated weights."""
        candidates = self._get_candidates(constraints)

        if not candidates:
            return []

        # Use SelectionEngine to score candidates
        scored = self._selection_engine.score_candidates(candidates, constraints)

        # Convert to dict format and take top N
        top_candidates = []
        for sc in scored[:count]:
            top_candidates.append({
                'filepath': sc.image.filepath,
                'filename': sc.image.filename,
                'weight': sc.weight,
                'is_favorite': sc.image.is_favorite,
                'times_shown': sc.image.times_shown,
                'source_id': sc.image.source_id,
            })

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
        """Optimize and compact the database."""
        if self.db.vacuum():
            logger.info("Database vacuum completed successfully")
            return True
        else:
            logger.warning("Database vacuum failed")
            return False

    def verify_index(self) -> Dict[str, Any]:
        """Verify database integrity and check for issues."""
        return self.db.verify_integrity()

    def cleanup_index(self, remove_orphans: bool = True,
                      remove_missing: bool = True) -> Dict[str, int]:
        """Clean up the index by removing invalid entries."""
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
        """Create a backup of the database."""
        if backup_path is None:
            backup_path = self.db.db_path + '.backup'

        if self.db.backup(backup_path):
            logger.info(f"Database backup created at {backup_path}")
            return True
        else:
            logger.warning(f"Failed to create database backup at {backup_path}")
            return False
