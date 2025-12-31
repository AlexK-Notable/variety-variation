# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Time-based palette adaptation for the Smart Selection Engine.

Adjusts wallpaper palette preferences based on time of day, supporting:
- Sunrise/sunset calculation (via astral library)
- Fixed schedule (user-defined day/night times)
- System theme detection (dark/light mode via GSettings)
"""

from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, Tuple
import logging

# Try to import astral for sunrise/sunset calculation
try:
    from astral import LocationInfo
    from astral.sun import sun
    ASTRAL_AVAILABLE = True
except ImportError:
    ASTRAL_AVAILABLE = False

# Try to import Gio for system theme detection
try:
    from gi.repository import Gio
except ImportError:
    Gio = None

from variety.smart_selection.config import SelectionConfig


logger = logging.getLogger(__name__)


@dataclass
class PaletteTarget:
    """Target palette characteristics for a time period.

    Attributes:
        lightness: Target brightness (0.0=dark to 1.0=bright).
        temperature: Color warmth (-1.0=cool/blue to +1.0=warm/orange).
        saturation: Color intensity (0.0=muted to 1.0=vibrant).
        tolerance: How strictly to match (lower=stricter). Default: 0.3.
    """
    lightness: float
    temperature: float
    saturation: float
    tolerance: float = 0.3


# Preset palette profiles for different time periods
PALETTE_PRESETS = {
    "bright_day": {
        "lightness": 0.7,
        "temperature": 0.3,
        "saturation": 0.6,
        "description": "Energetic, sunlit feel",
    },
    "neutral_day": {
        "lightness": 0.6,
        "temperature": 0.0,
        "saturation": 0.5,
        "description": "Balanced, non-distracting",
    },
    "cozy_night": {
        "lightness": 0.3,
        "temperature": 0.4,
        "saturation": 0.4,
        "description": "Warm, dim, relaxed",
    },
    "cool_night": {
        "lightness": 0.25,
        "temperature": -0.3,
        "saturation": 0.5,
        "description": "Blue-tinted, modern",
    },
    "dark_mode": {
        "lightness": 0.2,
        "temperature": 0.0,
        "saturation": 0.4,
        "description": "Minimal eye strain",
    },
    "custom": {
        "lightness": None,
        "temperature": None,
        "saturation": None,
        "description": "User-defined values",
    },
}


def parse_time_string(time_str: str) -> dt_time:
    """Parse a time string in HH:MM format.

    Args:
        time_str: Time string in "HH:MM" format (e.g., "07:00", "19:30").

    Returns:
        datetime.time object representing the time.

    Raises:
        ValueError: If the format is invalid or time is out of range.
    """
    if not time_str or ':' not in time_str:
        raise ValueError(f"Invalid time format: '{time_str}'. Expected HH:MM.")

    try:
        parts = time_str.strip().split(':')
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: '{time_str}'. Expected HH:MM.")

        hour = int(parts[0])
        minute = int(parts[1])

        if not (0 <= hour <= 23):
            raise ValueError(f"Hour {hour} out of range (0-23).")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute {minute} out of range (0-59).")

        return dt_time(hour, minute)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid time format: '{time_str}'. {e}")


def get_system_theme_preference() -> str:
    """Get current system theme preference from desktop settings.

    Tries to detect system dark/light mode by:
    1. GNOME: org.gnome.desktop.interface color-scheme
    2. Default: Returns 'day' if detection fails

    Returns:
        'day' for light mode, 'night' for dark mode.
    """
    if Gio is None:
        logger.debug("Gio not available, defaulting to 'day'")
        return "day"

    # Try GNOME settings first
    try:
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        scheme = settings.get_string("color-scheme")
        logger.debug(f"GNOME color-scheme: {scheme}")

        if scheme == "prefer-dark":
            return "night"
        elif scheme == "prefer-light":
            return "day"
        # "default" or other values default to day
        return "day"
    except Exception as e:
        logger.debug(f"Could not read GNOME settings: {e}")

    # TODO: Add Portal API detection for non-GNOME desktops
    # org.freedesktop.portal.Settings -> org.freedesktop.appearance color-scheme
    # Values: 0=no preference, 1=dark, 2=light

    logger.debug("System theme detection failed, defaulting to 'day'")
    return "day"


def get_sun_times(lat: float, lon: float, date: datetime.date) -> Tuple[datetime, datetime]:
    """Calculate sunrise and sunset times for a location and date.

    Uses the astral library for accurate astronomical calculations.
    Falls back to sensible defaults if astral is not available.

    Args:
        lat: Latitude of the location (-90 to 90).
        lon: Longitude of the location (-180 to 180).
        date: The date to calculate sun times for.

    Returns:
        Tuple of (sunrise, sunset) as datetime objects.
    """
    if ASTRAL_AVAILABLE:
        try:
            location = LocationInfo(latitude=lat, longitude=lon)
            s = sun(location.observer, date=date)
            return s['sunrise'], s['sunset']
        except Exception as e:
            logger.warning(f"Astral calculation failed: {e}, using fallback")

    # Fallback: default sunrise 07:00, sunset 19:00
    sunrise = datetime.combine(date, dt_time(7, 0))
    sunset = datetime.combine(date, dt_time(19, 0))
    return sunrise, sunset


class TimeAdapter:
    """Manages time-based palette preferences.

    Determines the current time period (day/night) using the configured
    timing method and provides the appropriate palette target.

    Attributes:
        config: SelectionConfig with time adaptation settings.
    """

    def __init__(self, config: SelectionConfig):
        """Initialize the TimeAdapter.

        Args:
            config: SelectionConfig with time adaptation fields.
        """
        self.config = config
        self._last_period: Optional[str] = None

    def get_current_period(self) -> str:
        """Get current time period based on the configured method.

        Returns:
            'day' or 'night' based on current time and config.
        """
        method = getattr(self.config, 'time_adaptation_method', 'fixed')

        if method == "sunrise_sunset":
            return self._get_period_sunrise_sunset()
        elif method == "fixed":
            return self._get_period_fixed()
        elif method == "system_theme":
            return self._get_period_system_theme()
        else:
            logger.debug(f"Unknown timing method '{method}', defaulting to 'day'")
            return "day"

    def get_palette_target(self) -> PaletteTarget:
        """Get target palette characteristics for current time period.

        Uses presets or custom values based on configuration.

        Returns:
            PaletteTarget with lightness, temperature, saturation, tolerance.
        """
        period = self.get_current_period()
        tolerance = getattr(self.config, 'palette_tolerance', 0.3)

        if period == "day":
            preset_name = getattr(self.config, 'day_preset', 'neutral_day')
            if preset_name == "custom":
                return PaletteTarget(
                    lightness=getattr(self.config, 'day_lightness', 0.6),
                    temperature=getattr(self.config, 'day_temperature', 0.0),
                    saturation=getattr(self.config, 'day_saturation', 0.5),
                    tolerance=tolerance,
                )
            return self._preset_to_target(preset_name, tolerance)
        else:
            preset_name = getattr(self.config, 'night_preset', 'cozy_night')
            if preset_name == "custom":
                return PaletteTarget(
                    lightness=getattr(self.config, 'night_lightness', 0.3),
                    temperature=getattr(self.config, 'night_temperature', 0.4),
                    saturation=getattr(self.config, 'night_saturation', 0.4),
                    tolerance=tolerance,
                )
            return self._preset_to_target(preset_name, tolerance)

    def get_next_transition(self) -> Optional[datetime]:
        """Get the datetime of the next day/night transition.

        Returns:
            datetime of next transition, or None if not applicable
            (e.g., system theme mode has no scheduled transitions).
        """
        method = getattr(self.config, 'time_adaptation_method', 'fixed')

        if method == "system_theme":
            # System theme changes are event-driven, not scheduled
            return None

        if method == "fixed":
            return self._get_next_transition_fixed()

        if method == "sunrise_sunset":
            return self._get_next_transition_sunrise_sunset()

        return None

    def _get_period_fixed(self) -> str:
        """Determine period using fixed schedule times.

        Compares current time against day_start_time and night_start_time.

        Returns:
            'day' or 'night' based on current time.
        """
        now = datetime.now()
        current_time = now.time()

        # Get configured times with defaults
        day_start_str = getattr(self.config, 'day_start_time', '07:00')
        night_start_str = getattr(self.config, 'night_start_time', '19:00')

        try:
            day_start = parse_time_string(day_start_str)
            night_start = parse_time_string(night_start_str)
        except ValueError as e:
            logger.warning(f"Invalid time config: {e}, using defaults")
            day_start = dt_time(7, 0)
            night_start = dt_time(19, 0)

        # Check if we're in daytime (between day_start and night_start)
        if day_start <= night_start:
            # Normal case: day is between day_start and night_start
            if day_start <= current_time < night_start:
                return "day"
            return "night"
        else:
            # Inverted case: night spans midnight
            # Day is from day_start to midnight OR midnight to night_start
            if current_time >= day_start or current_time < night_start:
                return "day"
            return "night"

    def _get_period_sunrise_sunset(self) -> str:
        """Determine period using astronomical sunrise/sunset.

        Uses astral library to calculate actual sunrise and sunset
        for the configured location.

        Returns:
            'day' if between sunrise and sunset, 'night' otherwise.
        """
        lat = getattr(self.config, 'location_lat', None)
        lon = getattr(self.config, 'location_lon', None)

        if lat is None or lon is None:
            logger.warning("No location configured for sunrise/sunset, falling back to fixed")
            return self._get_period_fixed()

        now = datetime.now()
        try:
            sunrise, sunset = get_sun_times(lat, lon, now.date())

            # Make sure we compare with timezone-aware datetimes if needed
            # astral may return timezone-aware datetimes
            now_naive = now.replace(tzinfo=None)
            sunrise_naive = sunrise.replace(tzinfo=None) if sunrise.tzinfo else sunrise
            sunset_naive = sunset.replace(tzinfo=None) if sunset.tzinfo else sunset

            if sunrise_naive <= now_naive < sunset_naive:
                return "day"
            return "night"
        except Exception as e:
            logger.warning(f"Sunrise/sunset calculation failed: {e}, falling back to fixed")
            return self._get_period_fixed()

    def _get_period_system_theme(self) -> str:
        """Determine period using system dark/light mode.

        Returns:
            'day' for light mode, 'night' for dark mode.
        """
        return get_system_theme_preference()

    def _get_next_transition_fixed(self) -> Optional[datetime]:
        """Calculate next transition time for fixed schedule.

        Returns:
            datetime of next transition.
        """
        now = datetime.now()
        current_time = now.time()
        today = now.date()

        day_start_str = getattr(self.config, 'day_start_time', '07:00')
        night_start_str = getattr(self.config, 'night_start_time', '19:00')

        try:
            day_start = parse_time_string(day_start_str)
            night_start = parse_time_string(night_start_str)
        except ValueError:
            day_start = dt_time(7, 0)
            night_start = dt_time(19, 0)

        # Find the next transition
        current_period = self.get_current_period()

        if current_period == "day":
            # Currently day, next transition is night_start
            next_time = night_start
            if current_time >= night_start:
                # Already past night_start today, use tomorrow
                return datetime.combine(today + timedelta(days=1), next_time)
            return datetime.combine(today, next_time)
        else:
            # Currently night, next transition is day_start
            next_time = day_start
            if current_time >= day_start:
                # Already past day_start today, use tomorrow
                return datetime.combine(today + timedelta(days=1), next_time)
            return datetime.combine(today, next_time)

    def _get_next_transition_sunrise_sunset(self) -> Optional[datetime]:
        """Calculate next transition for sunrise/sunset mode.

        Returns:
            datetime of next sunrise or sunset.
        """
        lat = getattr(self.config, 'location_lat', None)
        lon = getattr(self.config, 'location_lon', None)

        if lat is None or lon is None:
            return self._get_next_transition_fixed()

        now = datetime.now()
        today = now.date()

        try:
            sunrise, sunset = get_sun_times(lat, lon, today)

            # Make naive for comparison
            now_naive = now.replace(tzinfo=None)
            sunrise_naive = sunrise.replace(tzinfo=None) if sunrise.tzinfo else sunrise
            sunset_naive = sunset.replace(tzinfo=None) if sunset.tzinfo else sunset

            current_period = self.get_current_period()

            if current_period == "day":
                # Next is sunset
                if now_naive < sunset_naive:
                    return sunset_naive
                # Get tomorrow's sunrise
                tomorrow_sunrise, _ = get_sun_times(lat, lon, today + timedelta(days=1))
                return tomorrow_sunrise.replace(tzinfo=None) if tomorrow_sunrise.tzinfo else tomorrow_sunrise
            else:
                # Next is sunrise
                if now_naive < sunrise_naive:
                    return sunrise_naive
                # Get tomorrow's sunrise
                tomorrow_sunrise, _ = get_sun_times(lat, lon, today + timedelta(days=1))
                return tomorrow_sunrise.replace(tzinfo=None) if tomorrow_sunrise.tzinfo else tomorrow_sunrise
        except Exception as e:
            logger.warning(f"Failed to calculate next sun transition: {e}")
            return self._get_next_transition_fixed()

    def _preset_to_target(self, preset_name: str, tolerance: float = 0.3) -> PaletteTarget:
        """Convert a preset name to a PaletteTarget.

        Args:
            preset_name: Name of the preset (e.g., 'bright_day').
            tolerance: Tolerance value to use.

        Returns:
            PaletteTarget with values from the preset.
        """
        preset = PALETTE_PRESETS.get(preset_name)

        if preset is None or preset['lightness'] is None:
            # Unknown preset or custom without values, use neutral defaults
            preset = PALETTE_PRESETS.get('neutral_day', {
                'lightness': 0.6,
                'temperature': 0.0,
                'saturation': 0.5,
            })

        return PaletteTarget(
            lightness=preset['lightness'],
            temperature=preset['temperature'],
            saturation=preset['saturation'],
            tolerance=tolerance,
        )
