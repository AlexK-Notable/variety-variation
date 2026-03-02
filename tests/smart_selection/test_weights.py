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


class TestCalculateTimeAffinity(unittest.TestCase):
    """Tests for calculate_time_affinity calculation."""

    def test_import_calculate_time_affinity(self):
        """calculate_time_affinity can be imported from weights module."""
        from variety.smart_selection.weights import calculate_time_affinity
        self.assertIsNotNone(calculate_time_affinity)

    def test_returns_neutral_without_palette(self):
        """Returns 1.0 when image_palette is None."""
        from variety.smart_selection.weights import calculate_time_affinity

        affinity = calculate_time_affinity(
            image_palette=None,
            target_lightness=0.5,
            target_temperature=0.0,
            target_saturation=0.5,
        )
        self.assertEqual(affinity, 1.0)

    def test_returns_boost_for_perfect_match(self):
        """Returns max boost (3.0 at strength=2.0) for perfect palette match."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.6,
            color_temperature=0.0,
            avg_saturation=0.5,
        )

        affinity = calculate_time_affinity(
            image_palette=palette,
            target_lightness=0.6,
            target_temperature=0.0,
            target_saturation=0.5,
        )
        # At strength=2.0 (default): max_mult = 1.0 + strength = 3.0
        self.assertEqual(affinity, 3.0)

    def test_returns_penalty_for_poor_match(self):
        """Returns min penalty (~0.33 at strength=2.0) for poor palette match."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        # Bright, warm palette
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.9,
            color_temperature=0.8,
            avg_saturation=0.8,
        )

        # Target is dark, cool
        affinity = calculate_time_affinity(
            image_palette=palette,
            target_lightness=0.2,
            target_temperature=-0.5,
            target_saturation=0.3,
            tolerance=0.3,
        )
        # At strength=2.0 (default): min_mult = 1.0 / (1.0 + strength) = 0.333...
        self.assertAlmostEqual(affinity, 0.333, places=2)

    def test_returns_intermediate_for_partial_match(self):
        """Returns intermediate value for partial match."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.5,
            color_temperature=0.0,
            avg_saturation=0.5,
        )

        # Slightly different target
        affinity = calculate_time_affinity(
            image_palette=palette,
            target_lightness=0.6,  # +0.1 difference
            target_temperature=0.0,
            target_saturation=0.5,
            tolerance=0.3,
        )
        # At strength=2.0: range is 0.33 to 3.0
        # Should be between min and max, but not at extremes
        self.assertGreater(affinity, 0.33)
        self.assertLess(affinity, 3.0)

    def test_lightness_weighted_more_heavily(self):
        """Lightness differences have more impact than other dimensions."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        target_l, target_t, target_s = 0.5, 0.0, 0.5

        # Palette with lightness difference
        palette_lightness_diff = PaletteRecord(
            filepath='/test/img1.jpg',
            avg_lightness=0.7,  # +0.2 difference
            color_temperature=0.0,
            avg_saturation=0.5,
        )

        # Palette with temperature difference (same magnitude)
        palette_temp_diff = PaletteRecord(
            filepath='/test/img2.jpg',
            avg_lightness=0.5,
            color_temperature=0.2,  # +0.2 difference
            avg_saturation=0.5,
        )

        affinity_lightness = calculate_time_affinity(
            palette_lightness_diff, target_l, target_t, target_s
        )
        affinity_temp = calculate_time_affinity(
            palette_temp_diff, target_l, target_t, target_s
        )

        # Lightness diff should have more impact (lower affinity)
        self.assertLess(affinity_lightness, affinity_temp)

    def test_tolerance_affects_sensitivity(self):
        """Lower tolerance means stricter matching."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.6,
            color_temperature=0.1,
            avg_saturation=0.4,
        )

        # Same target, different tolerances
        affinity_loose = calculate_time_affinity(
            image_palette=palette,
            target_lightness=0.5,
            target_temperature=0.0,
            target_saturation=0.5,
            tolerance=0.5,  # Loose
        )

        affinity_strict = calculate_time_affinity(
            image_palette=palette,
            target_lightness=0.5,
            target_temperature=0.0,
            target_saturation=0.5,
            tolerance=0.1,  # Strict
        )

        # Loose tolerance should give higher affinity for same difference
        self.assertGreater(affinity_loose, affinity_strict)

    def test_clamped_to_valid_range(self):
        """Affinity is always between min (0.33) and max (3.0) at strength=2.0."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        # Test extreme match
        perfect_palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.5,
            color_temperature=0.0,
            avg_saturation=0.5,
        )
        affinity_perfect = calculate_time_affinity(
            perfect_palette, 0.5, 0.0, 0.5
        )
        # At strength=2.0: range is 0.33 to 3.0
        self.assertLessEqual(affinity_perfect, 3.0)
        self.assertGreaterEqual(affinity_perfect, 0.33)

        # Test extreme mismatch
        opposite_palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=1.0,
            color_temperature=1.0,
            avg_saturation=1.0,
        )
        affinity_opposite = calculate_time_affinity(
            opposite_palette, 0.0, -1.0, 0.0
        )
        self.assertLessEqual(affinity_opposite, 3.0)
        self.assertGreaterEqual(affinity_opposite, 0.33)

    def test_handles_none_palette_metrics(self):
        """Handles palette with None values by using neutral defaults."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        # Palette with no metrics (all None)
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=None,
            color_temperature=None,
            avg_saturation=None,
        )

        # Should not raise an error
        affinity = calculate_time_affinity(
            image_palette=palette,
            target_lightness=0.5,
            target_temperature=0.0,
            target_saturation=0.5,
        )
        # Should return a valid value within the strength=2.0 range (0.33 to 3.0)
        self.assertGreaterEqual(affinity, 0.33)
        self.assertLessEqual(affinity, 3.0)


class TestTimeAffinityInCalculateWeight(unittest.TestCase):
    """Tests for time affinity integration in calculate_weight."""

    def test_calculate_weight_with_time_targets(self):
        """calculate_weight applies time affinity when targets provided."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord, PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(time_adaptation_enabled=True)
        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg', times_shown=0)

        # Matching palette
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.6,
            color_temperature=0.0,
            avg_saturation=0.5,
        )

        # Weight with time targets matching the palette
        w_matching = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette,
            time_target_lightness=0.6,
            time_target_temperature=0.0,
            time_target_saturation=0.5,
        )

        # Weight with time targets not matching
        w_not_matching = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette,
            time_target_lightness=0.2,
            time_target_temperature=-0.5,
            time_target_saturation=0.3,
        )

        self.assertGreater(w_matching, w_not_matching)

    def test_calculate_weight_no_time_targets_neutral(self):
        """calculate_weight returns neutral when time targets not provided."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord, PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(time_adaptation_enabled=True)
        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg', times_shown=0)
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.9,  # Extreme value
            color_temperature=0.8,
            avg_saturation=0.8,
        )

        # Without time targets
        w_no_targets = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette,
        )

        # With time targets = None (some None)
        w_partial_targets = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette,
            time_target_lightness=0.5,
            time_target_temperature=None,  # Missing one
            time_target_saturation=0.5,
        )

        # Both should be equal (no time affinity applied)
        self.assertEqual(w_no_targets, w_partial_targets)

    def test_calculate_weight_time_adaptation_disabled(self):
        """calculate_weight ignores time targets when adaptation disabled."""
        from variety.smart_selection.weights import calculate_weight
        from variety.smart_selection.models import ImageRecord, PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(time_adaptation_enabled=False)
        image = ImageRecord(filepath='/test/img.jpg', filename='img.jpg', times_shown=0)
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.9,
            color_temperature=0.8,
            avg_saturation=0.8,
        )

        # With mismatched targets (but adaptation disabled)
        w_with_targets = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette,
            time_target_lightness=0.2,
            time_target_temperature=-0.5,
            time_target_saturation=0.3,
        )

        # Without targets
        w_without_targets = calculate_weight(
            image, source_last_shown_at=None, config=config,
            image_palette=palette,
        )

        # Should be equal (time affinity not applied when disabled)
        self.assertEqual(w_with_targets, w_without_targets)


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


class TestTimeAffinityPerceivedBrightness(unittest.TestCase):
    """Tests that calculate_time_affinity prefers perceived_brightness.

    Layer 3: when a PaletteRecord has perceived_brightness set, it should
    be used instead of avg_lightness for the lightness component of time
    affinity. This gives more accurate day/night selection based on actual
    image pixel brightness rather than palette-derived BT.709 average.
    """

    def test_prefers_perceived_brightness_over_avg_lightness(self):
        """Uses perceived_brightness when available, not avg_lightness."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        # Image where perceived_brightness (0.2 = dark) disagrees with
        # avg_lightness (0.8 = bright). This can happen when a wallpaper
        # has a few bright accent colors but is mostly dark.
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.8,
            perceived_brightness=0.2,
            color_temperature=0.0,
            avg_saturation=0.5,
        )

        # Target wants dark (0.1) — should match perceived_brightness (0.2)
        affinity_dark_target = calculate_time_affinity(
            palette, target_lightness=0.1,
            target_temperature=0.0, target_saturation=0.5,
        )

        # Target wants bright (0.9) — should NOT match perceived_brightness (0.2)
        affinity_bright_target = calculate_time_affinity(
            palette, target_lightness=0.9,
            target_temperature=0.0, target_saturation=0.5,
        )

        # Dark target should score higher (perceived_brightness=0.2 is closer to 0.1)
        self.assertGreater(
            affinity_dark_target, affinity_bright_target,
            f"Dark target ({affinity_dark_target:.3f}) should score higher than "
            f"bright target ({affinity_bright_target:.3f}) for image with "
            f"perceived_brightness=0.2 (avg_lightness=0.8 should be ignored)"
        )

    def test_falls_back_to_avg_lightness(self):
        """Falls back to avg_lightness when perceived_brightness is None."""
        from variety.smart_selection.weights import calculate_time_affinity
        from variety.smart_selection.models import PaletteRecord

        # No perceived_brightness — should use avg_lightness (0.8)
        palette = PaletteRecord(
            filepath='/test/img.jpg',
            avg_lightness=0.8,
            perceived_brightness=None,
            color_temperature=0.0,
            avg_saturation=0.5,
        )

        # Target wants bright (0.9) — should match avg_lightness (0.8)
        affinity_bright_target = calculate_time_affinity(
            palette, target_lightness=0.9,
            target_temperature=0.0, target_saturation=0.5,
        )

        # Target wants dark (0.1) — should NOT match avg_lightness (0.8)
        affinity_dark_target = calculate_time_affinity(
            palette, target_lightness=0.1,
            target_temperature=0.0, target_saturation=0.5,
        )

        # Bright target should score higher (using avg_lightness=0.8 fallback)
        self.assertGreater(
            affinity_bright_target, affinity_dark_target,
            "Bright target should score higher with avg_lightness=0.8 fallback"
        )


