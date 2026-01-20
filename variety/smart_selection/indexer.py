# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Directory scanning and image indexing for the Smart Selection Engine.

Scans directories for image files, extracts metadata, and populates
the database with ImageRecords.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any, Set, Callable, Iterator

from PIL import Image

from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.models import ImageRecord, SourceRecord, IndexingResult

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.avif'}


class ImageIndexer:
    """Scans directories and indexes images into the database.

    Extracts metadata including dimensions, file size, and modification time.
    Derives source_id from parent directory names.

    Supports eager palette extraction via on_images_indexed callback.
    """

    def __init__(
        self,
        db: ImageDatabase,
        favorites_folder: Optional[str] = None,
        on_images_indexed: Optional[Callable[[List[str]], None]] = None,
    ):
        """Initialize the indexer.

        Args:
            db: ImageDatabase instance for storing records.
            favorites_folder: Path to favorites folder. Images in this folder
                or its subfolders will be marked as favorites.
            on_images_indexed: Optional callback called after each batch of images
                is indexed. Receives list of filepaths. Use this to trigger
                eager palette extraction.
        """
        self.db = db
        self.favorites_folder = favorites_folder
        self.on_images_indexed = on_images_indexed
        if favorites_folder:
            self.favorites_folder = os.path.normpath(favorites_folder)

    def scan_directory(
        self,
        directory: str,
        recursive: bool = False,
    ) -> List[str]:
        """Scan a directory for image files.

        Args:
            directory: Path to directory to scan.
            recursive: If True, scan subdirectories too.

        Returns:
            List of absolute paths to image files found.
        """
        images = []
        directory = os.path.normpath(directory)

        if recursive:
            for root, _, files in os.walk(directory):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    if self._is_image_file(filepath):
                        images.append(filepath)
        else:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                if os.path.isfile(filepath) and self._is_image_file(filepath):
                    images.append(filepath)

        return images

    def _is_image_file(self, filepath: str) -> bool:
        """Check if a file is a supported image format.

        Args:
            filepath: Path to file.

        Returns:
            True if file extension indicates an image.
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in IMAGE_EXTENSIONS

    def index_image(self, filepath: str) -> Optional[ImageRecord]:
        """Index a single image file.

        Extracts metadata and creates an ImageRecord. Does not add to database.

        Args:
            filepath: Path to image file.

        Returns:
            ImageRecord if successful, None if file is not a valid image.
        """
        if not self._is_image_file(filepath):
            return None

        try:
            filepath = os.path.normpath(filepath)

            # Get file metadata
            file_stat = os.stat(filepath)
            file_size = file_stat.st_size
            file_mtime = int(file_stat.st_mtime)

            # Get image dimensions
            with Image.open(filepath) as img:
                width, height = img.size

            # Derive source_id from parent directory name
            source_id = os.path.basename(os.path.dirname(filepath))

            # Check if in favorites folder
            is_favorite = False
            if self.favorites_folder:
                is_favorite = filepath.startswith(self.favorites_folder)

            now = int(time.time())

            return ImageRecord(
                filepath=filepath,
                filename=os.path.basename(filepath),
                source_id=source_id,
                width=width,
                height=height,
                aspect_ratio=width / height if height > 0 else 0,
                file_size=file_size,
                file_mtime=file_mtime,
                is_favorite=is_favorite,
                first_indexed_at=now,
                last_indexed_at=now,
            )

        except Exception as e:
            logger.warning(f"Failed to index image {filepath}: {e}")
            return None

    def index_directory(
        self,
        directory: str,
        recursive: bool = False,
        batch_size: int = 100,
    ) -> int:
        """Scan and index all images in a directory.

        Uses batch inserts for improved performance when indexing many images.

        Args:
            directory: Path to directory to index.
            recursive: If True, index subdirectories too.
            batch_size: Number of records to batch before inserting (default 100).

        Returns:
            Number of images newly indexed or updated.
        """
        images = self.scan_directory(directory, recursive)
        indexed_count = 0
        sources_seen: Set[str] = set()
        batch: List[ImageRecord] = []

        for filepath in images:
            # Check if already indexed and unchanged
            existing = self.db.get_image(filepath)
            if existing:
                file_stat = os.stat(filepath)
                if existing.file_mtime == int(file_stat.st_mtime):
                    # Unchanged, skip
                    continue

            # Index the image
            record = self.index_image(filepath)
            if record:
                # Preserve first_indexed_at if updating
                if existing:
                    record.first_indexed_at = existing.first_indexed_at
                    record.times_shown = existing.times_shown
                    record.last_shown_at = existing.last_shown_at

                batch.append(record)
                indexed_count += 1

                # Track source
                if record.source_id:
                    sources_seen.add(record.source_id)

                # Flush batch when full
                if len(batch) >= batch_size:
                    self.db.batch_upsert_images(batch)
                    # Trigger eager palette extraction
                    if self.on_images_indexed:
                        indexed_paths = [r.filepath for r in batch]
                        try:
                            self.on_images_indexed(indexed_paths)
                        except Exception as e:
                            logger.warning(f"Palette extraction callback failed: {e}")
                    batch = []

        # Flush remaining batch
        if batch:
            self.db.batch_upsert_images(batch)
            # Trigger eager palette extraction for final batch
            if self.on_images_indexed:
                indexed_paths = [r.filepath for r in batch]
                try:
                    self.on_images_indexed(indexed_paths)
                except Exception as e:
                    logger.warning(f"Palette extraction callback failed: {e}")

        # Create/update source records in batch
        new_sources = []
        for source_id in sources_seen:
            existing_source = self.db.get_source(source_id)
            if not existing_source:
                new_sources.append(SourceRecord(
                    source_id=source_id,
                    source_type=self._detect_source_type(source_id),
                ))
        if new_sources:
            self.db.batch_upsert_sources(new_sources)

        return indexed_count

    def _detect_source_type(self, source_id: str) -> str:
        """Detect the type of source from its ID.

        Args:
            source_id: Source identifier (usually directory name).

        Returns:
            Source type string: 'remote', 'favorites', or 'local'.
        """
        source_lower = source_id.lower()

        # Known remote sources (exact match)
        remote_sources = {'unsplash', 'wallhaven', 'reddit', 'flickr', 'bing', 'earthview'}
        if source_lower in remote_sources:
            return 'remote'

        # Remote source prefixes (for search-term-specific folders like wallhaven_abstract)
        remote_prefixes = ('wallhaven_', 'reddit_', 'flickr_', 'unsplash_')
        if any(source_lower.startswith(prefix) for prefix in remote_prefixes):
            return 'remote'

        # Check for favorites
        if source_lower in {'favorites', 'faves'}:
            return 'favorites'

        return 'local'

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the current index.

        Returns:
            Dictionary with index statistics.
        """
        all_images = self.db.get_all_images()
        all_sources = self.db.get_all_sources()
        images_with_palettes = self.db.get_images_with_palettes()

        return {
            'total_images': len(all_images),
            'total_sources': len(all_sources),
            'images_with_palettes': len(images_with_palettes),
            'favorites_count': sum(1 for img in all_images if img.is_favorite),
        }

    def index_directory_incremental(
        self,
        directory: str,
        recursive: bool = True,
        batch_size: int = 500,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> IndexingResult:
        """Incrementally index a directory with progress reporting.

        Efficiently handles large directories by:
        - Loading existing index into memory for O(1) mtime comparison
        - Using generators to avoid loading all paths into memory
        - Processing in batches to limit memory usage
        - Detecting and removing deleted files
        - Preserving selection history when re-indexing modified files

        Args:
            directory: Directory path to index.
            recursive: If True, scan subdirectories.
            batch_size: Number of files to process per batch.
            progress_callback: Optional callback(current, total, message)
                for progress reporting.

        Returns:
            IndexingResult with counts of added, updated, removed files.
        """
        directory = os.path.normpath(directory)
        if not os.path.isdir(directory):
            return IndexingResult()

        result = IndexingResult()

        # Step 1: Load existing index for this directory (O(1) lookup)
        indexed_mtime = self.db.get_indexed_mtime_map(directory)
        indexed_paths = set(indexed_mtime.keys())

        # Step 2: Scan directory and categorize files
        disk_paths: Set[str] = set()
        to_index: List[str] = []
        to_update: List[str] = []

        for filepath in self._scan_directory_generator(directory, recursive):
            disk_paths.add(filepath)

            if filepath not in indexed_paths:
                to_index.append(filepath)
            else:
                try:
                    current_mtime = int(os.stat(filepath).st_mtime)
                    if current_mtime != indexed_mtime.get(filepath):
                        to_update.append(filepath)
                except OSError:
                    pass

        # Step 3: Find deleted files
        to_delete = list(indexed_paths - disk_paths)

        # Step 4: Calculate total work
        total_work = len(to_index) + len(to_update) + len(to_delete)
        processed = 0

        # Track sources for batch creation
        sources_seen: Set[str] = set()

        # Step 5: Index new files in batches
        for batch in self._batch(to_index, batch_size):
            records = []
            for filepath in batch:
                record = self.index_image(filepath)
                if record:
                    records.append(record)
                    if record.source_id:
                        sources_seen.add(record.source_id)
                else:
                    result.errors += 1

            if records:
                self.db.batch_upsert_images(records)
                result.added += len(records)

                # Trigger eager palette extraction for newly indexed images
                if self.on_images_indexed:
                    indexed_paths = [r.filepath for r in records]
                    try:
                        self.on_images_indexed(indexed_paths)
                    except Exception as e:
                        logger.warning(f"Palette extraction callback failed: {e}")

            processed += len(batch)
            if progress_callback:
                progress_callback(processed, total_work, "Indexing new files...")

        # Step 6: Update modified files in batches (preserve history)
        for batch in self._batch(to_update, batch_size):
            records = []
            for filepath in batch:
                existing = self.db.get_image(filepath)
                new_record = self.index_image(filepath)
                if new_record and existing:
                    # Preserve selection history
                    new_record.first_indexed_at = existing.first_indexed_at
                    new_record.times_shown = existing.times_shown
                    new_record.last_shown_at = existing.last_shown_at
                    # Reset palette status for modified files (content may have changed)
                    new_record.palette_status = 'pending'
                    records.append(new_record)
                    if new_record.source_id:
                        sources_seen.add(new_record.source_id)
                elif new_record:
                    records.append(new_record)
                    if new_record.source_id:
                        sources_seen.add(new_record.source_id)
                else:
                    result.errors += 1

            if records:
                self.db.batch_upsert_images(records)
                result.updated += len(records)

                # Trigger eager palette extraction for modified images
                if self.on_images_indexed:
                    updated_paths = [r.filepath for r in records]
                    try:
                        self.on_images_indexed(updated_paths)
                    except Exception as e:
                        logger.warning(f"Palette extraction callback failed: {e}")

            processed += len(batch)
            if progress_callback:
                progress_callback(processed, total_work, "Updating modified files...")

        # Step 7: Delete removed files
        if to_delete:
            self.db.batch_delete_images(to_delete)
            result.removed = len(to_delete)
            processed += len(to_delete)
            if progress_callback:
                progress_callback(processed, total_work, "Cleaning up removed files...")

        # Step 8: Create new source records
        new_sources = []
        for source_id in sources_seen:
            existing_source = self.db.get_source(source_id)
            if not existing_source:
                new_sources.append(SourceRecord(
                    source_id=source_id,
                    source_type=self._detect_source_type(source_id),
                ))
        if new_sources:
            self.db.batch_upsert_sources(new_sources)

        return result

    def _scan_directory_generator(
        self,
        directory: str,
        recursive: bool = True
    ) -> Iterator[str]:
        """Generator that yields file paths without loading all into memory.

        Uses os.walk for recursive scanning and os.scandir for non-recursive,
        both of which are memory-efficient.

        Args:
            directory: Directory to scan.
            recursive: If True, include subdirectories.

        Yields:
            Absolute paths to image files.
        """
        directory = os.path.normpath(directory)

        if recursive:
            for root, _, files in os.walk(directory):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    if self._is_image_file(filepath):
                        yield filepath
        else:
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.is_file() and self._is_image_file(entry.path):
                            yield entry.path
            except OSError:
                pass

    @staticmethod
    def _batch(items: List[Any], size: int) -> Iterator[List[Any]]:
        """Yield successive batches from a list.

        Args:
            items: List to batch.
            size: Maximum batch size.

        Yields:
            Lists of at most `size` items.
        """
        for i in range(0, len(items), size):
            yield items[i:i+size]
