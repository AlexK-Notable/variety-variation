# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Theme override for the Reverse Theming Pipeline.

Manages active theme state and provides palette override for
template processing and wallpaper selection matching.
"""

import logging
from typing import Dict, Any, Optional

from variety.smart_selection.database import ImageDatabase

logger = logging.getLogger(__name__)


class ThemeOverride:
    """Manages active theme state and provides palette override.

    When a theme is activated, template processing uses the theme's
    palette instead of wallust-extracted palettes. Also provides
    target palette data for wallpaper selection matching.
    """

    def __init__(self, db: ImageDatabase):
        """Initialize theme override.

        Args:
            db: ImageDatabase instance for theme lookups.
        """
        self._db = db
        self._active_theme_id: Optional[str] = None
        self._cached_palette: Optional[Dict[str, str]] = None

    @property
    def is_active(self) -> bool:
        """Whether a theme override is currently active."""
        return self._active_theme_id is not None

    @property
    def active_theme_id(self) -> Optional[str]:
        """The currently active theme ID, or None."""
        return self._active_theme_id

    def activate(self, theme_id: str) -> None:
        """Activate theme override.

        Loads the theme from the database and caches its palette.

        Args:
            theme_id: ID of the theme to activate.

        Raises:
            ValueError: If the theme is not found in the database.
        """
        theme = self._db.get_color_theme(theme_id)
        if theme is None:
            raise ValueError(f"Theme not found: {theme_id}")
        self._active_theme_id = theme_id
        self._cached_palette = theme.to_dict()

    def deactivate(self) -> None:
        """Deactivate theme override, return to wallust-driven mode."""
        self._active_theme_id = None
        self._cached_palette = None

    def get_override_palette(self) -> Optional[Dict[str, str]]:
        """Get the active theme's palette dict, or None if inactive.

        Returns:
            Dict with color0-15, background, foreground, cursor keys,
            or None if no theme is active.
        """
        if not self.is_active:
            return None
        return self._cached_palette

    def get_target_palette_for_selection(self) -> Optional[Dict[str, Any]]:
        """Get palette dict with metrics for wallpaper selection matching.

        Returns dict with color0-15 + avg_hue, avg_saturation, avg_lightness,
        color_temperature -- suitable for use as SelectionConstraints.target_palette.

        Returns:
            Dict with color and metric keys when active, None if inactive.
        """
        if not self.is_active or not self._active_theme_id:
            return None
        theme = self._db.get_color_theme(self._active_theme_id)
        if theme is None:
            return None
        return theme.to_dict(include_metrics=True)
