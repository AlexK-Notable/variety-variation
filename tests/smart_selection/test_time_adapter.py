#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for smart_selection.time_adapter - Time-based palette adaptation."""

import unittest
from datetime import datetime, time as dt_time
from unittest.mock import patch, MagicMock


class TestPaletteTargetDataclass(unittest.TestCase):
    """Tests for PaletteTarget dataclass."""

    def test_import_palette_target(self):
        """PaletteTarget can be imported from time_adapter module."""
        from variety.smart_selection.time_adapter import PaletteTarget
        self.assertIsNotNone(PaletteTarget)

    def test_palette_target_has_required_fields(self):
        """PaletteTarget has lightness, temperature, saturation, tolerance."""
        from variety.smart_selection.time_adapter import PaletteTarget

        target = PaletteTarget(
            lightness=0.6,
            temperature=0.0,
            saturation=0.5,
            tolerance=0.3,
        )
        self.assertEqual(target.lightness, 0.6)
        self.assertEqual(target.temperature, 0.0)
        self.assertEqual(target.saturation, 0.5)
        self.assertEqual(target.tolerance, 0.3)

    def test_palette_target_default_tolerance(self):
        """PaletteTarget has default tolerance of 0.3."""
        from variety.smart_selection.time_adapter import PaletteTarget

        target = PaletteTarget(lightness=0.5, temperature=0.0, saturation=0.5)
        self.assertEqual(target.tolerance, 0.3)


class TestPalettePresets(unittest.TestCase):
    """Tests for PALETTE_PRESETS dictionary."""

    def test_import_palette_presets(self):
        """PALETTE_PRESETS can be imported from time_adapter module."""
        from variety.smart_selection.time_adapter import PALETTE_PRESETS
        self.assertIsNotNone(PALETTE_PRESETS)
        self.assertIsInstance(PALETTE_PRESETS, dict)

    def test_presets_contain_required_keys(self):
        """PALETTE_PRESETS contains all required preset names."""
        from variety.smart_selection.time_adapter import PALETTE_PRESETS

        required_presets = {
            'bright_day', 'neutral_day', 'cozy_night',
            'cool_night', 'dark_mode', 'custom',
        }
        self.assertTrue(required_presets.issubset(set(PALETTE_PRESETS.keys())))

    def test_preset_has_required_values(self):
        """Each preset has lightness, temperature, saturation, description."""
        from variety.smart_selection.time_adapter import PALETTE_PRESETS

        for name, preset in PALETTE_PRESETS.items():
            self.assertIn('lightness', preset, f"Preset {name} missing lightness")
            self.assertIn('temperature', preset, f"Preset {name} missing temperature")
            self.assertIn('saturation', preset, f"Preset {name} missing saturation")
            self.assertIn('description', preset, f"Preset {name} missing description")

    def test_custom_preset_has_none_values(self):
        """Custom preset has None values for user-defined settings."""
        from variety.smart_selection.time_adapter import PALETTE_PRESETS

        custom = PALETTE_PRESETS['custom']
        self.assertIsNone(custom['lightness'])
        self.assertIsNone(custom['temperature'])
        self.assertIsNone(custom['saturation'])

    def test_bright_day_values(self):
        """bright_day preset has expected values."""
        from variety.smart_selection.time_adapter import PALETTE_PRESETS

        preset = PALETTE_PRESETS['bright_day']
        self.assertEqual(preset['lightness'], 0.7)
        self.assertEqual(preset['temperature'], 0.3)
        self.assertEqual(preset['saturation'], 0.6)

    def test_cozy_night_values(self):
        """cozy_night preset has expected values."""
        from variety.smart_selection.time_adapter import PALETTE_PRESETS

        preset = PALETTE_PRESETS['cozy_night']
        self.assertEqual(preset['lightness'], 0.3)
        self.assertEqual(preset['temperature'], 0.4)
        self.assertEqual(preset['saturation'], 0.4)


