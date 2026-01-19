# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Configuration for the Smart Selection Engine.

Defines parameters that control selection behavior including
recency penalties, weight multipliers, and decay functions.
"""

from dataclasses import dataclass, field, fields as dataclass_fields, asdict
from typing import Dict, Any, Optional


@dataclass
class SelectionConfig:
    """Configuration for smart wallpaper selection.

    Attributes:
        image_cooldown_days: Days before an image can be selected again.
            0 = disabled. Default: 7 days.
        source_cooldown_days: Days before a source is favored again.
            0 = disabled. Default: 1 day.
        favorite_boost: Weight multiplier for favorite images.
            1.0 = no boost. Default: 2.0.
        new_image_boost: Weight multiplier for never-shown images.
            1.0 = no boost. Default: 1.5.
        color_match_weight: How much color similarity affects weight.
            0 = disabled. Default: 1.0.
        recency_decay: How recency penalty decays over time.
            Options: 'exponential', 'linear', 'step'. Default: 'exponential'.
        enabled: Whether smart selection is enabled.
            If False, falls back to random selection. Default: True.
        use_oklab_similarity: Use perceptually uniform OKLAB color space for
            color similarity calculations. OKLAB provides more accurate
            perceptual matching than HSL. Default: True.

        # Time adaptation settings
        time_adaptation_enabled: Whether to adjust palette preferences based
            on time of day. Default: True.
        time_adaptation_method: How to determine day vs night.
            Options: 'sunrise_sunset', 'fixed', 'system_theme'. Default: 'fixed'.
        day_start_time: Time when day period begins (HH:MM format).
            Only used with 'fixed' method. Default: '07:00'.
        night_start_time: Time when night period begins (HH:MM format).
            Only used with 'fixed' method. Default: '19:00'.
        location_lat: Latitude for sunrise/sunset calculation.
            Only used with 'sunrise_sunset' method.
        location_lon: Longitude for sunrise/sunset calculation.
            Only used with 'sunrise_sunset' method.
        location_name: Human-readable location name for display.
        day_preset: Palette preset for day period.
            Options: 'bright_day', 'neutral_day', 'custom'. Default: 'neutral_day'.
        night_preset: Palette preset for night period.
            Options: 'cozy_night', 'cool_night', 'dark_mode', 'custom'.
            Default: 'cozy_night'.
        day_lightness: Target lightness for day (0.0-1.0).
            Only used when day_preset is 'custom'. Default: 0.6.
        day_temperature: Target temperature for day (-1.0 to +1.0).
            Only used when day_preset is 'custom'. Default: 0.0.
        day_saturation: Target saturation for day (0.0-1.0).
            Only used when day_preset is 'custom'. Default: 0.5.
        night_lightness: Target lightness for night (0.0-1.0).
            Only used when night_preset is 'custom'. Default: 0.3.
        night_temperature: Target temperature for night (-1.0 to +1.0).
            Only used when night_preset is 'custom'. Default: 0.4.
        night_saturation: Target saturation for night (0.0-1.0).
            Only used when night_preset is 'custom'. Default: 0.4.
        palette_tolerance: How strictly to match palette targets (0.1-0.5).
            Lower = stricter matching with less variety. Default: 0.2.
        time_affinity_weight: Strength of time-based palette preference (1.0-5.0).
            Higher values more aggressively penalize mismatched brightness.
            2.0 = moderate (0.33x-3.0x), 4.0 = strong (0.2x-5.0x). Default: 4.0.
    """
    image_cooldown_days: float = 7.0
    source_cooldown_days: float = 1.0
    favorite_boost: float = 2.0
    new_image_boost: float = 1.5
    color_match_weight: float = 1.0
    recency_decay: str = 'exponential'
    enabled: bool = True
    use_oklab_similarity: bool = True

    # Time adaptation settings
    time_adaptation_enabled: bool = True
    time_adaptation_method: str = 'fixed'  # 'sunrise_sunset', 'fixed', 'system_theme'
    day_start_time: str = '07:00'
    night_start_time: str = '19:00'
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    location_name: str = ''
    day_preset: str = 'neutral_day'
    night_preset: str = 'cozy_night'
    day_lightness: float = 0.6
    day_temperature: float = 0.0
    day_saturation: float = 0.5
    night_lightness: float = 0.3
    night_temperature: float = 0.4
    night_saturation: float = 0.4
    palette_tolerance: float = 0.2
    time_affinity_weight: float = 4.0  # Strong preference for matching brightness

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to a dictionary.

        Returns:
            Dictionary representation of the config.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SelectionConfig':
        """Create a SelectionConfig from a dictionary.

        Unknown keys are ignored. Missing keys use defaults.

        Args:
            data: Dictionary with config values.

        Returns:
            New SelectionConfig instance.
        """
        # Get valid field names
        valid_fields = {f.name for f in dataclass_fields(cls)}

        # Filter to only valid fields
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)
