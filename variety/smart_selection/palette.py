# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Wallust color palette integration for the Smart Selection Engine.

Extracts color palettes from images using wallust and calculates
derived color metrics for similarity matching.
"""

import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Any, List, Optional, Tuple

from variety.smart_selection.models import PaletteRecord
from variety.smart_selection.wallust_config import get_config_manager

logger = logging.getLogger(__name__)


def hex_to_hsl(hex_color: str) -> Tuple[float, float, float]:
    """Convert hex color to HSL (Hue, Saturation, Lightness).

    Args:
        hex_color: Hex color string like "#FF0000" or "#ff0000".

    Returns:
        Tuple of (hue, saturation, lightness) where:
        - hue is 0-360 degrees
        - saturation is 0-1
        - lightness is 0-1
    """
    # Remove # prefix and convert to RGB
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    max_c = max(r, g, b)
    min_c = min(r, g, b)
    delta = max_c - min_c

    # Lightness
    l = (max_c + min_c) / 2.0

    # Saturation
    if delta == 0:
        s = 0.0
    elif l < 0.5:
        s = delta / (max_c + min_c)
    else:
        s = delta / (2.0 - max_c - min_c)

    # Hue
    if delta == 0:
        h = 0.0
    elif max_c == r:
        h = 60.0 * (((g - b) / delta) % 6)
    elif max_c == g:
        h = 60.0 * (((b - r) / delta) + 2)
    else:  # max_c == b
        h = 60.0 * (((r - g) / delta) + 4)

    # Ensure hue is positive
    if h < 0:
        h += 360.0

    return (h, s, l)


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert HSL values to hex color string.

    Args:
        h: Hue in degrees (0-360).
        s: Saturation (0-1).
        l: Lightness (0-1).

    Returns:
        Hex color string like "#FF0000".
    """
    # Clamp values to valid ranges
    h = h % 360
    s = max(0.0, min(1.0, s))
    l = max(0.0, min(1.0, l))

    # Achromatic case
    if s == 0:
        val = int(l * 255)
        return f"#{val:02x}{val:02x}{val:02x}"

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1/6:
            return p + (q - p) * 6 * t
        if t < 1/2:
            return q
        if t < 2/3:
            return p + (q - p) * (2/3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    h_normalized = h / 360

    r = hue_to_rgb(p, q, h_normalized + 1/3)
    g = hue_to_rgb(p, q, h_normalized)
    b = hue_to_rgb(p, q, h_normalized - 1/3)

    r_int = int(round(r * 255))
    g_int = int(round(g * 255))
    b_int = int(round(b * 255))

    # Clamp to valid range
    r_int = max(0, min(255, r_int))
    g_int = max(0, min(255, g_int))
    b_int = max(0, min(255, b_int))

    return f"#{r_int:02x}{g_int:02x}{b_int:02x}"


def calculate_temperature(hue: float, saturation: float, lightness: float) -> float:
    """Calculate color temperature from HSL values.

    Returns a value from -1 (very cool/blue) to +1 (very warm/orange).
    Desaturated colors return near zero.

    Args:
        hue: Hue in degrees (0-360).
        saturation: Saturation (0-1).
        lightness: Lightness (0-1).

    Returns:
        Temperature value from -1 to +1.
    """
    # Low saturation = neutral temperature
    if saturation < 0.1:
        return 0.0

    # Map hue to temperature
    # Warm: 0-60 (red to yellow), 300-360 (magenta to red)
    # Cool: 150-270 (cyan to blue-violet)
    # Neutral: 60-150 (yellow-green to cyan), 270-300 (violet to magenta)

    if hue <= 60:
        # Red to yellow: very warm
        temp = 1.0 - (hue / 60.0) * 0.3  # 1.0 to 0.7
    elif hue <= 150:
        # Yellow-green to cyan: transitioning to cool
        temp = 0.7 - ((hue - 60) / 90.0) * 1.4  # 0.7 to -0.7
    elif hue <= 270:
        # Cyan to blue-violet: cool
        temp = -0.7 - ((hue - 150) / 120.0) * 0.3  # -0.7 to -1.0
    else:
        # Violet to red: transitioning back to warm
        temp = -1.0 + ((hue - 270) / 90.0) * 2.0  # -1.0 to 1.0

    # Scale by saturation (less saturated = more neutral)
    return temp * saturation


def rgb_dict_to_hex(rgb: Dict[str, float]) -> str:
    """Convert RGB dict with 0-1 float values to hex string.

    Args:
        rgb: Dict with 'red', 'green', 'blue' keys (0-1 float range).

    Returns:
        Hex color string like "#FF0000".
    """
    r = int(rgb.get('red', 0) * 255)
    g = int(rgb.get('green', 0) * 255)
    b = int(rgb.get('blue', 0) * 255)
    # Clamp to valid range
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_wallust_json(json_data) -> Dict[str, Any]:
    """Parse wallust JSON output and calculate derived metrics.

    Handles two formats:
    1. Legacy dict format: {"color0": "#RRGGBB", "color1": "#RRGGBB", ...}
    2. Cache format: [[{"red": 0.9, "green": 0.8, "blue": 0.7}, ...], ...]
       (list of palettes, each containing RGB dicts with 0-1 float values)

    Args:
        json_data: Either dict or list from wallust JSON output.

    Returns:
        Dictionary with colors and derived metrics.
    """
    result = {}

    # Detect and convert cache format (list of palettes)
    if isinstance(json_data, list) and len(json_data) > 0:
        # Take the first palette (usually the main one)
        first_palette = json_data[0]
        if isinstance(first_palette, list):
            # Convert RGB dicts to colorN format
            logger.debug(f"Converting wallust cache format: {len(first_palette)} colors")
            for i, rgb in enumerate(first_palette[:16]):
                if isinstance(rgb, dict) and 'red' in rgb:
                    result[f'color{i}'] = rgb_dict_to_hex(rgb)
            # Use first color as background, color7 as foreground (common convention)
            if first_palette:
                result['background'] = rgb_dict_to_hex(first_palette[0])
            if len(first_palette) > 7:
                result['foreground'] = rgb_dict_to_hex(first_palette[7])
                # Default cursor to foreground
                result['cursor'] = result['foreground']
    elif isinstance(json_data, dict):
        # Legacy format: copy color values directly
        for key in ['background', 'foreground', 'cursor']:
            if key in json_data:
                result[key] = json_data[key]

        for i in range(16):
            key = f'color{i}'
            if key in json_data:
                result[key] = json_data[key]

        # Fallback: cursor defaults to foreground if not provided
        if 'cursor' not in result and 'foreground' in result:
            result['cursor'] = result['foreground']
    else:
        logger.warning(f"Unknown wallust JSON format: {type(json_data)}")
        return result

    # Calculate average metrics from the 16 colors
    hues = []
    saturations = []
    lightnesses = []
    temperatures = []

    for i in range(16):
        key = f'color{i}'
        if key in result:
            h, s, l = hex_to_hsl(result[key])
            hues.append(h)
            saturations.append(s)
            lightnesses.append(l)
            temperatures.append(calculate_temperature(h, s, l))

    if hues:
        # For hue, we need to handle circular average
        # Convert to unit vectors and average
        sin_sum = sum(math.sin(math.radians(h)) for h in hues)
        cos_sum = sum(math.cos(math.radians(h)) for h in hues)
        avg_hue = math.degrees(math.atan2(sin_sum, cos_sum))
        if avg_hue < 0:
            avg_hue += 360

        result['avg_hue'] = avg_hue
        result['avg_saturation'] = sum(saturations) / len(saturations)
        result['avg_lightness'] = sum(lightnesses) / len(lightnesses)
        result['color_temperature'] = sum(temperatures) / len(temperatures)

    return result


class PaletteExtractor:
    """Extracts color palettes from images using wallust."""

    def __init__(self, wallust_path: Optional[str] = None):
        """Initialize the palette extractor.

        Args:
            wallust_path: Path to wallust binary. If None, uses system PATH.
        """
        self.wallust_path = wallust_path or shutil.which('wallust')
        self._executor: Optional[ThreadPoolExecutor] = None
        self._shutdown_event = threading.Event()

    def is_wallust_available(self) -> bool:
        """Check if wallust is available.

        Returns:
            True if wallust is installed and executable.
        """
        if not self.wallust_path:
            return False

        try:
            result = subprocess.run(
                [self.wallust_path, '--version'],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_palette_type(self) -> str:
        """Get the palette type from wallust configuration.

        Uses centralized WallustConfigManager for caching and change detection.

        Returns:
            Palette type string like 'Dark16', 'Light16', etc.
        """
        return get_config_manager().get_palette_type()

    def extract_palette(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Extract color palette from an image using wallust.

        Args:
            image_path: Path to the image file.

        Returns:
            Dictionary with colors and derived metrics, or None on failure.
        """
        if not os.path.exists(image_path):
            return None

        if not self.wallust_path:
            logger.warning("wallust not available")
            return None

        try:
            # Record time before running wallust to find new cache entries
            start_time = time.time()

            # Run wallust with fastresize backend (doesn't need ImageMagick)
            # Skip terminal sequences and templates, just generate cache
            # Use -w to overwrite cache so mtime is always updated
            result = subprocess.run(
                [
                    self.wallust_path, 'run',
                    '-s',  # Skip terminal sequences
                    '-T',  # Skip templates
                    '-q',  # Quiet
                    '-w',  # Overwrite cache (ensures mtime is updated)
                    '--backend', 'fastresize',
                    image_path,
                ],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')
                if 'Not enough colors' in stderr:
                    logger.debug(f"Image has insufficient color variety: {image_path}")
                else:
                    logger.warning(f"wallust failed for {image_path}: {stderr}")
                return None

            # Read from wallust's cache
            # Wallust stores palettes in ~/.cache/wallust/{hash}_1.7/
            cache_dir = os.path.expanduser('~/.cache/wallust')
            if not os.path.isdir(cache_dir):
                logger.warning("wallust cache directory not found")
                return None

            # Find cache entries modified AFTER we started wallust
            # This ensures we get the correct entry even with concurrent processes
            # Subtract 1 second tolerance for filesystem timing differences
            #
            # LIMITATION: Timestamp-based cache matching
            # -------------------------------------------
            # This cache file discovery uses filesystem modification times (mtime)
            # to identify the wallust output for the current image. This approach
            # is best-effort and has the following characteristics:
            #
            # 1. SAFE for single-process Variety usage (the normal case):
            #    - Variety's debouncing ensures only one wallust process runs at a time
            #    - The 1-second tolerance handles filesystem timestamp precision
            #
            # 2. THEORETICAL RACE CONDITION with multiple Variety instances:
            #    - If two Variety processes run wallust simultaneously, timestamp
            #      matching could theoretically select the wrong cache file
            #    - This is an edge case: multiple Variety instances are rare
            #    - Even if it occurs, the worst case is selecting a different palette
            #      (not a crash or data corruption)
            #
            # 3. MORE ROBUST SOLUTION would require wallust changes:
            #    - Wallust could include the source image hash in cache filenames
            #    - This would allow deterministic matching without timestamp dependency
            #    - Example: ~/.cache/wallust/{image_hash}_{palette_type}.json
            #
            # The current implementation prioritizes simplicity and works reliably
            # for the vast majority of use cases. The timestamp approach is adequate
            # given Variety's single-threaded architecture and wallust debouncing.
            search_threshold = start_time - 1.0
            latest_time = 0
            latest_file = None

            # Get configured palette type
            palette_type = self._get_palette_type()

            for entry in os.listdir(cache_dir):
                entry_path = os.path.join(cache_dir, entry)
                if os.path.isdir(entry_path):
                    # Look for palette files matching configured type
                    for subfile in os.listdir(entry_path):
                        if palette_type in subfile:
                            filepath = os.path.join(entry_path, subfile)
                            mtime = os.path.getmtime(filepath)
                            # Only consider files modified after threshold
                            if mtime >= search_threshold and mtime > latest_time:
                                latest_time = mtime
                                latest_file = filepath

            if latest_file:
                with open(latest_file, 'r') as f:
                    json_data = json.load(f)
                return parse_wallust_json(json_data)

            logger.warning(f"wallust did not produce cached output for {image_path}")
            return None

        except subprocess.TimeoutExpired:
            logger.warning(f"wallust timed out processing {image_path}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse wallust JSON: {e}")
            return None
        except subprocess.SubprocessError as e:
            logger.warning(f"wallust subprocess error for {image_path}: {e}")
            return None
        except OSError as e:
            logger.warning(f"OS error extracting palette from {image_path}: {e}")
            return None
        except ValueError as e:
            # Palette parsing errors (e.g., invalid color format)
            logger.warning(f"Failed to parse palette data from {image_path}: {e}")
            return None

    def _extract_single(self, image_path: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Thread-safe wrapper for single extraction.

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (image_path, palette_data or None).
        """
        # Check shutdown event before processing
        if self._shutdown_event.is_set():
            return (image_path, None)

        try:
            result = self.extract_palette(image_path)
            return (image_path, result)
        except Exception as e:
            logger.warning(f"Exception extracting palette from {image_path}: {e}")
            return (image_path, None)

    def extract_all_palettes_parallel(
        self,
        images: List[str],
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Extract palettes in parallel using ThreadPoolExecutor.

        Args:
            images: List of image paths.
            max_workers: Number of parallel workers (default 4).
            progress_callback: Called with (completed, total).

        Returns:
            Dict mapping filepath to palette data (or None if failed).
        """
        if not images:
            return {}

        results: Dict[str, Optional[Dict[str, Any]]] = {}
        total = len(images)
        completed = 0

        # Reset shutdown event for new extraction batch
        self._shutdown_event.clear()

        # Create executor for this batch
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        try:
            # Submit all tasks
            future_to_path = {
                self._executor.submit(self._extract_single, path): path
                for path in images
            }

            # Process results as they complete
            for future in as_completed(future_to_path):
                # Check for shutdown
                if self._shutdown_event.is_set():
                    # Cancel remaining futures
                    for f in future_to_path:
                        f.cancel()
                    break

                try:
                    path, palette_data = future.result(timeout=60)
                    results[path] = palette_data
                except Exception as e:
                    # Handle any exception from the future
                    path = future_to_path[future]
                    logger.warning(f"Failed to get result for {path}: {e}")
                    results[path] = None

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        finally:
            # Clean up executor
            self._executor.shutdown(wait=False)
            self._executor = None

        # Ensure all paths are in results (for cancelled futures)
        for path in images:
            if path not in results:
                results[path] = None

        return results

    def shutdown(self) -> None:
        """Graceful shutdown with event signaling.

        Signals running extractions to stop and cleans up the executor.
        Safe to call multiple times.
        """
        # Signal shutdown to running extractions
        self._shutdown_event.set()

        # Shutdown executor if active
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None


def create_palette_record(filepath: str, palette_data: Dict[str, Any]) -> PaletteRecord:
    """Create a PaletteRecord from extracted palette data.

    Args:
        filepath: Path to the image file.
        palette_data: Dictionary from parse_wallust_json.

    Returns:
        PaletteRecord instance.
    """
    return PaletteRecord(
        filepath=filepath,
        color0=palette_data.get('color0'),
        color1=palette_data.get('color1'),
        color2=palette_data.get('color2'),
        color3=palette_data.get('color3'),
        color4=palette_data.get('color4'),
        color5=palette_data.get('color5'),
        color6=palette_data.get('color6'),
        color7=palette_data.get('color7'),
        color8=palette_data.get('color8'),
        color9=palette_data.get('color9'),
        color10=palette_data.get('color10'),
        color11=palette_data.get('color11'),
        color12=palette_data.get('color12'),
        color13=palette_data.get('color13'),
        color14=palette_data.get('color14'),
        color15=palette_data.get('color15'),
        background=palette_data.get('background'),
        foreground=palette_data.get('foreground'),
        cursor=palette_data.get('cursor'),
        avg_hue=palette_data.get('avg_hue'),
        avg_saturation=palette_data.get('avg_saturation'),
        avg_lightness=palette_data.get('avg_lightness'),
        color_temperature=palette_data.get('color_temperature'),
        indexed_at=int(time.time()),
    )


def palette_similarity_hsl(palette1: Dict[str, Any], palette2: Dict[str, Any]) -> float:
    """Calculate similarity between two palettes using HSL metrics.

    This is the legacy HSL-based similarity calculation. It uses a weighted
    combination of:
    - Hue similarity (circular distance)
    - Saturation difference
    - Lightness difference
    - Temperature difference

    Note: HSL has non-uniform perceptual properties. For more accurate
    perceptual matching, use palette_similarity with use_oklab=True.

    Args:
        palette1: First palette with avg_* metrics.
        palette2: Second palette with avg_* metrics.

    Returns:
        Similarity score from 0 (very different) to 1 (identical).
    """
    # Handle missing data
    if not palette1 or not palette2:
        return 0.0

    # Hue similarity (circular)
    hue1 = palette1.get('avg_hue', 0)
    hue2 = palette2.get('avg_hue', 0)
    hue_diff = abs(hue1 - hue2)
    if hue_diff > 180:
        hue_diff = 360 - hue_diff
    hue_similarity = 1 - (hue_diff / 180.0)

    # Saturation similarity
    sat1 = palette1.get('avg_saturation', 0.5)
    sat2 = palette2.get('avg_saturation', 0.5)
    sat_similarity = 1 - abs(sat1 - sat2)

    # Lightness similarity
    light1 = palette1.get('avg_lightness', 0.5)
    light2 = palette2.get('avg_lightness', 0.5)
    light_similarity = 1 - abs(light1 - light2)

    # Temperature similarity
    temp1 = palette1.get('color_temperature', 0)
    temp2 = palette2.get('color_temperature', 0)
    temp_similarity = 1 - (abs(temp1 - temp2) / 2.0)  # Range is -1 to 1

    # Weighted average (hue and lightness are most perceptually important)
    weights = {
        'hue': 0.35,
        'saturation': 0.15,
        'lightness': 0.35,
        'temperature': 0.15,
    }

    similarity = (
        weights['hue'] * hue_similarity +
        weights['saturation'] * sat_similarity +
        weights['lightness'] * light_similarity +
        weights['temperature'] * temp_similarity
    )

    return max(0.0, min(1.0, similarity))


def palette_similarity(
    palette1: Dict[str, Any],
    palette2: Dict[str, Any],
    use_oklab: bool = True,
) -> float:
    """Calculate similarity between two palettes.

    When use_oklab=True (default), uses the perceptually uniform OKLAB
    color space for more accurate color matching. This requires color
    values in the palette (color0-color15).

    When use_oklab=False, falls back to HSL-based metrics (avg_hue,
    avg_saturation, avg_lightness, color_temperature).

    Args:
        palette1: First palette dict. For OKLAB: needs color0-color15.
                  For HSL: needs avg_* metrics.
        palette2: Second palette dict.
        use_oklab: If True, use OKLAB color space (default).
                   If False, use legacy HSL-based similarity.

    Returns:
        Similarity score from 0 (very different) to 1 (identical).
    """
    # Handle missing data
    if not palette1 or not palette2:
        return 0.0

    if use_oklab:
        # Extract colors for OKLAB comparison
        colors1 = _extract_palette_colors(palette1)
        colors2 = _extract_palette_colors(palette2)

        if colors1 and colors2:
            from variety.smart_selection.color_science import palette_similarity_oklab
            return palette_similarity_oklab(
                {'colors': colors1},
                {'colors': colors2},
            )
        # Fall back to HSL if no color values available
        return palette_similarity_hsl(palette1, palette2)

    return palette_similarity_hsl(palette1, palette2)


def _extract_palette_colors(palette: Dict[str, Any]) -> list:
    """Extract color hex values from a palette dict.

    Looks for color0 through color15 keys.

    Args:
        palette: Palette dict with colorN keys.

    Returns:
        List of hex color strings found.
    """
    colors = []
    for i in range(16):
        key = f'color{i}'
        if key in palette and palette[key]:
            colors.append(palette[key])
    return colors
