# tests/smart_selection/e2e/test_edge_cases.py
"""Edge case and error handling tests for Smart Selection Engine."""

import os
import shutil
import pytest


class TestDeletedFileHandling:
    """Test handling of files that disappear after indexing."""

    @pytest.mark.e2e
    @pytest.mark.skip(reason="File existence validation not yet implemented in selector")
    def test_deleted_file_not_selected(self, temp_db, temp_dir, fixture_images):
        """Deleted files are not selected.

        Note: This test is skipped because the current implementation
        does not validate file existence during selection. This could
        be a future enhancement.
        """
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Copy fixtures to temp dir
        for img in fixture_images:
            shutil.copy(img, temp_dir)

        # Index the images
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(temp_dir)

            all_images = db.get_all_images()
            assert len(all_images) == len(fixture_images)

        # Delete one image from disk (but not from database)
        deleted_image = os.path.join(temp_dir, os.path.basename(fixture_images[0]))
        os.remove(deleted_image)

        # Selection should only return existing files
        with SmartSelector(temp_db, SelectionConfig()) as selector:
            for _ in range(50):
                selected = selector.select_images(count=5)
                for path in selected:
                    assert os.path.exists(path), f"Selected non-existent file: {path}"

    @pytest.mark.e2e
    @pytest.mark.skip(reason="cleanup_missing_files() not yet implemented")
    def test_deleted_file_skipped_in_reindex(self, temp_db, temp_dir, fixture_images):
        """Re-indexing removes deleted files from database.

        Note: This test is skipped because cleanup_missing_files()
        is not yet implemented. This could be a future enhancement.
        """
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        # Copy fixtures to temp dir
        for img in fixture_images:
            shutil.copy(img, temp_dir)

        # Initial index
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(temp_dir)
            initial_count = len(db.get_all_images())

        # Delete one image
        deleted_image = os.path.join(temp_dir, os.path.basename(fixture_images[0]))
        os.remove(deleted_image)

        # Re-index with cleanup
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.cleanup_missing_files()
            final_count = len(db.get_all_images())

        assert final_count == initial_count - 1


class TestEmptyStates:
    """Test handling of empty states."""

    @pytest.mark.e2e
    def test_empty_directory_indexes_nothing(self, temp_db, temp_dir):
        """Indexing an empty directory adds nothing."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            count = indexer.index_directory(temp_dir)

            assert count == 0
            assert len(db.get_all_images()) == 0

    @pytest.mark.e2e
    def test_select_from_empty_returns_empty(self, temp_db):
        """Selecting from empty database returns empty list."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(temp_db, SelectionConfig()) as selector:
            selected = selector.select_images(count=10)
            assert selected == []

    @pytest.mark.e2e
    def test_select_more_than_available(self, indexed_database):
        """Requesting more images than available returns all available."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            all_images = selector.db.get_all_images()
            requested = len(all_images) + 10

            selected = selector.select_images(count=requested)

            assert len(selected) == len(all_images)


class TestConstraintEdgeCases:
    """Test edge cases with selection constraints."""

    @pytest.mark.e2e
    def test_impossible_constraints_return_empty(self, indexed_database):
        """Constraints that match no images return empty list."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        # Require impossibly large dimensions
        constraints = SelectionConstraints(
            min_width=100000,
            min_height=100000,
        )

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=5, constraints=constraints)
            assert selected == []

    @pytest.mark.e2e
    def test_narrow_aspect_ratio_constraint(self, indexed_database):
        """Very narrow aspect ratio range still works."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        # Very narrow aspect ratio range
        constraints = SelectionConstraints(
            min_aspect_ratio=1.5,
            max_aspect_ratio=1.8,
        )

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=10, constraints=constraints)

            # All selected should match constraints
            for filepath in selected:
                img = selector.db.get_image(filepath)
                assert 1.5 <= img.aspect_ratio <= 1.8


class TestConcurrentAccess:
    """Test database behavior with multiple connections."""

    @pytest.mark.e2e
    def test_multiple_readers_work(self, indexed_database):
        """Multiple read connections can coexist."""
        from variety.smart_selection.database import ImageDatabase

        # Open two connections and read from both
        with ImageDatabase(indexed_database) as db1:
            with ImageDatabase(indexed_database) as db2:
                images1 = db1.get_all_images()
                images2 = db2.get_all_images()

                assert len(images1) == len(images2)
                assert images1[0].filepath == images2[0].filepath


class TestInvalidInputHandling:
    """Test handling of invalid inputs."""

    @pytest.mark.e2e
    def test_record_nonexistent_image(self, indexed_database):
        """Recording a non-existent image doesn't crash."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            # Should not raise, just do nothing
            selector.record_shown("/nonexistent/path/image.jpg")

    @pytest.mark.e2e
    def test_index_nonexistent_directory_raises(self, temp_db):
        """Indexing a non-existent directory raises FileNotFoundError."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            with pytest.raises(FileNotFoundError):
                indexer.index_directory("/nonexistent/directory/path")

    @pytest.mark.e2e
    def test_select_zero_count(self, indexed_database):
        """Requesting zero images returns empty list."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=0)
            assert selected == []

    @pytest.mark.e2e
    def test_select_negative_count(self, indexed_database):
        """Requesting negative count returns empty list."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=-5)
            assert selected == []


class TestNonImageFileHandling:
    """Test handling of non-image files."""

    @pytest.mark.e2e
    def test_non_image_files_ignored(self, temp_db, temp_dir, fixture_images):
        """Non-image files in directory are ignored during indexing."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        # Copy one image
        shutil.copy(fixture_images[0], temp_dir)

        # Create some non-image files
        with open(os.path.join(temp_dir, 'readme.txt'), 'w') as f:
            f.write('This is a text file')
        with open(os.path.join(temp_dir, 'data.json'), 'w') as f:
            f.write('{"key": "value"}')
        with open(os.path.join(temp_dir, 'script.sh'), 'w') as f:
            f.write('#!/bin/bash\necho hello')

        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            count = indexer.index_directory(temp_dir)

            assert count == 1  # Only the image
            images = db.get_all_images()
            assert len(images) == 1
            assert images[0].filepath.endswith(('.jpg', '.jpeg', '.png', '.webp'))
