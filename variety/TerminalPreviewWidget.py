# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Terminal preview widget for theme color visualization.

Renders a mock terminal session using PangoCairo with theme colors
applied to simulate how ANSI colors appear in a real terminal.
"""

import logging
from typing import Dict, Optional

import cairo

# fmt: off
import gi  # isort:skip
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo  # isort:skip
# fmt: on

logger = logging.getLogger(__name__)

# Default fallback palette when none is set
_DEFAULT_PALETTE = {
    'background': '#1e1e2e',
    'foreground': '#cdd6f4',
    'cursor': '#f5e0dc',
    'color0': '#45475a', 'color1': '#f38ba8', 'color2': '#a6e3a1',
    'color3': '#f9e2af', 'color4': '#89b4fa', 'color5': '#f5c2e7',
    'color6': '#94e2d5', 'color7': '#bac2de', 'color8': '#585b70',
    'color9': '#f38ba8', 'color10': '#a6e3a1', 'color11': '#f9e2af',
    'color12': '#89b4fa', 'color13': '#f5c2e7', 'color14': '#94e2d5',
    'color15': '#a6adc8',
}

# Mock terminal content: list of lines, each line is a list of (text, color_key) tuples.
# Exercises all 16 ANSI colors + background, foreground, cursor.
_TERMINAL_LINES = [
    # Prompt + neofetch-style header
    [('user', 'color2'), ('@', 'color0'), ('archlinux', 'color2'),
     (':', 'foreground'), ('~', 'color4'),
     ('$ ', 'foreground'), ('neofetch --off', 'color7')],
    [('user', 'color4'), ('@', 'color8'), ('archlinux', 'color4')],
    [('──────────────', 'color8')],
    [('OS', 'color4'), (': ', 'foreground'), ('Arch Linux x86_64', 'color7')],
    [('Kernel', 'color4'), (': ', 'foreground'), ('6.19.5-3-cachyos', 'color7')],
    [('Shell', 'color4'), (': ', 'foreground'), ('zsh 5.9', 'color7')],
    [('WM', 'color4'), (': ', 'foreground'), ('Hyprland', 'color7')],
    [('Theme', 'color4'), (': ', 'foreground'), ('Catppuccin-Mocha', 'color5')],
    [('Terminal', 'color4'), (': ', 'foreground'), ('foot', 'color7')],
    [('CPU', 'color4'), (': ', 'foreground'), ('AMD Ryzen 9 7950X', 'color7'),
     (' @ ', 'color8'), ('5.76 GHz', 'color3')],
    [('Memory', 'color4'), (': ', 'foreground'), ('12.4', 'color2'),
     ('/', 'color8'), ('62.7 GiB', 'color1'), (' (20%)', 'color8')],
    [('')],
    # Color swatch blocks — normal 0-7, then bright 8-15
    [('\u2588\u2588', 'color0'), (' ', 'background'),
     ('\u2588\u2588', 'color1'), (' ', 'background'),
     ('\u2588\u2588', 'color2'), (' ', 'background'),
     ('\u2588\u2588', 'color3'), (' ', 'background'),
     ('\u2588\u2588', 'color4'), (' ', 'background'),
     ('\u2588\u2588', 'color5'), (' ', 'background'),
     ('\u2588\u2588', 'color6'), (' ', 'background'),
     ('\u2588\u2588', 'color7')],
    [('\u2588\u2588', 'color8'), (' ', 'background'),
     ('\u2588\u2588', 'color9'), (' ', 'background'),
     ('\u2588\u2588', 'color10'), (' ', 'background'),
     ('\u2588\u2588', 'color11'), (' ', 'background'),
     ('\u2588\u2588', 'color12'), (' ', 'background'),
     ('\u2588\u2588', 'color13'), (' ', 'background'),
     ('\u2588\u2588', 'color14'), (' ', 'background'),
     ('\u2588\u2588', 'color15')],
    [('')],
    # Prompt + directory listing
    [('user', 'color10'), ('@', 'color0'), ('archlinux', 'color10'),
     (':', 'foreground'), ('~/projects', 'color12'),
     ('$ ', 'foreground'), ('ls -la', 'color7')],
    [('drwxr-xr-x  ', 'color8'), ('src/', 'color4')],
    [('drwxr-xr-x  ', 'color8'), ('tests/', 'color4')],
    [('-rw-r--r--  ', 'color8'), ('main.py', 'foreground')],
    [('-rwxr-xr-x  ', 'color8'), ('run.sh', 'color2')],
    [('lrwxrwxrwx  ', 'color8'), ('config', 'color6'), (' -> ', 'foreground'),
     ('.config', 'color5')],
    [('-rw-r--r--  ', 'color8'), ('README.md', 'foreground')],
    [('-rw-r--r--  ', 'color8'), ('Makefile', 'color3')],
    [('')],
    # Prompt + cat a Python script
    [('user', 'color2'), ('@', 'color0'), ('archlinux', 'color2'),
     (':', 'foreground'), ('~/projects', 'color4'),
     ('$ ', 'foreground'), ('cat src/palette.py', 'color7')],
    [('#!/usr/bin/env python3', 'color8')],
    [('"""Color palette analysis module."""', 'color2')],
    [('')],
    [('import ', 'color1'), ('math', 'color14')],
    [('import ', 'color1'), ('colorsys', 'color14')],
    [('from ', 'color1'), ('pathlib ', 'color14'),
     ('import ', 'color1'), ('Path', 'color3')],
    [('from ', 'color1'), ('typing ', 'color14'),
     ('import ', 'color1'), ('Dict', 'color3'), (', ', 'foreground'),
     ('List', 'color3'), (', ', 'foreground'), ('Tuple', 'color3')],
    [('')],
    [('WARM_HUES', 'foreground'), (' = ', 'color9'),
     ('(', 'foreground'), ('0', 'color5'), (', ', 'foreground'),
     ('60', 'color5'), (', ', 'foreground'), ('300', 'color5'),
     (', ', 'foreground'), ('360', 'color5'), (')', 'foreground')],
    [('COOL_HUES', 'foreground'), (' = ', 'color9'),
     ('(', 'foreground'), ('150', 'color5'), (', ', 'foreground'),
     ('270', 'color5'), (')', 'foreground')],
    [('MAX_COLORS', 'foreground'), (' = ', 'color9'),
     ('16', 'color5')],
    [('')],
    [('')],
    [('class ', 'color1'), ('PaletteAnalyzer', 'color3'), (':', 'foreground')],
    [('    ', 'foreground'), ('"""Analyze color palettes."""', 'color2')],
    [('')],
    [('    ', 'foreground'), ('def ', 'color1'), ('__init__', 'color13'),
     ('(', 'foreground'), ('self', 'color9'), (', ', 'foreground'),
     ('colors', 'color14'), (': ', 'foreground'), ('List', 'color3'),
     ('[', 'foreground'), ('str', 'color3'), (']', 'foreground'),
     (')', 'foreground'), (':', 'foreground')],
    [('        ', 'foreground'), ('self', 'color9'),
     ('.colors = colors', 'foreground')],
    [('        ', 'foreground'), ('self', 'color9'),
     ('._cache: ', 'foreground'), ('Dict', 'color3'),
     (' = {}', 'foreground')],
    [('')],
    [('    ', 'foreground'), ('def ', 'color1'), ('hex_to_hsl', 'color4'),
     ('(', 'foreground'), ('self', 'color9'), (', ', 'foreground'),
     ('hex_color', 'color14'), (': ', 'foreground'), ('str', 'color3'),
     (')', 'foreground'), (':', 'foreground')],
    [('        ', 'foreground'), ('# Convert hex to HSL values', 'color8')],
    [('        ', 'foreground'), ('h', 'foreground'), (' = ', 'color9'),
     ('hex_color', 'foreground'), ('.lstrip(', 'foreground'),
     ("'#'", 'color2'), (')', 'foreground')],
    [('        ', 'foreground'), ('r', 'foreground'), (' = ', 'color9'),
     ('int', 'color12'), ('(h[', 'foreground'), ('0', 'color5'),
     (':', 'foreground'), ('2', 'color5'), ('], ', 'foreground'),
     ('16', 'color5'), (') / ', 'foreground'), ('255.0', 'color5')],
    [('        ', 'foreground'), ('g', 'foreground'), (' = ', 'color9'),
     ('int', 'color12'), ('(h[', 'foreground'), ('2', 'color5'),
     (':', 'foreground'), ('4', 'color5'), ('], ', 'foreground'),
     ('16', 'color5'), (') / ', 'foreground'), ('255.0', 'color5')],
    [('        ', 'foreground'), ('b', 'foreground'), (' = ', 'color9'),
     ('int', 'color12'), ('(h[', 'foreground'), ('4', 'color5'),
     (':', 'foreground'), ('6', 'color5'), ('], ', 'foreground'),
     ('16', 'color5'), (') / ', 'foreground'), ('255.0', 'color5')],
    [('        ', 'foreground'), ('return ', 'color1'),
     ('colorsys', 'foreground'), ('.rgb_to_hls(r, g, b)', 'foreground')],
    [('')],
    [('    ', 'foreground'), ('def ', 'color1'), ('temperature', 'color4'),
     ('(', 'foreground'), ('self', 'color9'), (')', 'foreground'),
     (' -> ', 'color9'), ('float', 'color3'), (':', 'foreground')],
    [('        ', 'foreground'), ('"""Calculate palette warmth (-1..1)."""', 'color2')],
    [('        ', 'foreground'), ('if ', 'color1'), ('not ', 'color1'),
     ('self', 'color9'), ('.colors:', 'foreground')],
    [('            ', 'foreground'), ('return ', 'color1'),
     ('0.0', 'color5')],
    [('        ', 'foreground'), ('temps', 'foreground'), (' = ', 'color9'),
     ('[', 'foreground')],
    [('            ', 'foreground'), ('self', 'color9'),
     ('._hue_temp(c)', 'foreground')],
    [('            ', 'foreground'), ('for ', 'color1'),
     ('c', 'foreground'), (' in ', 'color1'), ('self', 'color9'),
     ('.colors', 'foreground')],
    [('        ', 'foreground'), (']', 'foreground')],
    [('        ', 'foreground'), ('return ', 'color1'),
     ('sum', 'color12'), ('(temps) / ', 'foreground'),
     ('len', 'color12'), ('(temps)', 'foreground')],
    [('')],
    # Prompt + git status
    [('user', 'color10'), ('@', 'color0'), ('archlinux', 'color10'),
     (':', 'foreground'), ('~/projects', 'color12'),
     ('$ ', 'foreground'), ('git status', 'color7')],
    [('On branch ', 'foreground'), ('feature/themes', 'color2')],
    [('Changes staged for commit:', 'foreground')],
    [('  modified:  ', 'color2'), ('src/palette.py', 'foreground')],
    [('  new file:  ', 'color2'), ('tests/test_palette.py', 'foreground')],
    [('Changes not staged:', 'foreground')],
    [('  modified:  ', 'color1'), ('README.md', 'foreground')],
    [('Untracked files:', 'foreground')],
    [('  ', 'foreground'), ('docs/', 'color1')],
    [('')],
    # Prompt + compile output
    [('user', 'color2'), ('@', 'color0'), ('archlinux', 'color2'),
     (':', 'foreground'), ('~/projects', 'color4'),
     ('$ ', 'foreground'), ('make test', 'color7')],
    [('Running ', 'foreground'), ('42', 'color5'), (' tests...', 'foreground')],
    [('  ', 'foreground'), ('PASS', 'color2'), ('  test_hex_to_hsl', 'foreground')],
    [('  ', 'foreground'), ('PASS', 'color2'), ('  test_temperature', 'foreground')],
    [('  ', 'foreground'), ('PASS', 'color2'), ('  test_similarity', 'foreground')],
    [('  ', 'foreground'), ('FAIL', 'color1'), ('  test_edge_cases', 'foreground'),
     (' - ', 'color8'), ('AssertionError', 'color9')],
    [('  ', 'foreground'), ('WARN', 'color3'), ('  test_performance', 'foreground'),
     (' - ', 'color8'), ('slow (2.4s)', 'color11')],
    [('Results: ', 'foreground'), ('40 passed', 'color2'),
     (', ', 'foreground'), ('1 failed', 'color1'),
     (', ', 'foreground'), ('1 warning', 'color3')],
    [('')],
    # Final prompt with cursor
    [('user', 'color10'), ('@', 'color0'), ('archlinux', 'color10'),
     (':', 'foreground'), ('~/projects', 'color12'),
     ('$ ', 'foreground')],
]

# Font settings
_FONT_FAMILY = "monospace"
_FONT_SIZE = 10
_LINE_PADDING = 3
_MARGIN = 12


def _hex_to_rgb(hex_color: str):
    """Convert hex color string to (r, g, b) floats in 0-1 range."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return r, g, b
    except (ValueError, IndexError):
        return 0.8, 0.8, 0.8


