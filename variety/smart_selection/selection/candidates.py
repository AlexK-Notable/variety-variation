# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Candidate image retrieval from the database.

Provides database queries for retrieving candidate images based on
source filters and favorites settings.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.models import ImageRecord, SelectionConstraints


@dataclass
class CandidateQuery:
    """Query parameters for retrieving candidate images.

    Attributes:
        source_type: Filter by source type (e.g., 'unsplash', 'wallhaven').
        source_id: Filter by specific source ID.
        sources: List of source_ids to include (None = all sources).
        min_width: Minimum image width in pixels.
        min_height: Minimum image height in pixels.
        favorites_only: If True, only return favorite images.
        exclude_filepaths: Set of filepaths to exclude from results.
    """
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    sources: Optional[List[str]] = None
    min_width: Optional[int] = None
    min_height: Optional[int] = None
    favorites_only: bool = False
    exclude_filepaths: Set[str] = field(default_factory=set)

    @classmethod
    def from_constraints(cls, constraints: Optional['SelectionConstraints']) -> 'CandidateQuery':
        """Create a CandidateQuery from SelectionConstraints.

        Args:
            constraints: SelectionConstraints to convert, or None for defaults.

        Returns:
            New CandidateQuery instance.
        """
        if constraints is None:
            return cls()

        return cls(
            sources=constraints.sources,
            favorites_only=constraints.favorites_only,
        )


class CandidateProvider:
    """Provides candidate images from the database.

    Handles database queries for retrieving candidate images based on
    source filters, favorites, and file existence validation.
    """

    def __init__(self, db: 'ImageDatabase'):
        """Initialize the candidate provider.

        Args:
            db: ImageDatabase instance for queries.
        """
        self.db = db

    def get_candidates(self, query: CandidateQuery) -> List['ImageRecord']:
        """Get candidate images matching the query.

        Retrieves images from the database matching the query parameters,
        then filters out files that no longer exist on disk.

        Args:
            query: CandidateQuery with filter parameters.

        Returns:
            List of ImageRecord objects matching the query.
        """
        # Get candidates from database based on query
        candidates = self._query_database(query)

        # Filter out non-existent files (phantom index protection)
        candidates = [img for img in candidates if os.path.exists(img.filepath)]

        # Apply exclude list
        if query.exclude_filepaths:
            candidates = [
                img for img in candidates
                if img.filepath not in query.exclude_filepaths
            ]

        return candidates

    def _query_database(self, query: CandidateQuery) -> List['ImageRecord']:
        """Query the database for candidate images.

        Args:
            query: CandidateQuery with filter parameters.

        Returns:
            List of ImageRecord objects from database.
        """
        # Filter by specific source(s)
        if query.sources:
            candidates = []
            for source_id in query.sources:
                candidates.extend(self.db.get_images_by_source(source_id))
            return candidates

        # Filter by single source_id
        if query.source_id:
            return self.db.get_images_by_source(query.source_id)

        # Filter to favorites only
        if query.favorites_only:
            return self.db.get_favorite_images()

        # Return all images
        return self.db.get_all_images()