class TestHelperFunctions(unittest.TestCase):
    """Tests for helper functions."""

    def test_import_parse_time_string(self):
        """parse_time_string can be imported."""
        from variety.smart_selection.time_adapter import parse_time_string
        self.assertIsNotNone(parse_time_string)

    def test_parse_time_string_valid_format(self):
        """parse_time_string handles valid HH:MM format."""
        from variety.smart_selection.time_adapter import parse_time_string

        result = parse_time_string("07:00")
        self.assertEqual(result.hour, 7)
        self.assertEqual(result.minute, 0)

        result = parse_time_string("19:30")
        self.assertEqual(result.hour, 19)
        self.assertEqual(result.minute, 30)

    def test_parse_time_string_returns_time_object(self):
        """parse_time_string returns a datetime.time object."""
        from variety.smart_selection.time_adapter import parse_time_string

        result = parse_time_string("12:00")
        self.assertIsInstance(result, dt_time)

    def test_parse_time_string_invalid_format(self):
        """parse_time_string raises ValueError for invalid format."""
        from variety.smart_selection.time_adapter import parse_time_string

        with self.assertRaises(ValueError):
            parse_time_string("invalid")

        with self.assertRaises(ValueError):
            parse_time_string("25:00")

        with self.assertRaises(ValueError):
            parse_time_string("12:60")

    def test_parse_time_string_edge_cases(self):
        """parse_time_string handles edge cases."""
        from variety.smart_selection.time_adapter import parse_time_string

        # Midnight
        result = parse_time_string("00:00")
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)

        # Last minute of day
        result = parse_time_string("23:59")
        self.assertEqual(result.hour, 23)
        self.assertEqual(result.minute, 59)

    def test_import_get_system_theme_preference(self):
        """get_system_theme_preference can be imported."""
        from variety.smart_selection.time_adapter import get_system_theme_preference
        self.assertIsNotNone(get_system_theme_preference)

    def test_get_system_theme_preference_returns_valid_value(self):
        """get_system_theme_preference returns 'day' or 'night'."""
        from variety.smart_selection.time_adapter import get_system_theme_preference

        result = get_system_theme_preference()
        self.assertIn(result, ['day', 'night'])

    @patch('variety.smart_selection.time_adapter.Gio')
    def test_get_system_theme_preference_prefer_dark(self, mock_gio):
        """get_system_theme_preference returns 'night' for prefer-dark."""
        from variety.smart_selection.time_adapter import get_system_theme_preference

        mock_settings = MagicMock()
        mock_settings.get_string.return_value = 'prefer-dark'
        mock_gio.Settings.new.return_value = mock_settings

        result = get_system_theme_preference()
        self.assertEqual(result, 'night')

    @patch('variety.smart_selection.time_adapter.Gio')
    def test_get_system_theme_preference_prefer_light(self, mock_gio):
        """get_system_theme_preference returns 'day' for prefer-light."""
        from variety.smart_selection.time_adapter import get_system_theme_preference

        mock_settings = MagicMock()
        mock_settings.get_string.return_value = 'prefer-light'
        mock_gio.Settings.new.return_value = mock_settings

        result = get_system_theme_preference()
        self.assertEqual(result, 'day')

    @patch('variety.smart_selection.time_adapter.Gio')
    def test_get_system_theme_preference_fallback_on_error(self, mock_gio):
        """get_system_theme_preference returns 'day' on error."""
        from variety.smart_selection.time_adapter import get_system_theme_preference

        mock_gio.Settings.new.side_effect = Exception("GSettings not available")

        result = get_system_theme_preference()
        self.assertEqual(result, 'day')


