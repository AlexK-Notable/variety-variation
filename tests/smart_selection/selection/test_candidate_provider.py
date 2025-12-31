#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for CandidateProvider - database queries for candidate images."""

import os
import tempfile
import shutil
import unittest
from PIL import Image


class TestCandidateQuery(unittest.TestCase):
    """Tests for CandidateQuery dataclass."""

    def test_candidate_query_import(self):
        """CandidateQuery can be imported from candidates module."""
        from variety.smart_selection.selection.candidates import CandidateQuery
        self.assertIsNotNone(CandidateQuery)

    def test_candidate_query_default_values(self):
        """CandidateQuery has sensible defaults."""
        from variety.smart_selection.selection.candidates import CandidateQuery

        query = CandidateQuery()

        self.assertIsNone(query.source_type)
        self.assertIsNone(query.source_id)
        self.assertIsNone(query.min_width)
        self.assertIsNone(query.min_height)
        self.assertFalse(query.favorites_only)
        self.assertEqual(query.exclude_filepaths, set())

    def test_candidate_query_with_values(self):
        """CandidateQuery accepts custom values."""
        from variety.smart_selection.selection.candidates import CandidateQuery

        query = CandidateQuery(
            source_type='unsplash',
            source_id='unsplash-123',
            min_width=1920,
            min_height=1080,
            favorites_only=True,
            exclude_filepaths={'/path/to/exclude.jpg'},
        )

        self.assertEqual(query.source_type, 'unsplash')
        self.assertEqual(query.source_id, 'unsplash-123')
        self.assertEqual(query.min_width, 1920)
        self.assertEqual(query.min_height, 1080)
        self.assertTrue(query.favorites_only)
        self.assertEqual(query.exclude_filepaths, {'/path/to/exclude.jpg'})


class TestCandidateProviderCreation(unittest.TestCase):
    """Tests for CandidateProvider instantiation."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_candidate_provider_import(self):
        """CandidateProvider can be imported from candidates module."""
        from variety.smart_selection.selection.candidates import CandidateProvider
        self.assertIsNotNone(CandidateProvider)

    def test_candidate_provider_creation(self):
        """CandidateProvider can be created with a database."""
        from variety.smart_selection.selection.candidates import CandidateProvider
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            provider = CandidateProvider(db)
            self.assertIsNotNone(provider)
        finally:
            db.close()


class TestCandidateProviderQueries(unittest.TestCase):
    """Tests for CandidateProvider.get_candidates()."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.images_dir = os.path.join(self.temp_dir, 'images')
        self.favorites_dir = os.path.join(self.temp_dir, 'favorites')
        os.makedirs(self.images_dir)
        os.makedirs(self.favorites_dir)

        # Create regular images
        self.regular_paths = []
        for i in range(5):
            path = os.path.join(self.images_dir, f'img{i}.jpg')
            img = Image.new('RGB', (1920, 1080), color='blue')
            img.save(path)
            self.regular_paths.append(path)

        # Create favorite images
        self.favorite_paths = []
        for i in range(3):
            path = os.path.join(self.favorites_dir, f'fav{i}.jpg')
            img = Image.new('RGB', (2560, 1440), color='red')
            img.save(path)
            self.favorite_paths.append(path)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def _populate_database(self, db):
        """Add test images to database."""
        from variety.smart_selection.indexer import ImageIndexer
        indexer = ImageIndexer(db, favorites_folder=self.favorites_dir)
        indexer.index_directory(self.images_dir)
        indexer.index_directory(self.favorites_dir)

    def test_get_candidates_returns_all_images(self):
        """get_candidates returns all images when no constraints."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            provider = CandidateProvider(db)

            candidates = provider.get_candidates(CandidateQuery())

            self.assertEqual(len(candidates), 8)  # 5 regular + 3 favorites
        finally:
            db.close()

    def test_get_candidates_filters_favorites_only(self):
        """get_candidates returns only favorites when favorites_only=True."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            provider = CandidateProvider(db)

            query = CandidateQuery(favorites_only=True)
            candidates = provider.get_candidates(query)

            self.assertEqual(len(candidates), 3)
            for img in candidates:
                self.assertTrue(img.is_favorite)
        finally:
            db.close()

    def test_get_candidates_filters_by_source_id(self):
        """get_candidates filters by source_id."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            provider = CandidateProvider(db)

            # Use the directory name as source_id
            query = CandidateQuery(source_id='images')
            candidates = provider.get_candidates(query)

            self.assertEqual(len(candidates), 5)
        finally:
            db.close()

    def test_get_candidates_filters_nonexistent_files(self):
        """get_candidates excludes files that no longer exist on disk."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            provider = CandidateProvider(db)

            # Delete one file
            deleted_path = self.regular_paths[0]
            os.remove(deleted_path)

            candidates = provider.get_candidates(CandidateQuery())

            self.assertEqual(len(candidates), 7)  # 4 regular + 3 favorites
            filepaths = [img.filepath for img in candidates]
            self.assertNotIn(deleted_path, filepaths)
        finally:
            db.close()

    def test_get_candidates_excludes_specified_filepaths(self):
        """get_candidates excludes filepaths in exclude_filepaths."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            provider = CandidateProvider(db)

            exclude = {self.regular_paths[0], self.regular_paths[1]}
            query = CandidateQuery(exclude_filepaths=exclude)
            candidates = provider.get_candidates(query)

            self.assertEqual(len(candidates), 6)  # 3 regular + 3 favorites
            filepaths = [img.filepath for img in candidates]
            for path in exclude:
                self.assertNotIn(path, filepaths)
        finally:
            db.close()

    def test_get_candidates_filters_by_sources_list(self):
        """get_candidates filters by list of source_ids."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            self._populate_database(db)
            provider = CandidateProvider(db)

            # Filter by both sources
            query = CandidateQuery(sources=['images', 'favorites'])
            candidates = provider.get_candidates(query)

            self.assertEqual(len(candidates), 8)  # All images
        finally:
            db.close()

    def test_get_candidates_empty_database(self):
        """get_candidates returns empty list for empty database."""
        from variety.smart_selection.selection.candidates import CandidateProvider, CandidateQuery
        from variety.smart_selection.database import ImageDatabase

        db = ImageDatabase(self.db_path)
        try:
            provider = CandidateProvider(db)

            candidates = provider.get_candidates(CandidateQuery())

            self.assertEqual(candidates, [])
        finally:
            db.close()


class TestCandidateQueryFromConstraints(unittest.TestCase):
    """Tests for CandidateQuery.from_constraints factory method."""

    def test_from_constraints_with_none(self):
        """from_constraints returns default query when constraints is None."""
        from variety.smart_selection.selection.candidates import CandidateQuery

        query = CandidateQuery.from_constraints(None)

        self.assertIsNone(query.source_id)
        self.assertFalse(query.favorites_only)

    def test_from_constraints_extracts_sources(self):
        """from_constraints extracts sources from SelectionConstraints."""
        from variety.smart_selection.selection.candidates import CandidateQuery
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(sources=['source1', 'source2'])
        query = CandidateQuery.from_constraints(constraints)

        self.assertEqual(query.sources, ['source1', 'source2'])

    def test_from_constraints_extracts_favorites_only(self):
        """from_constraints extracts favorites_only from SelectionConstraints."""
        from variety.smart_selection.selection.candidates import CandidateQuery
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(favorites_only=True)
        query = CandidateQuery.from_constraints(constraints)

        self.assertTrue(query.favorites_only)


if __name__ == '__main__':
    unittest.main()
