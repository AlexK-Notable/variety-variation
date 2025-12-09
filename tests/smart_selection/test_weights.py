#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.weights - Weight calculation strategies."""

import time
import unittest


class TestRecencyFactor(unittest.TestCase):
    """Tests for recency_factor calculation."""

    def test_import_recency_factor(self):
        """recency_factor can be imported from weights module."""
        from variety.smart_selection.weights import recency_factor
        self.assertIsNotNone(recency_factor)

    def test_never_shown_returns_one(self):
        """Image never shown (last_shown_at=None) returns factor of 1.0."""
        from variety.smart_selection.weights import recency_factor

        factor = recency_factor(last_shown_at=None, cooldown_days=7)
        self.assertEqual(factor, 1.0)

    def test_shown_today_returns_zero(self):
        """Image shown just now returns factor close to 0."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        factor = recency_factor(last_shown_at=now, cooldown_days=7)
        self.assertLess(factor, 0.1)

    def test_shown_after_cooldown_returns_one(self):
        """Image shown after cooldown period returns factor of 1.0."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        eight_days_ago = now - (8 * 24 * 60 * 60)
        factor = recency_factor(last_shown_at=eight_days_ago, cooldown_days=7)
        self.assertEqual(factor, 1.0)

    def test_shown_halfway_cooldown_partial_factor(self):
        """Image shown halfway through cooldown returns partial factor."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        half_cooldown_ago = now - (3.5 * 24 * 60 * 60)  # 3.5 days for 7-day cooldown
        factor = recency_factor(last_shown_at=int(half_cooldown_ago), cooldown_days=7)
        self.assertGreater(factor, 0.3)
        self.assertLess(factor, 0.7)

    def test_exponential_decay(self):
        """Exponential decay produces smooth curve."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        factors = []
        for days in range(8):
            shown_at = now - (days * 24 * 60 * 60)
            f = recency_factor(last_shown_at=shown_at, cooldown_days=7, decay='exponential')
            factors.append(f)

        # Should increase over time
        for i in range(len(factors) - 1):
            self.assertLessEqual(factors[i], factors[i + 1])

    def test_linear_decay(self):
        """Linear decay produces straight line increase."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        one_day_ago = now - (1 * 24 * 60 * 60)
        two_days_ago = now - (2 * 24 * 60 * 60)

        f1 = recency_factor(last_shown_at=one_day_ago, cooldown_days=7, decay='linear')
        f2 = recency_factor(last_shown_at=two_days_ago, cooldown_days=7, decay='linear')

        # Linear: difference should be proportional
        self.assertAlmostEqual(f2 - f1, 1/7, places=2)

    def test_step_decay(self):
        """Step decay returns 0 before cooldown, 1 after."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        six_days_ago = now - (6 * 24 * 60 * 60)
        eight_days_ago = now - (8 * 24 * 60 * 60)

        f_before = recency_factor(last_shown_at=six_days_ago, cooldown_days=7, decay='step')
        f_after = recency_factor(last_shown_at=eight_days_ago, cooldown_days=7, decay='step')

        self.assertEqual(f_before, 0.0)
        self.assertEqual(f_after, 1.0)

    def test_zero_cooldown_always_returns_one(self):
        """Zero cooldown days means no penalty, always returns 1.0."""
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        factor = recency_factor(last_shown_at=now, cooldown_days=0)
        self.assertEqual(factor, 1.0)


class TestSourceFactor(unittest.TestCase):
    """Tests for source_factor calculation."""

    def test_import_source_factor(self):
        """source_factor can be imported from weights module."""
        from variety.smart_selection.weights import source_factor
        self.assertIsNotNone(source_factor)

    def test_source_never_shown_returns_one(self):
        """Source never shown returns factor of 1.0."""
        from variety.smart_selection.weights import source_factor

        factor = source_factor(last_shown_at=None, cooldown_days=1)
        self.assertEqual(factor, 1.0)

    def test_source_shown_recently_returns_low_factor(self):
        """Source shown recently returns low factor."""
        from variety.smart_selection.weights import source_factor

        now = int(time.time())
        factor = source_factor(last_shown_at=now, cooldown_days=1)
        self.assertLess(factor, 0.2)

    def test_source_shown_after_cooldown_returns_one(self):
        """Source shown after cooldown returns 1.0."""
        from variety.smart_selection.weights import source_factor

        now = int(time.time())
        two_days_ago = now - (2 * 24 * 60 * 60)
        factor = source_factor(last_shown_at=two_days_ago, cooldown_days=1)
        self.assertEqual(factor, 1.0)