class TestGetSunTimes(unittest.TestCase):
    """Tests for get_sun_times helper function."""

    def test_import_get_sun_times(self):
        """get_sun_times can be imported."""
        from variety.smart_selection.time_adapter import get_sun_times
        self.assertIsNotNone(get_sun_times)

    def test_get_sun_times_returns_tuple(self):
        """get_sun_times returns a tuple of (sunrise, sunset) datetimes."""
        from variety.smart_selection.time_adapter import get_sun_times

        # New York coordinates
        lat, lon = 40.7128, -74.0060
        date = datetime(2025, 6, 21).date()

        result = get_sun_times(lat, lon, date)

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        sunrise, sunset = result
        self.assertIsInstance(sunrise, datetime)
        self.assertIsInstance(sunset, datetime)

    def test_get_sun_times_sunrise_before_sunset(self):
        """Sunrise time is before sunset time."""
        from variety.smart_selection.time_adapter import get_sun_times

        lat, lon = 40.7128, -74.0060
        date = datetime(2025, 6, 21).date()

        sunrise, sunset = get_sun_times(lat, lon, date)
        self.assertLess(sunrise, sunset)

    def test_get_sun_times_reasonable_hours(self):
        """Sun times are within reasonable hours."""
        from variety.smart_selection.time_adapter import get_sun_times

        lat, lon = 40.7128, -74.0060
        date = datetime(2025, 6, 21).date()

        sunrise, sunset = get_sun_times(lat, lon, date)

        # Sunrise should be roughly between 4 AM and 8 AM
        self.assertGreaterEqual(sunrise.hour, 4)
        self.assertLessEqual(sunrise.hour, 8)

        # Sunset should be roughly between 5 PM and 10 PM
        self.assertGreaterEqual(sunset.hour, 17)
        self.assertLessEqual(sunset.hour, 22)

    def test_get_sun_times_fallback_without_astral(self):
        """get_sun_times returns default times if astral is not available."""
        from variety.smart_selection.time_adapter import get_sun_times, ASTRAL_AVAILABLE

        # If astral is not available, should still work with fallback
        lat, lon = 40.7128, -74.0060
        date = datetime(2025, 6, 21).date()

        result = get_sun_times(lat, lon, date)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


class TestTimeAdapterClass(unittest.TestCase):
    """Tests for TimeAdapter class."""

    def test_import_time_adapter(self):
        """TimeAdapter can be imported."""
        from variety.smart_selection.time_adapter import TimeAdapter
        self.assertIsNotNone(TimeAdapter)

    def test_time_adapter_init(self):
        """TimeAdapter can be initialized with SelectionConfig."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig()
        adapter = TimeAdapter(config)

        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.config, config)

    def test_get_current_period_returns_day_or_night(self):
        """get_current_period returns 'day' or 'night'."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertIn(period, ['day', 'night'])

    def test_get_palette_target_returns_palette_target(self):
        """get_palette_target returns a PaletteTarget."""
        from variety.smart_selection.time_adapter import TimeAdapter, PaletteTarget
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig()
        adapter = TimeAdapter(config)

        target = adapter.get_palette_target()
        self.assertIsInstance(target, PaletteTarget)

    def test_get_next_transition_returns_datetime_or_none(self):
        """get_next_transition returns Optional[datetime]."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig()
        adapter = TimeAdapter(config)

        result = adapter.get_next_transition()
        self.assertTrue(result is None or isinstance(result, datetime))


class TestTimeAdapterFixedSchedule(unittest.TestCase):
    """Tests for TimeAdapter with fixed schedule method."""

    def _make_config(self, **kwargs):
        """Helper to create config with time adaptation settings."""
        from variety.smart_selection.config import SelectionConfig

        defaults = {
            'time_adaptation_enabled': True,
            'time_adaptation_method': 'fixed',
            'day_start_time': '07:00',
            'night_start_time': '19:00',
            'day_preset': 'neutral_day',
            'night_preset': 'cozy_night',
        }
        defaults.update(kwargs)
        return SelectionConfig.from_dict(defaults)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_fixed_schedule_daytime(self, mock_datetime):
        """Fixed schedule returns 'day' during daytime hours."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock current time to 12:00
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(12, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'day')

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_fixed_schedule_nighttime(self, mock_datetime):
        """Fixed schedule returns 'night' during nighttime hours."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock current time to 22:00
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(22, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'night')

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_fixed_schedule_early_morning(self, mock_datetime):
        """Fixed schedule returns 'night' before day_start."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock current time to 05:00
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(5, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'night')

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_fixed_schedule_at_day_start(self, mock_datetime):
        """Fixed schedule returns 'day' at exactly day_start time."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock current time to exactly 07:00
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(7, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'day')

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_fixed_schedule_at_night_start(self, mock_datetime):
        """Fixed schedule returns 'night' at exactly night_start time."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock current time to exactly 19:00
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(19, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'night')