class TerminalPreviewWidget(Gtk.DrawingArea):
    """PangoCairo-rendered terminal preview showing theme colors in context.

    Displays a mock terminal session with colored prompt, git output,
    and cursor using the 16 ANSI colors from a theme palette.
    """

    def __init__(self):
        super().__init__()
        self._palette = None
        self._last_requested_height = 0
        self.set_size_request(400, -1)  # Natural height from content
        self.connect('draw', self._on_draw)

    def set_palette(self, palette: Dict[str, str]):
        """Update the displayed palette and redraw.

        Args:
            palette: Dict with color0-15, background, foreground, cursor keys.
        """
        self._palette = palette
        self.queue_draw()

    def _get_color(self, key: str) -> str:
        """Get a color from the palette with fallback to defaults."""
        if self._palette and key in self._palette:
            return self._palette[key]
        return _DEFAULT_PALETTE.get(key, '#cdd6f4')

    def _on_draw(self, widget, cr):
        """Draw terminal preview with mock content using theme colors."""
        alloc = widget.get_allocation()
        width = alloc.width
        height = alloc.height

        # Fill background
        bg = self._get_color('background')
        r, g, b = _hex_to_rgb(bg)
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if self._palette is None:
            # Show placeholder text
            fg = _hex_to_rgb('#888888')
            cr.set_source_rgb(*fg)
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(
                Pango.FontDescription(f"{_FONT_FAMILY} {_FONT_SIZE}")
            )
            layout.set_text("Select a theme to preview", -1)
            tw, th = layout.get_pixel_size()
            cr.move_to((width - tw) / 2, (height - th) / 2)
            PangoCairo.update_layout(cr, layout)
            PangoCairo.show_layout(cr, layout)
            return

        # Draw terminal content
        font_desc = Pango.FontDescription(f"{_FONT_FAMILY} {_FONT_SIZE}")
        y = _MARGIN

        # Measure line height using a sample layout
        sample_layout = PangoCairo.create_layout(cr)
        sample_layout.set_font_description(font_desc)
        sample_layout.set_text("Xg", -1)
        _, line_height = sample_layout.get_pixel_size()
        line_height += _LINE_PADDING

        # Calculate needed height and request it (for scrolled container)
        needed_height = _MARGIN * 2 + len(_TERMINAL_LINES) * line_height
        if needed_height != self._last_requested_height:
            self._last_requested_height = needed_height
            self.set_size_request(400, needed_height)

        for line_spans in _TERMINAL_LINES:
            x = _MARGIN
            for span in line_spans:
                if len(span) == 1:
                    # Empty line marker
                    break
                text, color_key = span

                layout = PangoCairo.create_layout(cr)
                layout.set_font_description(font_desc)
                layout.set_text(text, -1)

                color_hex = self._get_color(color_key)
                r, g, b = _hex_to_rgb(color_hex)
                cr.set_source_rgb(r, g, b)

                cr.move_to(x, y)
                PangoCairo.update_layout(cr, layout)
                PangoCairo.show_layout(cr, layout)

                tw, _ = layout.get_pixel_size()
                x += tw

            y += line_height

        # Draw cursor block at end of last line
        cursor_hex = self._get_color('cursor')
        r, g, b = _hex_to_rgb(cursor_hex)
        cr.set_source_rgba(r, g, b, 0.8)

        # Measure a single character width for the cursor block
        char_layout = PangoCairo.create_layout(cr)
        char_layout.set_font_description(font_desc)
        char_layout.set_text(" ", -1)
        char_w, char_h = char_layout.get_pixel_size()

        # Position cursor after the last prompt
        cursor_y = y - line_height
        # Calculate x position from last line spans
        cursor_x = _MARGIN
        if _TERMINAL_LINES:
            last_line = _TERMINAL_LINES[-1]
            temp_layout = PangoCairo.create_layout(cr)
            temp_layout.set_font_description(font_desc)
            for span in last_line:
                if len(span) == 1:
                    break
                temp_layout.set_text(span[0], -1)
                tw, _ = temp_layout.get_pixel_size()
                cursor_x += tw

        cr.rectangle(cursor_x, cursor_y, char_w, char_h)
        cr.fill()
