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

        # Color science defaults (OKLAB enabled by default)
        self.assertTrue(config.use_oklab_similarity)

    def test_selection_config_has_oklab_field(self):
        """SelectionConfig has use_oklab_similarity field for perceptual color matching."""
        from variety.smart_selection.config import SelectionConfig

        field_names = {f.name for f in fields(SelectionConfig)}
        self.assertIn('use_oklab_similarity', field_names)

    def test_selection_config_oklab_can_be_disabled(self):
        """use_oklab_similarity can be set to False to use legacy HSL."""
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(use_oklab_similarity=False)
        self.assertFalse(config.use_oklab_similarity)

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


class TestTimeAdaptationConfig(unittest.TestCase):
    """Tests for time adaptation configuration fields."""

    def test_time_adaptation_fields_exist(self):
        """SelectionConfig has all time adaptation fields."""
        from variety.smart_selection.config import SelectionConfig

        field_names = {f.name for f in fields(SelectionConfig)}
        time_fields = {
            'time_adaptation_enabled',
            'time_adaptation_method',
            'day_start_time',
            'night_start_time',
            'location_lat',
            'location_lon',
            'location_name',
            'day_preset',
            'night_preset',
            'day_lightness',
            'day_temperature',
            'day_saturation',
            'night_lightness',
            'night_temperature',
            'night_saturation',
            'palette_tolerance',
        }
        self.assertTrue(time_fields.issubset(field_names))

    def test_time_adaptation_default_values(self):
        """Time adaptation fields have correct defaults."""
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig()

        # Enabled by default
        self.assertTrue(config.time_adaptation_enabled)

        # Fixed schedule by default
        self.assertEqual(config.time_adaptation_method, 'fixed')
        self.assertEqual(config.day_start_time, '07:00')
        self.assertEqual(config.night_start_time, '19:00')

        # Location unset by default
        self.assertIsNone(config.location_lat)
        self.assertIsNone(config.location_lon)
        self.assertEqual(config.location_name, '')

        # Default presets
        self.assertEqual(config.day_preset, 'neutral_day')
        self.assertEqual(config.night_preset, 'cozy_night')

        # Default day palette values
        self.assertEqual(config.day_lightness, 0.6)
        self.assertEqual(config.day_temperature, 0.0)
        self.assertEqual(config.day_saturation, 0.5)

        # Default night palette values
        self.assertEqual(config.night_lightness, 0.3)
        self.assertEqual(config.night_temperature, 0.4)
        self.assertEqual(config.night_saturation, 0.4)

        # Default tolerance
        self.assertEqual(config.palette_tolerance, 0.3)

    def test_time_adaptation_custom_values(self):
        """Time adaptation fields can be set to custom values."""
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(
            time_adaptation_enabled=False,
            time_adaptation_method='sunrise_sunset',
            day_start_time='06:30',
            night_start_time='20:00',
            location_lat=40.7128,
            location_lon=-74.0060,
            location_name='New York',
            day_preset='bright_day',
            night_preset='dark_mode',
            day_lightness=0.7,
            day_temperature=0.3,
            day_saturation=0.6,
            night_lightness=0.2,
            night_temperature=-0.3,
            night_saturation=0.3,
            palette_tolerance=0.2,
        )

        self.assertFalse(config.time_adaptation_enabled)
        self.assertEqual(config.time_adaptation_method, 'sunrise_sunset')
        self.assertEqual(config.day_start_time, '06:30')
        self.assertEqual(config.night_start_time, '20:00')
        self.assertEqual(config.location_lat, 40.7128)
        self.assertEqual(config.location_lon, -74.0060)
        self.assertEqual(config.location_name, 'New York')
        self.assertEqual(config.day_preset, 'bright_day')
        self.assertEqual(config.night_preset, 'dark_mode')
        self.assertEqual(config.day_lightness, 0.7)
        self.assertEqual(config.day_temperature, 0.3)
        self.assertEqual(config.day_saturation, 0.6)
        self.assertEqual(config.night_lightness, 0.2)
        self.assertEqual(config.night_temperature, -0.3)
        self.assertEqual(config.night_saturation, 0.3)
        self.assertEqual(config.palette_tolerance, 0.2)

    def test_time_adaptation_method_options(self):
        """time_adaptation_method accepts valid options."""
        from variety.smart_selection.config import SelectionConfig

        for method in ['sunrise_sunset', 'fixed', 'system_theme']:
            config = SelectionConfig(time_adaptation_method=method)
            self.assertEqual(config.time_adaptation_method, method)

    def test_time_adaptation_serialization(self):
        """Time adaptation fields serialize to/from dict correctly."""
        from variety.smart_selection.config import SelectionConfig

        original = SelectionConfig(
            time_adaptation_enabled=True,
            time_adaptation_method='sunrise_sunset',
            location_lat=51.5074,
            location_lon=-0.1278,
            day_preset='custom',
            day_lightness=0.65,
        )

        config_dict = original.to_dict()
        restored = SelectionConfig.from_dict(config_dict)

        self.assertEqual(restored.time_adaptation_enabled, original.time_adaptation_enabled)
        self.assertEqual(restored.time_adaptation_method, original.time_adaptation_method)
        self.assertEqual(restored.location_lat, original.location_lat)
        self.assertEqual(restored.location_lon, original.location_lon)
        self.assertEqual(restored.day_preset, original.day_preset)
        self.assertEqual(restored.day_lightness, original.day_lightness)


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