class TestTimeAdapterSystemTheme(unittest.TestCase):
    """Tests for TimeAdapter with system theme method."""

    def _make_config(self, **kwargs):
        """Helper to create config with system_theme method."""
        from variety.smart_selection.config import SelectionConfig

        defaults = {
            'time_adaptation_enabled': True,
            'time_adaptation_method': 'system_theme',
            'day_preset': 'neutral_day',
            'night_preset': 'cozy_night',
        }
        defaults.update(kwargs)
        return SelectionConfig.from_dict(defaults)

    @patch('variety.smart_selection.time_adapter.get_system_theme_preference')
    def test_system_theme_dark_mode(self, mock_get_theme):
        """System theme returns 'night' when system is in dark mode."""
        from variety.smart_selection.time_adapter import TimeAdapter

        mock_get_theme.return_value = 'night'

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'night')

    @patch('variety.smart_selection.time_adapter.get_system_theme_preference')
    def test_system_theme_light_mode(self, mock_get_theme):
        """System theme returns 'day' when system is in light mode."""
        from variety.smart_selection.time_adapter import TimeAdapter

        mock_get_theme.return_value = 'day'

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'day')


class TestTimeAdapterSunriseSunset(unittest.TestCase):
    """Tests for TimeAdapter with sunrise/sunset method."""

    def _make_config(self, **kwargs):
        """Helper to create config with sunrise_sunset method."""
        from variety.smart_selection.config import SelectionConfig

        defaults = {
            'time_adaptation_enabled': True,
            'time_adaptation_method': 'sunrise_sunset',
            'location_lat': 40.7128,
            'location_lon': -74.0060,
            'day_preset': 'neutral_day',
            'night_preset': 'cozy_night',
        }
        defaults.update(kwargs)
        return SelectionConfig.from_dict(defaults)

    @patch('variety.smart_selection.time_adapter.get_sun_times')
    @patch('variety.smart_selection.time_adapter.datetime')
    def test_sunrise_sunset_daytime(self, mock_datetime, mock_sun_times):
        """Sunrise/sunset method returns 'day' during daylight hours."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock sunrise at 6:00, sunset at 20:00
        now = datetime(2025, 6, 21, 12, 0)  # Noon
        sunrise = datetime(2025, 6, 21, 6, 0)
        sunset = datetime(2025, 6, 21, 20, 0)

        mock_datetime.now.return_value = now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        mock_sun_times.return_value = (sunrise, sunset)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'day')

    @patch('variety.smart_selection.time_adapter.get_sun_times')
    @patch('variety.smart_selection.time_adapter.datetime')
    def test_sunrise_sunset_nighttime(self, mock_datetime, mock_sun_times):
        """Sunrise/sunset method returns 'night' after sunset."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock sunrise at 6:00, sunset at 20:00
        now = datetime(2025, 6, 21, 22, 0)  # 10 PM
        sunrise = datetime(2025, 6, 21, 6, 0)
        sunset = datetime(2025, 6, 21, 20, 0)

        mock_datetime.now.return_value = now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        mock_sun_times.return_value = (sunrise, sunset)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'night')

    @patch('variety.smart_selection.time_adapter.get_sun_times')
    @patch('variety.smart_selection.time_adapter.datetime')
    def test_sunrise_sunset_before_sunrise(self, mock_datetime, mock_sun_times):
        """Sunrise/sunset method returns 'night' before sunrise."""
        from variety.smart_selection.time_adapter import TimeAdapter

        # Mock sunrise at 6:00, sunset at 20:00
        now = datetime(2025, 6, 21, 4, 0)  # 4 AM
        sunrise = datetime(2025, 6, 21, 6, 0)
        sunset = datetime(2025, 6, 21, 20, 0)

        mock_datetime.now.return_value = now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        mock_sun_times.return_value = (sunrise, sunset)

        config = self._make_config()
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'night')

    def test_sunrise_sunset_no_location_falls_back(self):
        """Sunrise/sunset method falls back to 'day' if no location set."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig.from_dict({
            'time_adaptation_enabled': True,
            'time_adaptation_method': 'sunrise_sunset',
            'location_lat': None,
            'location_lon': None,
        })
        adapter = TimeAdapter(config)

        # Should not crash, should fall back gracefully
        period = adapter.get_current_period()
        self.assertIn(period, ['day', 'night'])


class TestTimeAdapterPaletteTarget(unittest.TestCase):
    """Tests for TimeAdapter.get_palette_target()."""

    def _make_config(self, **kwargs):
        """Helper to create config with time adaptation settings."""
        from variety.smart_selection.config import SelectionConfig

        defaults = {
            'time_adaptation_enabled': True,
            'time_adaptation_method': 'fixed',
            'day_start_time': '07:00',
            'night_start_time': '19:00',
            'day_preset': 'neutral_day',
            'night_preset': 'cozy_night',
            'palette_tolerance': 0.3,
        }
        defaults.update(kwargs)
        return SelectionConfig.from_dict(defaults)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_get_palette_target_day_preset(self, mock_datetime):
        """get_palette_target returns correct values for day preset."""
        from variety.smart_selection.time_adapter import TimeAdapter

        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(12, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config(day_preset='bright_day')
        adapter = TimeAdapter(config)

        target = adapter.get_palette_target()

        # bright_day preset values
        self.assertEqual(target.lightness, 0.7)
        self.assertEqual(target.temperature, 0.3)
        self.assertEqual(target.saturation, 0.6)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_get_palette_target_night_preset(self, mock_datetime):
        """get_palette_target returns correct values for night preset."""
        from variety.smart_selection.time_adapter import TimeAdapter

        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(22, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config(night_preset='cool_night')
        adapter = TimeAdapter(config)

        target = adapter.get_palette_target()

        # cool_night preset values
        self.assertEqual(target.lightness, 0.25)
        self.assertEqual(target.temperature, -0.3)
        self.assertEqual(target.saturation, 0.5)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_get_palette_target_custom_day_values(self, mock_datetime):
        """get_palette_target uses custom values when preset is 'custom'."""
        from variety.smart_selection.time_adapter import TimeAdapter

        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(12, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config(
            day_preset='custom',
            day_lightness=0.8,
            day_temperature=0.5,
            day_saturation=0.7,
            palette_tolerance=0.25,
        )
        adapter = TimeAdapter(config)

        target = adapter.get_palette_target()

        self.assertEqual(target.lightness, 0.8)
        self.assertEqual(target.temperature, 0.5)
        self.assertEqual(target.saturation, 0.7)
        self.assertEqual(target.tolerance, 0.25)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_get_palette_target_custom_night_values(self, mock_datetime):
        """get_palette_target uses custom values for night when preset is 'custom'."""
        from variety.smart_selection.time_adapter import TimeAdapter

        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(22, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        config = self._make_config(
            night_preset='custom',
            night_lightness=0.15,
            night_temperature=-0.5,
            night_saturation=0.3,
            palette_tolerance=0.4,
        )
        adapter = TimeAdapter(config)

        target = adapter.get_palette_target()

        self.assertEqual(target.lightness, 0.15)
        self.assertEqual(target.temperature, -0.5)
        self.assertEqual(target.saturation, 0.3)
        self.assertEqual(target.tolerance, 0.4)


class TestTimeAdapterNextTransition(unittest.TestCase):
    """Tests for TimeAdapter.get_next_transition()."""

    def _make_config(self, **kwargs):
        """Helper to create config."""
        from variety.smart_selection.config import SelectionConfig

        defaults = {
            'time_adaptation_enabled': True,
            'time_adaptation_method': 'fixed',
            'day_start_time': '07:00',
            'night_start_time': '19:00',
        }
        defaults.update(kwargs)
        return SelectionConfig.from_dict(defaults)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_get_next_transition_during_day(self, mock_datetime):
        """During day, next transition is night_start_time."""
        from variety.smart_selection.time_adapter import TimeAdapter

        now = datetime(2025, 6, 21, 12, 0)
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(12, 0)
        mock_now.date.return_value = now.date()
        mock_now.replace = lambda hour, minute, second=0, microsecond=0: datetime(
            2025, 6, 21, hour, minute, second, microsecond
        )
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        mock_datetime.combine = datetime.combine

        config = self._make_config()
        adapter = TimeAdapter(config)

        next_trans = adapter.get_next_transition()

        # Should be 19:00 today
        self.assertIsNotNone(next_trans)
        self.assertEqual(next_trans.hour, 19)
        self.assertEqual(next_trans.minute, 0)

    @patch('variety.smart_selection.time_adapter.datetime')
    def test_get_next_transition_during_night(self, mock_datetime):
        """During night, next transition is day_start_time."""
        from variety.smart_selection.time_adapter import TimeAdapter

        now = datetime(2025, 6, 21, 22, 0)
        mock_now = MagicMock()
        mock_now.time.return_value = dt_time(22, 0)
        mock_now.date.return_value = now.date()
        mock_now.replace = lambda hour, minute, second=0, microsecond=0: datetime(
            2025, 6, 21, hour, minute, second, microsecond
        )
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        mock_datetime.combine = datetime.combine

        config = self._make_config()
        adapter = TimeAdapter(config)

        next_trans = adapter.get_next_transition()

        # Should be 07:00 tomorrow
        self.assertIsNotNone(next_trans)
        self.assertEqual(next_trans.hour, 7)
        self.assertEqual(next_trans.minute, 0)

    def test_get_next_transition_system_theme_returns_none(self):
        """System theme method returns None (no scheduled transitions)."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig.from_dict({
            'time_adaptation_method': 'system_theme',
        })
        adapter = TimeAdapter(config)

        result = adapter.get_next_transition()
        self.assertIsNone(result)


