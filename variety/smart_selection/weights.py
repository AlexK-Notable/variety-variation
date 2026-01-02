# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Weight calculation strategies for the Smart Selection Engine.

Calculates selection weights based on recency, source rotation,
favorites boost, and new image boost.
"""

import math
import time
from typing import Optional, Dict, Any

from variety.smart_selection.models import ImageRecord, PaletteRecord, SelectionConstraints
from variety.smart_selection.config import SelectionConfig
from variety.smart_selection.palette import palette_similarity


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
    # Never shown or cooldown disabled - handle None and invalid types defensively
    if last_shown_at is None or not isinstance(last_shown_at, (int, float)):
        return 1.0
    if cooldown_days is None or cooldown_days <= 0:
        return 1.0

    now = int(time.time())
    elapsed_seconds = now - int(last_shown_at)
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


def calculate_time_affinity(
    image_palette: Optional[PaletteRecord],
    target_lightness: float,
    target_temperature: float,
    target_saturation: float,
    tolerance: float = 0.3,
    strength: float = 2.0,
) -> float:
    """Calculate affinity between image palette and time-based target.

    This function computes a weight multiplier based on how well an image's
    color characteristics match the target values for the current time period.
    Lightness is weighted most heavily since it matters most for day/night.

    Args:
        image_palette: PaletteRecord for the image, or None if unknown.
        target_lightness: Target lightness value (0.0-1.0).
        target_temperature: Target temperature value (-1.0 to +1.0).
        target_saturation: Target saturation value (0.0-1.0).
        tolerance: How strictly to match (0.1-0.5). Lower = stricter.
        strength: How aggressively to penalize/boost (1.0-3.0).
            1.0 = moderate (0.5x-1.5x), 2.0 = strong (0.25x-2.0x).

    Returns:
        Multiplier based on strength. At strength=2.0:
        - 0.25 for poor match (far from target)
        - 2.0 for excellent match (close to target)
        Returns 1.0 (neutral) if no palette data is available.
    """
    # No palette data - return neutral (don't penalize unindexed images)
    if not image_palette:
        return 1.0

    # Validate target values - return neutral if any are invalid
    if target_lightness is None or target_temperature is None or target_saturation is None:
        return 1.0

    # Get image palette metrics, defaulting to neutral values
    img_lightness = image_palette.avg_lightness if image_palette.avg_lightness is not None else 0.5
    img_temperature = image_palette.color_temperature if image_palette.color_temperature is not None else 0.0
    img_saturation = image_palette.avg_saturation if image_palette.avg_saturation is not None else 0.5

    # Calculate distance in each dimension
    lightness_diff = abs(float(img_lightness) - float(target_lightness))
    temp_diff = abs(float(img_temperature) - float(target_temperature))
    sat_diff = abs(float(img_saturation) - float(target_saturation))

    # Weighted average: lightness matters MOST for day/night distinction
    # Lightness: 70%, Temperature: 20%, Saturation: 10%
    distance = (lightness_diff * 0.7) + (temp_diff * 0.2) + (sat_diff * 0.1)

    # Calculate penalty/boost range based on strength
    # strength=1.0: min=0.5, max=1.5 (weak)
    # strength=2.0: min=0.25, max=2.0 (strong)
    # strength=3.0: min=0.125, max=2.5 (very strong)
    min_mult = 1.0 / (1.0 + strength)  # e.g., 0.33 at strength=2
    max_mult = 1.0 + strength          # e.g., 3.0 at strength=2

    # Convert distance to affinity score using tolerance
    if distance >= tolerance:
        return min_mult

    # Linear interpolation: max_mult at distance=0, min_mult at distance=tolerance
    ratio = distance / tolerance
    affinity = max_mult - (ratio * (max_mult - min_mult))
    return max(min_mult, min(max_mult, affinity))


def color_affinity_factor(
    image_palette: Optional[PaletteRecord],
    target_palette: Optional[Dict[str, Any]],
    config: SelectionConfig,
    constraints: Optional[SelectionConstraints] = None,
) -> float:
    """Calculate color affinity weight multiplier.

    Computes a weight multiplier based on how similar the image's color
    palette is to the target palette. This provides a soft boost/penalty
    for color matching rather than a hard filter.

    Args:
        image_palette: PaletteRecord for the image, or None if unknown.
        target_palette: Target palette dict with avg_* metrics, or None.
        config: SelectionConfig with color_match_weight.
        constraints: Optional constraints with continuity settings.

    Returns:
        Multiplier between 0.1 and 2.0:
        - 0.1 = Very dissimilar (strong penalty)
        - 0.8 = Missing palette data (slight penalty)
        - 1.0 = Neutral (no filtering or color matching disabled)
        - 2.0 = Very similar (strong boost)
    """
    # Color matching disabled or no target
    if not config.color_match_weight or not target_palette:
        return 1.0

    # No palette data for this image - slight penalty to prefer known palettes
    if not image_palette:
        return 0.8

    # Convert PaletteRecord to dict for similarity calculation
    # Include both avg_* metrics (for HSL) and color values (for OKLAB)
    img_palette = {
        'avg_hue': image_palette.avg_hue,
        'avg_saturation': image_palette.avg_saturation,
        'avg_lightness': image_palette.avg_lightness,
        'color_temperature': image_palette.color_temperature,
    }
    # Add color values for OKLAB similarity
    for i in range(16):
        color_attr = f'color{i}'
        if hasattr(image_palette, color_attr):
            img_palette[color_attr] = getattr(image_palette, color_attr)

    # Calculate similarity (0.0 to 1.0)
    # Use OKLAB if configured (default True for perceptual accuracy)
    use_oklab = getattr(config, 'use_oklab_similarity', True)
    similarity = palette_similarity(target_palette, img_palette, use_oklab=use_oklab)

    # Get weight factor from constraints (continuity mode) or config
    weight = config.color_match_weight
    if constraints and hasattr(constraints, 'continuity_weight') and constraints.continuity_weight:
        weight = constraints.continuity_weight

    # Map similarity to affinity multiplier
    # similarity 0.0 -> affinity 0.1 (strong penalty)
    # similarity 0.5 -> affinity 1.0 (neutral)
    # similarity 1.0 -> affinity 2.0 (strong boost)
    if similarity >= 0.5:
        # Linear interpolation from 1.0 to (1.0 + weight)
        # At similarity=1.0, affinity = 1.0 + weight (capped at 2.0)
        affinity = 1.0 + (similarity - 0.5) * 2.0 * weight
    else:
        # Linear interpolation from 0.1 to 1.0
        # At similarity=0.0, affinity = 0.1
        affinity = 0.1 + (similarity / 0.5) * 0.9

    # Clamp to valid range
    return max(0.1, min(2.0, affinity))


def calculate_weight(
    image: ImageRecord,
    source_last_shown_at: Optional[int],
    config: SelectionConfig,
    image_palette: Optional[PaletteRecord] = None,
    target_palette: Optional[Dict[str, Any]] = None,
    constraints: Optional[SelectionConstraints] = None,
    time_target_lightness: Optional[float] = None,
    time_target_temperature: Optional[float] = None,
    time_target_saturation: Optional[float] = None,
) -> float:
    """Calculate combined selection weight for an image.

    Weight formula:
        weight = recency * source_recency * favorite_boost * new_boost * color_affinity * time_affinity

    All factors are multiplicative, so a low score in any area
    significantly reduces the overall weight.

    Args:
        image: ImageRecord with image metadata.
        source_last_shown_at: When the image's source was last used.
        config: SelectionConfig with weight parameters.
        image_palette: Optional PaletteRecord for color affinity calculation.
        target_palette: Optional target palette dict for color matching.
        constraints: Optional SelectionConstraints with color settings.
        time_target_lightness: Target lightness for time-based selection (0.0-1.0).
            If None, time affinity is not applied.
        time_target_temperature: Target temperature for time-based selection (-1.0 to +1.0).
        time_target_saturation: Target saturation for time-based selection (0.0-1.0).

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
    color_affinity = color_affinity_factor(image_palette, target_palette, config, constraints)

    # Calculate time affinity if time adaptation is enabled and targets are provided
    time_affinity = 1.0
    if (config.time_adaptation_enabled and
        time_target_lightness is not None and
        time_target_temperature is not None and
        time_target_saturation is not None):
        time_affinity = calculate_time_affinity(
            image_palette,
            time_target_lightness,
            time_target_temperature,
            time_target_saturation,
            config.palette_tolerance,
            getattr(config, 'time_affinity_weight', 2.0),
        )

    # Combine multiplicatively with minimum floor to prevent zero collapse
    weight = recency * source * fav_boost * new_boost * color_affinity * time_affinity
    return max(weight, 1e-6)
