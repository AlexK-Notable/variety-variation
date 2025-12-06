# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Weight calculation strategies for the Smart Selection Engine.

Calculates selection weights based on recency, source rotation,
favorites boost, and new image boost.
"""

import math
import time
from typing import Optional

from variety.smart_selection.models import ImageRecord
from variety.smart_selection.config import SelectionConfig


def recency_factor(
    last_shown_at: Optional[int],
    cooldown_days: float,
    decay: str = 'exponential',
) -> float:
    """Calculate recency factor for an image.

    Returns a value between 0 and 1, where:
    - 1.0 = fully available (never shown or past cooldown)
    - 0.0 = completely suppressed (just shown, with step decay)

    Args:
        last_shown_at: Unix timestamp when image was last shown, or None.
        cooldown_days: Number of days for full cooldown. 0 = disabled.
        decay: Decay function type: 'exponential', 'linear', or 'step'.

    Returns:
        Factor between 0 and 1.
    """
    # Never shown or cooldown disabled
    if last_shown_at is None or cooldown_days <= 0:
        return 1.0

    now = int(time.time())
    elapsed_seconds = now - last_shown_at
    cooldown_seconds = cooldown_days * 24 * 60 * 60

    # Guard against negative elapsed time (clock jumped backward)
    # Treat as "just shown" to avoid math errors
    if elapsed_seconds < 0:
        elapsed_seconds = 0

    # Past cooldown
    if elapsed_seconds >= cooldown_seconds:
        return 1.0

    # Calculate progress through cooldown (0 = just shown, 1 = cooldown complete)
    progress = elapsed_seconds / cooldown_seconds

    if decay == 'step':
        # Hard cutoff: 0 until cooldown, then 1
        return 0.0
    elif decay == 'linear':
        # Linear increase from 0 to 1
        return progress
    else:  # exponential (default)
        # S-curve using sigmoid: gives ~0.5 at midpoint
        # Transform progress [0,1] to sigmoid input [-6, 6] for smooth S-curve
        x = (progress - 0.5) * 12  # Maps 0->-6, 0.5->0, 1->6
        return 1 / (1 + math.exp(-x))


def source_factor(
    last_shown_at: Optional[int],
    cooldown_days: float,
    decay: str = 'exponential',
) -> float:
    """Calculate source rotation factor.

    Same logic as recency_factor but for source-level tracking.

    Args:
        last_shown_at: Unix timestamp when source was last used, or None.
        cooldown_days: Number of days for source cooldown. 0 = disabled.
        decay: Decay function type.

    Returns:
        Factor between 0 and 1.
    """
    return recency_factor(last_shown_at, cooldown_days, decay)


def favorite_boost(is_favorite: bool, boost_value: float) -> float:
    """Calculate favorite boost multiplier.

    Args:
        is_favorite: Whether the image is a favorite.
        boost_value: The boost multiplier to apply.

    Returns:
        boost_value if favorite, 1.0 otherwise.
    """
    return boost_value if is_favorite else 1.0


def new_image_boost(times_shown: int, boost_value: float) -> float:
    """Calculate new image boost multiplier.

    Args:
        times_shown: Number of times image has been shown.
        boost_value: The boost multiplier to apply.

    Returns:
        boost_value if never shown (times_shown=0), 1.0 otherwise.
    """
    return boost_value if times_shown == 0 else 1.0


def calculate_weight(
    image: ImageRecord,
    source_last_shown_at: Optional[int],
    config: SelectionConfig,
) -> float:
    """Calculate combined selection weight for an image.

    Weight formula:
        weight = recency * source_recency * favorite_boost * new_boost

    All factors are multiplicative, so a low score in any area
    significantly reduces the overall weight.

    Args:
        image: ImageRecord with image metadata.
        source_last_shown_at: When the image's source was last used.
        config: SelectionConfig with weight parameters.

    Returns:
        Combined weight (higher = more likely to be selected).
    """
    # If smart selection disabled, return uniform weights
    if not config.enabled:
        return 1.0

    # Calculate individual factors
    recency = recency_factor(
        image.last_shown_at,
        config.image_cooldown_days,
        config.recency_decay,
    )

    source = source_factor(
        source_last_shown_at,
        config.source_cooldown_days,
        config.recency_decay,
    )

    fav_boost = favorite_boost(image.is_favorite, config.favorite_boost)
    new_boost = new_image_boost(image.times_shown, config.new_image_boost)

    # Combine multiplicatively with minimum floor to prevent zero collapse
    weight = recency * source * fav_boost * new_boost
    return max(weight, 1e-6)
