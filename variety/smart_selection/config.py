# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Configuration for the Smart Selection Engine.

Defines parameters that control selection behavior including
recency penalties, weight multipliers, and decay functions.
"""

from dataclasses import dataclass, field, fields as dataclass_fields, asdict
from typing import Dict, Any


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
    """
    image_cooldown_days: float = 7.0
    source_cooldown_days: float = 1.0
    favorite_boost: float = 2.0
    new_image_boost: float = 1.5
    color_match_weight: float = 1.0
    recency_decay: str = 'exponential'
    enabled: bool = True

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