class TestBoostFactors(unittest.TestCase):
    """Tests for favorite_boost and new_image_boost."""

    def test_import_favorite_boost(self):
        """favorite_boost can be imported."""
        from variety.smart_selection.weights import favorite_boost
        self.assertIsNotNone(favorite_boost)

    def test_favorite_boost_for_favorite(self):
        """Favorite images get the boost multiplier."""
        from variety.smart_selection.weights import favorite_boost

        boost = favorite_boost(is_favorite=True, boost_value=2.0)
        self.assertEqual(boost, 2.0)

    def test_favorite_boost_for_non_favorite(self):
        """Non-favorite images get 1.0 (no boost)."""
        from variety.smart_selection.weights import favorite_boost

        boost = favorite_boost(is_favorite=False, boost_value=2.0)
        self.assertEqual(boost, 1.0)

    def test_import_new_image_boost(self):
        """new_image_boost can be imported."""
        from variety.smart_selection.weights import new_image_boost
        self.assertIsNotNone(new_image_boost)

    def test_new_image_boost_for_never_shown(self):
        """Never-shown images (times_shown=0) get the boost."""
        from variety.smart_selection.weights import new_image_boost

        boost = new_image_boost(times_shown=0, boost_value=1.5)
        self.assertEqual(boost, 1.5)

    def test_new_image_boost_for_shown_image(self):
        """Previously shown images get 1.0 (no boost)."""
        from variety.smart_selection.weights import new_image_boost

        boost = new_image_boost(times_shown=5, boost_value=1.5)
        self.assertEqual(boost, 1.0)


class TestCalculateWeight(unittest.TestCase):
    """Tests for combined weight calculation."""

    def test_import_calculate_weight(self):
        """calculate_weight can be imported."""
        from variety.smart_selection.weights import calculate_weight
        self.assertIsNotNone(calculate_weight)

    def test_calculate_weight_with_defaults(self):
        """calculate_weight works with ImageRecord and default config."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        image = ImageRecord(
            filepath='/test/img.jpg',
            filename='img.jpg',
            is_favorite=False,
            times_shown=0,
            last_shown_at=None,
        )
        config = SelectionConfig()

        weight = calculate_weight(image, source_last_shown_at=None, config=config)

        # New, never-shown, non-favorite image should have positive weight
        self.assertGreater(weight, 0)

    def test_calculate_weight_favorite_higher(self):
        """Favorite images have higher weight than non-favorites."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(favorite_boost=2.0)

        regular = ImageRecord(filepath='/test/regular.jpg', filename='regular.jpg',
                              is_favorite=False, times_shown=0)
        favorite = ImageRecord(filepath='/test/fav.jpg', filename='fav.jpg',
                               is_favorite=True, times_shown=0)

        w_regular = calculate_weight(regular, source_last_shown_at=None, config=config)
        w_favorite = calculate_weight(favorite, source_last_shown_at=None, config=config)

        self.assertGreater(w_favorite, w_regular)
        self.assertAlmostEqual(w_favorite / w_regular, 2.0, places=1)

    def test_calculate_weight_new_image_higher(self):
        """New images have higher weight than previously shown."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(new_image_boost=1.5)

        old = ImageRecord(filepath='/test/old.jpg', filename='old.jpg',
                          times_shown=10, last_shown_at=None)
        new = ImageRecord(filepath='/test/new.jpg', filename='new.jpg',
                          times_shown=0, last_shown_at=None)

        w_old = calculate_weight(old, source_last_shown_at=None, config=config)
        w_new = calculate_weight(new, source_last_shown_at=None, config=config)

        self.assertGreater(w_new, w_old)

    def test_calculate_weight_recently_shown_lower(self):
        """Recently shown images have lower weight."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(image_cooldown_days=7)
        now = int(time.time())

        recent = ImageRecord(filepath='/test/recent.jpg', filename='recent.jpg',
                             times_shown=1, last_shown_at=now)
        old = ImageRecord(filepath='/test/old.jpg', filename='old.jpg',
                          times_shown=1, last_shown_at=now - (10 * 24 * 60 * 60))

        w_recent = calculate_weight(recent, source_last_shown_at=None, config=config)
        w_old = calculate_weight(old, source_last_shown_at=None, config=config)

        self.assertLess(w_recent, w_old)

    def test_calculate_weight_source_cooldown(self):
        """Images from recently shown sources have lower weight."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(source_cooldown_days=1)
        now = int(time.time())

        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg',
                            times_shown=1, last_shown_at=None)

        w_recent_source = calculate_weight(image, source_last_shown_at=now, config=config)
        w_old_source = calculate_weight(image, source_last_shown_at=now - (2 * 24 * 60 * 60),
                                        config=config)

        self.assertLess(w_recent_source, w_old_source)

    def test_calculate_weight_combines_factors(self):
        """Weight combines all factors multiplicatively."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(
            favorite_boost=2.0,
            new_image_boost=1.5,
            image_cooldown_days=7,
            source_cooldown_days=1,
        )

        # Optimal case: favorite, never shown, no recent activity
        optimal = ImageRecord(filepath='/test/optimal.jpg', filename='optimal.jpg',
                              is_favorite=True, times_shown=0, last_shown_at=None)

        # Worst case: not favorite, shown many times, just shown, source just used
        now = int(time.time())
        worst = ImageRecord(filepath='/test/worst.jpg', filename='worst.jpg',
                            is_favorite=False, times_shown=100, last_shown_at=now)

        w_optimal = calculate_weight(optimal, source_last_shown_at=None, config=config)
        w_worst = calculate_weight(worst, source_last_shown_at=now, config=config)

        # Optimal should be much higher (avoid division by near-zero)
        self.assertGreater(w_optimal, 1.0)  # Should have boosts
        self.assertLess(w_worst, 0.01)  # Should be heavily penalized
        self.assertGreater(w_optimal, w_worst * 100)  # Order of magnitude difference


