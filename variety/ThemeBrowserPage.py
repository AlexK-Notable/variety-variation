# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Theme browser page for the Preferences notebook.

Provides a GTK3 interface for browsing, previewing, and activating
color themes from the theme library. Includes a terminal preview
widget and color swatch grid for visual theme comparison.
"""

import logging
from typing import Dict, Optional

# fmt: off
import gi  # isort:skip
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk  # isort:skip
# fmt: on

from variety.TerminalPreviewWidget import TerminalPreviewWidget

logger = logging.getLogger(__name__)


class ColorSwatchGrid(Gtk.Grid):
    """Grid of 16 color swatches showing the ANSI palette."""

    def __init__(self):
        super().__init__()
        self.set_column_spacing(4)
        self.set_row_spacing(4)
        self._palette = None
        self._swatches = []
        self._build_grid()

    def _build_grid(self):
        """Create 2x8 grid of color swatches (colors 0-7, 8-15)."""
        for i in range(16):
            swatch = Gtk.DrawingArea()
            swatch.set_size_request(32, 24)
            swatch.connect('draw', self._draw_swatch, i)
            swatch.set_tooltip_text(f"color{i}")
            row = i // 8
            col = i % 8
            self.attach(swatch, col, row, 1, 1)
            self._swatches.append(swatch)

    def set_palette(self, palette: Optional[Dict[str, str]]):
        """Update swatch colors and redraw.

        Args:
            palette: Dict with color0-15 keys as hex strings.
        """
        self._palette = palette
        for swatch in self._swatches:
            swatch.queue_draw()

    def _draw_swatch(self, widget, cr, color_index):
        """Draw a single color swatch."""
        alloc = widget.get_allocation()
        w = alloc.width
        h = alloc.height

        key = f"color{color_index}"
        hex_color = '#888888'
        if self._palette and key in self._palette:
            hex_color = self._palette[key]

        r, g, b = _hex_to_rgb(hex_color)
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Draw subtle border
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.3)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w - 1, h - 1)
        cr.stroke()


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
        return 0.5, 0.5, 0.5


class ThemeBrowserPage(Gtk.Box):
    """Main theme browser page for the Preferences notebook.

    Provides a horizontally paned layout with a searchable theme list
    on the left and a terminal preview with color swatches on the right.

    Can be instantiated without arguments for standalone use or testing.
    When theme_library, theme_override, and config are provided, the
    page connects to the backend for theme management operations.
    """

    def __init__(self, theme_library=None, theme_override=None, config=None,
                 on_theme_changed=None):
        """Initialize the theme browser page.

        Args:
            theme_library: ThemeLibrary instance for listing/importing themes.
            theme_override: ThemeOverride instance for activating/deactivating.
            config: SelectionConfig instance for persisting active_theme_id.
            on_theme_changed: Optional callback invoked after theme is applied
                or cleared. Receives the active theme_id (str or None).
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._theme_library = theme_library
        self._theme_override = theme_override
        self._config = config
        self._on_theme_changed = on_theme_changed
        self._selected_theme_id = None
        self._selected_palette = None
        self.set_border_width(6)
        self._build_ui()

    def _build_ui(self):
        """Build the complete UI layout."""
        # Top toolbar: Search + Import button
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search themes...")
        self._search_entry.connect('search-changed', self._on_search_changed)
        toolbar.pack_start(self._search_entry, True, True, 0)

        import_btn = Gtk.Button(label="Refresh from Zed")
        import_btn.connect('clicked', self._on_refresh_clicked)
        toolbar.pack_end(import_btn, False, False, 0)

        self.pack_start(toolbar, False, False, 0)

        # Main content: HPaned with list left, preview right
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(280)

        # Left pane: Theme list in ScrolledWindow
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_width(250)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # ListStore: theme_id, name, appearance, source_type
        self._theme_store = Gtk.ListStore(str, str, str, str)
        self._theme_filter = self._theme_store.filter_new()
        self._theme_filter.set_visible_func(self._filter_visible)

        self._theme_view = Gtk.TreeView(model=self._theme_filter)
        self._theme_view.set_headers_visible(True)
        self._theme_view.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
        self._theme_view.get_selection().connect('changed', self._on_theme_selected)

        # Name column
        name_renderer = Gtk.CellRendererText()
        name_col = Gtk.TreeViewColumn("Name", name_renderer, text=1)
        name_col.set_expand(True)
        name_col.set_sort_column_id(1)
        self._theme_view.append_column(name_col)

        # Appearance column
        appear_renderer = Gtk.CellRendererText()
        appear_col = Gtk.TreeViewColumn("Style", appear_renderer, text=2)
        appear_col.set_min_width(60)
        appear_col.set_sort_column_id(2)
        self._theme_view.append_column(appear_col)

        scroll.add(self._theme_view)
        left_box.pack_start(scroll, True, True, 0)

        # Theme count label
        self._count_label = Gtk.Label(label="No themes loaded")
        self._count_label.set_xalign(0)
        left_box.pack_start(self._count_label, False, False, 0)

        paned.pack1(left_box, resize=True, shrink=False)

        # Right pane: Preview + swatches + buttons
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Terminal preview in a frame
        preview_frame = Gtk.Frame()
        self._terminal_preview = TerminalPreviewWidget()
        preview_frame.add(self._terminal_preview)
        right_box.pack_start(preview_frame, True, True, 0)

        # Color swatch grid
        swatch_label = Gtk.Label(label="ANSI Colors")
        swatch_label.set_xalign(0)
        right_box.pack_start(swatch_label, False, False, 0)

        self._swatch_grid = ColorSwatchGrid()
        right_box.pack_start(self._swatch_grid, False, False, 0)

        # Special colors (background, foreground, cursor)
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._bg_label = Gtk.Label(label="BG: -")
        self._fg_label = Gtk.Label(label="FG: -")
        self._cursor_label = Gtk.Label(label="Cursor: -")
        meta_box.pack_start(self._bg_label, False, False, 0)
        meta_box.pack_start(self._fg_label, False, False, 0)
        meta_box.pack_start(self._cursor_label, False, False, 0)
        right_box.pack_start(meta_box, False, False, 0)

        # Theme info label
        self._info_label = Gtk.Label(label="")
        self._info_label.set_xalign(0)
        self._info_label.set_line_wrap(True)
        right_box.pack_start(self._info_label, False, False, 0)

        # Action buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._apply_btn = Gtk.Button(label="Apply Theme")
        self._apply_btn.get_style_context().add_class('suggested-action')
        self._apply_btn.connect('clicked', self._on_apply_clicked)
        self._apply_btn.set_sensitive(False)
        btn_box.pack_start(self._apply_btn, True, True, 0)

        self._clear_btn = Gtk.Button(label="Clear Override")
        self._clear_btn.connect('clicked', self._on_clear_clicked)
        self._clear_btn.set_sensitive(False)
        btn_box.pack_start(self._clear_btn, True, True, 0)

        right_box.pack_start(btn_box, False, False, 0)

        paned.pack2(right_box, resize=True, shrink=False)
        self.pack_start(paned, True, True, 0)

    def _filter_visible(self, model, iter, data=None):
        """Filter function for the theme list based on search text."""
        search_text = self._search_entry.get_text().lower()
        if not search_text:
            return True
        name = model[iter][1]
        appearance = model[iter][2]
        source_type = model[iter][3]
        return (
            search_text in (name or '').lower()
            or search_text in (appearance or '').lower()
            or search_text in (source_type or '').lower()
        )

    def _on_search_changed(self, entry):
        """Handle search text changes."""
        self._theme_filter.refilter()
        self._update_count_label()

    def _on_theme_selected(self, selection):
        """Update preview when a theme is selected."""
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            self._selected_theme_id = None
            self._selected_palette = None
            self._terminal_preview.set_palette(None)
            self._swatch_grid.set_palette(None)
            self._apply_btn.set_sensitive(False)
            self._info_label.set_text("")
            self._bg_label.set_text("BG: -")
            self._fg_label.set_text("FG: -")
            self._cursor_label.set_text("Cursor: -")
            return

        # Get theme_id from the underlying store
        child_iter = self._theme_filter.convert_iter_to_child_iter(tree_iter)
        theme_id = self._theme_store[child_iter][0]
        theme_name = self._theme_store[child_iter][1]
        appearance = self._theme_store[child_iter][2]
        source_type = self._theme_store[child_iter][3]

        self._selected_theme_id = theme_id
        self._apply_btn.set_sensitive(True)

        # Load palette from theme library
        palette = None
        if self._theme_library:
            palette = self._theme_library.get_theme_palette(theme_id)

        self._selected_palette = palette
        self._terminal_preview.set_palette(palette)
        self._swatch_grid.set_palette(palette)

        # Update info labels
        self._info_label.set_text(f"{theme_name} ({source_type})")
        if palette:
            self._bg_label.set_text(f"BG: {palette.get('background', '-')}")
            self._fg_label.set_text(f"FG: {palette.get('foreground', '-')}")
            self._cursor_label.set_text(f"Cursor: {palette.get('cursor', '-')}")
        else:
            self._bg_label.set_text("BG: -")
            self._fg_label.set_text("FG: -")
            self._cursor_label.set_text("Cursor: -")

    def _on_apply_clicked(self, button):
        """Activate selected theme and trigger template processing."""
        if not self._selected_theme_id:
            return
        if self._theme_override:
            try:
                self._theme_override.activate(self._selected_theme_id)
                if self._config:
                    self._config.active_theme_id = self._selected_theme_id
                self._clear_btn.set_sensitive(True)
                logger.info("Theme activated: %s", self._selected_theme_id)
                if self._on_theme_changed:
                    self._on_theme_changed(self._selected_theme_id)
            except ValueError as e:
                logger.warning("Failed to activate theme: %s", e)

    def _on_clear_clicked(self, button):
        """Deactivate theme override and revert to wallust-driven mode."""
        if self._theme_override:
            self._theme_override.deactivate()
        if self._config:
            self._config.active_theme_id = None
        self._clear_btn.set_sensitive(False)
        logger.info("Theme override cleared")
        if self._on_theme_changed:
            self._on_theme_changed(None)

    def _on_refresh_clicked(self, button):
        """Import themes from Zed."""
        if not self._theme_library:
            logger.warning("No theme library available for import")
            return
        try:
            count = self._theme_library.import_from_zed()
            self._refresh_theme_list()
            logger.info("Imported %d themes from Zed", count)
        except Exception as e:
            logger.warning("Failed to import Zed themes: %s", e)

    def _refresh_theme_list(self):
        """Reload themes from database into the list store."""
        self._theme_store.clear()
        if not self._theme_library:
            self._update_count_label()
            return

        try:
            themes = self._theme_library.db.get_all_color_themes()
            for theme in themes:
                self._theme_store.append([
                    theme.theme_id,
                    theme.name,
                    theme.appearance or '',
                    theme.source_type or '',
                ])
        except Exception as e:
            logger.warning("Failed to load themes: %s", e)

        self._update_count_label()

        # Update clear button sensitivity based on current override state
        if self._theme_override and self._theme_override.is_active:
            self._clear_btn.set_sensitive(True)

    def _update_count_label(self):
        """Update the theme count label."""
        total = len(self._theme_store)
        visible = len(self._theme_filter)
        if total == 0:
            self._count_label.set_text("No themes loaded")
        elif visible == total:
            self._count_label.set_text(f"{total} themes")
        else:
            self._count_label.set_text(f"{visible} of {total} themes")

    def load_themes(self):
        """Public method to trigger theme list loading.

        Call this when the tab is first shown to avoid loading
        themes during dialog construction.
        """
        self._refresh_theme_list()
