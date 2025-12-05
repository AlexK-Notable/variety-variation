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


if __name__ == '__main__':
    unittest.main()