class TestTimeAdapterUnknownMethod(unittest.TestCase):
    """Tests for TimeAdapter with unknown timing method."""

    def test_unknown_method_defaults_to_day(self):
        """Unknown timing method defaults to 'day'."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig.from_dict({
            'time_adaptation_method': 'unknown_method',
        })
        adapter = TimeAdapter(config)

        period = adapter.get_current_period()
        self.assertEqual(period, 'day')


class TestTimeAdapterEdgeCases(unittest.TestCase):
    """Edge case tests for TimeAdapter."""

    def test_missing_config_values_use_defaults(self):
        """Missing config values use sensible defaults."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        # Minimal config without time adaptation fields
        config = SelectionConfig()
        adapter = TimeAdapter(config)

        # Should not crash
        period = adapter.get_current_period()
        self.assertIn(period, ['day', 'night'])

    def test_invalid_time_strings_handled(self):
        """Invalid time strings in config are handled gracefully."""
        from variety.smart_selection.time_adapter import TimeAdapter
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig.from_dict({
            'time_adaptation_method': 'fixed',
            'day_start_time': 'invalid',
            'night_start_time': 'also_invalid',
        })

        # TimeAdapter should handle invalid times gracefully
        adapter = TimeAdapter(config)

        # Should not crash
        period = adapter.get_current_period()
        self.assertIn(period, ['day', 'night'])


if __name__ == '__main__':
    unittest.main()
