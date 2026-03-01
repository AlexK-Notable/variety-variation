# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Theme browser page for the Preferences notebook.

Provides a GTK3 interface for browsing, previewing, and activating
color themes from the theme library. Includes a terminal preview
widget, color swatch grid with editable colors, dark/light filtering,
palette adherence control, and matching wallpaper count.
"""

import logging
import threading
from typing import Dict, Optional, Callable

# fmt: off
import gi  # isort:skip
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # isort:skip
# fmt: on

from variety.TerminalPreviewWidget import TerminalPreviewWidget
from variety.smart_selection.models import ADHERENCE_CHOICES

logger = logging.getLogger(__name__)


class ColorSwatchGrid(Gtk.Grid):
    """Grid of 16 color swatches showing the ANSI palette.

    Swatches are clickable — clicking opens a color chooser dialog
    for editing that color. Edits are reported via the on_color_edited
    callback.
    """

    def __init__(self, on_color_edited=None):
        """Initialize swatch grid.

        Args:
            on_color_edited: Callback(color_key, new_hex) when a swatch color
                is changed by the user.
        """
        super().__init__()
        self.set_column_spacing(4)
        self.set_row_spacing(4)
        self._palette = None
        self._swatches = []
        self._on_color_edited = on_color_edited
        self._build_grid()

    def _build_grid(self):
        """Create 2x8 grid of clickable color swatches (colors 0-7, 8-15)."""
        for i in range(16):
            event_box = Gtk.EventBox()
            event_box.set_tooltip_text(f"color{i}")
            event_box.connect('button-press-event', self._on_swatch_clicked, i)

            swatch = Gtk.DrawingArea()
            swatch.set_size_request(32, 24)
            swatch.connect('draw', self._draw_swatch, i)
            event_box.add(swatch)

            row = i // 8
            col = i % 8
            self.attach(event_box, col, row, 1, 1)
            self._swatches.append(swatch)

    def set_palette(self, palette: Optional[Dict[str, str]]):
        """Update swatch colors and redraw."""
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

    def _on_swatch_clicked(self, event_box, event, color_index):
        """Open color chooser for a swatch."""
        if event.button != 1:
            return
        key = f"color{color_index}"
        current_hex = '#888888'
        if self._palette and key in self._palette:
            current_hex = self._palette[key]

        new_hex = _run_color_chooser(
            event_box.get_toplevel(), f"Edit {key}", current_hex
        )
        if new_hex and self._on_color_edited:
            self._on_color_edited(key, new_hex)


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


def _run_color_chooser(parent_window, title: str, current_hex: str) -> Optional[str]:
    """Open a GTK ColorChooserDialog and return the selected hex color.

    Returns None if the user cancels.
    """
    dialog = Gtk.ColorChooserDialog(title=title, transient_for=parent_window)
    r, g, b = _hex_to_rgb(current_hex)
    dialog.set_rgba(Gdk.RGBA(r, g, b, 1.0))
    dialog.set_use_alpha(False)
    response = dialog.run()
    result = None
    if response == Gtk.ResponseType.OK:
        rgba = dialog.get_rgba()
        result = '#{:02x}{:02x}{:02x}'.format(
            int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255)
        )
    dialog.destroy()
    return result


class ThemeBrowserPage(Gtk.Box):
    """Main theme browser page for the Preferences notebook.

    Provides a horizontally paned layout with a searchable/filterable
    theme list on the left and a terminal preview with editable color
    swatches on the right.
    """

    def __init__(self, theme_library=None, theme_override=None, config=None,
                 on_theme_changed=None):
        """Initialize the theme browser page.

        Args:
            theme_library: ThemeLibrary instance for listing/importing themes.
            theme_override: ThemeOverride instance for activating/deactivating.
            config: SelectionConfig instance for persisting active_theme_id.
            on_theme_changed: Optional callback invoked after theme is applied
                or cleared. Receives (theme_id_or_None, adherence_str_or_None).
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._theme_library = theme_library
        self._theme_override = theme_override
        self._config = config
        self._on_theme_changed = on_theme_changed
        self._selected_theme_id = None
        self._selected_palette = None
        self._editing_palette = None  # Unsaved color edits
        self._appearance_filter = 'all'  # 'all', 'dark', 'light'
        self.set_border_width(6)
        self._build_ui()

    def _build_ui(self):
        """Build the complete UI layout."""
        # Top toolbar: Search + Dark/Light toggle + Import button
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search themes...")
        self._search_entry.connect('search-changed', self._on_search_changed)
        toolbar.pack_start(self._search_entry, True, True, 0)

        # Dark/Light/All toggle
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        filter_box.get_style_context().add_class('linked')
        self._filter_all = Gtk.RadioButton.new_with_label(None, "All")
        self._filter_dark = Gtk.RadioButton.new_with_label_from_widget(
            self._filter_all, "Dark"
        )
        self._filter_light = Gtk.RadioButton.new_with_label_from_widget(
            self._filter_all, "Light"
        )
        self._filter_all.set_mode(False)  # Button-style, not radio dot
        self._filter_dark.set_mode(False)
        self._filter_light.set_mode(False)
        self._filter_all.connect('toggled', self._on_appearance_toggled, 'all')
        self._filter_dark.connect('toggled', self._on_appearance_toggled, 'dark')
        self._filter_light.connect('toggled', self._on_appearance_toggled, 'light')
        filter_box.pack_start(self._filter_all, False, False, 0)
        filter_box.pack_start(self._filter_dark, False, False, 0)
        filter_box.pack_start(self._filter_light, False, False, 0)
        toolbar.pack_start(filter_box, False, False, 0)

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

        # Right pane: Preview + swatches + buttons + controls
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Terminal preview in a scrollable frame
        preview_frame = Gtk.Frame()
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._terminal_preview = TerminalPreviewWidget()
        preview_scroll.add(self._terminal_preview)
        preview_frame.add(preview_scroll)
        right_box.pack_start(preview_frame, True, True, 0)

        # Color swatch grid (clickable for editing)
        swatch_label = Gtk.Label(label="ANSI Colors (click to edit)")
        swatch_label.set_xalign(0)
        right_box.pack_start(swatch_label, False, False, 0)

        self._swatch_grid = ColorSwatchGrid(on_color_edited=self._on_color_edited)
        right_box.pack_start(self._swatch_grid, False, False, 0)

        # Special colors (background, foreground, cursor) — clickable
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._bg_btn = Gtk.Button(label="BG: -")
        self._bg_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._bg_btn.connect('clicked', self._on_meta_color_clicked, 'background')
        self._fg_btn = Gtk.Button(label="FG: -")
        self._fg_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._fg_btn.connect('clicked', self._on_meta_color_clicked, 'foreground')
        self._cursor_btn = Gtk.Button(label="Cursor: -")
        self._cursor_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._cursor_btn.connect('clicked', self._on_meta_color_clicked, 'cursor')
        meta_box.pack_start(self._bg_btn, False, False, 0)
        meta_box.pack_start(self._fg_btn, False, False, 0)
        meta_box.pack_start(self._cursor_btn, False, False, 0)
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

        self._save_custom_btn = Gtk.Button(label="Save as Custom")
        self._save_custom_btn.connect('clicked', self._on_save_custom_clicked)
        self._save_custom_btn.set_sensitive(False)
        self._save_custom_btn.set_tooltip_text(
            "Save edited colors as a new custom theme"
        )
        btn_box.pack_start(self._save_custom_btn, True, True, 0)

        self._clear_btn = Gtk.Button(label="Clear Override")
        self._clear_btn.connect('clicked', self._on_clear_clicked)
        self._clear_btn.set_sensitive(False)
        btn_box.pack_start(self._clear_btn, True, True, 0)

        right_box.pack_start(btn_box, False, False, 0)

        # Separator before adherence controls
        right_box.pack_start(Gtk.Separator(), False, False, 2)

        # Palette adherence control
        adherence_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        adherence_label = Gtk.Label(label="Wallpaper matching:")
        adherence_label.set_xalign(0)
        adherence_box.pack_start(adherence_label, False, False, 0)

        self._adherence_combo = Gtk.ComboBoxText()
        for label, _ in ADHERENCE_CHOICES:
            self._adherence_combo.append_text(label)
        self._adherence_combo.set_active(2)  # Default: Moderate
        self._adherence_combo.connect('changed', self._on_adherence_changed)
        adherence_box.pack_start(self._adherence_combo, False, False, 0)
        right_box.pack_start(adherence_box, False, False, 0)

        # Matching wallpaper count
        self._match_label = Gtk.Label(label="")
        self._match_label.set_xalign(0)
        right_box.pack_start(self._match_label, False, False, 0)

        paned.pack2(right_box, resize=True, shrink=False)
        self.pack_start(paned, True, True, 0)

    # =========================================================================
    # Filtering
    # =========================================================================

    def _filter_visible(self, model, iter, data=None):
        """Filter function combining search text and appearance toggle."""
        # Appearance filter
        if self._appearance_filter != 'all':
            appearance = (model[iter][2] or '').lower()
            if appearance != self._appearance_filter:
                return False

        # Search text filter
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

    def _on_appearance_toggled(self, button, appearance):
        """Handle dark/light/all filter toggle."""
        if button.get_active():
            self._appearance_filter = appearance
            self._theme_filter.refilter()
            self._update_count_label()

    # =========================================================================
    # Theme selection and preview
    # =========================================================================

    def _on_theme_selected(self, selection):
        """Update preview when a theme is selected."""
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            self._selected_theme_id = None
            self._selected_palette = None
            self._editing_palette = None
            self._terminal_preview.set_palette(None)
            self._swatch_grid.set_palette(None)
            self._apply_btn.set_sensitive(False)
            self._save_custom_btn.set_sensitive(False)
            self._info_label.set_text("")
            self._bg_btn.set_label("BG: -")
            self._fg_btn.set_label("FG: -")
            self._cursor_btn.set_label("Cursor: -")
            self._match_label.set_text("")
            return

        # Get theme_id from the underlying store
        child_iter = self._theme_filter.convert_iter_to_child_iter(tree_iter)
        theme_id = self._theme_store[child_iter][0]
        theme_name = self._theme_store[child_iter][1]
        source_type = self._theme_store[child_iter][3]

        self._selected_theme_id = theme_id
        self._apply_btn.set_sensitive(True)

        # Load palette from theme library
        palette = None
        if self._theme_library:
            palette = self._theme_library.get_theme_palette(theme_id)

        self._selected_palette = palette
        self._editing_palette = dict(palette) if palette else None
        self._save_custom_btn.set_sensitive(False)
        self._update_preview()

        # Update info labels
        self._info_label.set_text(f"{theme_name} ({source_type})")

        # Update wallpaper count
        self._update_match_count()

    def _update_preview(self):
        """Update terminal preview and swatches from editing palette."""
        palette = self._editing_palette
        # Pass a new dict copy so set_palette always sees a "new" object,
        # ensuring GTK schedules a full redraw even if the reference is the same.
        preview_palette = dict(palette) if palette else None
        self._terminal_preview.set_palette(preview_palette)
        self._swatch_grid.set_palette(preview_palette)
        if palette:
            self._bg_btn.set_label(f"BG: {palette.get('background', '-')}")
            self._fg_btn.set_label(f"FG: {palette.get('foreground', '-')}")
            self._cursor_btn.set_label(f"Cursor: {palette.get('cursor', '-')}")
        else:
            self._bg_btn.set_label("BG: -")
            self._fg_btn.set_label("FG: -")
            self._cursor_btn.set_label("Cursor: -")

    # =========================================================================
    # Color editing
    # =========================================================================

    def _on_color_edited(self, color_key, new_hex):
        """Handle color swatch edit from the grid."""
        if not self._editing_palette:
            return
        self._editing_palette[color_key] = new_hex
        self._save_custom_btn.set_sensitive(True)
        self._update_preview()

    def _on_meta_color_clicked(self, button, color_key):
        """Handle click on BG/FG/Cursor button to edit that color."""
        if not self._editing_palette:
            return
        current = self._editing_palette.get(color_key, '#888888')
        labels = {'background': 'Background', 'foreground': 'Foreground', 'cursor': 'Cursor'}
        new_hex = _run_color_chooser(
            self.get_toplevel(), f"Edit {labels.get(color_key, color_key)}", current
        )
        if new_hex:
            self._editing_palette[color_key] = new_hex
            self._save_custom_btn.set_sensitive(True)
            self._update_preview()

    def _on_save_custom_clicked(self, button):
        """Save edited colors as a new custom theme."""
        if not self._theme_library or not self._selected_theme_id:
            return
        if not self._editing_palette:
            return

        # Prompt for name
        dialog = Gtk.Dialog(
            title="Save Custom Theme",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        )
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        label = Gtk.Label(label="Name for the custom theme:")
        box.pack_start(label, False, False, 0)
        entry = Gtk.Entry()
        entry.set_text(f"Custom - {self._theme_store[self._theme_filter.convert_iter_to_child_iter(self._theme_view.get_selection().get_selected()[1])][1]}")
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()

        response = dialog.run()
        name = entry.get_text().strip()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not name:
            return

        try:
            # Fork the theme
            forked = self._theme_library.fork_theme(self._selected_theme_id, name)
            if not forked:
                logger.warning("Failed to fork theme: parent not found")
                return

            # Apply the edited colors to the forked record
            from variety.smart_selection.palette import calculate_palette_metrics
            for key, val in self._editing_palette.items():
                if hasattr(forked, key):
                    object.__setattr__(forked, key, val)

            # Recalculate metrics
            metrics = calculate_palette_metrics(self._editing_palette)
            for metric_key in ('avg_hue', 'avg_saturation', 'avg_lightness',
                               'color_temperature'):
                if metric_key in metrics:
                    object.__setattr__(forked, metric_key, metrics[metric_key])

            # Save to database
            self._theme_library.db.upsert_color_theme(forked)

            # Refresh list and select the new theme
            self._refresh_theme_list()
            self._select_theme_by_id(forked.theme_id)

            logger.info("Saved custom theme: %s (%s)", name, forked.theme_id)

        except Exception as e:
            logger.warning("Failed to save custom theme: %s", e)

    def _select_theme_by_id(self, theme_id: str):
        """Select a theme in the tree view by its ID."""
        for i, row in enumerate(self._theme_filter):
            child_iter = self._theme_filter.convert_iter_to_child_iter(
                self._theme_filter.get_iter(Gtk.TreePath(i))
            )
            if self._theme_store[child_iter][0] == theme_id:
                path = Gtk.TreePath(i)
                self._theme_view.get_selection().select_path(path)
                self._theme_view.scroll_to_cell(path, None, False, 0, 0)
                return

    # =========================================================================
    # Theme activation
    # =========================================================================

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
                    adherence = self._get_adherence_value()
                    self._on_theme_changed(self._selected_theme_id, adherence)
            except ValueError as e:
                logger.warning("Failed to activate theme: %s", e)

    def _on_clear_clicked(self, button):
        """Deactivate theme override and revert to wallust-driven mode."""
        if self._theme_override:
            self._theme_override.deactivate()
        if self._config:
            self._config.active_theme_id = None
        self._clear_btn.set_sensitive(False)
        self._match_label.set_text("")
        logger.info("Theme override cleared")
        if self._on_theme_changed:
            self._on_theme_changed(None, None)

    # =========================================================================
    # Adherence control
    # =========================================================================

    def _get_adherence_value(self) -> Optional[float]:
        """Get current adherence min_color_similarity value."""
        idx = self._adherence_combo.get_active()
        if idx < 0 or idx >= len(ADHERENCE_CHOICES):
            return 0.30
        return ADHERENCE_CHOICES[idx][1]

    def _get_adherence_label(self) -> str:
        """Get current adherence level label."""
        idx = self._adherence_combo.get_active()
        if idx < 0 or idx >= len(ADHERENCE_CHOICES):
            return "moderate"
        return ADHERENCE_CHOICES[idx][0].lower()

    def _on_adherence_changed(self, combo):
        """Handle adherence level change."""
        self._update_match_count()
        # Notify parent if a theme is active
        if self._theme_override and self._theme_override.is_active:
            if self._on_theme_changed:
                adherence = self._get_adherence_value()
                self._on_theme_changed(
                    self._theme_override.active_theme_id, adherence
                )

    # =========================================================================
    # Matching wallpaper count
    # =========================================================================

    def _update_match_count(self):
        """Update the matching wallpaper count label in a background thread."""
        palette = self._editing_palette
        adherence = self._get_adherence_value()

        if not palette or adherence is None:
            self._match_label.set_text(
                "All wallpapers (no color filter)" if palette else ""
            )
            return

        if not self._theme_library:
            self._match_label.set_text("")
            return

        self._match_label.set_text("Counting...")

        db = self._theme_library.db
        # Snapshot the palette for the background thread
        palette_snapshot = dict(palette)

        def _count():
            try:
                from variety.smart_selection.palette import (
                    calculate_palette_metrics, palette_similarity
                )
                # Compute theme's aggregate HSL metrics from its hex colors.
                # Use HSL for mood matching — same as the actual selector's
                # ConstraintApplier._passes_color_constraints.
                theme_metrics = calculate_palette_metrics(palette_snapshot)
                if not theme_metrics:
                    GLib.idle_add(self._set_match_label, -1, 0)
                    return

                # Get all wallpaper palette records
                all_palettes = db.get_all_palettes()
                total = len(all_palettes)
                matching = 0
                for p in all_palettes:
                    img_metrics = {
                        'avg_hue': p.avg_hue,
                        'avg_saturation': p.avg_saturation,
                        'avg_lightness': p.avg_lightness,
                        'color_temperature': p.color_temperature,
                    }
                    sim = palette_similarity(
                        theme_metrics, img_metrics, use_oklab=False
                    )
                    if sim >= adherence:
                        matching += 1
                GLib.idle_add(self._set_match_label, matching, total)
            except Exception as e:
                logger.debug("Failed to count matching wallpapers: %s", e)
                GLib.idle_add(self._set_match_label, -1, 0)

        thread = threading.Thread(target=_count, daemon=True)
        thread.start()

    def _set_match_label(self, matching: int, total: int):
        """Set the match label from the main thread."""
        if matching < 0:
            self._match_label.set_text("Could not count wallpapers")
        elif total == 0:
            self._match_label.set_text("No indexed wallpapers")
        else:
            self._match_label.set_text(f"{matching} of {total} wallpapers match")

    # =========================================================================
    # Import and list management
    # =========================================================================

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
