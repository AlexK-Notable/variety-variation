# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Zed IDE theme extraction and library management.

Extracts terminal ANSI color palettes from Zed theme files, computes
derived metrics, and stores them in the database via the CRUD layer.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from variety.smart_selection.models import ColorThemeRecord
from variety.smart_selection.palette import calculate_palette_metrics

logger = logging.getLogger(__name__)

# Mapping from Zed terminal.ansi.* suffixes to our color0-15 keys
ANSI_MAP = {
    'black': 'color0', 'red': 'color1', 'green': 'color2', 'yellow': 'color3',
    'blue': 'color4', 'magenta': 'color5', 'cyan': 'color6', 'white': 'color7',
    'bright_black': 'color8', 'bright_red': 'color9', 'bright_green': 'color10',
    'bright_yellow': 'color11', 'bright_blue': 'color12', 'bright_magenta': 'color13',
    'bright_cyan': 'color14', 'bright_white': 'color15',
}

# Minimum ANSI colors required for a valid extraction
_MIN_ANSI_COLORS = 8


def _normalize_hex(color: str) -> str:
    """Normalize a hex color to 6-digit form (#RRGGBB).

    Handles 3-digit shorthand (#RGB -> #RRGGBB) and strips leading #.
    Returns the color unchanged if already 6-digit or not a valid hex.
    """
    if not color or not isinstance(color, str):
        return color
    c = color.lstrip('#')
    if len(c) == 3:
        c = c[0] * 2 + c[1] * 2 + c[2] * 2
    return '#' + c