class TestWeightDisabled(unittest.TestCase):
    """Tests for behavior when smart selection is disabled."""

    def test_calculate_weight_returns_one_when_disabled(self):
        """When config.enabled=False, all weights return 1.0."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(enabled=False)

        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg',
                            is_favorite=True, times_shown=0, last_shown_at=None)

        weight = calculate_weight(image, source_last_shown_at=None, config=config)
        self.assertEqual(weight, 1.0)


class TestNegativeTimeGuard(unittest.TestCase):
    """Tests for handling backward clock jumps (negative elapsed time)."""

    def test_future_timestamp_handled_gracefully(self):
        """Image with future timestamp (clock jumped back) returns valid factor.

        If system clock jumps backward, last_shown_at could be in the "future"
        relative to current time. This must not produce negative weights or
        cause math errors.
        """
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        future_timestamp = now + (24 * 60 * 60)  # 1 day in future

        factor = recency_factor(last_shown_at=future_timestamp, cooldown_days=7)

        # Should return a valid factor (clamped to just-shown behavior)
        self.assertGreaterEqual(factor, 0.0)
        self.assertLessEqual(factor, 1.0)

    def test_negative_elapsed_time_returns_minimum_factor(self):
        """Negative elapsed time (future timestamp) returns factor close to 0.

        When elapsed_seconds would be negative, the image should be treated
        as "just shown" (minimum factor) rather than causing math errors.
        """
        from variety.smart_selection.weights import recency_factor

        now = int(time.time())
        far_future = now + (30 * 24 * 60 * 60)  # 30 days in future

        factor = recency_factor(last_shown_at=far_future, cooldown_days=7)

        # Should be treated as just-shown (very low factor)
        self.assertLess(factor, 0.1)


class TestMinimumWeightFloor(unittest.TestCase):
    """Tests for minimum weight floor to prevent zero-weight collapse."""

    def test_weight_never_zero(self):
        """Combined weight should never be exactly zero.

        When all factors multiply to zero, a minimum floor should be applied
        to prevent the selection algorithm from degenerating to uniform random.
        """
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig

        # Worst case: just shown, source just used, step decay (returns 0)
        config = SelectionConfig(
            image_cooldown_days=7,
            source_cooldown_days=1,
            recency_decay='step',  # Returns exactly 0 before cooldown
        )
        now = int(time.time())

        image = ImageRecord(
            filepath='/test/worst.jpg',
            filename='worst.jpg',
            is_favorite=False,
            times_shown=100,
            last_shown_at=now,
        )

        weight = calculate_weight(image, source_last_shown_at=now, config=config)

        # Weight should be positive (minimum floor applied)
        self.assertGreater(weight, 0)

    def test_weight_is_finite(self):
        """Weight should never be NaN or infinite."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord
        from variety.smart_selection.config import SelectionConfig
        import math

        config = SelectionConfig(
            favorite_boost=1000.0,  # Extreme boost
            new_image_boost=1000.0,
        )

        image = ImageRecord(
            filepath='/test/boosted.jpg',
            filename='boosted.jpg',
            is_favorite=True,
            times_shown=0,
            last_shown_at=None,
        )

        weight = calculate_weight(image, source_last_shown_at=None, config=config)

        self.assertTrue(math.isfinite(weight))
        self.assertGreater(weight, 0)


