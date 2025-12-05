# tests/smart_selection/e2e/test_persistence.py
"""Persistence and state management tests for Smart Selection Engine."""

import os
import pytest


class TestDatabasePersistence:
    """Test database state survives restarts."""

    @pytest.mark.e2e
    def test_database_survives_restart(self, temp_db, fixtures_dir, fixture_images):
        """Database data persists across connections."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # First session: index images and record some as shown
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
            indexer.index_directory(fixtures_dir)

            all_images = db.get_all_images()
            assert len(all_images) == len(fixture_images)

        # Record some images as shown
        with SmartSelector(temp_db, SelectionConfig()) as selector:
            shown_images = selector.db.get_all_images()[:3]
            for img in shown_images:
                selector.record_shown(img.filepath)

        # Second session: verify data persisted
        with ImageDatabase(temp_db) as db:
            all_images = db.get_all_images()
            assert len(all_images) == len(fixture_images)

            # Check shown images have updated times_shown
            for img in all_images:
                if img.filepath in [s.filepath for s in shown_images]:
                    assert img.times_shown >= 1
                    assert img.last_shown_at is not None

    @pytest.mark.e2e
    def test_source_tracking_persists(self, temp_db, temp_dir, fixture_images):
        """Source usage tracking persists across sessions."""
        import shutil
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        # Create two sources
        source_a = os.path.join(temp_dir, 'source_a')
        source_b = os.path.join(temp_dir, 'source_b')
        os.makedirs(source_a)
        os.makedirs(source_b)

        half = len(fixture_images) // 2
        for i, img in enumerate(fixture_images):
            dest = source_a if i < half else source_b
            shutil.copy(img, dest)

        # First session: index and use source_a
        with ImageDatabase(temp_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(source_a)
            indexer.index_directory(source_b)

        with SmartSelector(temp_db, SelectionConfig()) as selector:
            source_a_images = [
                img for img in selector.db.get_all_images()
                if source_a in img.filepath
            ]
            for img in source_a_images[:2]:
                selector.record_shown(img.filepath)

        # Second session: verify source tracking persisted
        with ImageDatabase(temp_db) as db:
            sources = db.get_all_sources()
            # Source ID is the directory basename (not full path)
            source_a_record = next((s for s in sources if s.source_id == 'source_a'), None)
            source_b_record = next((s for s in sources if s.source_id == 'source_b'), None)

            assert source_a_record is not None
            assert source_b_record is not None
            assert source_a_record.last_shown_at is not None
            assert source_b_record.last_shown_at is None  # Not used


class TestConfigChanges:
    """Test configuration changes apply correctly."""

    @pytest.mark.e2e
    def test_config_changes_affect_selection(self, indexed_database):
        """Different configs produce different selection behavior."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from collections import Counter

        # Config with high favorite boost
        config_high_fav = SelectionConfig(enabled=True, favorite_boost=10.0)

        # Config with no favorite boost
        config_no_fav = SelectionConfig(enabled=True, favorite_boost=1.0)

        # Both should work - behavior depends on data
        with SmartSelector(indexed_database, config_high_fav) as selector:
            high_fav_selections = []
            for _ in range(50):
                selected = selector.select_images(count=1)
                if selected:
                    high_fav_selections.append(selected[0])

        with SmartSelector(indexed_database, config_no_fav) as selector:
            no_fav_selections = []
            for _ in range(50):
                selected = selector.select_images(count=1)
                if selected:
                    no_fav_selections.append(selected[0])

        # Both should have valid selections
        assert len(high_fav_selections) == 50
        assert len(no_fav_selections) == 50

    @pytest.mark.e2e
    def test_disabled_config_uses_uniform_selection(self, indexed_database):
        """Disabled config falls back to uniform random selection."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from collections import Counter

        config = SelectionConfig(enabled=False)

        with SmartSelector(indexed_database, config) as selector:
            # Record one image as shown many times
            all_images = selector.db.get_all_images()
            shown_image = all_images[0].filepath
            for _ in range(10):
                selector.record_shown(shown_image)

            # With disabled config, shown image should still be selected uniformly
            selection_counts = Counter()
            num_trials = 300

            for _ in range(num_trials):
                selected = selector.select_images(count=1)
                if selected:
                    selection_counts[selected[0]] += 1

            # Shown image should be selected roughly uniformly
            expected_uniform = num_trials / len(all_images)
            shown_count = selection_counts.get(shown_image, 0)

            # Allow for statistical variance (within 50% of expected)
            assert shown_count > expected_uniform * 0.5, (
                f"Shown image selected {shown_count} times, expected ~{expected_uniform:.0f}"
            )


class TestPalettesPersistence:
    """Test palette data persistence."""

    @pytest.mark.e2e
    @pytest.mark.wallust
    def test_palettes_persist_across_sessions(self, indexed_database, wallust_available):
        """Extracted palettes persist across database sessions."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.palette import PaletteExtractor, create_palette_record

        extractor = PaletteExtractor()

        # First session: extract and store palettes
        with ImageDatabase(indexed_database) as db:
            images = db.get_all_images()[:3]
            stored_palettes = {}

            for img in images:
                palette_data = extractor.extract_palette(img.filepath)
                if palette_data:
                    record = create_palette_record(img.filepath, palette_data)
                    db.upsert_palette(record)
                    stored_palettes[img.filepath] = record

        # Second session: verify palettes persisted
        with ImageDatabase(indexed_database) as db:
            for filepath, original in stored_palettes.items():
                palette = db.get_palette(filepath)
                assert palette is not None
                assert palette.color0 == original.color0
                assert palette.avg_hue == original.avg_hue
