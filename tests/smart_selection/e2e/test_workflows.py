# tests/smart_selection/e2e/test_workflows.py
"""End-to-end workflow tests for Smart Selection Engine."""

import os
import shutil
import pytest
from collections import Counter


class TestFreshStartWorkflow:
    """Test complete fresh start workflow."""

    @pytest.mark.e2e
    def test_fresh_database_index_and_select(self, temp_db, fixtures_dir, fixture_images):
        """Complete workflow: create DB, index, select."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Step 1: Create fresh database and index
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            count = indexer.index_directory(fixtures_dir)

            # Verify indexing
            assert count == len(fixture_images)
            assert count > 0

            # Verify metadata extracted
            all_images = db.get_all_images()
            assert len(all_images) == count

            for img in all_images:
                assert img.width is not None
                assert img.height is not None
                assert img.aspect_ratio is not None
                assert img.file_size is not None
                assert img.is_favorite is True  # All in favorites_folder

        # Step 2: Select images
        with SmartSelector(temp_db, SelectionConfig()) as selector:
            selected = selector.select_images(count=3)

            # Verify selection
            assert len(selected) == 3
            assert all(os.path.exists(p) for p in selected)
            assert all(p in [img.filepath for img in all_images] for p in selected)

    @pytest.mark.e2e
    def test_empty_database_returns_empty_selection(self, temp_db):
        """Empty database returns empty selection."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(temp_db, SelectionConfig()) as selector:
            selected = selector.select_images(count=5)
            assert selected == []


class TestSelectionLifecycleWorkflow:
    """Test selection behavior over time."""

    @pytest.mark.e2e
    def test_recently_shown_image_less_likely(self, indexed_database):
        """Recently shown images appear less frequently in selections."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(
            enabled=True,
            image_cooldown_days=7,
            source_cooldown_days=0,  # Disable source cooldown to isolate image recency
            recency_decay='linear',
        )

        with SmartSelector(indexed_database, config) as selector:
            # Get all images
            all_images = selector.db.get_all_images()
            assert len(all_images) >= 3, "Need at least 3 fixture images"

            # Record one image as shown multiple times to create strong recency
            shown_image = all_images[0].filepath
            for _ in range(5):
                selector.record_shown(shown_image)

            # Verify the image has been marked as shown
            updated_image = selector.db.get_image(shown_image)
            assert updated_image.last_shown_at is not None, "last_shown_at should be set"
            assert updated_image.times_shown == 5, "times_shown should be 5"

            # Select many times and count occurrences
            selection_counts = Counter()
            num_trials = 300

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    selection_counts[selected[0]] += 1

            # Recently shown image should appear less than average
            expected_uniform = num_trials / len(all_images)
            shown_count = selection_counts.get(shown_image, 0)

            # With linear decay at elapsed_time ~0, recency factor is ~0
            # The shown image should rarely or never be selected
            assert shown_count < expected_uniform * 0.5, (
                f"Recently shown image selected {shown_count} times, "
                f"expected less than {expected_uniform * 0.5:.0f} (recency should suppress it)"
            )

    @pytest.mark.e2e
    def test_times_shown_increments(self, indexed_database):
        """Recording shown increments times_shown counter."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            image = selector.db.get_all_images()[0]

            assert image.times_shown == 0

            selector.record_shown(image.filepath)
            updated = selector.db.get_image(image.filepath)
            assert updated.times_shown == 1

            selector.record_shown(image.filepath)
            updated = selector.db.get_image(image.filepath)
            assert updated.times_shown == 2