class TestColorAffinityFactor(unittest.TestCase):
    """Tests for color_affinity_factor calculation."""

    def test_import_color_affinity_factor(self):
        """color_affinity_factor can be imported from weights module."""
        from variety.smart_selection.weights import color_affinity_factor
        self.assertIsNotNone(color_affinity_factor)

    def test_returns_neutral_without_target_palette(self):
        """Returns 1.0 when target_palette is None."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)

        affinity = color_affinity_factor(palette, target_palette=None, config=config)
        self.assertEqual(affinity, 1.0)

    def test_returns_neutral_when_color_matching_disabled(self):
        """Returns 1.0 when color_match_weight is 0."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=0.0)
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)
        target = {'avg_hue': 0, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        affinity = color_affinity_factor(palette, target_palette=target, config=config)
        self.assertEqual(affinity, 1.0)

    def test_returns_penalty_for_missing_palette(self):
        """Returns 0.8 when image has no palette data."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        target = {'avg_hue': 180, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        affinity = color_affinity_factor(image_palette=None, target_palette=target,
                                         config=config)
        self.assertEqual(affinity, 0.8)

    def test_returns_boost_for_identical_palettes(self):
        """Returns boost > 1.0 for identical palettes."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)
        target = {'avg_hue': 180, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        affinity = color_affinity_factor(palette, target_palette=target, config=config)
        self.assertGreater(affinity, 1.5)  # Should get strong boost

    def test_returns_penalty_for_dissimilar_palettes(self):
        """Returns penalty < 1.0 for very different palettes."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        # Bright, warm palette
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=30,
                                avg_saturation=0.8, avg_lightness=0.9,
                                color_temperature=0.8)
        # Dark, cool target
        target = {'avg_hue': 210, 'avg_saturation': 0.2,
                  'avg_lightness': 0.1, 'color_temperature': -0.8}

        affinity = color_affinity_factor(palette, target_palette=target, config=config)
        self.assertLess(affinity, 0.5)  # Should get penalty

    def test_affinity_clamped_to_min_max_range(self):
        """Affinity is always between 0.1 and 2.0."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=5.0)  # Extreme weight

        # Perfect match
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)
        target = {'avg_hue': 180, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        affinity = color_affinity_factor(palette, target_palette=target, config=config)
        self.assertLessEqual(affinity, 2.0)
        self.assertGreaterEqual(affinity, 0.1)

    def test_neutral_at_fifty_percent_similarity(self):
        """Returns approximately 1.0 at 50% similarity."""
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        # Palettes with ~50% similarity
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=90,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)
        target = {'avg_hue': 270, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        affinity = color_affinity_factor(palette, target_palette=target, config=config)
        # Should be close to 1.0 (neutral) - allowing some margin
        self.assertGreater(affinity, 0.7)
        self.assertLessEqual(affinity, 1.35)


class TestColorAffinityInCalculateWeight(unittest.TestCase):
    """Tests for color affinity integration in calculate_weight."""

    def test_calculate_weight_with_similar_palette_gets_boost(self):
        """calculate_weight returns higher weight for similar color palette."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord, PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg',
                            times_shown=0)

        # Similar palette
        similar_palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                        avg_saturation=0.5, avg_lightness=0.5,
                                        color_temperature=0.0)
        target = {'avg_hue': 180, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        # Dissimilar palette
        dissimilar_palette = PaletteRecord(filepath='/test/img2.jpg', avg_hue=0,
                                           avg_saturation=0.1, avg_lightness=0.9,
                                           color_temperature=0.8)

        w_similar = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=similar_palette, target_palette=target
        )
        w_dissimilar = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=dissimilar_palette, target_palette=target
        )

        self.assertGreater(w_similar, w_dissimilar)

    def test_calculate_weight_no_palette_penalty(self):
        """calculate_weight applies slight penalty when image has no palette."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord, PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg',
                            times_shown=0)
        target = {'avg_hue': 180, 'avg_saturation': 0.5,
                  'avg_lightness': 0.5, 'color_temperature': 0.0}

        # With palette (similar)
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)
        w_with_palette = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette, target_palette=target
        )

        # Without palette
        w_no_palette = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=None, target_palette=target
        )

        # Weight with similar palette should be higher
        self.assertGreater(w_with_palette, w_no_palette)

    def test_calculate_weight_color_affinity_neutral_without_target(self):
        """calculate_weight is unaffected when no target palette specified."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord, PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg',
                            times_shown=0)
        palette = PaletteRecord(filepath='/test/img.jpg', avg_hue=180,
                                avg_saturation=0.5, avg_lightness=0.5,
                                color_temperature=0.0)

        w_with_target = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette, target_palette={'avg_hue': 180,
                                                   'avg_saturation': 0.5,
                                                   'avg_lightness': 0.5,
                                                   'color_temperature': 0.0}
        )
        w_no_target = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette, target_palette=None
        )

        # Without target, color affinity is neutral (1.0)
        # With identical target, should get boost
        self.assertGreater(w_with_target, w_no_target)


if __name__ == '__main__':
    unittest.main()
