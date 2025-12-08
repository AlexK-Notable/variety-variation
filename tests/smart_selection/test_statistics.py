# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Unit tests for the CollectionStatistics class."""

import pytest
import tempfile
import os

from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.statistics import CollectionStatistics
from variety.smart_selection.models import ImageRecord, PaletteRecord


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    database = ImageDatabase(db_path)
    yield database

    database.close()
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def stats(db):
    """Create a CollectionStatistics instance."""
    return CollectionStatistics(db)


class TestBasicFunctionality:
    """Test basic statistics functionality."""

    def test_empty_database(self, stats, db):
        """Test statistics on an empty database."""
        # Should return zeros for all distributions
        lightness = stats.get_lightness_distribution()
        assert lightness == {'dark': 0, 'medium_dark': 0, 'medium_light': 0, 'light': 0}

        hue = stats.get_hue_distribution()
        assert all(count == 0 for count in hue.values())

        saturation = stats.get_saturation_distribution()
        assert saturation == {'muted': 0, 'moderate': 0, 'saturated': 0, 'vibrant': 0}

        freshness = stats.get_freshness_distribution()
        assert freshness == {'never_shown': 0, 'rarely_shown': 0, 'often_shown': 0, 'frequently_shown': 0}

        # No gaps in empty database
        gaps = stats.get_gaps()
        assert gaps == []

    def test_images_without_palettes(self, stats, db):
        """Test that images without palettes don't affect color stats."""
        # Add images without palettes
        for i in range(5):
            record = ImageRecord(
                filepath=f'/test/image{i}.jpg',
                filename=f'image{i}.jpg',
                times_shown=0
            )
            db.upsert_image(record)

        # Color stats should be zero
        lightness = stats.get_lightness_distribution()
        assert all(count == 0 for count in lightness.values())

        # But freshness stats should work (uses images table)
        freshness = stats.get_freshness_distribution()
        assert freshness['never_shown'] == 5
        assert freshness['rarely_shown'] == 0

    def test_get_all_stats_structure(self, stats, db):
        """Test that get_all_stats returns expected structure."""
        all_stats = stats.get_all_stats()

        # Check all required keys are present
        assert 'total_images' in all_stats
        assert 'total_with_palettes' in all_stats
        assert 'lightness_distribution' in all_stats
        assert 'hue_distribution' in all_stats
        assert 'saturation_distribution' in all_stats
        assert 'freshness_distribution' in all_stats
        assert 'lightness_summary' in all_stats
        assert 'hue_summary' in all_stats
        assert 'saturation_summary' in all_stats
        assert 'freshness_summary' in all_stats
        assert 'gaps' in all_stats


class TestCaching:
    """Test caching behavior."""

    def test_cache_invalidation(self, stats, db):
        """Test that cache invalidation works."""
        # Add an image with palette
        img = ImageRecord(filepath='/test/img.jpg', filename='img.jpg')
        db.upsert_image(img)

        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.1,
            avg_saturation=0.5,
            avg_hue=200
        )
        db.upsert_palette(palette)

        # First call should populate cache
        lightness1 = stats.get_lightness_distribution()
        assert lightness1['dark'] == 1

        # Manually modify database
        palette.avg_lightness = 0.9  # Change from dark to light
        db.upsert_palette(palette)

        # Without invalidation, cache should return old value
        lightness2 = stats.get_lightness_distribution()
        assert lightness2 == lightness1  # Still cached

        # After invalidation, should get new value
        stats.invalidate()
        lightness3 = stats.get_lightness_distribution()
        assert lightness3['light'] == 1
        assert lightness3['dark'] == 0

    def test_cache_revalidation(self, stats, db):
        """Test that cache is revalidated after invalidation."""
        # Add image
        img = ImageRecord(filepath='/test/img.jpg', filename='img.jpg')
        db.upsert_image(img)

        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.5,
            avg_saturation=0.5,
            avg_hue=100
        )
        db.upsert_palette(palette)

        # Populate cache
        stats.get_lightness_distribution()
        assert stats._cache_valid

        # Invalidate
        stats.invalidate()
        assert not stats._cache_valid

        # Next call should repopulate cache
        stats.get_lightness_distribution()
        assert stats._cache_valid


