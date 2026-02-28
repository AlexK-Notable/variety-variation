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

# Mock terminal content: list of lines, each line is a list of (text, color_key) tuples
_TERMINAL_LINES = [
    # Prompt line
    [('user@host', 'color2'), (':', 'foreground'), ('~/projects', 'color4'),
     ('$ ', 'foreground'), ('git status', 'color7')],
    # Git output
    [('On branch ', 'foreground'), ('main', 'color6')],
    [('Changes not staged for commit:', 'foreground')],
    [('  modified:   ', 'color1'), ('src/config.py', 'color1')],
    [('  modified:   ', 'color1'), ('src/palette.py', 'color1')],
    [('')],
    [('Untracked files:', 'foreground')],
    [('  new file:   ', 'color2'), ('src/theme.py', 'color2')],
    [('  new file:   ', 'color2'), ('tests/test_theme.py', 'color2')],
    [('')],
    # Second prompt
    [('user@host', 'color2'), (':', 'foreground'), ('~/projects', 'color4'),
     ('$ ', 'foreground'), ('echo "hello world"', 'color3')],
    [('hello world', 'foreground')],
    # Third prompt with cursor
    [('user@host', 'color2'), (':', 'foreground'), ('~/projects', 'color4'),
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
        self.set_size_request(400, 250)
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

        for line_spans in _TERMINAL_LINES:
            if y + line_height > height - _MARGIN:
                break

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
