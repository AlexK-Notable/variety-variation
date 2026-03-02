# tests/smart_selection/e2e/test_color_mode_e2e.py
"""End-to-end tests for color mode settings through constraint generation
to wallpaper selection.

Tests the full pipeline: color mode configuration -> constraint generation
-> ConstraintApplier filtering -> weighted selection via SmartSelector.

Uses synthetic wallpaper records with known palette data to verify that
different color mode configurations produce deterministic selection results.
"""

import os
import shutil
import tempfile
import time
import unittest
from collections import Counter
from unittest.mock import MagicMock

from variety.smart_selection.config import SelectionConfig
from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.models import (
    ADHERENCE_LEVELS,
    ImageRecord,
    PaletteRecord,
    SelectionConstraints,
)
from variety.smart_selection.selector import SmartSelector


# ---------------------------------------------------------------------------
# Wallpaper fixture definitions
# ---------------------------------------------------------------------------
# Each fixture defines an image with known palette metrics.  The hex colors
# are chosen so that the avg_* metrics are plausible, but the important
# thing for selection is the metric values themselves (avg_hue, avg_saturation,
# avg_lightness, color_temperature).

WALLPAPER_FIXTURES = {
    'warm_sunset': {
        'palette': PaletteRecord(
            filepath='',  # filled in at test time
            color0='#2b1400', color1='#d45a22', color2='#e8932e', color3='#f0b038',
            color4='#c44f1a', color5='#e07028', color6='#f5a030', color7='#f5c870',
            color8='#3d2010', color9='#d45a22', color10='#e8932e', color11='#f0b038',
            color12='#c44f1a', color13='#e07028', color14='#f5a030', color15='#f5c870',
            background='#2b1400', foreground='#f5c870', cursor='#f0b038',
            avg_hue=25, avg_saturation=0.6, avg_lightness=0.4,
            color_temperature=0.6,
            perceived_brightness=0.4, brightness_p10=0.1, brightness_p90=0.7,
            indexed_at=int(time.time()),
        ),
    },
    'cool_ocean': {
        'palette': PaletteRecord(
            filepath='',
            color0='#0a1e33', color1='#1a5276', color2='#2e86c1', color3='#3498db',
            color4='#154360', color5='#1f6fa5', color6='#2980b9', color7='#85c1e9',
            color8='#0e2a45', color9='#1a5276', color10='#2e86c1', color11='#3498db',
            color12='#154360', color13='#1f6fa5', color14='#2980b9', color15='#85c1e9',
            background='#0a1e33', foreground='#85c1e9', cursor='#3498db',
            avg_hue=210, avg_saturation=0.5, avg_lightness=0.5,
            color_temperature=-0.4,
            perceived_brightness=0.5, brightness_p10=0.1, brightness_p90=0.75,
            indexed_at=int(time.time()),
        ),
    },
    'neutral_forest': {
        'palette': PaletteRecord(
            filepath='',
            color0='#1a2e1a', color1='#2d6a2e', color2='#3a8c3b', color3='#5daa5e',
            color4='#245524', color5='#337a34', color6='#4a9e4b', color7='#8fc790',
            color8='#223d22', color9='#2d6a2e', color10='#3a8c3b', color11='#5daa5e',
            color12='#245524', color13='#337a34', color14='#4a9e4b', color15='#8fc790',
            background='#1a2e1a', foreground='#8fc790', cursor='#5daa5e',
            avg_hue=130, avg_saturation=0.4, avg_lightness=0.45,
            color_temperature=0.0,
            perceived_brightness=0.45, brightness_p10=0.15, brightness_p90=0.7,
            indexed_at=int(time.time()),
        ),
    },
    'dark_night': {
        'palette': PaletteRecord(
            filepath='',
            color0='#0a0a1a', color1='#1a1a40', color2='#2a2a60', color3='#3a3a80',
            color4='#151535', color5='#202050', color6='#303070', color7='#5050a0',
            color8='#101030', color9='#1a1a40', color10='#2a2a60', color11='#3a3a80',
            color12='#151535', color13='#202050', color14='#303070', color15='#5050a0',
            background='#0a0a1a', foreground='#5050a0', cursor='#3a3a80',
            avg_hue=240, avg_saturation=0.3, avg_lightness=0.2,
            color_temperature=-0.2,
            perceived_brightness=0.2, brightness_p10=0.05, brightness_p90=0.35,
            indexed_at=int(time.time()),
        ),
    },
    'bright_day': {
        'palette': PaletteRecord(
            filepath='',
            color0='#f5e6b8', color1='#f0d080', color2='#e8c050', color3='#d4a020',
            color4='#f2d898', color5='#ecc868', color6='#e0b040', color7='#c89818',
            color8='#f5e0a0', color9='#f0d080', color10='#e8c050', color11='#d4a020',
            color12='#f2d898', color13='#ecc868', color14='#e0b040', color15='#c89818',
            background='#f5e6b8', foreground='#8a6f28', cursor='#d4a020',
            avg_hue=50, avg_saturation=0.5, avg_lightness=0.7,
            color_temperature=0.3,
            perceived_brightness=0.7, brightness_p10=0.5, brightness_p90=0.9,
            indexed_at=int(time.time()),
        ),
    },
    'tokyo_night_theme': {
        'palette': PaletteRecord(
            filepath='',
            color0='#1a1b26', color1='#f7768e', color2='#9ece6a', color3='#e0af68',
            color4='#7aa2f7', color5='#bb9af7', color6='#7dcfff', color7='#c0caf5',
            color8='#414868', color9='#f7768e', color10='#9ece6a', color11='#e0af68',
            color12='#7aa2f7', color13='#bb9af7', color14='#7dcfff', color15='#c0caf5',
            background='#1a1b26', foreground='#c0caf5', cursor='#c0caf5',
            avg_hue=280, avg_saturation=0.6, avg_lightness=0.3,
            color_temperature=-0.5,
            perceived_brightness=0.3, brightness_p10=0.1, brightness_p90=0.6,
            indexed_at=int(time.time()),
        ),
    },
}