class TestGapDetection:
    """Test gap detection logic."""

    def test_no_gaps_with_balanced_distribution(self, stats, db):
        """Test that balanced distributions have no gaps."""
        # Add images across all lightness, saturation, and hue buckets (balanced)
        # 20 images per lightness bucket, 20 per saturation bucket
        lightness_values = [0.1, 0.35, 0.65, 0.85]
        saturation_values = [0.1, 0.35, 0.65, 0.85]
        hue_values = [5, 30, 60, 120, 180, 225, 270, 315]  # Cover all hue families

        i = 0
        # Cycle through different saturation and hue values to balance
        for lightness in lightness_values:
            for _ in range(20):
                img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
                db.upsert_image(img)

                palette = PaletteRecord(
                    filepath=f'/test/img{i}.jpg',
                    avg_lightness=lightness,
                    avg_saturation=saturation_values[i % len(saturation_values)],
                    avg_hue=hue_values[i % len(hue_values)]
                )
                db.upsert_palette(palette)
                i += 1

        gaps = stats.get_gaps()
        # Should have no gaps since we balanced all distributions
        assert gaps == []

    def test_gap_detection_for_missing_category(self, stats, db):
        """Test gap detection when a category is completely missing."""
        # Add only dark images (no light, medium-dark, medium-light)
        for i in range(20):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.1,  # All dark
                avg_saturation=0.5,
                avg_hue=180
            )
            db.upsert_palette(palette)

        gaps = stats.get_gaps()

        # Should detect missing categories
        assert any('No medium-dark' in gap for gap in gaps)
        assert any('No medium-light' in gap for gap in gaps)
        assert any('No light' in gap for gap in gaps)

    def test_gap_detection_for_underrepresented_category(self, stats, db):
        """Test gap detection for categories under 5%."""
        # Add 100 images: 96 dark, 4 light (4% < 5% threshold)
        for i in range(96):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.1,  # Dark
                avg_saturation=0.5,
                avg_hue=180
            )
            db.upsert_palette(palette)

        for i in range(96, 100):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.9,  # Light
                avg_saturation=0.5,
                avg_hue=180
            )
            db.upsert_palette(palette)

        gaps = stats.get_gaps()

        # Should detect light as underrepresented (4%)
        assert any('4% light' in gap for gap in gaps)

    def test_gap_detection_hue_families(self, stats, db):
        """Test gap detection for missing hue families."""
        # Add 20 blue images, nothing else
        for i in range(20):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.5,
                avg_saturation=0.5,  # High enough to not be neutral
                avg_hue=220  # Blue
            )
            db.upsert_palette(palette)

        gaps = stats.get_gaps()

        # Should detect missing color families
        assert any('No red' in gap for gap in gaps)
        assert any('No green' in gap for gap in gaps)
        assert any('No purple' in gap for gap in gaps)

    def test_gap_detection_ignores_neutral(self, stats, db):
        """Test that neutral/grayscale is not reported as a gap."""
        # Add only saturated images (no neutral)
        for i in range(20):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.5,
                avg_saturation=0.8,  # High saturation (not neutral)
                avg_hue=180
            )
            db.upsert_palette(palette)

        gaps = stats.get_gaps()

        # "No neutral" should not be in gaps (neutral is optional)
        assert not any('neutral' in gap.lower() for gap in gaps)


class TestSummaryGeneration:
    """Test summary text generation."""

    def test_lightness_summary_dominant(self, stats, db):
        """Test lightness summary when one bucket is dominant."""
        # Add 100 images: 80 dark, 20 light
        for i in range(80):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)
            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.1
            )
            db.upsert_palette(palette)

        for i in range(80, 100):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)
            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=0.9
            )
            db.upsert_palette(palette)

        all_stats = stats.get_all_stats()
        summary = all_stats['lightness_summary']

        # Should mention "dark" and percentage
        assert 'dark' in summary
        assert '80%' in summary

    def test_hue_summary_dominant_colors(self, stats, db):
        """Test hue summary shows top 2 colors."""
        # Add 100 images: 40 blue, 30 green, 30 other colors
        for i in range(40):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)
            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_saturation=0.5,
                avg_hue=220  # Blue
            )
            db.upsert_palette(palette)

        for i in range(40, 70):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)
            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_saturation=0.5,
                avg_hue=100  # Green
            )
            db.upsert_palette(palette)

        for i in range(70, 100):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)
            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_saturation=0.5,
                avg_hue=30  # Orange
            )
            db.upsert_palette(palette)

        all_stats = stats.get_all_stats()
        summary = all_stats['hue_summary']

        # Should mention blue (top 1) and either green or orange (top 2)
        # Since blue=40, green=30, orange=30, top 2 will be blue and orange
        assert 'Blue' in summary or 'blue' in summary
        assert ('Green' in summary or 'green' in summary or
                'Orange' in summary or 'orange' in summary)

    def test_freshness_summary_never_shown(self, stats, db):
        """Test freshness summary highlights never shown count."""
        # Add 50 images: 30 never shown, 20 shown once
        for i in range(30):
            img = ImageRecord(
                filepath=f'/test/img{i}.jpg',
                filename=f'img{i}.jpg',
                times_shown=0
            )
            db.upsert_image(img)

        for i in range(30, 50):
            img = ImageRecord(
                filepath=f'/test/img{i}.jpg',
                filename=f'img{i}.jpg',
                times_shown=1
            )
            db.upsert_image(img)

        all_stats = stats.get_all_stats()
        summary = all_stats['freshness_summary']

        # Should mention "30 wallpapers never shown"
        assert '30' in summary
        assert 'never shown' in summary

    def test_summary_empty_database(self, stats, db):
        """Test summaries for empty database."""
        all_stats = stats.get_all_stats()

        # All summaries should gracefully handle empty state
        assert all_stats['lightness_summary'] is not None
        assert all_stats['hue_summary'] is not None
        assert all_stats['saturation_summary'] is not None
        assert all_stats['freshness_summary'] is not None


