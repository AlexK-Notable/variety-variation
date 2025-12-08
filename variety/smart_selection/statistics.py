# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Collection statistics calculator for the Smart Selection Engine.

Provides cached statistical analysis of the wallpaper collection including:
- Lightness distribution (dark/medium-dark/medium-light/light)
- Hue distribution (8 color families from the color wheel)
- Saturation distribution (muted/moderate/saturated/vibrant)
- Freshness distribution (never shown/rarely shown/often shown/frequently shown)
- Gap detection for underrepresented categories
- Summary text generation for UI display
"""

import logging
from typing import Dict, List, Any, Optional

from variety.smart_selection.database import ImageDatabase

logger = logging.getLogger(__name__)


class CollectionStatistics:
    """Calculates and caches collection statistics.

    This class wraps database aggregate queries and provides caching
    to avoid redundant calculations. Cache is invalidated when the
    collection changes (images shown, palettes indexed, etc.).

    Thread-safety: All database operations are thread-safe via the
    ImageDatabase's internal locking. The cache flag is a simple
    boolean that doesn't require additional locking.
    """

    def __init__(self, db: ImageDatabase):
        """Initialize the statistics calculator.

        Args:
            db: ImageDatabase instance to query.
        """
        self.db = db
        self._cache: Dict[str, Any] = {}
        self._cache_valid = False

    def invalidate(self):
        """Mark cache as dirty. Called on data changes.

        Should be called whenever images are shown, indexed,
        or palette data is updated to ensure fresh statistics.
        """
        self._cache_valid = False
        self._cache = {}
        logger.debug("Statistics cache invalidated")

    def _ensure_cache_populated(self):
        """Populate all caches in one batch if invalid.

        This "all-or-nothing" cache design ensures consistency:
        either all distributions are cached together, or none are.
        """
        if self._cache_valid:
            return

        # Fetch all distributions in a single pass
        self._cache['lightness'] = self.db.get_lightness_counts()
        self._cache['hue'] = self.db.get_hue_counts()
        self._cache['saturation'] = self.db.get_saturation_counts()
        self._cache['freshness'] = self.db.get_freshness_counts()
        self._cache_valid = True
        logger.debug("Statistics cache populated")

    def get_lightness_distribution(self) -> Dict[str, int]:
        """Get image count by lightness bucket.

        Buckets images based on avg_lightness value from palettes:
        - dark: 0.00 - 0.25
        - medium_dark: 0.25 - 0.50
        - medium_light: 0.50 - 0.75
        - light: 0.75 - 1.00

        Returns:
            Dict[str, int] with bucket names as keys and counts as values.
            Example: {'dark': 15, 'medium_dark': 42, 'medium_light': 30, 'light': 13}
        """
        self._ensure_cache_populated()
        return self._cache['lightness']

    def get_hue_distribution(self) -> Dict[str, int]:
        """Get image count by hue family.

        Categorizes images into 8 color families based on avg_hue (0-360°):
        - red: 0-15° or 345-360°
        - orange: 15-45°
        - yellow: 45-75°
        - green: 75-165°
        - cyan: 165-195°
        - blue: 195-255°
        - purple: 255-285°
        - pink: 285-345°
        - neutral: Images with avg_saturation < 0.1 (grayscale)

        Returns:
            Dict[str, int] with hue family names as keys and counts as values.
            Example: {'red': 5, 'orange': 3, ..., 'neutral': 12}
        """
        self._ensure_cache_populated()
        return self._cache['hue']

    def get_saturation_distribution(self) -> Dict[str, int]:
        """Get image count by saturation level.

        Buckets images based on avg_saturation value from palettes:
        - muted: 0.00 - 0.25
        - moderate: 0.25 - 0.50
        - saturated: 0.50 - 0.75
        - vibrant: 0.75 - 1.00

        Returns:
            Dict[str, int] with bucket names as keys and counts as values.
            Example: {'muted': 20, 'moderate': 35, 'saturated': 30, 'vibrant': 15}
        """
        self._ensure_cache_populated()
        return self._cache['saturation']

    def get_freshness_distribution(self) -> Dict[str, int]:
        """Get image count by display frequency.

        Categorizes images based on times_shown value:
        - never_shown: 0
        - rarely_shown: 1-4
        - often_shown: 5-9
        - frequently_shown: >= 10

        Returns:
            Dict[str, int] with category names as keys and counts as values.
            Example: {'never_shown': 142, 'rarely_shown': 50, 'often_shown': 8, 'frequently_shown': 0}
        """
        self._ensure_cache_populated()
        return self._cache['freshness']

    def get_gaps(self) -> List[str]:
        """Identify underrepresented categories in the collection.

        Analyzes all distributions and returns human-readable insights
        about categories with less than 5% representation.

        Returns:
            List of insight strings. Examples:
            - "Only 3% vibrant wallpapers"
            - "No cyan wallpapers"
            - "Only 2% light wallpapers"

            Empty list if no significant gaps or no images with palettes.
        """
        gaps = []
        total_with_palettes = self.db.count_images_with_palettes()

        if total_with_palettes == 0:
            return gaps

        # Threshold: 5% of total
        threshold = total_with_palettes * 0.05

        # Check lightness gaps
        lightness_dist = self.get_lightness_distribution()
        for category, count in lightness_dist.items():
            if count == 0:
                gaps.append(f"No {category.replace('_', '-')} wallpapers")
            elif count < threshold:
                percentage = int(count / total_with_palettes * 100)
                gaps.append(f"Only {percentage}% {category.replace('_', '-')} wallpapers")

        # Check saturation gaps
        saturation_dist = self.get_saturation_distribution()
        for category, count in saturation_dist.items():
            if count == 0:
                gaps.append(f"No {category} wallpapers")
            elif count < threshold:
                percentage = int(count / total_with_palettes * 100)
                gaps.append(f"Only {percentage}% {category} wallpapers")

        # Check hue gaps (skip neutral as it's expected to vary)
        hue_dist = self.get_hue_distribution()
        for category, count in hue_dist.items():
            if category == 'neutral':
                continue
            if count == 0:
                gaps.append(f"No {category} wallpapers")
            elif count < threshold:
                percentage = int(count / total_with_palettes * 100)
                gaps.append(f"Only {percentage}% {category} wallpapers")

        return gaps

    def _generate_summary(self, category: str, distribution: Dict[str, int]) -> str:
        """Generate summary text for a distribution category.

        Creates human-readable summary text like:
        - "Your collection leans dark (52%)"
        - "Balanced across color families"
        - "Mostly moderate saturation"

        Args:
            category: Category name ('lightness', 'hue', 'saturation', 'freshness')
            distribution: The distribution dict for the category

        Returns:
            Summary text string suitable for UI display
        """
        total = sum(distribution.values())
        if total == 0:
            return "No analyzed wallpapers"

        if category == 'lightness':
            # Find dominant bucket
            max_bucket = max(distribution.items(), key=lambda x: x[1])
            percentage = int(max_bucket[1] / total * 100)
            bucket_name = max_bucket[0].replace('_', '-')
            if percentage >= 40:
                return f"Your collection leans {bucket_name} ({percentage}%)"
            else:
                return "Balanced lightness distribution"

        elif category == 'hue':
            # Find top 2 colors (excluding neutral)
            color_counts = {k: v for k, v in distribution.items() if k != 'neutral'}
            if not color_counts or sum(color_counts.values()) == 0:
                return "Mostly grayscale/neutral tones"

            sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
            top1 = sorted_colors[0]
            top1_pct = int(top1[1] / sum(color_counts.values()) * 100)

            if len(sorted_colors) > 1:
                top2 = sorted_colors[1]
                top2_pct = int(top2[1] / sum(color_counts.values()) * 100)
                return f"Dominant: {top1[0].capitalize()} ({top1_pct}%), {top2[0].capitalize()} ({top2_pct}%)"
            else:
                return f"Dominant: {top1[0].capitalize()} ({top1_pct}%)"

        elif category == 'saturation':
            # Find dominant level
            max_level = max(distribution.items(), key=lambda x: x[1])
            percentage = int(max_level[1] / total * 100)
            if percentage >= 40:
                return f"Mostly {max_level[0]} ({percentage}%)"
            else:
                return "Balanced saturation levels"

        elif category == 'freshness':
            # Highlight never shown count
            never_shown = distribution.get('never_shown', 0)
            if never_shown == 0:
                return "All wallpapers have been shown"
            elif never_shown == total:
                return "No wallpapers shown yet"
            else:
                return f"{never_shown} wallpapers never shown"

        return "Distribution available"

    def get_all_stats(self) -> Dict[str, Any]:
        """Get all statistics in one call (for UI).

        Returns a comprehensive dictionary with all distributions,
        counts, summaries, and gap insights.

        Returns:
            Dictionary containing:
            - total_images: Total images in database
            - total_with_palettes: Count of images with palette data
            - lightness_distribution: Dict of lightness buckets
            - hue_distribution: Dict of hue families
            - saturation_distribution: Dict of saturation levels
            - freshness_distribution: Dict of freshness categories
            - lightness_summary: Summary text for lightness
            - hue_summary: Summary text for hue
            - saturation_summary: Summary text for saturation
            - freshness_summary: Summary text for freshness
            - gaps: List of gap insight strings
        """
        # Ensure cache is populated (uses _ensure_cache_populated internally)
        lightness_dist = self.get_lightness_distribution()
        hue_dist = self.get_hue_distribution()
        saturation_dist = self.get_saturation_distribution()
        freshness_dist = self.get_freshness_distribution()

        # Get counts
        total_images = self.db.count_images()
        total_with_palettes = self.db.count_images_with_palettes()

        # Generate summaries
        lightness_summary = self._generate_summary('lightness', lightness_dist)
        hue_summary = self._generate_summary('hue', hue_dist)
        saturation_summary = self._generate_summary('saturation', saturation_dist)
        freshness_summary = self._generate_summary('freshness', freshness_dist)

        # Get gaps
        gaps = self.get_gaps()

        return {
            'total_images': total_images,
            'total_with_palettes': total_with_palettes,
            'lightness_distribution': lightness_dist,
            'hue_distribution': hue_dist,
            'saturation_distribution': saturation_dist,
            'freshness_distribution': freshness_dist,
            'lightness_summary': lightness_summary,
            'hue_summary': hue_summary,
            'saturation_summary': saturation_summary,
            'freshness_summary': freshness_summary,
            'gaps': gaps,
        }