class TestHexToLightnessIsOKLAB(unittest.TestCase):
    """Tests that hex_to_lightness in weights.py uses OKLAB L.

    Both hex_to_lightness (weights) and hex_to_luminance (palette)
    delegate to get_oklab_lightness from color_science.
    """

    def test_yellow_bright_blue_below_mid(self):
        """Yellow and blue have dramatically different lightness (not both 0.5)."""
        from variety.smart_selection.weights import hex_to_lightness

        yellow = hex_to_lightness('#FFFF00')
        blue = hex_to_lightness('#0000FF')

        self.assertGreater(yellow, 0.9, "Yellow should be >0.9 with OKLAB")
        self.assertLess(blue, 0.5, "Blue should be <0.5 with OKLAB")

    def test_matches_palette_hex_to_luminance(self):
        """weights.hex_to_lightness matches palette.hex_to_luminance."""
        from variety.smart_selection.weights import hex_to_lightness
        from variety.smart_selection.palette import hex_to_luminance

        test_colors = ['#FF0000', '#00FF00', '#0000FF', '#FFFF00',
                       '#FF00FF', '#00FFFF', '#808080', '#FFFFFF', '#000000']

        for color in test_colors:
            self.assertAlmostEqual(
                hex_to_lightness(color),
                hex_to_luminance(color),
                places=6,
                msg=f"Mismatch for {color}"
            )

    def test_matches_get_oklab_lightness(self):
        """weights.hex_to_lightness matches color_science.get_oklab_lightness."""
        from variety.smart_selection.weights import hex_to_lightness
        from variety.smart_selection.color_science import get_oklab_lightness

        test_colors = ['#FF0000', '#00FF00', '#0000FF', '#808080', '#FFFFFF', '#000000']

        for color in test_colors:
            self.assertAlmostEqual(
                hex_to_lightness(color),
                get_oklab_lightness(color),
                places=6,
                msg=f"Mismatch for {color}"
            )


