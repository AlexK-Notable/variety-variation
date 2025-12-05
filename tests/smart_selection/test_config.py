#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.config - Selection configuration."""

import unittest
from dataclasses import fields


class TestSelectionConfig(unittest.TestCase):
    """Tests for SelectionConfig dataclass."""

    def test_import_selection_config(self):
        """SelectionConfig can be imported from smart_selection.config."""
        from variety.smart_selection.config import SelectionConfig
        self.assertIsNotNone(SelectionConfig)

    def test_selection_config_has_recency_fields(self):
        """SelectionConfig has fields for recency penalties."""
        from variety.smart_selection.config import SelectionConfig

        field_names = {f.name for f in fields(SelectionConfig)}
        recency_fields = {
            'image_cooldown_days',
            'source_cooldown_days',
        }
        self.assertTrue(recency_fields.issubset(field_names))

    def test_selection_config_has_weight_fields(self):
        """SelectionConfig has fields for weight multipliers."""
        from variety.smart_selection.config import SelectionConfig

        field_names = {f.name for f in fields(SelectionConfig)}
        weight_fields = {
            'favorite_boost',
            'new_image_boost',
            'color_match_weight',
        }
        self.assertTrue(weight_fields.issubset(field_names))

    def test_selection_config_has_behavior_fields(self):
        """SelectionConfig has fields for selection behavior."""
        from variety.smart_selection.config import SelectionConfig

        field_names = {f.name for f in fields(SelectionConfig)}
        behavior_fields = {
            'recency_decay',
            'enabled',
        }
        self.assertTrue(behavior_fields.issubset(field_names))

    def test_selection_config_default_values(self):
        """SelectionConfig has sensible default values."""
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig()

        # Recency defaults
        self.assertEqual(config.image_cooldown_days, 7.0)
        self.assertEqual(config.source_cooldown_days, 1.0)

        # Weight defaults
        self.assertEqual(config.favorite_boost, 2.0)
        self.assertEqual(config.new_image_boost, 1.5)
        self.assertEqual(config.color_match_weight, 1.0)

        # Behavior defaults
        self.assertEqual(config.recency_decay, 'exponential')
        self.assertTrue(config.enabled)

    def test_selection_config_custom_values(self):
        """SelectionConfig can be created with custom values."""
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(
            image_cooldown_days=14.0,
            source_cooldown_days=0.5,
            favorite_boost=3.0,
            enabled=False,
        )

        self.assertEqual(config.image_cooldown_days, 14.0)
        self.assertEqual(config.source_cooldown_days, 0.5)
        self.assertEqual(config.favorite_boost, 3.0)
        self.assertFalse(config.enabled)

    def test_selection_config_recency_decay_options(self):
        """recency_decay accepts valid options."""
        from variety.smart_selection.config import SelectionConfig

        for decay in ['exponential', 'linear', 'step']:
            config = SelectionConfig(recency_decay=decay)
            self.assertEqual(config.recency_decay, decay)


class TestConfigSerialization(unittest.TestCase):
    """Tests for config serialization to/from dict."""

    def test_config_to_dict(self):
        """SelectionConfig can be converted to a dict."""
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(
            image_cooldown_days=10.0,
            favorite_boost=2.5,
        )
        config_dict = config.to_dict()

        self.assertIsInstance(config_dict, dict)
        self.assertEqual(config_dict['image_cooldown_days'], 10.0)
        self.assertEqual(config_dict['favorite_boost'], 2.5)

    def test_config_from_dict(self):
        """SelectionConfig can be created from a dict."""
        from variety.smart_selection.config import SelectionConfig

        config_dict = {
            'image_cooldown_days': 5.0,
            'source_cooldown_days': 2.0,
            'favorite_boost': 1.5,
            'enabled': False,
        }
        config = SelectionConfig.from_dict(config_dict)

        self.assertEqual(config.image_cooldown_days, 5.0)
        self.assertEqual(config.source_cooldown_days, 2.0)
        self.assertEqual(config.favorite_boost, 1.5)
        self.assertFalse(config.enabled)

    def test_config_from_dict_with_missing_keys(self):
        """SelectionConfig.from_dict uses defaults for missing keys."""
        from variety.smart_selection.config import SelectionConfig

        config_dict = {
            'image_cooldown_days': 3.0,
        }
        config = SelectionConfig.from_dict(config_dict)

        self.assertEqual(config.image_cooldown_days, 3.0)
        # Other fields should use defaults
        self.assertEqual(config.source_cooldown_days, 1.0)
        self.assertEqual(config.favorite_boost, 2.0)
        self.assertTrue(config.enabled)

    def test_config_from_dict_ignores_unknown_keys(self):
        """SelectionConfig.from_dict ignores unknown keys."""
        from variety.smart_selection.config import SelectionConfig

        config_dict = {
            'image_cooldown_days': 3.0,
            'unknown_field': 'ignored',
        }
        config = SelectionConfig.from_dict(config_dict)

        self.assertEqual(config.image_cooldown_days, 3.0)
        self.assertFalse(hasattr(config, 'unknown_field'))


if __name__ == '__main__':
    unittest.main()