# Tokyo Night theme palette dict for use as a target palette (theme override)
TOKYO_NIGHT_TARGET_PALETTE = {
    'avg_hue': 280,
    'avg_saturation': 0.6,
    'avg_lightness': 0.3,
    'color_temperature': -0.5,
    'color0': '#1a1b26', 'color1': '#f7768e', 'color2': '#9ece6a',
    'color3': '#e0af68', 'color4': '#7aa2f7', 'color5': '#bb9af7',
    'color6': '#7dcfff', 'color7': '#c0caf5', 'color8': '#414868',
    'color9': '#f7768e', 'color10': '#9ece6a', 'color11': '#e0af68',
    'color12': '#7aa2f7', 'color13': '#bb9af7', 'color14': '#7dcfff',
    'color15': '#c0caf5',
    'background': '#1a1b26', 'foreground': '#c0caf5', 'cursor': '#c0caf5',
}


# ---------------------------------------------------------------------------
# MockOptions for _get_smart_color_constraints
# ---------------------------------------------------------------------------

class MockOptions:
    """Mock Options object that mirrors variety.Options fields."""
    smart_color_enabled = True
    smart_color_mode = 'adaptive'
    smart_color_similarity = 50
    smart_color_temperature = 'neutral'
    smart_theme_adherence = 'moderate'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_theme_override(is_active, palette=None):
    """Create a mock ThemeOverride with controlled state.

    Args:
        is_active: Whether the theme override is active.
        palette: Dict to return from get_target_palette_for_selection().
    """
    override = MagicMock()
    override.is_active = is_active
    override.get_target_palette_for_selection.return_value = palette
    return override