class TestColorAffinityWithThemePalette(unittest.TestCase):
    """Tests for color_affinity_factor with theme-derived palette dicts.

    Phase 4 of the Reverse Theming Pipeline: theme palette dicts (with
    color0-15 + avg_* metrics) must be accepted by color_affinity_factor()
    and produce meaningful boost/penalty factors.

    Written against the interface defined in plan phase 4.
    """

    def _make_theme_palette(self, **overrides):
        """Create a theme-style palette dict with all expected keys.

        Returns a dict matching ThemeOverride.get_target_palette_for_selection()
        output: color0-15, background, foreground, cursor, and avg_* metrics.
        """
        palette = {
            'color0': '#1a1b26',
            'color1': '#f7768e',
            'color2': '#9ece6a',
            'color3': '#e0af68',
            'color4': '#7aa2f7',
            'color5': '#bb9af7',
            'color6': '#7dcfff',
            'color7': '#c0caf5',
            'color8': '#414868',
            'color9': '#f7768e',
            'color10': '#9ece6a',
            'color11': '#e0af68',
            'color12': '#7aa2f7',
            'color13': '#bb9af7',
            'color14': '#7dcfff',
            'color15': '#c0caf5',
            'background': '#1a1b26',
            'foreground': '#c0caf5',
            'cursor': '#c0caf5',
            'avg_hue': 220.0,
            'avg_saturation': 0.5,
            'avg_lightness': 0.4,
            'color_temperature': -0.3,
        }
        palette.update(overrides)
        return palette

    def test_theme_palette_dict_accepted_without_error(self):
        """Theme palette dict is accepted by color_affinity_factor().

        Bug caught: color_affinity_factor() rejects dict with extra keys
        (color0-15, background, foreground, cursor) beyond avg_* metrics.
        """
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        image_palette = PaletteRecord(
            filepath='/test/img.jpg',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a',
            color3='#e0af68', color4='#7aa2f7', color5='#bb9af7',
            color6='#7dcfff', color7='#c0caf5', color8='#414868',
            color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff',
            color15='#c0caf5', background='#1a1b26',
            foreground='#c0caf5', cursor='#c0caf5',
            avg_hue=220.0, avg_saturation=0.5, avg_lightness=0.4,
            color_temperature=-0.3,
        )
        theme_palette = self._make_theme_palette()

        # Should not raise any exception
        factor = color_affinity_factor(image_palette, theme_palette, config)

        self.assertIsInstance(factor, float)
        self.assertGreater(factor, 0)

    def test_similar_palette_gets_boost(self):
        """Image palette similar to theme palette produces factor > 1.0.

        Bug caught: theme palette dict shape causes similarity calculation
        to return 0 or raises error, resulting in penalty instead of boost.
        """
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)

        # Image palette that closely matches the theme
        similar_palette = PaletteRecord(
            filepath='/test/similar.jpg',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a',
            color3='#e0af68', color4='#7aa2f7', color5='#bb9af7',
            color6='#7dcfff', color7='#c0caf5', color8='#414868',
            color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff',
            color15='#c0caf5', background='#1a1b26',
            foreground='#c0caf5', cursor='#c0caf5',
            avg_hue=220.0, avg_saturation=0.5, avg_lightness=0.4,
            color_temperature=-0.3,
        )
        theme_palette = self._make_theme_palette()

        factor = color_affinity_factor(similar_palette, theme_palette, config)

        self.assertGreater(
            factor, 1.0,
            f"Similar palette should get boost > 1.0, got {factor}"
        )

    def test_dissimilar_palette_scores_lower_than_similar(self):
        """Dissimilar image scores lower than a similar image.

        Bug caught: all images get the same factor regardless of similarity,
        meaning theme selection has no effect on wallpaper choice.

        Note: In OKLAB perceptual space, even visually different palettes
        may have >0.5 similarity, so we compare relative factors rather
        than asserting an absolute <1.0 threshold.
        """
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        theme_palette = self._make_theme_palette()

        # Similar image (same colors as theme)
        similar_palette = PaletteRecord(
            filepath='/test/similar.jpg',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a',
            color3='#e0af68', color4='#7aa2f7', color5='#bb9af7',
            color6='#7dcfff', color7='#c0caf5', color8='#414868',
            color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff',
            color15='#c0caf5', background='#1a1b26',
            foreground='#c0caf5', cursor='#c0caf5',
            avg_hue=220.0, avg_saturation=0.5, avg_lightness=0.4,
            color_temperature=-0.3,
        )

        # Dissimilar image (bright warm vs dark cool theme)
        dissimilar_palette = PaletteRecord(
            filepath='/test/dissimilar.jpg',
            color0='#fff8e1', color1='#ff6f00', color2='#ffd54f',
            color3='#ffab40', color4='#ff8f00', color5='#ffc107',
            color6='#ffecb3', color7='#fff3e0', color8='#ffe0b2',
            color9='#ffb74d', color10='#ffa726', color11='#ff9800',
            color12='#fb8c00', color13='#f57c00', color14='#ef6c00',
            color15='#e65100', background='#fff8e1',
            foreground='#3e2723', cursor='#ff6f00',
            avg_hue=35.0, avg_saturation=0.8, avg_lightness=0.8,
            color_temperature=0.8,
        )

        f_similar = color_affinity_factor(similar_palette, theme_palette, config)
        f_dissimilar = color_affinity_factor(dissimilar_palette, theme_palette, config)

        self.assertGreater(
            f_similar, f_dissimilar,
            f"Similar ({f_similar:.3f}) should score higher than "
            f"dissimilar ({f_dissimilar:.3f}) for theme palette"
        )

    def test_theme_palette_produces_meaningful_discrimination(self):
        """Similar and dissimilar images produce different factors.

        Bug caught: color_affinity_factor ignores color0-15 keys in theme
        palette and only uses avg_* metrics, reducing discrimination power.
        """
        from variety.smart_selection.weights import color_affinity_factor
        from variety.smart_selection.models import PaletteRecord
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(color_match_weight=1.0)
        theme_palette = self._make_theme_palette()

        # Similar image (dark, cool, similar colors)
        similar = PaletteRecord(
            filepath='/test/similar.jpg',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a',
            color3='#e0af68', color4='#7aa2f7', color5='#bb9af7',
            color6='#7dcfff', color7='#c0caf5', color8='#414868',
            color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff',
            color15='#c0caf5', background='#1a1b26',
            foreground='#c0caf5', cursor='#c0caf5',
            avg_hue=220.0, avg_saturation=0.5, avg_lightness=0.4,
            color_temperature=-0.3,
        )

        # Dissimilar image (bright, warm, different colors)
        dissimilar = PaletteRecord(
            filepath='/test/dissimilar.jpg',
            color0='#fff8e1', color1='#ff6f00', color2='#ffd54f',
            color3='#ffab40', color4='#ff8f00', color5='#ffc107',
            color6='#ffecb3', color7='#fff3e0', color8='#ffe0b2',
            color9='#ffb74d', color10='#ffa726', color11='#ff9800',
            color12='#fb8c00', color13='#f57c00', color14='#ef6c00',
            color15='#e65100', background='#fff8e1',
            foreground='#3e2723', cursor='#ff6f00',
            avg_hue=35.0, avg_saturation=0.8, avg_lightness=0.8,
            color_temperature=0.8,
        )

        f_similar = color_affinity_factor(similar, theme_palette, config)
        f_dissimilar = color_affinity_factor(dissimilar, theme_palette, config)

        self.assertGreater(
            f_similar, f_dissimilar,
            f"Similar image ({f_similar:.3f}) should score higher than "
            f"dissimilar image ({f_dissimilar:.3f})"
        )


if __name__ == '__main__':
    unittest.main()
