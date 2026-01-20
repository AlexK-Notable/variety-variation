# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (c) 2012, Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

# This is the preferences dialog.

import logging
import os
import random
import shutil
import stat
import subprocess
import threading

from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk  # pylint: disable=E0611

from variety import Texts
from variety.AddConfigurableDialog import AddConfigurableDialog
from variety.AddFlickrDialog import AddFlickrDialog
from variety.AddWallhavenDialog import AddWallhavenDialog
from variety.EditFavoriteOperationsDialog import EditFavoriteOperationsDialog
from variety.FolderChooser import FolderChooser
from variety.Options import Options
from variety.plugins.IQuoteSource import IQuoteSource
from variety.profile import (
    get_autostart_file_path,
    get_profile_path,
    get_profile_short_name,
    get_profile_wm_class,
    is_default_profile,
)
from variety.Util import Util, _, on_gtk
from variety_lib import varietyconfig
from variety_lib.PreferencesDialog import PreferencesDialog
from variety_lib.varietyconfig import get_data_file

random.seed()
logger = logging.getLogger("variety")

SLIDESHOW_PAGE_INDEX = 4
SMART_SELECTION_PAGE_INDEX = 7
DONATE_PAGE_INDEX = 11

# Tooltips for Smart Selection controls
SMART_SELECTION_TOOLTIPS = {
    "smart_selection_enabled": _("Use intelligent selection instead of random"),
    "smart_image_cooldown": _("Days before a wallpaper can repeat"),
    "smart_source_cooldown": _("Days before favoring the same source again"),
    "smart_favorite_boost": _("How much more likely favorites are selected"),
    "smart_new_boost": _("How much more likely new images are selected"),
    "smart_decay_type": _("How quickly the recency penalty decreases over time"),
    "smart_color_enabled": _("Prefer wallpapers with similar color palettes"),
    "smart_color_temperature": _("Target color warmth for wallpaper selection"),
    "smart_color_similarity": _("Minimum similarity for color matching"),
    "smart_time_adaptation": _("Adjust palette preferences based on time of day"),
    "smart_theming_enabled": _("Update system theme colors when wallpaper changes"),
    "smart_theming_configure": _("Configure wallust theming templates"),
    "smart_rebuild_index": _("Rebuild the image index from scratch"),
    "smart_extract_palettes": _("Extract color palettes for all indexed images"),
    "smart_clear_history": _("Clear selection history and recency data"),
    "smart_preview_button": _("Preview which wallpapers would be selected next"),
}

# Extended help content for info popovers
SMART_SELECTION_HELP = {
    "overview": _(
        "Smart Selection replaces random wallpaper rotation with intelligent "
        "weighted selection. Images are scored based on recency (recently shown "
        "images have lower scores), source diversity, favorites status, and "
        "color palette matching.\n\n"
        "The algorithm ensures variety while respecting your preferences. "
        "Favorites appear more often, recently shown images get a cooldown "
        "period, and sources are balanced so one folder doesn't dominate.\n\n"
        "Statistics show how many images are indexed, palette extraction "
        "progress, and selection history."
    ),
    "time_adaptation": _(
        "Time adaptation adjusts which wallpapers are preferred based on the "
        "time of day. During the day, brighter and optionally warmer palettes "
        "are favored. At night, darker and cooler palettes take priority.\n\n"
        "Three timing methods are available:\n"
        "- Sunrise/Sunset - uses your location to calculate actual daylight hours\n"
        "- Fixed Schedule - set specific times for day and night\n"
        "- System Theme - follows your desktop's dark/light mode setting\n\n"
        "Presets provide quick configurations, or use Custom with the sliders "
        "for precise control."
    ),
    "color_matching": _(
        "Color matching uses the OKLAB perceptual color space to find "
        "wallpapers with similar palettes. OKLAB ensures that visually similar "
        "colors are mathematically close, unlike simpler color models.\n\n"
        "When enabled, wallpapers with palettes similar to your target "
        "preferences receive a selection boost. This works alongside time "
        "adaptation - if both are enabled, the current time period's target "
        "palette is used.\n\n"
        "Palettes are automatically extracted when wallpapers are shown. "
        "The 'Images with palettes' statistic shows extraction progress."
    ),
    "presets": _(
        "Presets provide quick configurations for common preferences:\n\n"
        "- Bright Day - energetic, sunlit feel (high lightness, warm)\n"
        "- Neutral Day - balanced, non-distracting\n"
        "- Cozy Night - warm, dim, relaxed atmosphere\n"
        "- Cool Night - blue-tinted, modern feel\n"
        "- Dark Mode - minimal eye strain, low lightness\n"
        "- Custom - configure your own values with sliders"
    ),
    "decay_types": _(
        "The decay type controls how the recency penalty decreases over time:\n\n"
        "- Exponential - penalty drops rapidly at first, then slowly (recommended)\n"
        "- Linear - penalty decreases at a constant rate\n"
        "- Step - full penalty until cooldown expires, then none\n\n"
        "Exponential decay provides the most natural-feeling variety, "
        "preventing immediate repeats while allowing occasional returns "
        "to recently-shown favorites."
    ),
    "theming": _(
        "The theming engine integrates with wallust to update your system "
        "theme colors based on the current wallpaper's palette.\n\n"
        "When enabled, wallust extracts colors from each new wallpaper and "
        "applies them to configured templates (terminal, GTK theme, etc.).\n\n"
        "Click 'Configure' to edit your wallust.toml file, which defines "
        "which templates are updated and how colors are mapped."
    ),
}