class ZedThemeExtractor:
    """Extracts color themes from Zed IDE theme files."""

    # Zed theme search paths (expanded at scan time)
    ZED_PATHS = [
        # Flatpak Zed Preview
        "~/.var/app/dev.zed.Zed-Preview/data/zed/extensions/installed/",
        # Flatpak Zed Stable
        "~/.var/app/dev.zed.Zed/data/zed/extensions/installed/",
        # Local install
        "~/.local/share/zed/extensions/installed/",
        # User themes directory
        "~/.config/zed/themes/",
    ]

    def scan(self, extra_paths: Optional[List[str]] = None) -> List[str]:
        """Find all .json/.jsonc theme files across Zed paths.

        Searches known Zed extension directories and any extra_paths for
        theme JSON files. Files are discovered recursively under
        ``*/themes/`` subdirectories as well as directly in the paths.

        Args:
            extra_paths: Additional directories to scan.

        Returns:
            Sorted list of absolute paths to theme files.
        """
        search_dirs = [os.path.expanduser(p) for p in self.ZED_PATHS]
        if extra_paths:
            search_dirs.extend(extra_paths)

        found = set()
        for base in search_dirs:
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for fname in files:
                    if fname.endswith(('.json', '.jsonc')):
                        found.add(os.path.join(root, fname))

        return sorted(found)

    def parse_theme_file(self, filepath: str) -> List[ColorThemeRecord]:
        """Parse a Zed theme file, returning one ColorThemeRecord per variant.

        Handles JSONC (strips // and /* */ comments), multiple theme
        variants per file, and both dark and light appearances.
        Malformed files return an empty list -- never raises.

        Args:
            filepath: Absolute path to the theme JSON/JSONC file.

        Returns:
            List of ColorThemeRecord instances extracted from the file.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Could not read theme file %s: %s", filepath, e)
            return []

        # Strip JSONC comments before parsing
        text = self._strip_jsonc_comments(text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.debug("Malformed JSON in %s: %s", filepath, e)
            return []

        if not isinstance(data, dict):
            return []

        themes_array = data.get('themes', [])
        if not isinstance(themes_array, list):
            return []

        filename_stem = Path(filepath).stem
        results = []

        for theme_dict in themes_array:
            record = self._extract_theme(theme_dict, filepath, filename_stem)
            if record is not None:
                results.append(record)

        return results

    def _strip_jsonc_comments(self, text: str) -> str:
        """Strip JSONC comments safely (handles strings containing //).

        Removes single-line ``// ...`` and block ``/* ... */`` comments
        while preserving string literals that may contain those sequences.

        Args:
            text: Raw JSONC text.

        Returns:
            JSON text with comments removed.
        """
        # Regex matches strings, single-line comments, or block comments.
        # By matching strings first we avoid stripping inside them.
        pattern = re.compile(
            r'"(?:[^"\\]|\\.)*"'   # double-quoted string (group 0 captures all)
            r'|//[^\n]*'           # single-line comment
            r'|/\*.*?\*/',         # block comment
            re.DOTALL,
        )

        def _replacer(match):
            s = match.group(0)
            if s.startswith('"'):
                return s  # preserve string
            return ''     # remove comment

        return pattern.sub(_replacer, text)

    def _extract_ansi_colors(self, style: dict) -> Optional[Dict[str, str]]:
        """Extract terminal.ansi.* colors from a Zed theme style dict.

        Maps the 16 standard ANSI color keys (black, red, ..., bright_white)
        to our color0-15 namespace.  Also extracts background, foreground, and
        cursor from terminal-level and player keys.

        Args:
            style: The ``style`` dict from a Zed theme variant.

        Returns:
            Dict mapping color0-15 + background/foreground/cursor to hex
            strings, or None if fewer than ``_MIN_ANSI_COLORS`` ANSI colors
            were found.
        """
        colors = {}
        for ansi_suffix, color_key in ANSI_MAP.items():
            value = style.get(f'terminal.ansi.{ansi_suffix}')
            if value and isinstance(value, str):
                colors[color_key] = _normalize_hex(value)

        if len(colors) < _MIN_ANSI_COLORS:
            return None

        # Background: prefer terminal.background, fall back to style background
        bg = style.get('terminal.background') or style.get('background')
        if bg and isinstance(bg, str):
            colors['background'] = _normalize_hex(bg)

        # Foreground: prefer terminal.foreground, fall back to editor.foreground
        fg = style.get('terminal.foreground') or style.get('editor.foreground')
        if fg and isinstance(fg, str):
            colors['foreground'] = _normalize_hex(fg)

        # Cursor: players[0].cursor, fall back to foreground
        players = style.get('players')
        if isinstance(players, list) and players:
            cursor_val = players[0].get('cursor') if isinstance(players[0], dict) else None
            if cursor_val and isinstance(cursor_val, str):
                colors['cursor'] = _normalize_hex(cursor_val)
        if 'cursor' not in colors and 'foreground' in colors:
            colors['cursor'] = colors['foreground']

        return colors

    def _extract_fallback_colors(self, style: dict) -> Optional[Dict[str, str]]:
        """Derive a 16-color palette from editor/syntax colors when ANSI keys are absent.

        This is a best-effort mapping for the ~9 themes that lack
        ``terminal.ansi.*`` keys entirely.  We build an approximate
        16-color palette from the editor background, foreground, and
        various syntax highlight colors.

        Args:
            style: The ``style`` dict from a Zed theme variant.

        Returns:
            Dict mapping color0-15 + background/foreground/cursor to hex
            strings, or None if insufficient colors were found.
        """
        bg = style.get('background') or style.get('editor.background')
        fg = style.get('editor.foreground') or style.get('text')

        if not bg or not fg or not isinstance(bg, str) or not isinstance(fg, str):
            return None

        bg = _normalize_hex(bg)
        fg = _normalize_hex(fg)
        colors = {'background': bg, 'foreground': fg}

        # Attempt to gather syntax highlight colors
        # Zed uses a style.syntax dict like:
        #   "syntax": {"comment": {"color": "#..."}, "string": {"color": "#..."}, ...}
        syntax = style.get('syntax', {})
        syntax_colors = []
        # Ordered list of syntax keys that tend to map well to ANSI roles
        syntax_role_keys = [
            'comment',    # -> dim/black
            'string',     # -> green
            'keyword',    # -> red or magenta
            'function',   # -> blue
            'type',       # -> yellow
            'constant',   # -> cyan
            'variable',   # -> white/fg
            'number',     # -> magenta
            'operator',   # -> red
            'attribute',  # -> yellow
            'property',   # -> cyan
            'punctuation',# -> dim
        ]

        for key in syntax_role_keys:
            entry = syntax.get(key)
            if isinstance(entry, dict):
                c = entry.get('color')
                if c and isinstance(c, str):
                    syntax_colors.append(_normalize_hex(c))

        # Also try editor-level accent colors
        for accent_key in ('link_text.color', 'conflict', 'created', 'deleted',
                           'error', 'warning', 'info', 'hint', 'success'):
            val = style.get(accent_key)
            if val and isinstance(val, str):
                syntax_colors.append(_normalize_hex(val))

        # Need at least a few colors to build a palette
        if len(syntax_colors) < 4:
            return None

        # Build a 16-color palette: bg, 7 syntax, then brighter variants (reuse)
        # color0 = bg-like, color7 = fg-like, color8 = bg dim, color15 = fg bright
        colors['color0'] = bg
        colors['color7'] = fg
        colors['color8'] = bg
        colors['color15'] = fg

        # Fill color1-6 from syntax_colors
        for i, c in enumerate(syntax_colors[:6]):
            colors[f'color{i + 1}'] = c

        # Fill remaining normal colors if we have enough
        for i in range(len(syntax_colors[:6]) + 1, 7):
            colors[f'color{i}'] = fg

        # Bright variants (color9-14): reuse syntax colors
        for i, c in enumerate(syntax_colors[:6]):
            colors[f'color{i + 9}'] = c
        for i in range(len(syntax_colors[:6]) + 9, 15):
            colors[f'color{i}'] = fg

        # Cursor
        players = style.get('players')
        if isinstance(players, list) and players:
            cursor_val = players[0].get('cursor') if isinstance(players[0], dict) else None
            if cursor_val and isinstance(cursor_val, str):
                colors['cursor'] = _normalize_hex(cursor_val)
        if 'cursor' not in colors:
            colors['cursor'] = fg

        return colors

    def _extract_theme(
        self, theme_dict: dict, filepath: str, filename_stem: str
    ) -> Optional[ColorThemeRecord]:
        """Extract a single theme variant into a ColorThemeRecord.

        Tries ANSI extraction first, then falls back to syntax/editor colors.
        Computes derived metrics via ``calculate_palette_metrics()``.

        Args:
            theme_dict: A single entry from the ``themes`` array.
            filepath: Source file path for provenance.
            filename_stem: Stem of the filename, used in theme_id generation.

        Returns:
            ColorThemeRecord with colors and metrics, or None on failure.
        """
        if not isinstance(theme_dict, dict):
            return None

        name = theme_dict.get('name')
        if not name or not isinstance(name, str):
            return None

        style = theme_dict.get('style', {})
        if not isinstance(style, dict):
            return None

        appearance = theme_dict.get('appearance', 'dark')

        # Try ANSI extraction, fall back to editor/syntax colors
        colors = self._extract_ansi_colors(style)
        if colors is None:
            colors = self._extract_fallback_colors(style)
        if colors is None:
            return None

        # Compute derived metrics from color0-15
        metrics = calculate_palette_metrics(colors)

        # Generate deterministic theme_id
        theme_id = f"zed:{filename_stem}:{name}"

        return ColorThemeRecord(
            theme_id=theme_id,
            name=name,
            source_type='zed',
            source_path=filepath,
            appearance=appearance,
            color0=colors.get('color0'),
            color1=colors.get('color1'),
            color2=colors.get('color2'),
            color3=colors.get('color3'),
            color4=colors.get('color4'),
            color5=colors.get('color5'),
            color6=colors.get('color6'),
            color7=colors.get('color7'),
            color8=colors.get('color8'),
            color9=colors.get('color9'),
            color10=colors.get('color10'),
            color11=colors.get('color11'),
            color12=colors.get('color12'),
            color13=colors.get('color13'),
            color14=colors.get('color14'),
            color15=colors.get('color15'),
            background=colors.get('background'),
            foreground=colors.get('foreground'),
            cursor=colors.get('cursor'),
            avg_hue=metrics.get('avg_hue'),
            avg_saturation=metrics.get('avg_saturation'),
            avg_lightness=metrics.get('avg_lightness'),
            color_temperature=metrics.get('color_temperature'),
            imported_at=int(time.time()),
        )


class ThemeLibrary:
    """High-level theme management wrapping database CRUD."""

    def __init__(self, db):
        """Initialize with a database instance.

        Args:
            db: ImageDatabase instance with color theme CRUD methods.
        """
        self.db = db
        self.extractor = ZedThemeExtractor()

    def import_from_zed(
        self,
        extra_paths: Optional[List[str]] = None,
        scan_paths: Optional[List[str]] = None,
    ) -> int:
        """Scan and import all Zed themes.

        When *scan_paths* is provided it completely replaces the default
        ``ZedThemeExtractor.ZED_PATHS`` -- useful for testing with fixture
        directories.  *extra_paths* is appended to the defaults.

        Args:
            extra_paths: Additional directories appended to default paths.
            scan_paths: If provided, overrides default scan paths entirely.

        Returns:
            Number of themes imported (inserted or updated).
        """
        if scan_paths is not None:
            # Override: use exactly these paths
            files = []
            for base in scan_paths:
                if not os.path.isdir(base):
                    continue
                for root, _dirs, fnames in os.walk(base):
                    for fname in fnames:
                        if fname.endswith(('.json', '.jsonc')):
                            files.append(os.path.join(root, fname))
            files.sort()
        else:
            files = self.extractor.scan(extra_paths=extra_paths)

        count = 0
        for fpath in files:
            records = self.extractor.parse_theme_file(fpath)
            for record in records:
                try:
                    self.db.upsert_color_theme(record)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to upsert theme %s: %s", record.theme_id, e)

        logger.info("Imported %d Zed themes from %d files", count, len(files))
        return count

    def get_theme_palette(self, theme_id: str) -> Optional[Dict[str, str]]:
        """Get theme as palette dict compatible with TemplateProcessor.

        Returns a dict with color0-15, background, foreground, cursor keys
        (non-None values only), matching the PaletteRecord.to_dict() protocol.

        Args:
            theme_id: Unique theme identifier.

        Returns:
            Palette dict or None if theme not found.
        """
        record = self.db.get_color_theme(theme_id)
        if record is None:
            return None
        return record.to_dict()

    def fork_theme(
        self, theme_id: str, new_name: str
    ) -> Optional[ColorThemeRecord]:
        """Create a custom copy of an existing theme.

        The forked theme gets a new deterministic ID based on ``custom``
        source type, is marked ``is_custom=True``, and links back to the
        parent via ``parent_theme_id``.

        Args:
            theme_id: ID of the theme to fork.
            new_name: Name for the new custom theme.

        Returns:
            The newly created ColorThemeRecord, or None if parent not found.
        """
        parent = self.db.get_color_theme(theme_id)
        if parent is None:
            return None

        new_id = f"custom:fork:{new_name}"
        forked = ColorThemeRecord(
            theme_id=new_id,
            name=new_name,
            source_type='custom',
            source_path=parent.source_path,
            appearance=parent.appearance,
            color0=parent.color0, color1=parent.color1,
            color2=parent.color2, color3=parent.color3,
            color4=parent.color4, color5=parent.color5,
            color6=parent.color6, color7=parent.color7,
            color8=parent.color8, color9=parent.color9,
            color10=parent.color10, color11=parent.color11,
            color12=parent.color12, color13=parent.color13,
            color14=parent.color14, color15=parent.color15,
            background=parent.background,
            foreground=parent.foreground,
            cursor=parent.cursor,
            avg_hue=parent.avg_hue,
            avg_saturation=parent.avg_saturation,
            avg_lightness=parent.avg_lightness,
            color_temperature=parent.color_temperature,
            imported_at=int(time.time()),
            is_custom=True,
            parent_theme_id=theme_id,
        )

        self.db.upsert_color_theme(forked)
        return forked