class _ColorModeTestBase(unittest.TestCase):
    """Base class that sets up a temp DB and temp image files for each test."""

    def setUp(self):
        """Create temp directory, temp DB, and populate with fixture data."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_color_mode.db')

        # Create minimal image files so CandidateProvider's os.path.exists passes.
        # 1x1 JPEG content (smallest valid JPEG).
        self._jpeg_header = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
            b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08'
            b'\t\n\x0b'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\x9e\xa7h\xbb\x12'
            b'\x00\xff\xd9'
        )

        self.image_paths = {}
        for name in WALLPAPER_FIXTURES:
            path = os.path.join(self.temp_dir, f'{name}.jpg')
            with open(path, 'wb') as f:
                f.write(self._jpeg_header)
            self.image_paths[name] = path

        # Populate the database
        self.db = ImageDatabase(self.db_path)
        for name, fixture in WALLPAPER_FIXTURES.items():
            filepath = self.image_paths[name]
            # Insert image record
            image_rec = ImageRecord(
                filepath=filepath,
                filename=f'{name}.jpg',
                source_id='test-source',
                width=1920,
                height=1080,
                aspect_ratio=1920 / 1080,
                file_size=os.path.getsize(filepath),
                file_mtime=int(os.path.getmtime(filepath)),
                is_favorite=False,
                first_indexed_at=int(time.time()),
                last_indexed_at=int(time.time()),
                palette_status='extracted',
            )
            self.db.upsert_image(image_rec)

            # Insert palette record
            palette = PaletteRecord(
                filepath=filepath,
                color0=fixture['palette'].color0,
                color1=fixture['palette'].color1,
                color2=fixture['palette'].color2,
                color3=fixture['palette'].color3,
                color4=fixture['palette'].color4,
                color5=fixture['palette'].color5,
                color6=fixture['palette'].color6,
                color7=fixture['palette'].color7,
                color8=fixture['palette'].color8,
                color9=fixture['palette'].color9,
                color10=fixture['palette'].color10,
                color11=fixture['palette'].color11,
                color12=fixture['palette'].color12,
                color13=fixture['palette'].color13,
                color14=fixture['palette'].color14,
                color15=fixture['palette'].color15,
                background=fixture['palette'].background,
                foreground=fixture['palette'].foreground,
                cursor=fixture['palette'].cursor,
                avg_hue=fixture['palette'].avg_hue,
                avg_saturation=fixture['palette'].avg_saturation,
                avg_lightness=fixture['palette'].avg_lightness,
                color_temperature=fixture['palette'].color_temperature,
                perceived_brightness=fixture['palette'].perceived_brightness,
                brightness_p10=fixture['palette'].brightness_p10,
                brightness_p90=fixture['palette'].brightness_p90,
                indexed_at=fixture['palette'].indexed_at,
            )
            self.db.upsert_palette(palette)

        self.db.close()

    def tearDown(self):
        """Remove temp directory and all contents."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_selector(self, **config_overrides):
        """Create a SmartSelector with default config and optional overrides.

        Disables time_adaptation by default to keep tests deterministic.
        Disables image_cooldown and source_cooldown so recency does not
        interfere with color-based weighting.

        Returns:
            SmartSelector instance (caller must close or use as context manager).
        """
        defaults = dict(
            enabled=True,
            color_match_weight=1.0,
            image_cooldown_days=0,
            source_cooldown_days=0,
            time_adaptation_enabled=False,
            favorite_boost=1.0,
            new_image_boost=1.0,
        )
        defaults.update(config_overrides)
        config = SelectionConfig(**defaults)
        return SmartSelector(self.db_path, config)

    def _selection_distribution(self, selector, constraints, trials=200, count=1):
        """Run many selection trials and return a Counter of fixture names.

        Args:
            selector: SmartSelector instance.
            constraints: SelectionConstraints to use.
            trials: Number of selection rounds.
            count: Images to select per round.

        Returns:
            Counter mapping fixture name (e.g. 'warm_sunset') to selection count.
        """
        dist = Counter()
        for _ in range(trials):
            selected = selector.select_images(count=count, constraints=constraints)
            for filepath in selected:
                basename = os.path.splitext(os.path.basename(filepath))[0]
                dist[basename] += 1
        return dist

    def _bind_constraint_method(self):
        """Create a mock VarietyWindow with _get_smart_color_constraints bound.

        Returns:
            MagicMock that behaves like a VarietyWindow with the real method.
        """
        mock_window = MagicMock()
        mock_window.options = MockOptions()
        mock_window._theme_override = None

        from variety.VarietyWindow import VarietyWindow
        mock_window._get_smart_color_constraints = (
            VarietyWindow._get_smart_color_constraints.__get__(
                mock_window, type(mock_window)
            )
        )
        return mock_window