class TestDistributions:
    """Test distribution calculations."""

    def test_lightness_buckets(self, stats, db):
        """Test lightness bucket boundaries."""
        # Test each bucket boundary
        test_cases = [
            (0.0, 'dark'),
            (0.24, 'dark'),
            (0.25, 'medium_dark'),
            (0.49, 'medium_dark'),
            (0.50, 'medium_light'),
            (0.74, 'medium_light'),
            (0.75, 'light'),
            (1.0, 'light'),
        ]

        for i, (lightness, expected_bucket) in enumerate(test_cases):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_lightness=lightness
            )
            db.upsert_palette(palette)

        stats.invalidate()
        distribution = stats.get_lightness_distribution()

        # Each bucket should have exactly 2 images (one at min, one near max)
        assert distribution['dark'] == 2
        assert distribution['medium_dark'] == 2
        assert distribution['medium_light'] == 2
        assert distribution['light'] == 2

    def test_hue_families(self, stats, db):
        """Test hue family boundaries."""
        # Test each hue family
        test_cases = [
            (5, 'red'),      # Red range 1
            (350, 'red'),    # Red range 2
            (30, 'orange'),
            (60, 'yellow'),
            (120, 'green'),
            (180, 'cyan'),
            (225, 'blue'),
            (270, 'purple'),
            (315, 'pink'),
        ]

        for i, (hue, expected_family) in enumerate(test_cases):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_saturation=0.5,  # High enough to not be neutral
                avg_hue=hue
            )
            db.upsert_palette(palette)

        stats.invalidate()
        distribution = stats.get_hue_distribution()

        # Check each family got its image
        assert distribution['red'] == 2  # Two red ranges
        assert distribution['orange'] == 1
        assert distribution['yellow'] == 1
        assert distribution['green'] == 1
        assert distribution['cyan'] == 1
        assert distribution['blue'] == 1
        assert distribution['purple'] == 1
        assert distribution['pink'] == 1

    def test_neutral_grayscale(self, stats, db):
        """Test that low saturation images are categorized as neutral."""
        # Add images with very low saturation
        for i in range(10):
            img = ImageRecord(filepath=f'/test/img{i}.jpg', filename=f'img{i}.jpg')
            db.upsert_image(img)

            palette = PaletteRecord(
                filepath=f'/test/img{i}.jpg',
                avg_saturation=0.05,  # Very low saturation
                avg_hue=180  # Hue doesn't matter for grayscale
            )
            db.upsert_palette(palette)

        distribution = stats.get_hue_distribution()

        # All should be neutral
        assert distribution['neutral'] == 10
        assert distribution['cyan'] == 0  # Not cyan despite hue=180

    def test_freshness_ranges(self, stats, db):
        """Test freshness category ranges."""
        # Test each freshness category
        test_cases = [
            (0, 'never_shown'),
            (1, 'rarely_shown'),
            (4, 'rarely_shown'),
            (5, 'often_shown'),
            (9, 'often_shown'),
            (10, 'frequently_shown'),
            (100, 'frequently_shown'),
        ]

        for i, (times_shown, expected_category) in enumerate(test_cases):
            img = ImageRecord(
                filepath=f'/test/img{i}.jpg',
                filename=f'img{i}.jpg',
                times_shown=times_shown
            )
            db.upsert_image(img)

        distribution = stats.get_freshness_distribution()

        assert distribution['never_shown'] == 1
        assert distribution['rarely_shown'] == 2
        assert distribution['often_shown'] == 2
        assert distribution['frequently_shown'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