class TestColorAwareWorkflow:
    """Test color-based selection workflows."""

    @pytest.mark.e2e
    @pytest.mark.wallust
    def test_color_similar_images_preferred(self, selector_with_palettes):
        """Images with similar colors are preferred when target_palette set."""
        from variety.smart_selection.models import SelectionConstraints
        from variety.smart_selection.palette import palette_similarity

        selector = selector_with_palettes

        # Get an image with a palette to use as target
        all_images = selector.db.get_all_images()
        target_image = None
        target_palette_data = None

        for img in all_images:
            palette = selector.db.get_palette(img.filepath)
            if palette and palette.avg_hue is not None:
                target_image = img
                target_palette_data = {
                    'avg_hue': palette.avg_hue,
                    'avg_saturation': palette.avg_saturation,
                    'avg_lightness': palette.avg_lightness,
                    'color_temperature': palette.color_temperature,
                }
                break

        assert target_image is not None, "No images with palettes found"

        # Calculate similarity scores for all images
        similarities = {}
        for img in all_images:
            palette = selector.db.get_palette(img.filepath)
            if palette and palette.avg_hue is not None:
                img_palette = {
                    'avg_hue': palette.avg_hue,
                    'avg_saturation': palette.avg_saturation,
                    'avg_lightness': palette.avg_lightness,
                    'color_temperature': palette.color_temperature,
                }
                similarities[img.filepath] = palette_similarity(
                    target_palette_data, img_palette
                )

        # Select with color constraint
        constraints = SelectionConstraints(
            target_palette=target_palette_data,
            min_color_similarity=0.5,
        )

        selection_counts = Counter()
        num_trials = 100

        for _ in range(num_trials):
            selected = selector.select_images(count=1, constraints=constraints)
            if selected:
                selection_counts[selected[0]] += 1

        # Verify only similar images were selected
        for filepath, count in selection_counts.items():
            assert filepath in similarities, f"{filepath} has no palette"
            assert similarities[filepath] >= 0.5, (
                f"{filepath} similarity {similarities[filepath]:.2f} below threshold"
            )

    @pytest.mark.e2e
    @pytest.mark.wallust
    def test_palette_extraction_on_record_shown(self, indexed_database, wallust_available):
        """Palette is extracted when record_shown is called with extraction enabled."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(
            indexed_database,
            SelectionConfig(),
            enable_palette_extraction=True
        ) as selector:
            image = selector.db.get_all_images()[0]

            # No palette initially
            assert selector.db.get_palette(image.filepath) is None

            # Record shown triggers extraction
            selector.record_shown(image.filepath)

            # Now palette should exist
            palette = selector.db.get_palette(image.filepath)
            assert palette is not None
            assert palette.avg_hue is not None
            assert palette.color0 is not None


class TestFavoritesWorkflow:
    """Test favorites boost behavior."""

    @pytest.mark.e2e
    def test_favorites_boosted_in_selection(self, temp_db, temp_dir, fixture_images):
        """Favorite images appear more frequently than non-favorites."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Create two directories: favorites and non-favorites
        fav_dir = os.path.join(temp_dir, 'favorites')
        other_dir = os.path.join(temp_dir, 'other')
        os.makedirs(fav_dir)
        os.makedirs(other_dir)

        # Split fixture images
        half = len(fixture_images) // 2
        for i, img in enumerate(fixture_images):
            dest_dir = fav_dir if i < half else other_dir
            shutil.copy(img, dest_dir)

        # Index with favorites folder set
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fav_dir)
            indexer.index_directory(fav_dir)
            indexer.index_directory(other_dir)

        # Select many times
        config = SelectionConfig(enabled=True, favorite_boost=3.0)
        with SmartSelector(temp_db, config) as selector:
            fav_count = 0
            other_count = 0
            num_trials = 200

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    if selected[0].startswith(fav_dir):
                        fav_count += 1
                    else:
                        other_count += 1

            # Favorites should be selected more often
            assert fav_count > other_count, (
                f"Favorites: {fav_count}, Others: {other_count}"
            )


class TestSourceRotationWorkflow:
    """Test source rotation behavior."""

    @pytest.mark.e2e
    def test_source_rotation_balances_selection(self, temp_db, temp_dir, fixture_images):
        """Sources rotate - recently used sources are deprioritized."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Create two source directories
        source_a = os.path.join(temp_dir, 'source_a')
        source_b = os.path.join(temp_dir, 'source_b')
        os.makedirs(source_a)
        os.makedirs(source_b)

        # Split images between sources
        half = len(fixture_images) // 2
        for i, img in enumerate(fixture_images):
            dest = source_a if i < half else source_b
            shutil.copy(img, dest)

        # Index both sources
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(source_a)
            indexer.index_directory(source_b)

        # Configure with source cooldown
        config = SelectionConfig(
            enabled=True,
            source_cooldown_days=1,
        )

        with SmartSelector(temp_db, config) as selector:
            # Record many shows from source_a
            source_a_images = [
                img for img in selector.db.get_all_images()
                if source_a in img.filepath
            ]
            for img in source_a_images[:3]:
                selector.record_shown(img.filepath)

            # Now selections should favor source_b
            source_counts = Counter()
            num_trials = 100

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    if source_a in selected[0]:
                        source_counts['a'] += 1
                    else:
                        source_counts['b'] += 1

            # Source B should be preferred
            assert source_counts['b'] > source_counts['a'], (
                f"Source A: {source_counts['a']}, Source B: {source_counts['b']}"
            )


class TestConstraintCombinations:
    """Test combining multiple constraints."""

    @pytest.mark.e2e
    def test_multiple_constraints_combined(self, indexed_database):
        """Multiple constraints are applied together."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(
            min_width=500,
            min_height=500,
            min_aspect_ratio=1.0,
            max_aspect_ratio=2.0,
        )

        with SmartSelector(indexed_database, SelectionConfig()) as selector:
            selected = selector.select_images(count=10, constraints=constraints)

            # All selected images should match all constraints
            for filepath in selected:
                img = selector.db.get_image(filepath)
                assert img.width >= 500
                assert img.height >= 500
                assert 1.0 <= img.aspect_ratio <= 2.0