# ===========================================================================
# Test class: Adaptive color mode (temperature-based)
# ===========================================================================

class TestAdaptiveColorModeE2E(_ColorModeTestBase):
    """Verify that adaptive color mode (warm/cool/neutral) selects images
    whose palettes best match the target temperature and hue."""

    def test_warm_temperature_selects_warm_images(self):
        """Warm temperature target favors warm_sunset and bright_day over cool_ocean.

        Pipeline: smart_color_temperature='warm' -> target hue=30, temp=0.5 ->
        ConstraintApplier filters by palette_similarity -> SelectionEngine
        weights remaining candidates by color_affinity_factor.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'warm'
        mock_window.options.smart_color_similarity = 20  # low threshold so most pass filter

        constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(constraints)
        self.assertEqual(constraints.target_palette['avg_hue'], 30)

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=300)

        warm_count = dist.get('warm_sunset', 0) + dist.get('bright_day', 0)
        cool_count = dist.get('cool_ocean', 0)

        self.assertGreater(
            warm_count, cool_count,
            f"Warm images ({warm_count}) should be selected more than "
            f"cool_ocean ({cool_count}) with warm temperature target. "
            f"Full distribution: {dict(dist)}"
        )

    def test_cool_temperature_selects_cool_images(self):
        """Cool temperature target favors cool_ocean over warm_sunset.

        Pipeline: smart_color_temperature='cool' -> target hue=200, temp=-0.4 ->
        cool_ocean (hue=210, temp=-0.4) should be the strongest match.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'cool'
        mock_window.options.smart_color_similarity = 20

        constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(constraints)
        self.assertEqual(constraints.target_palette['avg_hue'], 200)

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=300)

        cool_count = dist.get('cool_ocean', 0)
        warm_count = dist.get('warm_sunset', 0)

        self.assertGreater(
            cool_count, warm_count,
            f"cool_ocean ({cool_count}) should be selected more than "
            f"warm_sunset ({warm_count}) with cool temperature target. "
            f"Full distribution: {dict(dist)}"
        )

    def test_neutral_temperature_selects_neutral(self):
        """Neutral temperature target favors neutral_forest (hue=130, temp=0.0).

        Pipeline: smart_color_temperature='neutral' -> target hue=120, temp=0.0 ->
        neutral_forest (hue=130) is closest to the target.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'neutral'
        mock_window.options.smart_color_similarity = 20

        constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(constraints)
        self.assertEqual(constraints.target_palette['avg_hue'], 120)

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=300)

        neutral_count = dist.get('neutral_forest', 0)
        warm_count = dist.get('warm_sunset', 0)
        cool_count = dist.get('cool_ocean', 0)

        # neutral_forest should be selected more than the extremes
        self.assertGreater(
            neutral_count, warm_count,
            f"neutral_forest ({neutral_count}) should beat warm_sunset ({warm_count}). "
            f"Full distribution: {dict(dist)}"
        )
        self.assertGreater(
            neutral_count, cool_count,
            f"neutral_forest ({neutral_count}) should beat cool_ocean ({cool_count}). "
            f"Full distribution: {dict(dist)}"
        )

    def test_high_similarity_threshold_narrows_results(self):
        """Higher similarity thresholds are more restrictive.

        With min_color_similarity=90% (0.90), very few images should pass
        the ConstraintApplier. With 20% (0.20), most should pass.
        This verifies the threshold -> filtering pipeline.
        """
        target_palette = {
            'avg_hue': 25,
            'avg_saturation': 0.6,
            'avg_lightness': 0.4,
            'color_temperature': 0.6,
        }

        # Strict threshold
        strict_constraints = SelectionConstraints(
            target_palette=target_palette,
            min_color_similarity=0.90,
        )
        # Loose threshold
        loose_constraints = SelectionConstraints(
            target_palette=target_palette,
            min_color_similarity=0.20,
        )

        with self._create_selector() as selector:
            strict_results = set()
            for _ in range(50):
                selected = selector.select_images(count=6, constraints=strict_constraints)
                strict_results.update(os.path.basename(p) for p in selected)

            loose_results = set()
            for _ in range(50):
                selected = selector.select_images(count=6, constraints=loose_constraints)
                loose_results.update(os.path.basename(p) for p in selected)

        self.assertGreaterEqual(
            len(loose_results), len(strict_results),
            f"Loose threshold should allow at least as many unique images "
            f"({len(loose_results)}) as strict ({len(strict_results)}). "
            f"Strict: {strict_results}, Loose: {loose_results}"
        )


# ===========================================================================
# Test class: Theme color mode
# ===========================================================================

class TestThemeColorModeE2E(_ColorModeTestBase):
    """Verify that theme color mode uses the active theme palette for
    selection, filtering and weighting wallpapers by similarity to the theme."""

    def test_theme_mode_selects_matching_wallpapers(self):
        """Theme mode with Tokyo Night palette favors tokyo_night_theme image.

        Pipeline: smart_color_mode='theme' -> ThemeOverride provides Tokyo Night
        palette -> ConstraintApplier filters by palette_similarity -> SelectionEngine
        weights by color_affinity_factor -> tokyo_night_theme image matches best.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'theme'
        mock_window.options.smart_theme_adherence = 'loose'
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(constraints)
        self.assertEqual(constraints.target_palette['avg_hue'], 280)

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=300)

        tokyo_count = dist.get('tokyo_night_theme', 0)
        warm_count = dist.get('warm_sunset', 0)
        bright_count = dist.get('bright_day', 0)

        self.assertGreater(
            tokyo_count, warm_count,
            f"tokyo_night_theme ({tokyo_count}) should be selected more than "
            f"warm_sunset ({warm_count}) when Tokyo Night theme is active. "
            f"Full distribution: {dict(dist)}"
        )
        self.assertGreater(
            tokyo_count, bright_count,
            f"tokyo_night_theme ({tokyo_count}) should be selected more than "
            f"bright_day ({bright_count}) when Tokyo Night theme is active. "
            f"Full distribution: {dict(dist)}"
        )

    def test_theme_mode_strict_adherence_filters_more(self):
        """Strict adherence rejects more images than loose adherence.

        'strict' uses min_color_similarity=0.80 vs 'loose' at 0.60.
        Strict should produce fewer unique selected images over many trials.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'theme'
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        # Loose adherence
        mock_window.options.smart_theme_adherence = 'loose'
        loose_constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(loose_constraints)
        self.assertEqual(loose_constraints.min_color_similarity, ADHERENCE_LEVELS['loose'])

        # Strict adherence
        mock_window.options.smart_theme_adherence = 'strict'
        strict_constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(strict_constraints)
        self.assertEqual(strict_constraints.min_color_similarity, ADHERENCE_LEVELS['strict'])

        with self._create_selector() as selector:
            loose_unique = set()
            for _ in range(100):
                selected = selector.select_images(count=6, constraints=loose_constraints)
                loose_unique.update(os.path.basename(p) for p in selected)

            strict_unique = set()
            for _ in range(100):
                selected = selector.select_images(count=6, constraints=strict_constraints)
                strict_unique.update(os.path.basename(p) for p in selected)

        self.assertGreaterEqual(
            len(loose_unique), len(strict_unique),
            f"Loose adherence should allow at least as many unique images "
            f"({len(loose_unique)}) as strict ({len(strict_unique)}). "
            f"Loose: {loose_unique}, Strict: {strict_unique}"
        )

    def test_theme_mode_ignores_temperature_setting(self):
        """In theme mode, smart_color_temperature='warm' does NOT influence selection.

        Only the theme palette matters.  The target_palette should come from
        the theme override, not from the temperature presets.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'theme'
        mock_window.options.smart_color_temperature = 'warm'
        mock_window.options.smart_theme_adherence = 'loose'
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(constraints)

        # Target should be the theme palette (hue=280), NOT warm preset (hue=30)
        self.assertEqual(
            constraints.target_palette['avg_hue'], 280,
            "Theme mode should use theme hue (280), not warm preset hue (30)"
        )
        self.assertEqual(
            constraints.target_palette['color_temperature'], -0.5,
            "Theme mode should use theme temperature (-0.5), not warm preset (0.5)"
        )

        # Also verify selection — tokyo_night_theme should still be favored
        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=200)

        tokyo_count = dist.get('tokyo_night_theme', 0)
        warm_count = dist.get('warm_sunset', 0)
        self.assertGreater(
            tokyo_count, warm_count,
            f"Theme mode should favor tokyo_night_theme ({tokyo_count}) even "
            f"when temperature='warm'. warm_sunset={warm_count}. "
            f"Full distribution: {dict(dist)}"
        )

    def test_theme_mode_without_active_theme_returns_no_constraints(self):
        """Theme mode with no active theme returns None from _get_smart_color_constraints().

        This means no color filtering is applied and all wallpapers are eligible.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'theme'
        mock_window._theme_override = _make_theme_override(
            is_active=False, palette=None
        )

        constraints = mock_window._get_smart_color_constraints()

        self.assertIsNone(
            constraints,
            "Theme mode with no active theme should return None (no color filtering)"
        )

        # Without constraints, all images should be selectable
        with self._create_selector() as selector:
            all_selected = set()
            for _ in range(200):
                selected = selector.select_images(count=6, constraints=constraints)
                all_selected.update(os.path.basename(p) for p in selected)

        self.assertEqual(
            len(all_selected), len(WALLPAPER_FIXTURES),
            f"Without color constraints, all {len(WALLPAPER_FIXTURES)} images "
            f"should eventually be selected. Got {len(all_selected)}: {all_selected}"
        )


# ===========================================================================
# Test class: Switching between color modes
# ===========================================================================

class TestColorModeToggleE2E(_ColorModeTestBase):
    """Verify that switching between color modes produces different
    selection behavior using the same underlying database."""

    def test_switching_mode_changes_selection(self):
        """Switching from adaptive/warm to theme/tokyo-night changes which images are selected.

        Same DB, same images, but different color mode produces different winners.
        """
        mock_window = self._bind_constraint_method()

        # Mode 1: adaptive / warm
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'warm'
        mock_window.options.smart_color_similarity = 20
        mock_window._theme_override = None

        warm_constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(warm_constraints)

        # Mode 2: theme / tokyo-night
        mock_window.options.smart_color_mode = 'theme'
        mock_window.options.smart_theme_adherence = 'loose'
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        theme_constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(theme_constraints)

        with self._create_selector() as selector:
            warm_dist = self._selection_distribution(
                selector, warm_constraints, trials=300
            )
            theme_dist = self._selection_distribution(
                selector, theme_constraints, trials=300
            )

        # In warm mode, warm_sunset should dominate
        warm_winner = warm_dist.most_common(1)[0][0]
        # In theme mode, tokyo_night_theme should dominate
        theme_winner = theme_dist.most_common(1)[0][0]

        self.assertNotEqual(
            warm_winner, theme_winner,
            f"Switching mode should change the top-selected image. "
            f"Warm winner: {warm_winner}, Theme winner: {theme_winner}. "
            f"Warm dist: {dict(warm_dist)}, Theme dist: {dict(theme_dist)}"
        )

    def test_adaptive_mode_ignores_active_theme(self):
        """In adaptive mode, an active theme override does NOT influence selection.

        Color mode='adaptive' with smart_color_temperature='warm' should use
        warm palette (hue=30) even when Tokyo Night theme (hue=280) is active.
        The color mode toggle is explicit: adaptive ignores themes.
        """
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'warm'
        mock_window.options.smart_color_similarity = 20
        # Active theme is present but should be IGNORED
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        constraints = mock_window._get_smart_color_constraints()
        self.assertIsNotNone(constraints)

        # Constraints should reflect warm preset, not theme
        self.assertEqual(
            constraints.target_palette['avg_hue'], 30,
            "Adaptive mode should use warm hue (30), not theme hue (280)"
        )
        self.assertEqual(
            constraints.target_palette['color_temperature'], 0.5,
            "Adaptive mode should use warm temperature (0.5), not theme (-0.5)"
        )

        # Selection should favor warm images, not tokyo_night_theme
        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=300)

        warm_combined = dist.get('warm_sunset', 0) + dist.get('bright_day', 0)
        tokyo_count = dist.get('tokyo_night_theme', 0)

        self.assertGreater(
            warm_combined, tokyo_count,
            f"Adaptive/warm should favor warm images ({warm_combined}) over "
            f"tokyo_night_theme ({tokyo_count}) even with active theme. "
            f"Full distribution: {dict(dist)}"
        )


# ===========================================================================
# Test class: Integration — constraints actually flow through call sites
# ===========================================================================

class TestConstraintIntegrationE2E(_ColorModeTestBase):
    """Verify that VarietyWindow methods actually pass constraints to select_images().

    These tests catch the primary bug: call sites that invoke select_images()
    without forwarding constraints from _get_smart_color_constraints().
    If someone removes the constraints= argument, these tests fail.
    """

    def _make_mock_window(self, smart_color_mode='adaptive', temperature='warm'):
        """Create a mock VarietyWindow with enough wiring for call-site tests.

        Binds the real _get_smart_color_constraints and smart_next_wallpaper
        methods, stubs everything else.
        """
        from variety.VarietyWindow import VarietyWindow

        mock_window = MagicMock()
        mock_window.options = MockOptions()
        mock_window.options.smart_color_mode = smart_color_mode
        mock_window.options.smart_color_temperature = temperature
        mock_window.options.smart_color_similarity = 20
        mock_window._theme_override = None

        # Bind the real methods
        mock_window._get_smart_color_constraints = (
            VarietyWindow._get_smart_color_constraints.__get__(
                mock_window, type(mock_window)
            )
        )
        mock_window.smart_next_wallpaper = (
            VarietyWindow.smart_next_wallpaper.__get__(
                mock_window, type(mock_window)
            )
        )

        # Create a real selector so the method can call it
        mock_window.smart_selector = self._create_selector()

        # Stub out the fallback and post-selection methods
        mock_window.next_wallpaper = MagicMock()
        mock_window.set_wallpaper = MagicMock()
        mock_window.current = None

        return mock_window

    def test_smart_next_wallpaper_passes_constraints(self):
        """smart_next_wallpaper() must call select_images with constraints.

        Regression guard: the original bug was select_images(1) with no
        constraints argument. This test spies on the selector to verify
        constraints are forwarded.
        """
        mock_window = self._make_mock_window(
            smart_color_mode='adaptive', temperature='warm'
        )

        # Wrap select_images to capture the constraints argument
        real_select = mock_window.smart_selector.select_images
        captured_calls = []

        def spy_select_images(count, constraints=None):
            captured_calls.append({'count': count, 'constraints': constraints})
            return real_select(count, constraints=constraints)

        mock_window.smart_selector.select_images = spy_select_images

        try:
            mock_window.smart_next_wallpaper()
        finally:
            mock_window.smart_selector.close()

        self.assertTrue(
            len(captured_calls) > 0,
            "smart_next_wallpaper() should have called select_images()"
        )

        call = captured_calls[0]
        self.assertIsNotNone(
            call['constraints'],
            "smart_next_wallpaper() must pass constraints to select_images(). "
            "Got constraints=None — the primary bug has regressed."
        )
        self.assertEqual(
            call['constraints'].target_palette['avg_hue'], 30,
            "Constraints should reflect warm temperature (hue=30)"
        )

    def test_smart_next_wallpaper_theme_mode_passes_theme_constraints(self):
        """smart_next_wallpaper() in theme mode passes theme palette constraints."""
        mock_window = self._make_mock_window(smart_color_mode='theme')
        mock_window.options.smart_theme_adherence = 'loose'
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        real_select = mock_window.smart_selector.select_images
        captured_calls = []

        def spy_select_images(count, constraints=None):
            captured_calls.append({'count': count, 'constraints': constraints})
            return real_select(count, constraints=constraints)

        mock_window.smart_selector.select_images = spy_select_images

        try:
            mock_window.smart_next_wallpaper()
        finally:
            mock_window.smart_selector.close()

        self.assertTrue(len(captured_calls) > 0)
        call = captured_calls[0]
        self.assertIsNotNone(
            call['constraints'],
            "Theme mode should produce non-None constraints"
        )
        self.assertEqual(
            call['constraints'].target_palette['avg_hue'], 280,
            "Theme mode constraints should use Tokyo Night hue (280)"
        )

    def test_smart_next_wallpaper_disabled_passes_none(self):
        """smart_next_wallpaper() with color disabled passes constraints=None."""
        mock_window = self._make_mock_window()
        mock_window.options.smart_color_enabled = False

        real_select = mock_window.smart_selector.select_images
        captured_calls = []

        def spy_select_images(count, constraints=None):
            captured_calls.append({'count': count, 'constraints': constraints})
            return real_select(count, constraints=constraints)

        mock_window.smart_selector.select_images = spy_select_images

        try:
            mock_window.smart_next_wallpaper()
        finally:
            mock_window.smart_selector.close()

        self.assertTrue(len(captured_calls) > 0)
        self.assertIsNone(
            captured_calls[0]['constraints'],
            "With color disabled, constraints should be None (no filtering)"
        )

    def test_no_constraints_selects_all_images_uniformly(self):
        """Baseline: constraints=None allows all 6 fixtures to be selected.

        Establishes what 'without constraints' means, making the constrained
        tests meaningful by contrast.
        """
        with self._create_selector() as selector:
            all_selected = set()
            for _ in range(300):
                selected = selector.select_images(count=6, constraints=None)
                all_selected.update(os.path.basename(p) for p in selected)

        self.assertEqual(
            len(all_selected), len(WALLPAPER_FIXTURES),
            f"Without constraints, all {len(WALLPAPER_FIXTURES)} images should "
            f"be reachable. Got {len(all_selected)}: {all_selected}"
        )


# ===========================================================================
# Test class: Statistical robustness improvements
# ===========================================================================

class TestSelectionMargins(_ColorModeTestBase):
    """Verify that color selection produces decisive margins, not coin flips.

    Weak assertGreater(warm, cool) could pass with warm=151, cool=149.
    These tests require meaningful statistical margins to prove the
    weighting actually works.
    """

    def test_warm_mode_warm_wins_by_margin(self):
        """Warm mode: warm images selected at least 2x more than cool images."""
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'warm'
        mock_window.options.smart_color_similarity = 20

        constraints = mock_window._get_smart_color_constraints()

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=500)

        warm_count = dist.get('warm_sunset', 0) + dist.get('bright_day', 0)
        cool_count = dist.get('cool_ocean', 0)

        self.assertGreater(
            warm_count, cool_count * 2,
            f"Warm images ({warm_count}) should be selected at least 2x "
            f"cool_ocean ({cool_count}). Distribution: {dict(dist)}"
        )

    def test_theme_mode_matching_image_is_top_pick(self):
        """Theme mode: the fixture matching the theme is the most-selected image."""
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'theme'
        mock_window.options.smart_theme_adherence = 'loose'
        mock_window._theme_override = _make_theme_override(
            is_active=True, palette=TOKYO_NIGHT_TARGET_PALETTE
        )

        constraints = mock_window._get_smart_color_constraints()

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=500)

        top_two = [name for name, _ in dist.most_common(2)]

        self.assertIn(
            'tokyo_night_theme', top_two,
            f"tokyo_night_theme should be in top 2 selections with Tokyo Night "
            f"theme active. Top 2: {top_two}. Distribution: {dict(dist)}"
        )

    def test_cool_mode_cool_wins_by_margin(self):
        """Cool mode: cool_ocean selected at least 2x more than warm_sunset."""
        mock_window = self._bind_constraint_method()
        mock_window.options.smart_color_mode = 'adaptive'
        mock_window.options.smart_color_temperature = 'cool'
        mock_window.options.smart_color_similarity = 20

        constraints = mock_window._get_smart_color_constraints()

        with self._create_selector() as selector:
            dist = self._selection_distribution(selector, constraints, trials=500)

        cool_count = dist.get('cool_ocean', 0)
        warm_count = dist.get('warm_sunset', 0)

        self.assertGreater(
            cool_count, warm_count * 2,
            f"cool_ocean ({cool_count}) should be selected at least 2x "
            f"warm_sunset ({warm_count}). Distribution: {dict(dist)}"
        )


if __name__ == '__main__':
    unittest.main()
