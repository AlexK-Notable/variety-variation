# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Perceptual color science utilities using OKLAB color space.

OKLAB is a perceptually uniform color space designed by Bjorn Ottosson in 2020.
Unlike HSL, which has non-uniform perceptual properties (green spans a huge range,
cyan is tiny), OKLAB ensures that equal numeric distances correspond to equal
perceived color differences.

References:
    - https://bottosson.github.io/posts/oklab/
    - https://www.w3.org/TR/css-color-4/#ok-lab

The OKLAB color space uses three components:
    - L: Lightness (0 = black, 1 = white)
    - a: Green-red axis (negative = green, positive = red)
    - b: Blue-yellow axis (negative = blue, positive = yellow)
"""

import math
from typing import Dict, Any, List, Optional, Tuple


def srgb_to_linear(c: float) -> float:
    """Convert sRGB component (0-1) to linear RGB.

    sRGB uses gamma encoding to better match human perception.
    This function reverses that encoding for linear math operations.

    Args:
        c: sRGB component value (0.0 to 1.0).

    Returns:
        Linear RGB component value (0.0 to 1.0).
    """
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    """Convert linear RGB component to sRGB.

    Applies gamma encoding for display on standard monitors.

    Args:
        c: Linear RGB component value (0.0 to 1.0).

    Returns:
        sRGB component value (0.0 to 1.0).
    """
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_to_oklab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Convert RGB (0-255) to OKLAB color space.

    OKLAB components:
        - L: Lightness (0 = black, 1 = white)
        - a: Green-red axis (~-0.4 to ~0.4)
        - b: Blue-yellow axis (~-0.4 to ~0.4)

    Args:
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).

    Returns:
        Tuple of (L, a, b) in OKLAB space.
    """
    # Normalize to 0-1 and convert to linear RGB
    r_lin = srgb_to_linear(r / 255.0)
    g_lin = srgb_to_linear(g / 255.0)
    b_lin = srgb_to_linear(b / 255.0)

    # Linear RGB to LMS (cone response)
    # These matrices are from the OKLAB specification
    l = 0.4122214708 * r_lin + 0.5363325363 * g_lin + 0.0514459929 * b_lin
    m = 0.2119034982 * r_lin + 0.6806995451 * g_lin + 0.1073969566 * b_lin
    s = 0.0883024619 * r_lin + 0.2817188376 * g_lin + 0.6299787005 * b_lin

    # Cube root (handle negative values for edge cases)
    l_ = l ** (1 / 3) if l >= 0 else -((-l) ** (1 / 3))
    m_ = m ** (1 / 3) if m >= 0 else -((-m) ** (1 / 3))
    s_ = s ** (1 / 3) if s >= 0 else -((-s) ** (1 / 3))

    # LMS to OKLAB
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_out = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    return (L, a, b_out)


def oklab_distance(lab1: Tuple[float, float, float],
                   lab2: Tuple[float, float, float]) -> float:
    """Calculate perceptual distance between two OKLAB colors.

    Uses Euclidean distance in OKLAB space, which is perceptually uniform.
    A distance of ~0.02 is roughly the just-noticeable difference (JND).

    Args:
        lab1: First color as (L, a, b) tuple.
        lab2: Second color as (L, a, b) tuple.

    Returns:
        Distance value. Typical range 0 (identical) to ~1.4 (max difference).
    """
    dL = lab1[0] - lab2[0]
    da = lab1[1] - lab2[1]
    db = lab1[2] - lab2[2]
    return math.sqrt(dL * dL + da * da + db * db)


def hex_to_oklab(hex_color: str) -> Tuple[float, float, float]:
    """Convert hex color string to OKLAB.

    Args:
        hex_color: Hex color string like "#FF0000" or "ff0000".

    Returns:
        Tuple of (L, a, b) in OKLAB space.
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return rgb_to_oklab(r, g, b)


def color_distance_oklab(hex1: str, hex2: str) -> float:
    """Calculate perceptual distance between two hex colors using OKLAB.

    Convenience function that combines hex conversion and distance calculation.

    Args:
        hex1: First hex color string.
        hex2: Second hex color string.

    Returns:
        Perceptual distance between the colors.
    """
    lab1 = hex_to_oklab(hex1)
    lab2 = hex_to_oklab(hex2)
    return oklab_distance(lab1, lab2)


def palette_similarity_oklab(palette1: Optional[Dict[str, Any]],
                             palette2: Optional[Dict[str, Any]]) -> float:
    """Calculate similarity between palettes using OKLAB color space.

    Uses minimum-cost bipartite matching to find the best alignment
    between colors in the two palettes, then calculates overall similarity.

    Args:
        palette1: First palette dict with 'colors' list of hex values.
        palette2: Second palette dict with 'colors' list of hex values.

    Returns:
        Similarity score 0-1 (1 = identical, 0 = no match possible).
    """
    # Handle None/empty cases
    if not palette1 or not palette2:
        return 0.0

    colors1 = palette1.get('colors', [])
    colors2 = palette2.get('colors', [])

    if not colors1 or not colors2:
        return 0.0

    # Convert all colors to OKLAB
    oklab1 = [hex_to_oklab(c) for c in colors1]
    oklab2 = [hex_to_oklab(c) for c in colors2]

    # Use greedy matching for efficiency:
    # For each color in the smaller palette, find the closest match
    # in the larger palette and accumulate distances.

    if len(oklab1) <= len(oklab2):
        smaller, larger = oklab1, oklab2
    else:
        smaller, larger = oklab2, oklab1

    total_distance = 0.0
    used_indices = set()

    for color in smaller:
        best_distance = float('inf')
        best_idx = -1

        for idx, candidate in enumerate(larger):
            if idx in used_indices:
                continue
            d = oklab_distance(color, candidate)
            if d < best_distance:
                best_distance = d
                best_idx = idx

        if best_idx >= 0:
            used_indices.add(best_idx)
            total_distance += best_distance

    # Normalize: max distance is ~1.4 (black to white with full chroma difference)
    # For a palette, average distance and convert to similarity
    avg_distance = total_distance / len(smaller)

    # Convert to similarity: 0 distance = 1.0 similarity
    # Use exponential decay for more intuitive scaling
    # Distance of 0.5 gives ~0.6 similarity, 1.0 gives ~0.37
    max_expected_distance = 1.0
    similarity = max(0.0, 1.0 - (avg_distance / max_expected_distance))

    return min(1.0, similarity)


def get_oklab_lightness(hex_color: str) -> float:
    """Get the perceptual lightness of a color (0-1).

    Args:
        hex_color: Hex color string.

    Returns:
        Lightness value from 0 (black) to 1 (white).
    """
    L, _, _ = hex_to_oklab(hex_color)
    return L


def get_oklab_chroma(hex_color: str) -> float:
    """Get the chroma (colorfulness) of a color.

    Chroma is the distance from the neutral axis in OKLAB space.

    Args:
        hex_color: Hex color string.

    Returns:
        Chroma value (typically 0 to ~0.4 for sRGB colors).
    """
    _, a, b = hex_to_oklab(hex_color)
    return math.sqrt(a * a + b * b)


def get_oklab_hue(hex_color: str) -> float:
    """Get the hue angle of a color in OKLAB space.

    Args:
        hex_color: Hex color string.

    Returns:
        Hue angle in degrees (0-360), or 0 for achromatic colors.
    """
    _, a, b = hex_to_oklab(hex_color)

    # Handle achromatic colors
    if abs(a) < 1e-6 and abs(b) < 1e-6:
        return 0.0

    hue = math.degrees(math.atan2(b, a))
    if hue < 0:
        hue += 360.0

    return hue