class PreferencesVarietyDialog(PreferencesDialog):
    __gtype_name__ = "PreferencesVarietyDialog"

    def finish_initializing(self, builder, parent):  # pylint: disable=E1002
        """Set up the preferences dialog"""
        super(PreferencesVarietyDialog, self).finish_initializing(builder, parent)

        # Bind each preference widget to gsettings
        #        widget = self.builder.get_object('example_entry')
        #        settings.bind("example", widget, "text", Gio.SettingsBindFlags.DEFAULT)

        if Gdk.Screen.get_default().get_height() < 750:
            self.ui.sources_scrolled_window.set_size_request(0, 0)
            self.ui.hosts_scrolled_window.set_size_request(0, 0)
            self.ui.tips_scrolled_window.set_size_request(0, 0)

        PreferencesVarietyDialog.add_image_preview(self.ui.icon_chooser, 64)
        self.loading = False

        # Extraction state tracking
        self._extraction_cancelled = False
        self._extraction_thread = None

        self.fav_chooser = FolderChooser(
            self.ui.favorites_folder_chooser, self.on_favorites_changed
        )
        self.fetched_chooser = FolderChooser(
            self.ui.fetched_folder_chooser, self.on_fetched_changed
        )
        self.copyto_chooser = FolderChooser(self.ui.copyto_folder_chooser, self.on_copyto_changed)
        self.slideshow_custom_chooser = FolderChooser(
            self.ui.slideshow_custom_chooser, self.delayed_apply
        )

        if not Util.check_variety_slideshow_present():
            self.ui.notebook.remove_page(SLIDESHOW_PAGE_INDEX)

        profile_suffix = (
            "" if is_default_profile() else _(" (Profile: {})").format(get_profile_short_name())
        )
        self.set_title(_("Variety Preferences") + profile_suffix)
        self.set_wmclass(get_profile_wm_class(), get_profile_wm_class())

        self.reload()

    def fill_smart_profile_url(self, msg):
        if "%SMART_PROFILE_URL%" in msg:
            profile_url = self.parent.smart.get_profile_url()
            msg = msg.replace("%SMART_PROFILE_URL%", profile_url) if profile_url else ""
        return msg

    def update_status_message(self):
        msg = ""
        if self.parent.server_options:
            try:
                msg_dict = self.parent.server_options.get("status_message", {})
                ver = varietyconfig.get_version()
                if ver in msg_dict:
                    msg = msg_dict[ver].strip()
                elif "*" in msg_dict:
                    msg = msg_dict["*"].strip()

                msg = self.fill_smart_profile_url(msg)
            except Exception:
                logger.exception(lambda: "Could not parse status message")
                msg = ""

        self.set_status_message(msg)

    @on_gtk
    def set_status_message(self, msg):
        self.ui.status_message.set_visible(msg)
        self.ui.status_message.set_markup(msg)

    def reload(self):
        try:
            logger.info(lambda: "Reloading preferences dialog")

            self.loading = True

            self.options = Options()
            self.options.read()

            self.ui.autostart.set_active(os.path.isfile(get_autostart_file_path()))

            self.ui.change_enabled.set_active(self.options.change_enabled)
            self.set_change_interval(self.options.change_interval)
            self.ui.change_on_start.set_active(self.options.change_on_start)
            self.ui.internet_enabled.set_active(self.options.internet_enabled)

            self.fav_chooser.set_folder(os.path.expanduser(self.options.favorites_folder))
            self.ui.wallpaper_auto_rotate.set_active(self.options.wallpaper_auto_rotate)
            self.ui.wallpaper_display_mode.remove_all()
            for mode in self.parent.get_display_modes():
                self.ui.wallpaper_display_mode.append(mode.id, mode.title)
            self.ui.wallpaper_display_mode.set_active_id(self.options.wallpaper_display_mode)

            self.fetched_chooser.set_folder(os.path.expanduser(self.options.fetched_folder))
            self.ui.clipboard_enabled.set_active(self.options.clipboard_enabled)
            self.ui.clipboard_use_whitelist.set_active(self.options.clipboard_use_whitelist)
            self.ui.clipboard_hosts.get_buffer().set_text("\n".join(self.options.clipboard_hosts))

            if self.options.icon == "Light":
                self.ui.icon.set_active(0)
            elif self.options.icon == "Dark":
                self.ui.icon.set_active(1)
            elif self.options.icon == "1":
                self.ui.icon.set_active(2)
            elif self.options.icon == "2":
                self.ui.icon.set_active(3)
            elif self.options.icon == "3":
                self.ui.icon.set_active(4)
            elif self.options.icon == "4":
                self.ui.icon.set_active(5)
            elif self.options.icon == "Current":
                self.ui.icon.set_active(6)
            elif self.options.icon == "None":
                self.ui.icon.set_active(8)
            else:
                self.ui.icon.set_active(7)
                self.ui.icon_chooser.set_filename(self.options.icon)

            if self.options.favorites_operations == [["/", "Copy"]]:
                self.ui.favorites_operations.set_active(0)
            elif self.options.favorites_operations == [["/", "Move"]]:
                self.ui.favorites_operations.set_active(1)
            elif self.options.favorites_operations == [["/", "Both"]]:
                self.ui.favorites_operations.set_active(2)
            else:
                self.ui.favorites_operations.set_active(3)

            self.favorites_operations = self.options.favorites_operations

            self.ui.copyto_enabled.set_active(self.options.copyto_enabled)
            self.copyto_chooser.set_folder(self.parent.get_actual_copyto_folder())

            self.ui.desired_color_enabled.set_active(self.options.desired_color_enabled)
            self.ui.desired_color.set_color(
                Gdk.Color(red=160 * 256, green=160 * 256, blue=160 * 256)
            )
            c = self.options.desired_color
            if c:
                self.ui.desired_color.set_color(
                    Gdk.Color(red=c[0] * 256, green=c[1] * 256, blue=c[2] * 256)
                )

            self.ui.min_size_enabled.set_active(self.options.min_size_enabled)
            min_sizes = [50, 80, 100]
            index = 0
            while min_sizes[index] < self.options.min_size and index < len(min_sizes) - 1:
                index += 1
            self.ui.min_size.set_active(index)
            self.ui.landscape_enabled.set_active(self.options.use_landscape_enabled)
            self.ui.lightness_enabled.set_active(self.options.lightness_enabled)
            self.ui.lightness.set_active(
                0 if self.options.lightness_mode == Options.LightnessMode.DARK else 1
            )
            self.ui.min_rating_enabled.set_active(self.options.min_rating_enabled)
            self.ui.min_rating.set_active(self.options.min_rating - 1)
            self.ui.name_regex_enabled.set_active(self.options.name_regex_enabled)
            self.ui.name_regex.set_text(self.options.name_regex)
            self.ui.clock_enabled.set_active(self.options.clock_enabled)
            self.ui.clock_font.set_font_name(self.options.clock_font)
            self.ui.clock_date_font.set_font_name(self.options.clock_date_font)

            self.ui.quotes_enabled.set_active(self.options.quotes_enabled)
            self.ui.quotes_font.set_font_name(self.options.quotes_font)
            c = self.options.quotes_text_color
            self.ui.quotes_text_color.set_color(
                Gdk.Color(red=c[0] * 256, green=c[1] * 256, blue=c[2] * 256)
            )
            c = self.options.quotes_bg_color
            self.ui.quotes_bg_color.set_color(
                Gdk.Color(red=c[0] * 256, green=c[1] * 256, blue=c[2] * 256)
            )
            self.ui.quotes_bg_opacity.set_value(self.options.quotes_bg_opacity)
            self.ui.quotes_text_shadow.set_active(self.options.quotes_text_shadow)
            self.ui.quotes_tags.set_text(self.options.quotes_tags)
            self.ui.quotes_authors.set_text(self.options.quotes_authors)
            self.ui.quotes_change_enabled.set_active(self.options.quotes_change_enabled)
            self.set_quotes_change_interval(self.options.quotes_change_interval)
            self.ui.quotes_width.set_value(self.options.quotes_width)
            self.ui.quotes_hpos.set_value(self.options.quotes_hpos)
            self.ui.quotes_vpos.set_value(self.options.quotes_vpos)

            self.ui.slideshow_sources_enabled.set_active(self.options.slideshow_sources_enabled)
            self.ui.slideshow_favorites_enabled.set_active(self.options.slideshow_favorites_enabled)
            self.ui.slideshow_downloads_enabled.set_active(self.options.slideshow_downloads_enabled)
            self.ui.slideshow_custom_enabled.set_active(self.options.slideshow_custom_enabled)
            self.slideshow_custom_chooser.set_folder(
                os.path.expanduser(self.options.slideshow_custom_folder)
            )

            if self.options.slideshow_sort_order == "Random":
                self.ui.slideshow_sort_order.set_active(0)
            elif self.options.slideshow_sort_order == "Name, asc":
                self.ui.slideshow_sort_order.set_active(1)
            elif self.options.slideshow_sort_order == "Name, desc":
                self.ui.slideshow_sort_order.set_active(2)
            elif self.options.slideshow_sort_order == "Date, asc":
                self.ui.slideshow_sort_order.set_active(3)
            elif self.options.slideshow_sort_order == "Date, desc":
                self.ui.slideshow_sort_order.set_active(4)
            else:
                self.ui.slideshow_sort_order.set_active(0)

            self.ui.slideshow_monitor.remove_all()
            self.ui.slideshow_monitor.append_text(_("All"))

            screen = Gdk.Screen.get_default()
            for i in range(0, screen.get_n_monitors()):
                geo = screen.get_monitor_geometry(i)
                self.ui.slideshow_monitor.append_text(
                    "%d - %s, %dx%d"
                    % (i + 1, screen.get_monitor_plug_name(i), geo.width, geo.height)
                )
            self.ui.slideshow_monitor.set_active(0)
            try:
                self.ui.slideshow_monitor.set_active(int(self.options.slideshow_monitor))
            except:
                self.ui.slideshow_monitor.set_active(0)

            if self.options.slideshow_mode == "Fullscreen":
                self.ui.slideshow_mode.set_active(0)
            elif self.options.slideshow_mode == "Desktop":
                self.ui.slideshow_mode.set_active(1)
            elif self.options.slideshow_mode == "Maximized":
                self.ui.slideshow_mode.set_active(2)
            elif self.options.slideshow_mode == "Window":
                self.ui.slideshow_mode.set_active(3)
            else:
                self.ui.slideshow_mode.set_active(0)

            self.ui.slideshow_seconds.set_value(self.options.slideshow_seconds)
            self.ui.slideshow_fade.set_value(self.options.slideshow_fade)
            self.ui.slideshow_zoom.set_value(self.options.slideshow_zoom)
            self.ui.slideshow_pan.set_value(self.options.slideshow_pan)

            self.unsupported_sources = []
            self.ui.sources.get_model().clear()
            for s in self.options.sources:
                if s[1] in Options.get_all_supported_source_types():
                    self.ui.sources.get_model().append(self.source_to_model_row(s))
                else:
                    self.unsupported_sources.append(s)

            if not hasattr(self, "enabled_toggled_handler_id"):
                self.enabled_toggled_handler_id = self.ui.sources_enabled_checkbox_renderer.connect(
                    "toggled", self.source_enabled_toggled, self.ui.sources.get_model()
                )
            # self.ui.sources.get_selection().connect("changed", self.on_sources_selection_changed)

            if hasattr(self, "filter_checkboxes"):
                for cb in self.filter_checkboxes:  # pylint: disable=access-member-before-definition
                    self.ui.filters_grid.remove(cb)
                    cb.destroy()
            self.filter_checkboxes = []
            self.filter_name_to_checkbox = {}
            for i, f in enumerate(self.options.filters):
                cb = Gtk.CheckButton(Texts.FILTERS.get(f[1], f[1]))
                self.filter_name_to_checkbox[f[1]] = cb
                cb.connect("toggled", self.delayed_apply)
                cb.set_visible(True)
                cb.set_active(f[0])
                cb.set_margin_right(20)
                self.ui.filters_grid.attach(cb, i % 4, i // 4, 1, 1)
                self.filter_checkboxes.append(cb)

            # pylint: disable=access-member-before-definition
            if hasattr(self, "quotes_sources_checkboxes"):
                for cb in self.quotes_sources_checkboxes:
                    self.ui.quotes_sources_grid.remove(cb)
                    cb.destroy()
            self.quotes_sources_checkboxes = []
            for i, p in enumerate(self.parent.jumble.get_plugins(IQuoteSource)):
                cb = Gtk.CheckButton(p["info"]["name"])
                cb.connect("toggled", self.delayed_apply)
                cb.set_visible(True)
                cb.set_tooltip_text(p["info"]["description"])
                cb.set_active(p["info"]["name"] not in self.options.quotes_disabled_sources)
                cb.set_margin_right(20)
                self.ui.quotes_sources_grid.attach(cb, i % 4, i // 4, 1, 1)
                self.quotes_sources_checkboxes.append(cb)

            # Smart Selection settings
            self.ui.smart_selection_enabled.set_active(self.options.smart_selection_enabled)
            self.ui.smart_image_cooldown.set_value(self.options.smart_image_cooldown_days)
            self.ui.smart_source_cooldown.set_value(self.options.smart_source_cooldown_days)
            self.ui.smart_favorite_boost.set_value(self.options.smart_favorite_boost)
            self.ui.smart_new_boost.set_value(self.options.smart_new_boost)

            decay_types = {"exponential": 0, "linear": 1, "step": 2}
            self.ui.smart_decay_type.set_active(
                decay_types.get(self.options.smart_decay_type, 0)
            )

            self.ui.smart_color_enabled.set_active(self.options.smart_color_enabled)

            color_temps = {"warm": 0, "neutral": 1, "cool": 2, "adaptive": 3}
            self.ui.smart_color_temperature.set_active(
                color_temps.get(self.options.smart_color_temperature, 3)
            )

            self.ui.smart_color_similarity.set_value(self.options.smart_color_similarity)
            self.ui.smart_time_adaptation.set_active(self.options.smart_time_adaptation)

            # Time adaptation settings
            if hasattr(self.options, 'smart_time_method'):
                time_methods = {"sunrise_sunset": 0, "fixed": 1, "system_theme": 2}
                self.ui.smart_time_method.set_active(
                    time_methods.get(self.options.smart_time_method, 1)  # default to "fixed"
                )
            if hasattr(self.options, 'smart_day_start') and hasattr(self.ui, 'smart_day_start'):
                self.ui.smart_day_start.set_text(self.options.smart_day_start or "07:00")
            if hasattr(self.options, 'smart_night_start') and hasattr(self.ui, 'smart_night_start'):
                self.ui.smart_night_start.set_text(self.options.smart_night_start or "19:00")
            if hasattr(self.options, 'smart_location_name') and hasattr(self.ui, 'smart_location_name'):
                self.ui.smart_location_name.set_text(self.options.smart_location_name or "")
            if hasattr(self.options, 'smart_location_lat') and self.options.smart_location_lat is not None:
                self._location_lat = self.options.smart_location_lat
            if hasattr(self.options, 'smart_location_lon') and self.options.smart_location_lon is not None:
                self._location_lon = self.options.smart_location_lon
            if hasattr(self.options, 'smart_day_preset') and hasattr(self.ui, 'smart_day_preset'):
                presets = {"bright_day": 0, "neutral_day": 1, "custom": 2}
                self.ui.smart_day_preset.set_active(
                    presets.get(self.options.smart_day_preset, 1)  # default to "neutral_day"
                )
            if hasattr(self.options, 'smart_night_preset') and hasattr(self.ui, 'smart_night_preset'):
                presets = {"cozy_night": 0, "cool_night": 1, "dark_mode": 2, "custom": 3}
                self.ui.smart_night_preset.set_active(
                    presets.get(self.options.smart_night_preset, 0)  # default to "cozy_night"
                )
            if hasattr(self.options, 'smart_day_lightness') and hasattr(self.ui, 'smart_day_lightness'):
                self.ui.smart_day_lightness.set_value(self.options.smart_day_lightness)
            if hasattr(self.options, 'smart_day_temperature') and hasattr(self.ui, 'smart_day_temperature'):
                self.ui.smart_day_temperature.set_value(self.options.smart_day_temperature)
            if hasattr(self.options, 'smart_day_saturation') and hasattr(self.ui, 'smart_day_saturation'):
                self.ui.smart_day_saturation.set_value(self.options.smart_day_saturation)
            if hasattr(self.options, 'smart_night_lightness') and hasattr(self.ui, 'smart_night_lightness'):
                self.ui.smart_night_lightness.set_value(self.options.smart_night_lightness)
            if hasattr(self.options, 'smart_night_temperature') and hasattr(self.ui, 'smart_night_temperature'):
                self.ui.smart_night_temperature.set_value(self.options.smart_night_temperature)
            if hasattr(self.options, 'smart_night_saturation') and hasattr(self.ui, 'smart_night_saturation'):
                self.ui.smart_night_saturation.set_value(self.options.smart_night_saturation)
            if hasattr(self.options, 'smart_palette_tolerance') and hasattr(self.ui, 'smart_palette_tolerance'):
                self.ui.smart_palette_tolerance.set_value(self.options.smart_palette_tolerance)

            # Theming Engine settings
            if hasattr(self.options, 'smart_theming_enabled'):
                self.ui.smart_theming_enabled.set_active(self.options.smart_theming_enabled)
            self.update_smart_theming_templates_label()

            # Update Smart Selection labels
            self.update_smart_image_cooldown_label()
            self.update_smart_source_cooldown_label()
            self.update_smart_favorite_boost_label()
            self.update_smart_new_boost_label()
            self.update_smart_color_similarity_label()

            # Update Smart Selection statistics
            self.update_smart_selection_stats()

            # Build Collection Insights section
            self._build_insights_section()

            # Setup Smart Selection tooltips and help buttons
            self._setup_smart_selection_tooltips()
            self._connect_help_buttons()

            # Setup Wallhaven Manager tab
            self._setup_wallhaven_tab()
            self._populate_wallhaven_list()

            self.ui.tips_buffer.set_text(
                "\n\n".join(
                    [
                        tip.replace("{PROFILE_PATH}", get_profile_path(expanded=False))
                        for tip in Texts.TIPS
                    ]
                )
            )

            try:
                with open(get_data_file("ui/changes.txt")) as f:
                    self.ui.changes_buffer.set_text(f.read())
            except Exception:
                logger.warning(lambda: "Missing ui/changes.txt file")

            self.on_change_enabled_toggled()
            self.on_sources_selection_changed()
            self.on_desired_color_enabled_toggled()
            self.on_min_size_enabled_toggled()
            self.on_lightness_enabled_toggled()
            self.on_min_rating_enabled_toggled()
            self.on_name_regex_enabled_toggled()
            self.on_copyto_enabled_toggled()
            self.on_quotes_change_enabled_toggled()
            self.on_icon_changed()
            self.on_favorites_operations_changed()
            self.on_wallpaper_display_mode_changed()
            self.update_clipboard_state()
            self.update_status_message()
            self.on_smart_selection_enabled_toggled()
            self.on_smart_color_enabled_toggled()
            self.on_smart_color_temperature_changed()
            # Initialize time adaptation controls visibility
            self.on_smart_time_adaptation_toggled()
            self.on_smart_time_method_changed()
            self.on_smart_day_preset_changed()
            self.on_smart_night_preset_changed()
            self._hide_unimplemented_controls()
        finally:
            # To be sure we are completely loaded, pass via two hops: first delay, then idle_add:
            def _finish_loading():
                self.loading = False

            def _idle_finish_loading():
                Util.add_mainloop_task(_finish_loading)

            timer = threading.Timer(1, _idle_finish_loading)
            timer.start()

    def on_add_button_clicked(self, widget=None):
        def position(*args, **kwargs):
            button_alloc = self.ui.add_button.get_allocation()
            window_pos = self.ui.add_button.get_window().get_position()
            return (
                button_alloc.x + window_pos[0],
                button_alloc.y + button_alloc.height + window_pos[1],
                True,
            )

        add_menu = self.build_add_button_menu()
        add_menu.popup(None, self.ui.add_button, position, None, 0, Gtk.get_current_event_time())

    def on_remove_sources_clicked(self, widget=None):
        def position(*args, **kwargs):
            button_alloc = self.ui.remove_sources.get_allocation()
            window_pos = self.ui.remove_sources.get_window().get_position()
            return (
                button_alloc.x + window_pos[0],
                button_alloc.y + button_alloc.height + window_pos[1],
                True,
            )

        self.build_remove_button_menu().popup(
            None, self.ui.remove_sources, position, None, 0, Gtk.get_current_event_time()
        )

    def build_add_button_menu(self):
        add_menu = Gtk.Menu()

        items = [
            (False, _("Images"), _("Add individual wallpaper images"), self.on_add_images_clicked),
            (
                False,
                _("Folders"),
                _("Searched recursively for up to 10000 images, shown in random order"),
                lambda widget: self.on_add_folders_clicked(
                    widget, source_type=Options.SourceType.FOLDER
                ),
            ),
            (
                False,
                _("Sequential Albums (order by filename)"),
                _("Searched recursively for images, shown in sequence (by filename)"),
                lambda widget: self.on_add_folders_clicked(
                    widget, source_type=Options.SourceType.ALBUM_FILENAME
                ),
            ),
            (
                False,
                _("Sequential Albums (order by date)"),
                _("Searched recursively for images, shown in sequence (by file date)"),
                lambda widget: self.on_add_folders_clicked(
                    widget, source_type=Options.SourceType.ALBUM_DATE
                ),
            ),
            "-",
        ]

        configurable_items = [
            (True, _("Flickr"), _("Fetch images from Flickr"), self.on_add_flickr_clicked)
        ]
        for source in self.options.CONFIGURABLE_IMAGE_SOURCES:

            def _click(widget, source=source):
                self.on_add_configurable(source)

            configurable_items.append(
                (
                    source.needs_internet(),
                    source.get_source_name(),
                    source.get_ui_short_description(),
                    _click,
                )
            )
        configurable_items.sort(key=lambda x: x[1])
        items.extend(configurable_items)

        for x in items:
            if x == "-":
                item = Gtk.SeparatorMenuItem.new()
                item.set_margin_top(15)
                item.set_margin_bottom(15)
            else:
                item = Gtk.MenuItem()
                label = Gtk.Label("<b>{}</b>\n{}".format(x[1], x[2]))
                label.set_margin_top(6)
                label.set_margin_bottom(6)
                label.set_xalign(0)
                label.set_use_markup(True)
                item.add(label)
                if x[0] and not self.ui.internet_enabled.get_active():
                    # disable adding internet-requiring sources when internet is disabled
                    item.set_sensitive(False)
                else:
                    item.connect("activate", x[3])
            add_menu.append(item)

        add_menu.show_all()
        return add_menu

    def build_remove_button_menu(self):
        model, rows = self.ui.sources.get_selection().get_selected_rows()

        has_downloaders = False
        for row in rows:
            type = model[row][1]
            if type in Options.get_editable_source_types():
                has_downloaders = True

        self.remove_menu = Gtk.Menu()
        item1 = Gtk.MenuItem()
        item1.set_label(
            _("Remove the source, keep the files")
            if len(rows) == 1
            else _("Remove the sources, keep the files")
        )
        item1.connect("activate", self.remove_sources)
        self.remove_menu.append(item1)

        item2 = Gtk.MenuItem()

        def _remove_with_files(widget=None):
            self.remove_sources(delete_files=True)

        item2.set_label(
            _("Remove the source and delete the downloaded files")
            if len(rows) == 1
            else _("Remove the sources and delete the downloaded files")
        )
        item2.connect("activate", _remove_with_files)
        item2.set_sensitive(has_downloaders)
        self.remove_menu.append(item2)

        self.remove_menu.show_all()
        return self.remove_menu

    def source_enabled_toggled(self, widget, path, model):
        row = model[path]
        row[0] = not row[0]
        self.on_row_enabled_state_changed(row)

    def on_row_enabled_state_changed(self, row):
        # Special case when enabling refresher downloaders:
        refresher_dls = [
            dl
            for dl in Options.SIMPLE_DOWNLOADERS  # TODO: this will break if we have non-simple refresher downloaders
            if dl.get_source_type() == row[1] and dl.is_refresher()
        ]
        if row[0] and len(refresher_dls) > 0:
            refresh_time = refresher_dls[0].get_refresh_interval_seconds()
            updated = False
            if not self.ui.change_enabled.get_active():
                self.ui.change_enabled.set_active(True)
                updated = True
            if self.get_change_interval() > refresh_time:
                self.set_change_interval(refresh_time)
                updated = True

            if updated:
                self.parent.show_notification(
                    refresher_dls[0].get_description(),
                    _(
                        "Using this source requires wallpaper changing "
                        "enabled at intervals of %d minutes or less. "
                        "Settings were adjusted automatically."
                    )
                    % int(refresh_time / 60),
                )

    def set_time(self, interval, text, time_unit, times=(1, 60, 60 * 60, 24 * 60 * 60)):
        if interval < 5:
            interval = 5
        x = len(times) - 1
        while times[x] > interval:
            x -= 1
        text.set_text(str(interval // times[x]))
        time_unit.set_active(x)
        return

    def set_change_interval(self, seconds):
        self.set_time(seconds, self.ui.change_interval_text, self.ui.change_interval_time_unit)

    def set_quotes_change_interval(self, seconds):
        self.set_time(
            seconds, self.ui.quotes_change_interval_text, self.ui.quotes_change_interval_time_unit
        )

    def read_time(self, text_entry, time_unit_combo, minimum, default):
        result = default
        try:
            interval = int(text_entry.get_text())
            tree_iter = time_unit_combo.get_active_iter()
            if tree_iter:
                model = time_unit_combo.get_model()
                time_unit_seconds = model[tree_iter][1]
                result = interval * time_unit_seconds
                if result < minimum:
                    result = minimum
        except Exception:
            logger.exception(lambda: "Could not understand interval")
        return result

    def get_change_interval(self):
        return self.read_time(
            self.ui.change_interval_text,
            self.ui.change_interval_time_unit,
            5,
            self.options.change_interval,
        )

    def get_quotes_change_interval(self):
        return self.read_time(
            self.ui.quotes_change_interval_text,
            self.ui.quotes_change_interval_time_unit,
            10,
            self.options.quotes_change_interval,
        )

    @staticmethod
    def add_image_preview(chooser, size=250):
        preview = Gtk.Image()
        chooser.set_preview_widget(preview)

        def update_preview(c):
            try:
                file = chooser.get_preview_filename()
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(file, size, size)
                preview.set_from_pixbuf(pixbuf)
                chooser.set_preview_widget_active(True)
            except Exception:
                chooser.set_preview_widget_active(False)

        chooser.connect("update-preview", update_preview)

    def on_add_images_clicked(self, widget=None):
        chooser = Gtk.FileChooserDialog(
            _("Add Images"),
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=[_("Cancel"), Gtk.ResponseType.CANCEL, _("Add"), Gtk.ResponseType.OK],
        )
        self.dialog = chooser
        PreferencesVarietyDialog.add_image_preview(chooser)
        chooser.set_select_multiple(True)
        chooser.set_local_only(True)
        filter = Gtk.FileFilter()
        filter.set_name(_("Images"))
        for s in ["jpg", "jpeg", "png", "bmp", "tiff", "svg"]:
            filter.add_pattern("*." + s)
            filter.add_pattern("*." + s.upper())
        chooser.add_filter(filter)
        response = chooser.run()

        if response == Gtk.ResponseType.OK:
            images = list(chooser.get_filenames())
            images = [f for f in images if Util.is_image(f) and os.path.isfile(f)]
            self.add_sources(Options.SourceType.IMAGE, images)

        self.dialog = None
        chooser.destroy()

    def on_add_folders_clicked(self, widget=None, source_type=Options.SourceType.FOLDER):
        if source_type == Options.SourceType.FOLDER:
            title = _(
                "Add Folders - Only add the root folders, subfolders are searched recursively"
            )
        elif source_type == Options.SourceType.ALBUM_FILENAME:
            title = _(
                "Add Sequential Albums (ordered by filename). Subfolders are searched recursively."
            )
        elif source_type == Options.SourceType.ALBUM_DATE:
            title = _(
                "Add Sequential Albums (ordered by date). Subfolders are searched recursively."
            )
        else:
            raise Exception("Unsuppoted source_type {}".format(source_type))
        chooser = Gtk.FileChooserDialog(
            title,
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=[_("Cancel"), Gtk.ResponseType.CANCEL, _("Add"), Gtk.ResponseType.OK],
        )
        self.dialog = chooser
        chooser.set_select_multiple(True)
        chooser.set_local_only(True)
        response = chooser.run()

        if response == Gtk.ResponseType.OK:
            folders = list(chooser.get_filenames())
            folders = [f for f in folders if os.path.isdir(f)]
            self.add_sources(source_type, folders)

        self.dialog = None
        chooser.destroy()

    def add_sources(self, type, locations):
        self.ui.sources.get_selection().unselect_all()
        existing = {}
        for i, r in enumerate(self.ui.sources.get_model()):
            if r[1] == type:
                if type in (
                    Options.SourceType.FOLDER,
                    Options.SourceType.ALBUM_FILENAME,
                    Options.SourceType.ALBUM_DATE,
                ):
                    existing[os.path.normpath(r[2])] = r, i
                else:
                    existing[self.model_row_to_source(r)[2]] = r, i

        newly_added = 0
        for f in locations:
            if type in Options.SourceType.LOCAL_PATH_TYPES:
                f = os.path.normpath(f)
            elif type not in Options.get_editable_source_types():
                f = (
                    list(existing.keys())[0] if existing else None
                )  # reuse the already existing location, do not add another one

            if not f in existing:
                self.ui.sources.get_model().append(self.source_to_model_row([True, type, f]))
                self.ui.sources.get_selection().select_path(len(self.ui.sources.get_model()) - 1)
                self.ui.sources.scroll_to_cell(
                    len(self.ui.sources.get_model()) - 1, None, False, 0, 0
                )
                newly_added += 1
            else:
                logger.info(lambda: "Source already exists, activating it: " + f)
                existing[f][0][0] = True
                self.ui.sources.get_selection().select_path(existing[f][1])
                self.ui.sources.scroll_to_cell(existing[f][1], None, False, 0, 0)

        return newly_added

    def focus_source_and_image(self, source, image):
        self.ui.notebook.set_current_page(0)
        self.ui.sources.get_selection().unselect_all()
        for i, r in enumerate(self.ui.sources.get_model()):
            if self.model_row_to_source(r)[1:] == source[1:]:
                self.focused_image = image
                self.ui.sources.get_selection().select_path(i)
                self.ui.sources.scroll_to_cell(i, None, False, 0, 0)
                return

    def remove_sources(self, widget=None, delete_files=False):
        model, rows = self.ui.sources.get_selection().get_selected_rows()

        if delete_files:
            for row in rows:
                type = model[row][1]
                if type in Options.get_editable_source_types():
                    source = self.model_row_to_source(model[row])
                    self.parent.delete_files_of_source(source)

        # store the treeiters from paths
        iters = []
        for row in rows:
            if model[row][1] in Options.get_removable_source_types():
                iters.append(model.get_iter(row))
        # remove the rows (treeiters)
        for i in iters:
            if i is not None:
                model.remove(i)

    def on_source_doubleclicked(self, tree_view, row_index, arg4=None):
        self.edit_source(self.ui.sources.get_model()[row_index])

    def on_edit_source_clicked(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()
        if len(rows) == 1:
            self.edit_source(model[rows[0]])

    def on_open_folder_clicked(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()
        if len(rows) != 1:
            return
        row = model[rows[0]]
        type = row[1]
        if type in Options.SourceType.LOCAL_PATH_TYPES:
            subprocess.Popen(["xdg-open", os.path.realpath(row[2])])
        elif type == Options.SourceType.FAVORITES:
            subprocess.Popen(["xdg-open", self.parent.options.favorites_folder])
        elif type == Options.SourceType.FETCHED:
            subprocess.Popen(["xdg-open", self.parent.options.fetched_folder])
        else:
            subprocess.Popen(
                ["xdg-open", self.parent.get_folder_of_source(self.model_row_to_source(row))]
            )

    def on_use_clicked(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()
        for row in model:
            row[0] = False
        for path in rows:
            model[path][0] = True
        for row in model:
            # TODO we trigger for all rows, though some of them don't actually change state - but no problem for now
            self.on_row_enabled_state_changed(row)
        self.on_sources_selection_changed()

    def edit_source(self, edited_row):
        type = edited_row[1]

        if type in Options.get_editable_source_types():
            if type == Options.SourceType.FLICKR:
                self.dialog = AddFlickrDialog()
            elif type in Options.CONFIGURABLE_IMAGE_SOURCES_MAP:
                if type == Options.SourceType.WALLHAVEN:
                    self.dialog = AddWallhavenDialog(self.parent)
                else:
                    self.dialog = AddConfigurableDialog()
                self.dialog.set_source(Options.CONFIGURABLE_IMAGE_SOURCES_MAP[type])

            self.dialog.set_edited_row(edited_row)
            self.show_dialog(self.dialog)

    def on_internet_enabled_toggled(self, *args):
        self.delayed_apply()
        self.previous_selection = None
        self.on_sources_selection_changed()

    def on_sources_selection_changed(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()

        enabled = set(i for i, row in enumerate(model) if row[0])
        selected = set(row.get_indices()[0] for row in rows)
        self.ui.use_button.set_sensitive(selected and enabled != selected)

        # pylint: disable=access-member-before-definition
        if hasattr(self, "previous_selection") and rows == self.previous_selection:
            return

        self.previous_selection = rows

        self.ui.edit_source.set_sensitive(False)
        self.ui.edit_source.set_label(_("Edit..."))
        self.ui.open_folder.set_sensitive(len(rows) == 1)
        self.ui.open_folder.set_label(_("Open Folder"))

        if len(rows) == 1:
            source = model[rows[0]]
            type = source[1]
            if type == Options.SourceType.IMAGE:
                self.ui.open_folder.set_label(_("View Image"))
            elif type in Options.get_editable_source_types():
                self.ui.edit_source.set_sensitive(self.ui.internet_enabled.get_active())

        def timer_func():
            self.show_thumbs(list(model[row] for row in rows))

        # pylint: disable=access-member-before-definition
        if hasattr(self, "show_timer") and self.show_timer:
            self.show_timer.cancel()
        self.show_timer = threading.Timer(0.3, timer_func)
        self.show_timer.start()

        for row in rows:
            if model[row][1] not in Options.get_removable_source_types():
                self.ui.remove_sources.set_sensitive(False)
                return

        self.ui.remove_sources.set_sensitive(len(rows) > 0)

    def model_row_to_source(self, row):
        return [row[0], row[1], Texts.SOURCES[row[1]][0] if row[1] in Texts.SOURCES else row[2]]

    def source_to_model_row(self, s):
        srctype = s[1]
        return [s[0], srctype, s[2] if not srctype in Texts.SOURCES else Texts.SOURCES[srctype][1]]

    def show_thumbs(self, source_rows, pin=False, thumbs_type=None):
        try:
            if not source_rows:
                return

            self.parent.thumbs_manager.hide(force=True)

            images = []
            folders = []

            for row in source_rows:
                if not row:
                    continue

                type = row[1]
                if type == Options.SourceType.IMAGE:
                    images.append(row[2])
                else:
                    folder = self.parent.get_folder_of_source(self.model_row_to_source(row))
                    folders.append(folder)

            folder_images = list(
                Util.list_files(folders=folders, filter_func=Util.is_image, max_files=10000)
            )
            if len(source_rows) == 1 and source_rows[0][1] == Options.SourceType.ALBUM_FILENAME:
                folder_images = sorted(folder_images)
            elif len(source_rows) == 1 and source_rows[0][1] == Options.SourceType.ALBUM_DATE:
                folder_images = sorted(folder_images, key=os.path.getmtime)
            else:
                random.shuffle(folder_images)
            to_show = images + folder_images
            if hasattr(self, "focused_image") and self.focused_image is not None:
                try:
                    to_show.remove(self.focused_image)
                except Exception:
                    pass
                to_show.insert(0, self.focused_image)
                self.focused_image = None
            self.parent.thumbs_manager.show(
                to_show, screen=self.get_screen(), folders=folders, type=thumbs_type
            )
            if pin:
                self.parent.thumbs_manager.pin()
            if thumbs_type:
                self.parent.update_indicator(auto_changed=False)

        except Exception:
            logger.exception(lambda: "Could not create thumbs window:")

    def on_add_flickr_clicked(self, widget=None):
        self.show_dialog(AddFlickrDialog())

    def on_add_configurable(self, source):
        if source.get_source_type() == Options.SourceType.WALLHAVEN:
            dialog = AddWallhavenDialog(self.parent)
        else:
            dialog = AddConfigurableDialog()
        dialog.set_source(source)
        self.show_dialog(dialog)

    def on_wallpaper_display_mode_changed(self, *args):
        modes = [
            m
            for m in self.parent.get_display_modes()
            if m.id == self.ui.wallpaper_display_mode.get_active_id()
        ]
        if modes:
            self.ui.wallpaper_mode_description.set_text(modes[0].description)
        else:
            self.ui.wallpaper_mode_description.set_text("")

    def show_dialog(self, dialog):
        self.dialog = dialog
        self.dialog.parent = self
        self.dialog.set_transient_for(self)
        response = self.dialog.run()
        if response != Gtk.ResponseType.OK:
            if self.dialog:
                self.dialog.destroy()
            self.dialog = None

    def on_add_dialog_okay(self, source_type, location, edited_row):
        if edited_row:
            edited_row[2] = location
        else:
            self.add_sources(source_type, [location])
        self.dialog = None

    def close(self):
        self.ui.error_favorites.set_label("")
        self.ui.error_fetched.set_label("")

        self.hide()
        self.parent.trigger_download()
        self.on_destroy()

    def on_save_clicked(self, widget):
        self.delayed_apply()
        self.close()

    def delayed_apply(self, widget=None, *arg):
        if not self.loading:
            self.delayed_apply_with_interval(0.1)

    def delayed_apply_slow(self, widget=None, *arg):
        if not self.loading:
            self.delayed_apply_with_interval(1)

    def delayed_apply_with_interval(self, interval):
        # pylint: disable=access-member-before-definition
        if not self.loading:
            if hasattr(self, "apply_timer") and self.apply_timer:
                self.apply_timer.cancel()
                self.apply_timer = None

            self.apply_timer = threading.Timer(interval, self.apply)
            self.apply_timer.start()

    def apply(self):
        try:
            logger.info(lambda: "Applying preferences")

            self.options = Options()
            self.options.read()

            self.options.change_enabled = self.ui.change_enabled.get_active()
            self.options.change_on_start = self.ui.change_on_start.get_active()
            self.options.change_interval = self.get_change_interval()
            self.options.internet_enabled = self.ui.internet_enabled.get_active()

            if os.access(self.fav_chooser.get_folder(), os.W_OK):
                self.options.favorites_folder = self.fav_chooser.get_folder()
            self.options.favorites_operations = self.favorites_operations

            self.options.sources = []
            for r in self.ui.sources.get_model():
                self.options.sources.append(self.model_row_to_source(r))
            for s in self.unsupported_sources:
                self.options.sources.append(s)

            self.options.wallpaper_auto_rotate = self.ui.wallpaper_auto_rotate.get_active()
            self.options.wallpaper_display_mode = self.ui.wallpaper_display_mode.get_active_id()

            if os.access(self.fetched_chooser.get_folder(), os.W_OK):
                self.options.fetched_folder = self.fetched_chooser.get_folder()
            self.options.clipboard_enabled = self.ui.clipboard_enabled.get_active()
            self.options.clipboard_use_whitelist = self.ui.clipboard_use_whitelist.get_active()
            buf = self.ui.clipboard_hosts.get_buffer()
            self.options.clipboard_hosts = Util.split(
                buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            )

            if self.ui.icon.get_active() == 0:
                self.options.icon = "Light"
            elif self.ui.icon.get_active() == 1:
                self.options.icon = "Dark"
            elif self.ui.icon.get_active() == 2:
                self.options.icon = "1"
            elif self.ui.icon.get_active() == 3:
                self.options.icon = "2"
            elif self.ui.icon.get_active() == 4:
                self.options.icon = "3"
            elif self.ui.icon.get_active() == 5:
                self.options.icon = "4"
            elif self.ui.icon.get_active() == 6:
                self.options.icon = "Current"
            elif self.ui.icon.get_active() == 8:
                self.options.icon = "None"
            elif self.ui.icon.get_active() == 7:
                file = self.ui.icon_chooser.get_filename()
                if file and os.access(file, os.R_OK):
                    self.options.icon = file
                else:
                    self.options.icon = "Light"

            if self.ui.favorites_operations.get_active() == 0:
                self.options.favorites_operations = [["/", "Copy"]]
            elif self.ui.favorites_operations.get_active() == 1:
                self.options.favorites_operations = [["/", "Move"]]
            elif self.ui.favorites_operations.get_active() == 2:
                self.options.favorites_operations = [["/", "Both"]]
            elif self.ui.favorites_operations.get_active() == 3:
                # will be set in the favops editor dialog
                pass

            self.options.copyto_enabled = self.ui.copyto_enabled.get_active()
            copyto = os.path.normpath(self.copyto_chooser.get_folder())
            if copyto == os.path.normpath(self.parent.get_actual_copyto_folder("Default")):
                self.options.copyto_folder = "Default"
            else:
                self.options.copyto_folder = copyto

            self.options.desired_color_enabled = self.ui.desired_color_enabled.get_active()
            c = self.ui.desired_color.get_color()
            self.options.desired_color = (c.red // 256, c.green // 256, c.blue // 256)

            self.options.min_size_enabled = self.ui.min_size_enabled.get_active()
            try:
                self.options.min_size = int(self.ui.min_size.get_active_text())
            except Exception:
                pass

            self.options.use_landscape_enabled = self.ui.landscape_enabled.get_active()

            self.options.lightness_enabled = self.ui.lightness_enabled.get_active()
            self.options.lightness_mode = (
                Options.LightnessMode.DARK
                if self.ui.lightness.get_active() == 0
                else Options.LightnessMode.LIGHT
            )

            self.options.min_rating_enabled = self.ui.min_rating_enabled.get_active()
            try:
                self.options.min_rating = int(self.ui.min_rating.get_active_text())
            except Exception:
                pass

            self.options.name_regex_enabled = self.ui.name_regex_enabled.get_active()
            try:
                self.options.name_regex = self.ui.name_regex.get_text()
            except Exception:
                pass

            self.options.clock_enabled = self.ui.clock_enabled.get_active()
            self.options.clock_font = self.ui.clock_font.get_font_name()
            self.options.clock_date_font = self.ui.clock_date_font.get_font_name()

            self.options.quotes_enabled = self.ui.quotes_enabled.get_active()
            self.options.quotes_font = self.ui.quotes_font.get_font_name()
            c = self.ui.quotes_text_color.get_color()
            self.options.quotes_text_color = (c.red // 256, c.green // 256, c.blue // 256)
            c = self.ui.quotes_bg_color.get_color()
            self.options.quotes_bg_color = (c.red // 256, c.green // 256, c.blue // 256)
            self.options.quotes_bg_opacity = max(
                0, min(100, int(self.ui.quotes_bg_opacity.get_value()))
            )
            self.options.quotes_text_shadow = self.ui.quotes_text_shadow.get_active()
            self.options.quotes_tags = self.ui.quotes_tags.get_text()
            self.options.quotes_authors = self.ui.quotes_authors.get_text()
            self.options.quotes_change_enabled = self.ui.quotes_change_enabled.get_active()
            self.options.quotes_change_interval = self.get_quotes_change_interval()
            self.options.quotes_width = max(0, min(100, int(self.ui.quotes_width.get_value())))
            self.options.quotes_hpos = max(0, min(100, int(self.ui.quotes_hpos.get_value())))
            self.options.quotes_vpos = max(0, min(100, int(self.ui.quotes_vpos.get_value())))

            self.options.quotes_disabled_sources = [
                cb.get_label() for cb in self.quotes_sources_checkboxes if not cb.get_active()
            ]

            for f in self.options.filters:
                f[0] = self.filter_name_to_checkbox[f[1]].get_active()

            self.options.slideshow_sources_enabled = self.ui.slideshow_sources_enabled.get_active()
            self.options.slideshow_favorites_enabled = (
                self.ui.slideshow_favorites_enabled.get_active()
            )
            self.options.slideshow_downloads_enabled = (
                self.ui.slideshow_downloads_enabled.get_active()
            )
            self.options.slideshow_custom_enabled = self.ui.slideshow_custom_enabled.get_active()
            if os.access(self.slideshow_custom_chooser.get_folder(), os.R_OK):
                self.options.slideshow_custom_folder = self.slideshow_custom_chooser.get_folder()

            if self.ui.slideshow_sort_order.get_active() == 0:
                self.options.slideshow_sort_order = "Random"
            elif self.ui.slideshow_sort_order.get_active() == 1:
                self.options.slideshow_sort_order = "Name, asc"
            elif self.ui.slideshow_sort_order.get_active() == 2:
                self.options.slideshow_sort_order = "Name, desc"
            elif self.ui.slideshow_sort_order.get_active() == 3:
                self.options.slideshow_sort_order = "Date, asc"
            elif self.ui.slideshow_sort_order.get_active() == 4:
                self.options.slideshow_sort_order = "Date, desc"

            if self.ui.slideshow_monitor.get_active() == 0:
                self.options.slideshow_monitor = "All"
            else:
                self.options.slideshow_monitor = self.ui.slideshow_monitor.get_active()

            if self.ui.slideshow_mode.get_active() == 0:
                self.options.slideshow_mode = "Fullscreen"
            elif self.ui.slideshow_mode.get_active() == 1:
                self.options.slideshow_mode = "Desktop"
            elif self.ui.slideshow_mode.get_active() == 2:
                self.options.slideshow_mode = "Maximized"
            elif self.ui.slideshow_mode.get_active() == 3:
                self.options.slideshow_mode = "Window"

            self.options.slideshow_seconds = max(0.5, float(self.ui.slideshow_seconds.get_value()))
            self.options.slideshow_fade = max(0, min(1, float(self.ui.slideshow_fade.get_value())))
            self.options.slideshow_zoom = max(0, min(1, float(self.ui.slideshow_zoom.get_value())))
            self.options.slideshow_pan = max(0, min(0.2, float(self.ui.slideshow_pan.get_value())))

            # Smart Selection settings
            self.options.smart_selection_enabled = self.ui.smart_selection_enabled.get_active()
            self.options.smart_image_cooldown_days = max(
                0, min(30, float(self.ui.smart_image_cooldown.get_value()))
            )
            self.options.smart_source_cooldown_days = max(
                0, min(7, float(self.ui.smart_source_cooldown.get_value()))
            )
            self.options.smart_favorite_boost = max(
                1.0, min(5.0, float(self.ui.smart_favorite_boost.get_value()))
            )
            self.options.smart_new_boost = max(
                1.0, min(3.0, float(self.ui.smart_new_boost.get_value()))
            )

            decay_types = ["exponential", "linear", "step"]
            decay_idx = self.ui.smart_decay_type.get_active()
            if 0 <= decay_idx < len(decay_types):
                self.options.smart_decay_type = decay_types[decay_idx]

            self.options.smart_color_enabled = self.ui.smart_color_enabled.get_active()

            color_temps = ["warm", "neutral", "cool", "adaptive"]
            temp_idx = self.ui.smart_color_temperature.get_active()
            if 0 <= temp_idx < len(color_temps):
                self.options.smart_color_temperature = color_temps[temp_idx]

            self.options.smart_color_similarity = max(
                0, min(100, int(self.ui.smart_color_similarity.get_value()))
            )
            self.options.smart_time_adaptation = self.ui.smart_time_adaptation.get_active()

            # Time adaptation settings
            if hasattr(self.ui, 'smart_time_method'):
                time_methods = ["sunrise_sunset", "fixed", "system_theme"]
                method_idx = self.ui.smart_time_method.get_active()
                if 0 <= method_idx < len(time_methods):
                    self.options.smart_time_method = time_methods[method_idx]

            if hasattr(self.ui, 'smart_day_start'):
                self.options.smart_day_start = self.ui.smart_day_start.get_text().strip() or "07:00"
            if hasattr(self.ui, 'smart_night_start'):
                self.options.smart_night_start = self.ui.smart_night_start.get_text().strip() or "19:00"
            if hasattr(self.ui, 'smart_location_name'):
                self.options.smart_location_name = self.ui.smart_location_name.get_text().strip()
            if hasattr(self, '_location_lat'):
                self.options.smart_location_lat = self._location_lat
            if hasattr(self, '_location_lon'):
                self.options.smart_location_lon = self._location_lon

            if hasattr(self.ui, 'smart_day_preset'):
                presets = ["bright_day", "neutral_day", "custom"]
                preset_idx = self.ui.smart_day_preset.get_active()
                if 0 <= preset_idx < len(presets):
                    self.options.smart_day_preset = presets[preset_idx]
            if hasattr(self.ui, 'smart_night_preset'):
                presets = ["cozy_night", "cool_night", "dark_mode", "custom"]
                preset_idx = self.ui.smart_night_preset.get_active()
                if 0 <= preset_idx < len(presets):
                    self.options.smart_night_preset = presets[preset_idx]

            if hasattr(self.ui, 'smart_day_lightness'):
                self.options.smart_day_lightness = max(0.0, min(1.0, self.ui.smart_day_lightness.get_value()))
            if hasattr(self.ui, 'smart_day_temperature'):
                self.options.smart_day_temperature = max(-1.0, min(1.0, self.ui.smart_day_temperature.get_value()))
            if hasattr(self.ui, 'smart_day_saturation'):
                self.options.smart_day_saturation = max(0.0, min(1.0, self.ui.smart_day_saturation.get_value()))
            if hasattr(self.ui, 'smart_night_lightness'):
                self.options.smart_night_lightness = max(0.0, min(1.0, self.ui.smart_night_lightness.get_value()))
            if hasattr(self.ui, 'smart_night_temperature'):
                self.options.smart_night_temperature = max(-1.0, min(1.0, self.ui.smart_night_temperature.get_value()))
            if hasattr(self.ui, 'smart_night_saturation'):
                self.options.smart_night_saturation = max(0.0, min(1.0, self.ui.smart_night_saturation.get_value()))
            if hasattr(self.ui, 'smart_palette_tolerance'):
                self.options.smart_palette_tolerance = max(0.1, min(0.5, self.ui.smart_palette_tolerance.get_value()))

            # Theming Engine settings
            if hasattr(self.ui, 'smart_theming_enabled'):
                self.options.smart_theming_enabled = self.ui.smart_theming_enabled.get_active()

            self.options.write()

            if not self.parent.running:
                return

            self.parent.reload_config()

            self.update_autostart()
        except Exception:
            if self.parent.running:
                logger.exception(lambda: "Error while applying preferences")
                dialog = Gtk.MessageDialog(
                    self,
                    Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.ERROR,
                    Gtk.ButtonsType.OK,
                    "An error occurred while saving preferences.\n"
                    "Please run from a terminal with the -v flag and try again.",
                )
                dialog.set_title("Oops")
                dialog.run()
                dialog.destroy()

    def update_autostart(self):
        file = get_autostart_file_path()

        if not self.ui.autostart.get_active():
            if os.path.exists(file):
                logger.info(lambda: "Removing autostart entry")
                Util.safe_unlink(file)
        else:
            if not os.path.exists(file):
                self.parent.create_autostart_entry()

    def on_change_enabled_toggled(self, widget=None):
        self.ui.change_interval_text.set_sensitive(self.ui.change_enabled.get_active())
        self.ui.change_interval_time_unit.set_sensitive(self.ui.change_enabled.get_active())

    def on_quotes_change_enabled_toggled(self, widget=None):
        self.ui.quotes_change_interval_text.set_sensitive(
            self.ui.quotes_change_enabled.get_active()
        )
        self.ui.quotes_change_interval_time_unit.set_sensitive(
            self.ui.quotes_change_enabled.get_active()
        )

    def on_desired_color_enabled_toggled(self, widget=None):
        self.ui.desired_color.set_sensitive(self.ui.desired_color_enabled.get_active())

    def on_min_size_enabled_toggled(self, widget=None):
        self.ui.min_size.set_sensitive(self.ui.min_size_enabled.get_active())
        self.ui.min_size_label.set_sensitive(self.ui.min_size_enabled.get_active())

    def on_min_rating_enabled_toggled(self, widget=None):
        self.ui.min_rating.set_sensitive(self.ui.min_rating_enabled.get_active())

    def on_name_regex_enabled_toggled(self, widget=None):
        self.ui.name_regex.set_sensitive(self.ui.name_regex_enabled.get_active())

    def on_lightness_enabled_toggled(self, widget=None):
        self.ui.lightness.set_sensitive(self.ui.lightness_enabled.get_active())

    def on_destroy(self, widget=None):
        # Cancel all timers to prevent memory leak and callbacks on destroyed widgets
        if hasattr(self, '_preview_refresh_timer') and self._preview_refresh_timer:
            self._preview_refresh_timer.cancel()
            self._preview_refresh_timer = None

        if hasattr(self, 'show_timer') and self.show_timer:
            self.show_timer.cancel()
            self.show_timer = None

        if hasattr(self, 'apply_timer') and self.apply_timer:
            self.apply_timer.cancel()
            self.apply_timer = None

        if hasattr(self, "dialog") and self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass
        for chooser in (self.fav_chooser, self.fetched_chooser):
            try:
                chooser.destroy()
            except Exception:
                pass
        self.parent.thumbs_manager.hide(force=False)

    def on_favorites_changed(self, widget=None):
        self.delayed_apply()
        if not os.access(self.fav_chooser.get_folder(), os.W_OK):
            self.ui.error_favorites.set_label(_("No write permissions"))
        else:
            self.ui.error_favorites.set_label("")

    def on_fetched_changed(self, widget=None):
        self.delayed_apply()
        if not os.access(self.fetched_chooser.get_folder(), os.W_OK):
            self.ui.error_fetched.set_label(_("No write permissions"))
        else:
            self.ui.error_fetched.set_label("")

    def update_clipboard_state(self, widget=None):
        self.ui.clipboard_use_whitelist.set_sensitive(self.ui.clipboard_enabled.get_active())
        # keep the hosts list always enabled - user can wish to add hosts even when monitoring is not enabled - if undesired, uncomment below:
        # self.ui.clipboard_hosts.set_sensitive(self.ui.clipboard_enabled.get_active() and self.ui.clipboard_use_whitelist.get_active())

    def on_edit_favorites_operations_clicked(self, widget=None):
        self.dialog = EditFavoriteOperationsDialog()
        self.dialog.set_transient_for(self)
        buf = self.dialog.ui.textbuffer
        buf.set_text("\n".join(":".join(x) for x in self.favorites_operations))
        if self.dialog.run() == Gtk.ResponseType.OK:
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.favorites_operations = list([x.strip().split(":") for x in text.split("\n") if x])
            self.delayed_apply()
        self.dialog.destroy()
        self.dialog = None

    def on_icon_changed(self, widget=None):
        self.ui.icon_chooser.set_visible(self.ui.icon.get_active() == 7)

    def on_favorites_operations_changed(self, widget=None):
        self.ui.edit_favorites_operations.set_visible(
            self.ui.favorites_operations.get_active() == 3
        )

    def on_copyto_enabled_toggled(self, widget=None):
        self.copyto_chooser.set_sensitive(self.ui.copyto_enabled.get_active())
        self.ui.copyto_use_default.set_sensitive(self.ui.copyto_enabled.get_active())
        self.on_copyto_changed()

    def on_copyto_changed(self):
        self.ui.copyto_faq_link.set_sensitive(self.ui.copyto_enabled.get_active())
        if self.ui.copyto_enabled.get_active() and self.copyto_chooser.get_folder():
            folder = self.copyto_chooser.get_folder()
            self.ui.copyto_use_default.set_sensitive(
                folder != self.parent.get_actual_copyto_folder("Default")
            )
            under_encrypted = Util.is_home_encrypted() and folder.startswith(
                os.path.expanduser("~") + "/"
            )
            self.ui.copyto_encrypted_note.set_visible(under_encrypted)
            can_write = os.access(self.parent.get_actual_copyto_folder(folder), os.W_OK)
            can_read = os.stat(folder).st_mode | stat.S_IROTH
            self.ui.copyto_faq_link.set_visible(can_write and can_read and not under_encrypted)
            self.ui.copyto_permissions_box.set_visible(not can_write or not can_read)
            self.ui.copyto_write_permissions_warning.set_visible(not can_write)
            self.ui.copyto_read_permissions_warning.set_visible(not can_read)
        else:
            self.ui.copyto_faq_link.set_visible(True)
            self.ui.copyto_encrypted_note.set_visible(False)
            self.ui.copyto_permissions_box.set_visible(False)
        self.delayed_apply()

    def on_copyto_use_default_clicked(self, widget=None):
        self.copyto_chooser.set_folder(self.parent.get_actual_copyto_folder("Default"))
        self.on_copyto_changed()

    def on_copyto_fix_permissions_clicked(self, widget=None):
        folder = self.copyto_chooser.get_folder()
        can_write = os.access(self.parent.get_actual_copyto_folder(folder), os.W_OK)
        can_read = os.stat(folder).st_mode | stat.S_IROTH
        mode = "a+"
        if not can_read:
            mode += "r"
        if not can_write:
            mode += "w"
        try:
            Util.superuser_exec("chmod", mode, folder)
        except Exception:
            logger.exception(lambda: "Could not adjust copyto folder permissions")
            self.parent.show_notification(
                _("Could not adjust permissions"),
                _('You may try manually running this command:\nsudo chmod %s "%s"')
                % (mode, folder),
            )
        self.on_copyto_changed()

    def on_btn_slideshow_reset_clicked(self, widget=None):
        self.ui.slideshow_seconds.set_value(6)
        self.ui.slideshow_fade.set_value(0.4)
        self.ui.slideshow_zoom.set_value(0.2)
        self.ui.slideshow_pan.set_value(0.05)

    def on_btn_slideshow_start_clicked(self, widget=None):
        self.apply()
        self.parent.on_start_slideshow()

    # Smart Selection handlers

    def on_smart_selection_enabled_toggled(self, widget=None):
        """Toggle sensitivity of all Smart Selection controls."""
        enabled = self.ui.smart_selection_enabled.get_active()
        self.ui.smart_image_cooldown.set_sensitive(enabled)
        self.ui.smart_source_cooldown.set_sensitive(enabled)
        self.ui.smart_favorite_boost.set_sensitive(enabled)
        self.ui.smart_new_boost.set_sensitive(enabled)
        self.ui.smart_decay_type.set_sensitive(enabled)
        self.ui.smart_color_enabled.set_sensitive(enabled)
        # Color-aware controls depend on both main enable and color enable
        self.on_smart_color_enabled_toggled()

    def on_smart_color_enabled_toggled(self, widget=None):
        """Toggle sensitivity of color-aware selection controls."""
        main_enabled = self.ui.smart_selection_enabled.get_active()
        color_enabled = self.ui.smart_color_enabled.get_active()

        # Check wallust availability when user tries to enable color features
        if widget and color_enabled and not self.loading:
            if not shutil.which('wallust'):
                # Wallust not available - show warning and disable
                self.ui.smart_color_enabled.set_active(False)
                self.parent.show_notification(
                    _("Color-aware selection requires wallust. "
                      "Install wallust to enable this feature.")
                )
                color_enabled = False

        enabled = main_enabled and color_enabled
        self.ui.smart_color_temperature.set_sensitive(enabled)
        self.ui.smart_color_similarity.set_sensitive(enabled)
        self.ui.smart_time_adaptation.set_sensitive(enabled)
        # Time adaptation visibility depends on adaptive temperature
        self.on_smart_color_temperature_changed()

    def on_smart_color_temperature_changed(self, widget=None):
        """Update visibility of time adaptation based on temperature mode."""
        main_enabled = self.ui.smart_selection_enabled.get_active()
        color_enabled = self.ui.smart_color_enabled.get_active()
        # Time adaptation only makes sense when in "adaptive" mode
        is_adaptive = self.ui.smart_color_temperature.get_active() == 3
        self.ui.smart_time_adaptation.set_sensitive(
            main_enabled and color_enabled and is_adaptive
        )

    def on_smart_image_cooldown_changed(self, widget=None):
        """Update image cooldown label."""
        self.update_smart_image_cooldown_label()

    def on_smart_source_cooldown_changed(self, widget=None):
        """Update source cooldown label."""
        self.update_smart_source_cooldown_label()

    def on_smart_favorite_boost_changed(self, widget=None):
        """Update favorites boost label."""
        self.update_smart_favorite_boost_label()

    def on_smart_new_boost_changed(self, widget=None):
        """Update new image boost label."""
        self.update_smart_new_boost_label()

    def on_smart_color_similarity_changed(self, widget=None):
        """Update color similarity label."""
        self.update_smart_color_similarity_label()

    # Time Adaptation handlers

    def on_smart_time_adaptation_toggled(self, widget=None):
        """Toggle visibility and sensitivity of time adaptation controls."""
        enabled = self.ui.smart_time_adaptation.get_active()
        if hasattr(self.ui, 'smart_time_container'):
            self.ui.smart_time_container.set_sensitive(enabled)
        # Update the current mode indicator
        self.update_time_adaptation_status()

    def on_smart_time_method_changed(self, widget=None):
        """Show/hide conditional controls based on timing method selection."""
        if self.loading:
            return

        method_idx = self.ui.smart_time_method.get_active()
        methods = ["sunrise_sunset", "fixed", "system_theme"]
        method = methods[method_idx] if 0 <= method_idx < len(methods) else "fixed"

        # Show/hide controls based on method
        if hasattr(self.ui, 'smart_time_location_box'):
            self.ui.smart_time_location_box.set_visible(method == "sunrise_sunset")
        if hasattr(self.ui, 'smart_time_sun_status'):
            self.ui.smart_time_sun_status.set_visible(method == "sunrise_sunset")
        if hasattr(self.ui, 'smart_time_fixed_box'):
            self.ui.smart_time_fixed_box.set_visible(method == "fixed")
        if hasattr(self.ui, 'smart_time_theme_status'):
            self.ui.smart_time_theme_status.set_visible(method == "system_theme")

        # Update status displays
        self.update_time_adaptation_status()

    def on_smart_day_preset_changed(self, widget=None):
        """Handle day preset selection, show/hide custom sliders."""
        if self.loading:
            return

        preset_id = self.ui.smart_day_preset.get_active_id()
        show_custom = (preset_id == "custom")

        if hasattr(self.ui, 'smart_day_custom_box'):
            self.ui.smart_day_custom_box.set_visible(show_custom)

    def on_smart_night_preset_changed(self, widget=None):
        """Handle night preset selection, show/hide custom sliders."""
        if self.loading:
            return

        preset_id = self.ui.smart_night_preset.get_active_id()
        show_custom = (preset_id == "custom")

        if hasattr(self.ui, 'smart_night_custom_box'):
            self.ui.smart_night_custom_box.set_visible(show_custom)

    def on_smart_location_lookup_clicked(self, widget=None):
        """Geocode location name to lat/lon coordinates."""
        location_name = self.ui.smart_location_name.get_text().strip()
        if not location_name:
            self.parent.show_notification(_("Please enter a location name"))
            return

        # Try to parse as coordinates first (lat,lon format)
        import re
        coord_match = re.match(r'^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$', location_name)
        if coord_match:
            try:
                lat = float(coord_match.group(1))
                lon = float(coord_match.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    # Valid coordinates - store them and update display
                    self._set_location_coordinates(lat, lon)
                    self.update_time_adaptation_status()
                    self.delayed_apply()
                    return
            except ValueError:
                pass

        # Try geocoding the location name
        def do_geocode():
            try:
                # Use Nominatim for geocoding (free, no API key needed)
                import urllib.request
                import urllib.parse
                import json

                encoded_name = urllib.parse.quote(location_name)
                url = f"https://nominatim.openstreetmap.org/search?q={encoded_name}&format=json&limit=1"

                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'Variety Wallpaper Manager'}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))

                if data:
                    lat = float(data[0]['lat'])
                    lon = float(data[0]['lon'])
                    display_name = data[0].get('display_name', location_name)
                    return lat, lon, display_name
                else:
                    return None, None, None
            except Exception as e:
                logger.warning(lambda: f"Geocoding failed: {e}")
                return None, None, None

        def on_geocode_done(result):
            lat, lon, display_name = result
            if lat is not None and lon is not None:
                self._set_location_coordinates(lat, lon)
                # Update the entry with the resolved name
                if display_name and display_name != location_name:
                    # Show a shorter version of the display name
                    parts = display_name.split(', ')
                    short_name = ', '.join(parts[:2]) if len(parts) > 2 else display_name
                    self.ui.smart_location_name.set_text(short_name)
                self.update_time_adaptation_status()
                self.delayed_apply()
            else:
                self.parent.show_notification(
                    _("Could not find location: {}").format(location_name)
                )

        # Run geocoding in background thread
        import threading
        def geocode_thread():
            result = do_geocode()
            GLib.idle_add(on_geocode_done, result)

        thread = threading.Thread(target=geocode_thread, daemon=True)
        thread.start()

    def _set_location_coordinates(self, lat, lon):
        """Store location coordinates for later use."""
        # These will be saved to config when apply() is called
        self._location_lat = lat
        self._location_lon = lon

    def update_time_adaptation_status(self):
        """Update the 'Currently: Day/Night' indicator and sun times."""
        try:
            # Determine current period based on method
            method_idx = self.ui.smart_time_method.get_active()
            methods = ["sunrise_sunset", "fixed", "system_theme"]
            method = methods[method_idx] if 0 <= method_idx < len(methods) else "fixed"

            current_period = "day"  # Default
            from datetime import datetime

            if method == "fixed":
                # Use fixed schedule times
                day_start = self.ui.smart_day_start.get_text().strip()
                night_start = self.ui.smart_night_start.get_text().strip()

                try:
                    now = datetime.now().strftime("%H:%M")
                    if night_start <= now or now < day_start:
                        current_period = "night"
                    else:
                        current_period = "day"
                except Exception:
                    pass

            elif method == "sunrise_sunset":
                # Try to calculate based on location
                if hasattr(self, '_location_lat') and hasattr(self, '_location_lon'):
                    try:
                        from astral import LocationInfo
                        from astral.sun import sun
                        import datetime as dt

                        location = LocationInfo(
                            latitude=self._location_lat,
                            longitude=self._location_lon
                        )
                        s = sun(location.observer, date=dt.date.today())
                        sunrise = s['sunrise']
                        sunset = s['sunset']

                        # Update sun times display
                        if hasattr(self.ui, 'smart_time_sun_status'):
                            self.ui.smart_time_sun_status.set_text(
                                _("Sunrise: {}  Sunset: {}").format(
                                    sunrise.strftime("%H:%M"),
                                    sunset.strftime("%H:%M")
                                )
                            )

                        # Determine current period
                        now = datetime.now()
                        # Make sunrise/sunset timezone-aware or naive to match 'now'
                        sunrise_naive = sunrise.replace(tzinfo=None)
                        sunset_naive = sunset.replace(tzinfo=None)
                        if sunrise_naive <= now <= sunset_naive:
                            current_period = "day"
                        else:
                            current_period = "night"
                    except ImportError:
                        # astral not installed
                        if hasattr(self.ui, 'smart_time_sun_status'):
                            self.ui.smart_time_sun_status.set_text(
                                _("Install 'astral' library for sun times")
                            )
                    except Exception as e:
                        logger.debug(lambda: f"Sun calculation error: {e}")
                else:
                    if hasattr(self.ui, 'smart_time_sun_status'):
                        self.ui.smart_time_sun_status.set_text(
                            _("Enter location and click Lookup")
                        )

            elif method == "system_theme":
                # Try to detect system theme
                try:
                    from gi.repository import Gio
                    settings = Gio.Settings.new("org.gnome.desktop.interface")
                    scheme = settings.get_string("color-scheme")
                    if scheme == "prefer-dark":
                        current_period = "night"
                        theme_status = _("System theme: Dark")
                    elif scheme == "prefer-light":
                        current_period = "day"
                        theme_status = _("System theme: Light")
                    else:
                        current_period = "day"
                        theme_status = _("System theme: Default (Day)")

                    if hasattr(self.ui, 'smart_time_theme_status'):
                        self.ui.smart_time_theme_status.set_text(theme_status)
                except Exception:
                    if hasattr(self.ui, 'smart_time_theme_status'):
                        self.ui.smart_time_theme_status.set_text(
                            _("Could not detect system theme")
                        )

            # Update the current mode indicator
            if hasattr(self.ui, 'smart_time_current_mode'):
                if current_period == "night":
                    self.ui.smart_time_current_mode.set_text(_("Night"))
                else:
                    self.ui.smart_time_current_mode.set_text(_("Day"))

        except Exception:
            logger.exception(lambda: "Error updating time adaptation status")

    def update_smart_image_cooldown_label(self):
        """Update the image cooldown label text."""
        value = int(self.ui.smart_image_cooldown.get_value())
        if value == 0:
            self.ui.smart_image_cooldown_label.set_text(_("Disabled"))
        elif value == 1:
            self.ui.smart_image_cooldown_label.set_text(_("1 day"))
        else:
            self.ui.smart_image_cooldown_label.set_text(_("{} days").format(value))

    def update_smart_source_cooldown_label(self):
        """Update the source cooldown label text."""
        value = int(self.ui.smart_source_cooldown.get_value())
        if value == 0:
            self.ui.smart_source_cooldown_label.set_text(_("Disabled"))
        elif value == 1:
            self.ui.smart_source_cooldown_label.set_text(_("1 day"))
        else:
            self.ui.smart_source_cooldown_label.set_text(_("{} days").format(value))

    def update_smart_favorite_boost_label(self):
        """Update the favorites boost label text."""
        value = self.ui.smart_favorite_boost.get_value()
        self.ui.smart_favorite_boost_label.set_text("{:.1f}x".format(value))

    def update_smart_new_boost_label(self):
        """Update the new image boost label text."""
        value = self.ui.smart_new_boost.get_value()
        self.ui.smart_new_boost_label.set_text("{:.1f}x".format(value))

    def update_smart_color_similarity_label(self):
        """Update the color similarity label text."""
        value = int(self.ui.smart_color_similarity.get_value())
        self.ui.smart_color_similarity_label.set_text("{}%".format(value))

    def update_smart_selection_stats(self):
        """Update the Smart Selection statistics labels."""
        try:
            if hasattr(self.parent, 'smart_selector') and self.parent.smart_selector:
                stats = self.parent.smart_selector.get_statistics()
                image_count = stats.get('images_indexed', 0)
                source_count = stats.get('sources_count', 0)

                # Show "Indexing..." when count is 0 (work in progress)
                if image_count == 0:
                    self.ui.smart_stats_indexed.set_text(_("Indexing..."))
                else:
                    self.ui.smart_stats_indexed.set_text(
                        _("Images indexed: {}    Sources: {}").format(
                            image_count,
                            source_count
                        )
                    )

                images = stats.get('images_indexed', 0)
                palettes = stats.get('images_with_palettes', 0)
                pct = int(100 * palettes / images) if images > 0 else 0
                self.ui.smart_stats_palettes.set_text(
                    _("Images with palettes: {} ({}%)").format(palettes, pct)
                )
                self.ui.smart_stats_selections.set_text(
                    _("Total selections: {}    Unique shown: {}").format(
                        stats.get('total_selections', 0),
                        stats.get('unique_shown', 0)
                    )
                )
            else:
                self.ui.smart_stats_indexed.set_text(_("Indexing..."))
                self.ui.smart_stats_palettes.set_text(_("Images with palettes: 0 (0%)"))
                self.ui.smart_stats_selections.set_text(_("Total selections: 0    Unique shown: 0"))

            # Update insights section
            self._update_insights_async()
        except Exception:
            logger.exception(lambda: "Error updating smart selection stats")

    def _hide_unimplemented_controls(self):
        """Hide controls for features not yet implemented."""
        # Time adaptation controls are now implemented - no longer hiding them
        pass

    def _setup_smart_selection_tooltips(self):
        """Apply tooltips to all Smart Selection controls."""
        for widget_name, tooltip in SMART_SELECTION_TOOLTIPS.items():
            widget = getattr(self.ui, widget_name, None)
            if widget and hasattr(widget, 'set_tooltip_text'):
                widget.set_tooltip_text(tooltip)

    def _create_help_popover(self, help_key: str) -> Gtk.Popover:
        """Create a help popover with the given content.

        Args:
            help_key: Key into SMART_SELECTION_HELP dictionary

        Returns:
            Gtk.Popover with formatted help text
        """
        popover = Gtk.Popover()

        label = Gtk.Label()
        label.set_text(SMART_SELECTION_HELP.get(help_key, ""))
        label.set_line_wrap(True)
        label.set_max_width_chars(50)
        label.set_margin_start(12)
        label.set_margin_end(12)
        label.set_margin_top(12)
        label.set_margin_bottom(12)
        label.set_xalign(0)  # Left-align text

        popover.add(label)
        label.show()

        return popover

    def on_smart_help_overview_clicked(self, widget):
        """Show overview help popover."""
        popover = self._create_help_popover("overview")
        popover.set_relative_to(widget)
        popover.popup()

    def on_smart_help_time_adaptation_clicked(self, widget):
        """Show time adaptation help popover."""
        popover = self._create_help_popover("time_adaptation")
        popover.set_relative_to(widget)
        popover.popup()

    def on_smart_help_color_matching_clicked(self, widget):
        """Show color matching help popover."""
        popover = self._create_help_popover("color_matching")
        popover.set_relative_to(widget)
        popover.popup()

    def on_smart_help_presets_clicked(self, widget):
        """Show presets help popover."""
        popover = self._create_help_popover("presets")
        popover.set_relative_to(widget)
        popover.popup()

    def on_smart_help_decay_types_clicked(self, widget):
        """Show decay types help popover."""
        popover = self._create_help_popover("decay_types")
        popover.set_relative_to(widget)
        popover.popup()

    def on_smart_help_theming_clicked(self, widget):
        """Show theming help popover."""
        popover = self._create_help_popover("theming")
        popover.set_relative_to(widget)
        popover.popup()

    def _connect_help_buttons(self):
        """Connect help buttons to their popover handlers if they exist in the UI."""
        help_button_handlers = {
            "smart_help_overview": self.on_smart_help_overview_clicked,
            "smart_help_time_adaptation": self.on_smart_help_time_adaptation_clicked,
            "smart_help_color_matching": self.on_smart_help_color_matching_clicked,
            "smart_help_presets": self.on_smart_help_presets_clicked,
            "smart_help_decay_types": self.on_smart_help_decay_types_clicked,
            "smart_help_theming": self.on_smart_help_theming_clicked,
        }

        for widget_name, handler in help_button_handlers.items():
            widget = getattr(self.ui, widget_name, None)
            if widget and hasattr(widget, 'connect'):
                widget.connect("clicked", handler)

    def _build_insights_section(self):
        """Build the Collection Insights section with expandable cards."""
        try:
            container = self.ui.smart_insights_container

            # Clear any existing content
            for child in container.get_children():
                container.remove(child)

            # Header with title and refresh button
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            header_box.set_margin_bottom(10)

            title_label = Gtk.Label()
            title_label.set_markup("<b>{}</b>".format(_("Collection Insights")))
            title_label.set_halign(Gtk.Align.START)
            header_box.pack_start(title_label, False, True, 0)

            # Refresh button
            refresh_button = Gtk.Button(label=_("Refresh"))
            refresh_button.set_tooltip_text(_("Recalculate collection statistics from current data. Use after extracting palettes or when stats appear outdated."))
            refresh_button.connect("clicked", self.on_smart_refresh_insights_clicked)
            header_box.pack_start(refresh_button, False, False, 0)

            # Spinner (hidden by default)
            self.insights_spinner = Gtk.Spinner()
            header_box.pack_start(self.insights_spinner, False, False, 0)

            container.pack_start(header_box, False, False, 0)

            # Store references to expanders for updating
            self.insights_expanders = {}

            # Create 5 expandable insight cards
            categories = [
                ('time_adaptation', _("Time Adaptation"), "preferences-system-time-symbolic"),
                ('lightness', _("Lightness Balance"), "weather-clear-symbolic"),
                ('hue', _("Color Palette"), "preferences-color-symbolic"),
                ('saturation', _("Saturation Levels"), "view-continuous-symbolic"),
                ('freshness', _("Collection Freshness"), "document-new-symbolic"),
            ]

            for category_id, category_name, icon_name in categories:
                # Create expander
                expander = Gtk.Expander()
                expander.set_margin_top(5)
                expander.set_margin_bottom(5)

                # Create header box with icon and summary
                header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

                icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
                header.pack_start(icon, False, False, 0)

                summary_label = Gtk.Label()
                summary_label.set_halign(Gtk.Align.START)
                summary_label.set_text(_("Loading..."))
                header.pack_start(summary_label, True, True, 0)

                expander.set_label_widget(header)

                # Create content label for expanded view
                content_label = Gtk.Label()
                content_label.set_halign(Gtk.Align.START)
                content_label.set_margin_start(32)
                content_label.set_margin_top(5)
                content_label.set_margin_bottom(5)
                content_label.set_line_wrap(True)
                content_label.set_selectable(True)

                expander.add(content_label)
                container.pack_start(expander, False, False, 0)

                # Store references
                self.insights_expanders[category_id] = {
                    'expander': expander,
                    'summary': summary_label,
                    'content': content_label,
                    'icon': icon,
                }

            container.show_all()
            self.insights_spinner.hide()

        except Exception:
            logger.exception(lambda: "Error building insights section")

    def _update_insights(self):
        """Update the insights section with current statistics."""
        try:
            if not hasattr(self, 'insights_expanders'):
                return

            # Check if smart_selector is available
            if not hasattr(self.parent, 'smart_selector') or not self.parent.smart_selector:
                for category_id, refs in self.insights_expanders.items():
                    refs['summary'].set_text(_("Indexing..."))
                    refs['content'].set_text(_("Please wait while collection is being indexed."))
                return

            # Get statistics
            analyzer = self.parent.smart_selector.get_statistics_analyzer()
            stats = analyzer.get_all_stats()

            total_with_palettes = stats.get('total_with_palettes', 0)

            # If no palettes, show empty state
            if total_with_palettes == 0:
                empty_msg = _("Run 'Extract Palettes' to enable color insights")
                for category_id, refs in self.insights_expanders.items():
                    refs['summary'].set_text(empty_msg)
                    refs['content'].set_text(_("Color insights require palette data."))
                return

            # Update each category
            categories = {
                'lightness': {
                    'summary_key': 'lightness_summary',
                    'dist_key': 'lightness_distribution',
                    'labels': {
                        'dark': _("Dark"),
                        'medium_dark': _("Medium-dark"),
                        'medium_light': _("Medium-light"),
                        'light': _("Light"),
                    }
                },
                'hue': {
                    'summary_key': 'hue_summary',
                    'dist_key': 'hue_distribution',
                    'labels': {
                        'red': _("Red"),
                        'orange': _("Orange"),
                        'yellow': _("Yellow"),
                        'green': _("Green"),
                        'cyan': _("Cyan"),
                        'blue': _("Blue"),
                        'purple': _("Purple"),
                        'pink': _("Pink"),
                        'neutral': _("Neutral"),
                    }
                },
                'saturation': {
                    'summary_key': 'saturation_summary',
                    'dist_key': 'saturation_distribution',
                    'labels': {
                        'muted': _("Muted"),
                        'moderate': _("Moderate"),
                        'saturated': _("Saturated"),
                        'vibrant': _("Vibrant"),
                    }
                },
                'freshness': {
                    'summary_key': 'freshness_summary',
                    'dist_key': 'freshness_distribution',
                    'labels': {
                        'never_shown': _("Never shown"),
                        'rarely_shown': _("Rarely shown (1-4)"),
                        'often_shown': _("Often shown (5-9)"),
                        'frequently_shown': _("Frequently shown (10+)"),
                    }
                },
            }

            gaps = stats.get('gaps', [])

            # Update time adaptation category separately (uses different data source)
            if 'time_adaptation' in self.insights_expanders:
                refs = self.insights_expanders['time_adaptation']
                try:
                    time_status = self.parent.smart_selector.get_time_adaptation_status()
                    if time_status.get('enabled'):
                        period = time_status.get('period', 'unknown')
                        period_display = _("Day") if period == 'day' else _("Night")
                        suitable = time_status.get('suitable_count', 0)
                        next_trans = time_status.get('next_transition')
                        target_l = time_status.get('target_lightness')

                        # Summary: Current mode and suitable count
                        summary = _("Currently: {} · {} suitable wallpapers").format(
                            period_display, suitable
                        )
                        refs['summary'].set_text(summary)

                        # Detailed content
                        content_lines = [
                            _("Current period: {}").format(period_display),
                            _("Suitable wallpapers: {}").format(suitable),
                        ]
                        if target_l is not None:
                            content_lines.append(_("Target lightness: {:.0%}").format(target_l))
                        if next_trans:
                            next_period = _("Day") if period == 'night' else _("Night")
                            content_lines.append(_("Next transition: {} at {}").format(
                                next_period, next_trans
                            ))

                        # Add time suitability breakdown
                        time_suit = stats.get('time_suitability', {})
                        day_count = time_suit.get('day_suitable', 0)
                        night_count = time_suit.get('night_suitable', 0)
                        content_lines.append("")
                        content_lines.append(_("Collection breakdown:"))
                        content_lines.append(_("  Day-suitable (bright): {}").format(day_count))
                        content_lines.append(_("  Night-suitable (dark): {}").format(night_count))

                        refs['content'].set_text("\n".join(content_lines))

                        # Set icon based on period
                        if period == 'night':
                            refs['icon'].set_from_icon_name("weather-clear-night-symbolic", Gtk.IconSize.MENU)
                        else:
                            refs['icon'].set_from_icon_name("weather-clear-symbolic", Gtk.IconSize.MENU)
                    else:
                        refs['summary'].set_text(_("Disabled"))
                        refs['content'].set_text(_("Enable Time Adaptation above to adjust wallpaper selection based on time of day."))
                        refs['icon'].set_from_icon_name("preferences-system-time-symbolic", Gtk.IconSize.MENU)
                except Exception as e:
                    logger.debug(f"Failed to update time adaptation insight: {e}")
                    refs['summary'].set_text(_("Not available"))
                    refs['content'].set_text(_("Time adaptation status could not be determined."))

            for category_id, category_info in categories.items():
                if category_id not in self.insights_expanders:
                    continue

                refs = self.insights_expanders[category_id]

                # Update summary
                summary_text = stats.get(category_info['summary_key'], _("No data"))

                # Check if this category has gaps
                category_gaps = [g for g in gaps if any(
                    label.lower() in g.lower()
                    for label in category_info['labels'].values()
                )]

                if category_gaps:
                    # Add warning icon
                    refs['icon'].set_from_icon_name("dialog-warning-symbolic", Gtk.IconSize.MENU)
                else:
                    # Restore default icon
                    icon_names = {
                        'time_adaptation': "preferences-system-time-symbolic",
                        'lightness': "weather-clear-symbolic",
                        'hue': "preferences-color-symbolic",
                        'saturation': "view-continuous-symbolic",
                        'freshness': "document-new-symbolic",
                    }
                    refs['icon'].set_from_icon_name(icon_names.get(category_id, "dialog-question-symbolic"), Gtk.IconSize.MENU)

                refs['summary'].set_text(summary_text)

                # Build detailed content
                distribution = stats.get(category_info['dist_key'], {})
                labels = category_info['labels']

                content_lines = []
                for key, count in distribution.items():
                    label = labels.get(key, key.replace('_', '-').capitalize())
                    # Use correct denominator: freshness uses total_images (from images table),
                    # other categories use total_with_palettes (from palettes table)
                    if category_id == 'freshness':
                        denominator = stats.get('total_images', 1)
                    else:
                        denominator = total_with_palettes

                    if denominator > 0:
                        percentage = int(count / denominator * 100)
                        content_lines.append("{}: {} ({}%)".format(label, count, percentage))
                    else:
                        content_lines.append("{}: {}".format(label, count))

                # Add gaps for this category if any
                if category_gaps:
                    content_lines.append("")
                    content_lines.append(_("Gaps detected:"))
                    for gap in category_gaps:
                        content_lines.append("  • {}".format(gap))

                refs['content'].set_text("\n".join(content_lines))

        except Exception:
            logger.exception(lambda: "Error updating insights")

    def _update_insights_async(self):
        """Update insights asynchronously with spinner."""
        if not hasattr(self, 'insights_expanders') or not hasattr(self, 'insights_spinner'):
            # Insights section not built yet, skip
            return

        def show_spinner():
            self.insights_spinner.start()
            self.insights_spinner.show()

        def hide_spinner():
            self.insights_spinner.stop()
            self.insights_spinner.hide()

        def update():
            try:
                Util.add_mainloop_task(show_spinner)
                self._update_insights()
            finally:
                Util.add_mainloop_task(hide_spinner)

        threading.Thread(target=update, daemon=True).start()

    def on_smart_refresh_insights_clicked(self, widget=None):
        """Handle refresh insights button click."""
        if hasattr(self.parent, 'smart_selector') and self.parent.smart_selector:
            # Invalidate cache
            analyzer = self.parent.smart_selector.get_statistics_analyzer()
            analyzer.invalidate()
            # Update insights
            self._update_insights_async()

    def on_smart_rebuild_index_clicked(self, widget=None):
        """Rebuild the Smart Selection image index."""
        if hasattr(self.parent, 'smart_selector') and self.parent.smart_selector:
            # Show confirmation dialog
            dialog = Gtk.MessageDialog(
                self,
                Gtk.DialogFlags.MODAL,
                Gtk.MessageType.WARNING,
                Gtk.ButtonsType.YES_NO,
                _("Rebuild the entire image index?\n\n"
                  "This will:\n"
                  "• Delete all indexed image data\n"
                  "• Delete all extracted color palettes\n"
                  "• Re-scan all source folders from scratch\n\n"
                  "Use this when your wallpaper folders have changed significantly.")
            )
            dialog.set_title(_("Rebuild Index"))
            response = dialog.run()
            dialog.destroy()

            if response != Gtk.ResponseType.YES:
                return

            # Show progress UI
            self.ui.smart_rebuild_index.set_sensitive(False)
            self.ui.smart_rebuild_progress_box.set_visible(True)
            self.ui.smart_rebuild_progress.set_fraction(0.0)
            self.ui.smart_rebuild_progress.set_text(_("Starting..."))

            def progress_callback(current, total):
                """Update progress bar with rebuild progress."""
                def _update():
                    if total > 0:
                        fraction = current / total
                        self.ui.smart_rebuild_progress.set_fraction(fraction)
                        self.ui.smart_rebuild_progress.set_text(
                            _("Scanning folder {current} / {total}").format(
                                current=current, total=total
                            )
                        )
                Util.add_mainloop_task(_update)

            def rebuild():
                try:
                    # Collect all source folders
                    folders = self._get_all_source_folders()
                    favorites_folder = self.parent.options.favorites_folder
                    self.parent.smart_selector.rebuild_index(
                        source_folders=folders,
                        favorites_folder=favorites_folder,
                        progress_callback=progress_callback
                    )

                    # Get final counts for completion message
                    stats = self.parent.smart_selector.get_statistics()
                    images_count = stats.get('images_indexed', 0)
                    sources_count = stats.get('sources_count', 0)

                    def _on_success():
                        self.update_smart_selection_stats()
                        self.parent.show_notification(
                            _("Index rebuilt: {images} images from {sources} sources").format(
                                images=images_count, sources=sources_count
                            )
                        )
                    Util.add_mainloop_task(_on_success)

                except Exception:
                    logger.exception(lambda: "Error rebuilding smart selection index")
                    def _on_error():
                        self.parent.show_notification(_("Index rebuild failed"))
                    Util.add_mainloop_task(_on_error)

                finally:
                    def _restore():
                        self.ui.smart_rebuild_progress_box.set_visible(False)
                        self.ui.smart_rebuild_index.set_sensitive(True)
                    Util.add_mainloop_task(_restore)

            threading.Thread(target=rebuild, daemon=True).start()

    def _get_all_source_folders(self):
        """Get all enabled source folders for indexing."""
        folders = []

        # Favorites
        if self.parent.options.favorites_folder:
            folders.append(self.parent.options.favorites_folder)
            logger.info(f"Smart Selection: Added favorites folder: {self.parent.options.favorites_folder}")

        # Downloaded
        if hasattr(self.parent, 'real_download_folder') and self.parent.real_download_folder:
            folders.append(self.parent.real_download_folder)
            logger.info(f"Smart Selection: Added real_download_folder: {self.parent.real_download_folder}")
        elif self.parent.options.download_folder:
            folders.append(self.parent.options.download_folder)
            logger.info(f"Smart Selection: Added download_folder: {self.parent.options.download_folder}")

        # Fetched
        if self.parent.options.fetched_folder:
            folders.append(self.parent.options.fetched_folder)
            logger.info(f"Smart Selection: Added fetched_folder: {self.parent.options.fetched_folder}")

        # User folders
        for source in self.parent.options.sources:
            enabled, source_type, location = source
            if enabled and source_type == Options.SourceType.FOLDER:
                folders.append(os.path.expanduser(location))
                logger.info(f"Smart Selection: Added user folder: {location}")

        valid_folders = [f for f in folders if f and os.path.exists(f)]
        logger.info(f"Smart Selection: Total folders to index: {len(valid_folders)} of {len(folders)}")
        for f in folders:
            if f and not os.path.exists(f):
                logger.warning(f"Smart Selection: Folder does not exist: {f}")
        return valid_folders

    def on_smart_extract_palettes_clicked(self, widget=None):
        """Extract color palettes for all indexed images."""
        if not hasattr(self.parent, 'smart_selector') or not self.parent.smart_selector:
            return

        # Check wallust availability first
        if not shutil.which('wallust'):
            self._show_wallust_required_dialog()
            return

        # Get count of images without palettes for the dialog
        stats = self.parent.smart_selector.get_statistics()
        images_without = stats['images_indexed'] - stats['images_with_palettes']

        if images_without == 0:
            self.parent.show_notification(_("All images already have palettes"))
            return

        # Show confirmation dialog
        dialog = Gtk.MessageDialog(
            self,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.INFO,
            Gtk.ButtonsType.YES_NO,
            _("Extract color palettes for {count} images?\n\n"
              "This may take several minutes for large collections.\n"
              "You can cancel at any time.").format(count=images_without)
        )
        dialog.set_title(_("Extract Palettes"))
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        # Reset cancellation flag
        self._extraction_cancelled = False

        # Show progress UI
        self.ui.smart_extract_palettes.set_sensitive(False)
        self.ui.smart_extraction_progress_box.set_visible(True)
        self.ui.smart_extraction_progress.set_fraction(0.0)
        self.ui.smart_extraction_progress.set_text(_("Starting..."))
        self.ui.smart_extraction_cancel.set_sensitive(True)

        def progress_callback(current, total):
            """Update progress bar with extraction progress."""
            if self._extraction_cancelled:
                raise InterruptedError("Extraction cancelled by user")

            def _update():
                if total > 0:
                    fraction = current / total
                    self.ui.smart_extraction_progress.set_fraction(fraction)
                    self.ui.smart_extraction_progress.set_text(
                        _("{current} / {total} ({pct}%)").format(
                            current=current, total=total, pct=int(fraction * 100)
                        )
                    )
            Util.add_mainloop_task(_update)

        def extract():
            try:
                count = self.parent.smart_selector.extract_all_palettes(
                    progress_callback=progress_callback
                )

                def _on_success():
                    self.update_smart_selection_stats()
                    self.parent.show_notification(_("Extracted {} palettes").format(count))
                Util.add_mainloop_task(_on_success)

            except InterruptedError:
                def _on_cancelled():
                    self.parent.show_notification(_("Palette extraction cancelled"))
                Util.add_mainloop_task(_on_cancelled)

            except Exception:
                logger.exception(lambda: "Error extracting palettes")
                def _on_error():
                    self.parent.show_notification(_("Palette extraction failed"))
                Util.add_mainloop_task(_on_error)

            finally:
                def _restore():
                    self.ui.smart_extraction_progress_box.set_visible(False)
                    self.ui.smart_extract_palettes.set_sensitive(True)
                Util.add_mainloop_task(_restore)

        self._extraction_thread = threading.Thread(target=extract, daemon=True)
        self._extraction_thread.start()

    def on_smart_extraction_cancel_clicked(self, widget=None):
        """Cancel ongoing palette extraction."""
        self._extraction_cancelled = True
        self.ui.smart_extraction_progress.set_text(_("Cancelling..."))
        self.ui.smart_extraction_cancel.set_sensitive(False)

    def _show_wallust_required_dialog(self):
        """Show dialog explaining wallust is required."""
        dialog = Gtk.MessageDialog(
            self,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK,
            None
        )
        dialog.set_title(_("wallust Required"))

        dialog.format_secondary_markup(
            _("<b>wallust</b> is required for color-aware selection.\n\n"
              "<b>Installation Options:</b>\n"
              "  Cargo: <tt>cargo install wallust</tt>\n"
              "  Arch: <tt>pacman -S wallust</tt>\n"
              "  Nix: <tt>nix-env -iA nixpkgs.wallust</tt>\n\n"
              "<b>After installation:</b>\n"
              "  1. Run <tt>wallust run &lt;any_image&gt;</tt> to initialize\n"
              "  2. Re-enable color features in Variety")
        )

        dialog.run()
        dialog.destroy()

    def on_smart_theming_enabled_toggled(self, widget=None):
        """Toggle sensitivity of theming controls."""
        enabled = self.ui.smart_theming_enabled.get_active()
        self.ui.smart_theming_configure.set_sensitive(enabled)
        self.ui.smart_theming_templates_label.set_sensitive(enabled)

        if hasattr(self.parent, 'theme_engine'):
            if enabled:
                self.parent._init_theme_engine()
            else:
                if self.parent.theme_engine:
                    self.parent.theme_engine.cleanup()
                    self.parent.theme_engine = None

    def update_smart_theming_templates_label(self):
        """Update the templates count label."""
        if hasattr(self.parent, 'theme_engine') and self.parent.theme_engine:
            all_templates = self.parent.theme_engine.get_all_templates()
            enabled_templates = self.parent.theme_engine.get_enabled_templates()
            self.ui.smart_theming_templates_label.set_text(
                _("Templates: {} enabled of {}").format(len(enabled_templates), len(all_templates))
            )
        else:
            wallust_config = os.path.expanduser('~/.config/wallust/wallust.toml')
            if os.path.exists(wallust_config):
                self.ui.smart_theming_templates_label.set_text(_("Templates: Not loaded"))
            else:
                self.ui.smart_theming_templates_label.set_text(_("Templates: wallust.toml not found"))

    def on_smart_theming_configure_clicked(self, widget=None):
        """Open theming configuration dialog or file."""
        import subprocess

        theming_json = os.path.expanduser('~/.config/variety/theming.json')
        wallust_toml = os.path.expanduser('~/.config/wallust/wallust.toml')

        if os.path.exists(theming_json):
            target = theming_json
        elif os.path.exists(wallust_toml):
            target = wallust_toml
        else:
            dialog = Gtk.MessageDialog(
                self,
                Gtk.DialogFlags.MODAL,
                Gtk.MessageType.INFO,
                Gtk.ButtonsType.OK,
                _("Theming Configuration\n\n"
                  "To configure theming:\n\n"
                  "1. Install wallust\n"
                  "2. Create ~/.config/wallust/wallust.toml\n"
                  "3. Optionally create ~/.config/variety/theming.json")
            )
            dialog.set_title(_("Theming Setup"))
            dialog.run()
            dialog.destroy()
            return

        try:
            subprocess.Popen(['xdg-open', target])
        except Exception:
            logger.exception("Could not open {}".format(target))

    def on_smart_clear_history_clicked(self, widget=None):
        """Clear the Smart Selection history."""
        if hasattr(self.parent, 'smart_selector') and self.parent.smart_selector:
            dialog = Gtk.MessageDialog(
                self,
                Gtk.DialogFlags.MODAL,
                Gtk.MessageType.QUESTION,
                Gtk.ButtonsType.YES_NO,
                _("Clear all selection history?\n\n"
                  "This will reset the view counts for all images.\n"
                  "The image index will be preserved.")
            )
            dialog.set_title(_("Clear History"))
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                try:
                    self.parent.smart_selector.clear_history()
                    self.update_smart_selection_stats()
                    self.parent.show_notification(_("Selection history cleared"))
                except Exception:
                    logger.exception(lambda: "Error clearing selection history")

    def on_smart_preview_clicked(self, widget=None):
        """Generate and display preview of wallpaper candidates in a popout window."""
        if not hasattr(self.parent, 'smart_selector') or not self.parent.smart_selector:
            self.ui.smart_preview_status.set_text(_("Smart Selection not available"))
            return

        # Reuse existing dialog if present and visible
        if hasattr(self, '_smart_preview_dialog') and self._smart_preview_dialog:
            try:
                if self._smart_preview_dialog.get_visible():
                    # Just refresh the existing dialog's contents
                    self._refresh_preview_dialog(self._smart_preview_dialog)
                    self._smart_preview_dialog.present()
                    return
            except Exception:
                # Dialog was destroyed, create new one
                self._smart_preview_dialog = None

        # Create popout dialog
        dialog = Gtk.Dialog(
            title=_("Smart Selection Preview"),
            transient_for=self,
            modal=False,
            destroy_with_parent=True
        )
        dialog.set_default_size(800, 600)
        dialog.add_button(_("Close"), Gtk.ResponseType.CLOSE)

        # Store reference for reuse
        self._smart_preview_dialog = dialog

        content_area = dialog.get_content_area()
        content_area.set_spacing(6)
        content_area.set_margin_start(10)
        content_area.set_margin_end(10)
        content_area.set_margin_top(10)
        content_area.set_margin_bottom(10)

        # Header bar with controls
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Zoom control
        zoom_label = Gtk.Label(label=_("Thumbnail size:"))
        header_box.pack_start(zoom_label, False, False, 0)

        zoom_adj = Gtk.Adjustment(value=120, lower=80, upper=300, step_increment=20)
        zoom_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=zoom_adj)
        zoom_scale.set_size_request(150, -1)
        zoom_scale.set_draw_value(False)
        header_box.pack_start(zoom_scale, False, False, 0)

        zoom_value_label = Gtk.Label(label="120px")
        zoom_value_label.set_width_chars(6)
        header_box.pack_start(zoom_value_label, False, False, 0)

        # Refresh button
        refresh_button = Gtk.Button(label=_("Refresh"))
        header_box.pack_end(refresh_button, False, False, 0)

        # Spinner
        spinner = Gtk.Spinner()
        header_box.pack_end(spinner, False, False, 0)

        # Status label
        status_label = Gtk.Label(label=_("Loading preview..."))
        status_label.set_xalign(0)
        header_box.pack_start(status_label, True, True, 0)

        content_area.pack_start(header_box, False, False, 0)

        # Scrolled window with FlowBox
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        flowbox = Gtk.FlowBox()
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_min_children_per_line(2)
        flowbox.set_max_children_per_line(12)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_homogeneous(False)
        scrolled.add(flowbox)

        content_area.pack_start(scrolled, True, True, 0)

        # Store references for callbacks
        dialog._preview_data = {
            'flowbox': flowbox,
            'spinner': spinner,
            'status_label': status_label,
            'zoom_adj': zoom_adj,
            'zoom_value_label': zoom_value_label,
            'refresh_button': refresh_button,
            'candidates': []
        }

        def _load_preview():
            data = dialog._preview_data
            spinner.start()
            spinner.set_visible(True)
            refresh_button.set_sensitive(False)

            try:
                candidates = self.parent.smart_selector.get_preview_candidates(count=60)
                data['candidates'] = candidates

                def _update_ui():
                    self._populate_dialog_flowbox(dialog, candidates)
                    spinner.stop()
                    spinner.set_visible(False)
                    refresh_button.set_sensitive(True)
                    if candidates:
                        status_label.set_text(
                            _("Showing top {} candidates (sorted by selection weight)").format(
                                len(candidates)
                            )
                        )
                    else:
                        status_label.set_text(
                            _("No candidates found. Try rebuilding the index.")
                        )

                GObject.idle_add(_update_ui)

            except Exception as e:
                logger.exception(lambda: "Error loading preview")

                def _show_error():
                    spinner.stop()
                    spinner.set_visible(False)
                    refresh_button.set_sensitive(True)
                    status_label.set_text(_("Error loading preview"))

                GObject.idle_add(_show_error)

        def on_zoom_changed(adj):
            value = int(adj.get_value())
            zoom_value_label.set_text("{}px".format(value))
            self._resize_dialog_thumbnails(dialog, value)

        def on_refresh_clicked(btn):
            # Clear existing
            for child in flowbox.get_children():
                flowbox.remove(child)
            threading.Thread(target=_load_preview, daemon=True).start()

        zoom_adj.connect('value-changed', on_zoom_changed)
        refresh_button.connect('clicked', on_refresh_clicked)

        def on_dialog_response(d, r):
            self._smart_preview_dialog = None
            d.destroy()

        dialog.connect('response', on_dialog_response)

        dialog.show_all()
        spinner.set_visible(False)  # Hide until loading starts

        # Start loading
        threading.Thread(target=_load_preview, daemon=True).start()

    def _populate_dialog_flowbox(self, dialog, candidates):
        """Populate a dialog's FlowBox with thumbnail images (async loading)."""
        data = dialog._preview_data
        flowbox = data['flowbox']
        thumb_size = int(data['zoom_adj'].get_value())

        # Store image widgets for async updating
        image_widgets = []

        for candidate in candidates:
            filepath = candidate['filepath']
            weight = candidate.get('normalized_weight', 1.0)
            is_favorite = candidate.get('is_favorite', False)
            times_shown = candidate.get('times_shown', 0)

            # Create container for thumbnail and info
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_margin_start(3)
            vbox.set_margin_end(3)
            vbox.set_margin_top(3)
            vbox.set_margin_bottom(3)

            # Create placeholder image (will be replaced async)
            image = Gtk.Image.new_from_icon_name(
                "image-loading", Gtk.IconSize.DIALOG
            )
            image.set_size_request(thumb_size, thumb_size)

            # Add frame around image
            frame = Gtk.Frame()
            frame.add(image)
            vbox.pack_start(frame, False, False, 0)

            # Weight bar (visual indicator)
            weight_bar = Gtk.ProgressBar()
            weight_bar.set_fraction(weight)
            weight_bar.set_size_request(-1, 8)
            vbox.pack_start(weight_bar, False, False, 0)

            # Info label
            info_parts = []
            if is_favorite:
                info_parts.append("★")
            if times_shown > 0:
                info_parts.append(_("{} views").format(times_shown))
            else:
                info_parts.append(_("new"))

            info_label = Gtk.Label()
            info_label.set_markup(
                "<small>{}</small>".format(" · ".join(info_parts) if info_parts else "")
            )
            info_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            vbox.pack_start(info_label, False, False, 0)

            # Add tooltip with full path
            filename = os.path.basename(filepath)
            vbox.set_tooltip_text(
                "{}\nWeight: {:.0%}".format(filename, weight)
            )

            vbox.show_all()
            flowbox.add(vbox)

            # Track for async loading
            image_widgets.append((image, filepath, thumb_size))

        # Load thumbnails asynchronously
        self._load_thumbnails_async(image_widgets)

    def _load_thumbnails_async(self, image_widgets):
        """Load thumbnails in background threads to avoid UI blocking."""
        def load_single_thumbnail(image, filepath, thumb_size):
            """Load a single thumbnail and update the image widget."""
            try:
                if os.path.exists(filepath):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        filepath, thumb_size, thumb_size, True
                    )

                    def _update():
                        try:
                            image.set_from_pixbuf(pixbuf)
                        except Exception:
                            pass  # Widget may have been destroyed
                    GObject.idle_add(_update)
                else:
                    def _show_missing():
                        try:
                            image.set_from_icon_name(
                                "image-missing", Gtk.IconSize.DIALOG
                            )
                        except Exception:
                            pass
                    GObject.idle_add(_show_missing)
            except Exception:
                def _show_error():
                    try:
                        image.set_from_icon_name(
                            "image-missing", Gtk.IconSize.DIALOG
                        )
                    except Exception:
                        pass
                GObject.idle_add(_show_error)

        def _load_all():
            """Load all thumbnails in a thread pool (fire and forget)."""
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as executor:
                for image, filepath, thumb_size in image_widgets:
                    executor.submit(load_single_thumbnail, image, filepath, thumb_size)

        # Start loading in background thread so we don't block
        threading.Thread(target=_load_all, daemon=True).start()

    def _resize_dialog_thumbnails(self, dialog, thumb_size):
        """Resize thumbnails in a dialog without refetching candidates (async)."""
        data = dialog._preview_data
        candidates = data.get('candidates', [])
        if not candidates:
            return

        flowbox = data['flowbox']
        children = flowbox.get_children()

        # Collect image widgets for async resizing
        image_widgets = []

        for i, child in enumerate(children):
            if i >= len(candidates):
                break

            candidate = candidates[i]
            filepath = candidate['filepath']

            # Find the image widget inside the child
            # Structure: FlowBoxChild -> vbox -> frame -> image
            vbox = child.get_child()
            if not vbox:
                continue

            frame = None
            for widget in vbox.get_children():
                if isinstance(widget, Gtk.Frame):
                    frame = widget
                    break

            if not frame:
                continue

            image = frame.get_child()
            if not isinstance(image, Gtk.Image):
                continue

            image_widgets.append((image, filepath, thumb_size))

        # Load resized thumbnails asynchronously
        if image_widgets:
            self._load_thumbnails_async(image_widgets)

    def _refresh_preview_dialog(self, dialog):
        """Refresh the contents of an existing preview dialog."""
        if not dialog or not hasattr(dialog, '_preview_data'):
            return

        data = dialog._preview_data
        flowbox = data.get('flowbox')
        spinner = data.get('spinner')
        status_label = data.get('status_label')
        refresh_button = data.get('refresh_button')

        if not all([flowbox, spinner, status_label, refresh_button]):
            return

        def _load_preview():
            spinner.start()
            spinner.set_visible(True)
            refresh_button.set_sensitive(False)

            try:
                candidates = self.parent.smart_selector.get_preview_candidates(count=60)
                data['candidates'] = candidates

                def _update_ui():
                    self._populate_dialog_flowbox(dialog, candidates)
                    spinner.stop()
                    spinner.set_visible(False)
                    refresh_button.set_sensitive(True)
                    if candidates:
                        status_label.set_text(
                            _("Showing top {} candidates (sorted by selection weight)").format(
                                len(candidates)
                            )
                        )
                    else:
                        status_label.set_text(
                            _("No candidates found. Try rebuilding the index.")
                        )

                GObject.idle_add(_update_ui)

            except Exception as e:
                logger.exception(lambda: "Error refreshing preview")

                def _show_error():
                    spinner.stop()
                    spinner.set_visible(False)
                    refresh_button.set_sensitive(True)
                    status_label.set_text(_("Error refreshing preview"))

                GObject.idle_add(_show_error)

        threading.Thread(target=_load_preview, daemon=True).start()

    def _schedule_preview_refresh(self):
        """Schedule a preview refresh after settings change.

        Debounces rapid changes to avoid excessive refreshes.
        Only refreshes if the preview dialog is currently open.
        """
        if self.loading:
            return

        # Only refresh if preview dialog is currently visible
        if not hasattr(self, '_smart_preview_dialog') or not self._smart_preview_dialog:
            return
        try:
            if not self._smart_preview_dialog.get_visible():
                return
        except Exception:
            return

        # Cancel any pending refresh
        if hasattr(self, '_preview_refresh_timer') and self._preview_refresh_timer:
            self._preview_refresh_timer.cancel()

        # Schedule refresh after a short delay (debounce)
        def _do_refresh():
            if hasattr(self, '_smart_preview_dialog') and self._smart_preview_dialog:
                try:
                    if self._smart_preview_dialog.get_visible():
                        Util.add_mainloop_task(
                            lambda: self._refresh_preview_dialog(self._smart_preview_dialog)
                        )
                except Exception:
                    pass

        self._preview_refresh_timer = threading.Timer(0.5, _do_refresh)
        self._preview_refresh_timer.start()

    # =========================================================================
    # Wallhaven Manager Tab
    # =========================================================================

    def _setup_wallhaven_tab(self):
        """Set up Wallhaven tab toggle handler - called once from reload()."""
        if not hasattr(self, "_wallhaven_toggle_handler_id"):
            self._wallhaven_toggle_handler_id = self.ui.wallhaven_enabled_renderer.connect(
                "toggled", self._on_wallhaven_enabled_toggled, self.ui.wallhaven_liststore
            )

    def _populate_wallhaven_list(self):
        """Populate the Wallhaven list with sources and statistics."""
        self.ui.wallhaven_liststore.clear()

        # Get Wallhaven sources from options
        wallhaven_sources = self.options.get_wallhaven_sources()

        # Get image counts from smart selection database if available
        image_counts = {}
        shown_counts = {}
        if hasattr(self.parent, 'smart_selector') and self.parent.smart_selector:
            try:
                db = self.parent.smart_selector.db
                # Get per-source image counts
                image_counts = db.count_images_per_source('wallhaven_')
                # Get times_shown aggregates per source
                shown_counts = db.get_source_shown_counts('wallhaven_')
            except Exception as e:
                logger.warning(lambda: f"Failed to get Wallhaven stats: {e}")

        # Populate the list
        for source in wallhaven_sources:
            enabled = source[0]
            location = source[2]  # The search query

            # Extract display name from location (the search term)
            display_name = location

            # Convert location to source_id format (wallhaven_<query>)
            source_id = f"wallhaven_{location.lower().replace(' ', '_')}"

            # Get counts for this source
            img_count = image_counts.get(source_id, 0)
            times_shown = shown_counts.get(source_id, 0)

            # Add row: enabled, display_name, location, image_count, times_shown
            self.ui.wallhaven_liststore.append([enabled, display_name, location, img_count, times_shown])

        # Load API key if present
        if hasattr(self.options, 'wallhaven_api_key'):
            self.ui.wallhaven_apikey.set_text(self.options.wallhaven_api_key or "")

    def on_wallhaven_selection_changed(self, selection=None):
        """Handle Wallhaven list selection change - enable/disable Remove button."""
        model, tree_iter = self.ui.wallhaven_selection.get_selected()
        has_selection = tree_iter is not None
        self.ui.wallhaven_remove_button.set_sensitive(has_selection)

    def _on_wallhaven_enabled_toggled(self, widget, path, model):
        """Handle toggle of Wallhaven source enabled state."""
        model[path][0] = not model[path][0]
        location = model[path][2]  # The original query string
        self.options.set_wallhaven_source_enabled(location, model[path][0])
        self.delayed_apply()

    def on_wallhaven_add_clicked(self, widget=None):
        """Show dialog to add a new Wallhaven search term."""
        dialog = Gtk.Dialog(
            title=_("Add Wallhaven Search Term"),
            parent=self,
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )

        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(15)
        content.set_margin_end(15)
        content.set_margin_top(10)
        content.set_margin_bottom(10)

        # Label
        label = Gtk.Label(label=_("Enter a Wallhaven search term:"))
        label.set_halign(Gtk.Align.START)
        content.pack_start(label, False, False, 0)

        # Entry
        entry = Gtk.Entry()
        entry.set_placeholder_text(_("e.g., abstract, nature, minimalist"))
        entry.set_activates_default(True)
        content.pack_start(entry, False, False, 0)

        # Help text
        help_label = Gtk.Label(label=_(
            "Tip: Use Wallhaven search syntax for advanced queries.\n"
            "Examples: 'nature +forest', 'id:123456', 'like:your_username'"
        ))
        help_label.set_halign(Gtk.Align.START)
        help_label.get_style_context().add_class("dim-label")
        content.pack_start(help_label, False, False, 5)

        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()

        response = dialog.run()
        search_term = entry.get_text().strip()
        dialog.destroy()

        if response == Gtk.ResponseType.OK and search_term:
            # Add the new Wallhaven source
            if self.options.add_wallhaven_source(search_term, enabled=True):
                self._populate_wallhaven_list()
                self.delayed_apply()
            else:
                # Source already exists
                error_dialog = Gtk.MessageDialog(
                    parent=self,
                    modal=True,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text=_("Search term already exists"),
                )
                error_dialog.format_secondary_text(
                    _("The search term '{}' is already in your list.").format(search_term)
                )
                error_dialog.run()
                error_dialog.destroy()

    def on_wallhaven_remove_clicked(self, widget=None):
        """Remove the selected Wallhaven search term."""
        model, tree_iter = self.ui.wallhaven_selection.get_selected()
        if tree_iter:
            location = model[tree_iter][2]  # The original query string
            display_name = model[tree_iter][1]

            # Confirm removal
            dialog = Gtk.MessageDialog(
                parent=self,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=_("Remove Wallhaven search term?"),
            )
            dialog.format_secondary_text(
                _("Remove '{}' from your Wallhaven sources?\n\n"
                  "This will not delete any downloaded images.").format(display_name)
            )
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.options.remove_wallhaven_source(location)
                self._populate_wallhaven_list()
                self.delayed_apply()

    def on_wallhaven_refresh_clicked(self, widget=None):
        """Refresh Wallhaven statistics from the database."""
        self._populate_wallhaven_list()

    def on_wallhaven_apikey_changed(self, widget=None):
        """Handle Wallhaven API key change."""
        if self.loading:
            return
        self.options.wallhaven_api_key = self.ui.wallhaven_apikey.get_text().strip()
        self.delayed_apply()
