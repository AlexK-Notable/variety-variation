# Preferences UI - Implementation Plan

**Date:** 2025-12-08
**Status:** Planned
**Agent:** 5cf7b8cf

---

## Current Structure

The Smart Selection tab already exists with:
- Enable Smart Selection checkbox
- Selection Behavior section (cooldowns, boosts, decay type)
- Color Preferences section (temperature, similarity)
- Statistics section
- Action Buttons (Rebuild, Extract, Clear)
- Preview section

**Missing:** Theming Engine section

---

## What Needs to Be Added

### 1. `smart_theming_enabled` in Options.py

**In `set_defaults()` (~line 760):**
```python
self.smart_theming_enabled = True
```

**In `read()` (~line 355):**
```python
try:
    self.smart_theming_enabled = config["smart_theming_enabled"].lower() in TRUTH_VALUES
except Exception:
    pass
```

**In `write()` (~line 893):**
```python
config["smart_theming_enabled"] = str(self.smart_theming_enabled)
```

### 2. Theming Engine Section in UI

Add to `PreferencesVarietyDialog.ui` after position 13:

```xml
<!-- Theming Engine Section -->
<child>
  <object class="GtkLabel" id="smart_theming_label">
    <property name="visible">True</property>
    <property name="halign">start</property>
    <property name="margin_left">15</property>
    <property name="margin_top">15</property>
    <property name="label" translatable="yes">Theming Engine</property>
    <attributes>
      <attribute name="weight" value="bold"/>
    </attributes>
  </object>
  <packing>
    <property name="position">14</property>
  </packing>
</child>

<child>
  <object class="GtkCheckButton" id="smart_theming_enabled">
    <property name="label" translatable="yes">Enable instant theme switching</property>
    <property name="visible">True</property>
    <property name="margin_left">30</property>
    <property name="tooltip_text" translatable="yes">Apply wallust templates automatically when wallpaper changes.</property>
    <signal name="toggled" handler="delayed_apply"/>
    <signal name="toggled" handler="on_smart_theming_enabled_toggled"/>
  </object>
  <packing>
    <property name="position">15</property>
  </packing>
</child>

<child>
  <object class="GtkBox" id="smart_theming_templates_box">
    <property name="visible">True</property>
    <property name="margin_left">30</property>
    <property name="margin_right">15</property>
    <property name="spacing">10</property>
    <child>
      <object class="GtkLabel" id="smart_theming_templates_label">
        <property name="visible">True</property>
        <property name="halign">start</property>
        <property name="label" translatable="yes">Templates: 0 configured</property>
      </object>
    </child>
    <child>
      <object class="GtkButton" id="smart_theming_configure">
        <property name="label" translatable="yes">Configure...</property>
        <property name="visible">True</property>
        <property name="tooltip_text" translatable="yes">Open theming configuration.</property>
        <signal name="clicked" handler="on_smart_theming_configure_clicked"/>
      </object>
    </child>
  </object>
  <packing>
    <property name="position">16</property>
  </packing>
</child>

<child>
  <object class="GtkLabel" id="smart_theming_description">
    <property name="visible">True</property>
    <property name="halign">start</property>
    <property name="margin_left">30</property>
    <property name="margin_right">30</property>
    <property name="margin_top">5</property>
    <property name="label" translatable="yes">Uses wallust to generate terminal, bar, and app themes from wallpaper colors.</property>
    <property name="wrap">True</property>
    <property name="max_width_chars">60</property>
    <style>
      <class name="dim-label"/>
    </style>
  </object>
  <packing>
    <property name="position">17</property>
  </packing>
</child>
```

### 3. Signal Handlers

**In `reload()` (~line 358):**
```python
if hasattr(self.options, 'smart_theming_enabled'):
    self.ui.smart_theming_enabled.set_active(self.options.smart_theming_enabled)
self.update_smart_theming_templates_label()
```

**In `apply()` (~line 1209):**
```python
if hasattr(self.ui, 'smart_theming_enabled'):
    self.options.smart_theming_enabled = self.ui.smart_theming_enabled.get_active()
```

**New handlers (~line 1463):**
```python
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
        logger.exception(f"Could not open {target}")
```

---

## Tooltips

| Widget | Tooltip |
|--------|---------|
| smart_selection_enabled | Use intelligent wallpaper selection based on viewing history, favorites, and sources. |
| smart_image_cooldown | How many days to wait before showing the same wallpaper again. |
| smart_source_cooldown | How many days to prefer different sources before repeating. |
| smart_favorite_boost | How much more likely favorites are to be selected. |
| smart_new_boost | How much more likely never-seen images are to be selected. |
| smart_color_enabled | Select wallpapers based on color palette similarity. |
| smart_color_temperature | Prefer warm, cool, neutral, or time-adaptive palettes. |
| smart_color_similarity | How closely colors must match the target palette. |
| smart_theming_enabled | Apply wallust templates automatically when wallpaper changes. |

---

## Validation Logic

| Setting | Range | Default |
|---------|-------|---------|
| Image Cooldown | 0-30 days | 7 |
| Source Cooldown | 0-7 days | 1 |
| Favorite Boost | 1.0x-5.0x | 2.0 |
| New Image Boost | 1.0x-3.0x | 1.5 |
| Color Similarity | 0-100% | 70 |

All validation uses min/max clamping in Options.py.

---

## Files to Modify

1. **`variety/Options.py`** - Add `smart_theming_enabled` option
2. **`data/ui/PreferencesVarietyDialog.ui`** - Add theming section widgets
3. **`variety/PreferencesVarietyDialog.py`** - Add signal handlers and bindings
