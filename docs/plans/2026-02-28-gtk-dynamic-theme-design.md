# GTK Dynamic Theme Design

## Goal

Generate a standalone GTK3+4 theme (`Variety-Dynamic`) from wallpaper/theme palettes, auto-switched via gsettings. Same palette flow as existing templates (waybar, alacritty, etc.) but producing a full widget theme.

## Architecture

### Template Pipeline (existing, unchanged)

```
wallpaper change → palette (wallust or theme override)
  → TemplateProcessor processes each template
  → atomic write to target path
  → run reload commands
```

### New Components

1. **`gtk3-theme.css` template** — full GTK3 widget theme using `@define-color` + selectors
2. **`gtk4-theme.css` template** — full GTK4 widget theme using `:root` vars + selectors
3. **`gtk-index.theme`** — static theme metadata (written once)
4. **Scaffold method** — `_ensure_gtk_theme_scaffold()` creates dirs + `index.theme`
5. **gsettings reload** — toggle theme name to force GTK reload

### Output Structure

```
~/.local/share/themes/Variety-Dynamic/
├── index.theme          ← static, written once
├── gtk-3.0/
│   └── gtk.css          ← generated from gtk3-theme.css template
└── gtk-4.0/
    └── gtk.css          ← generated from gtk4-theme.css template
```

### Color Mapping (palette → GTK semantic colors)

| GTK Variable | Source | Notes |
|---|---|---|
| `theme_bg_color` / `window_bg_color` | `{{background}}` | Main window bg |
| `theme_fg_color` / `window_fg_color` | `{{foreground}}` | Main text |
| `theme_base_color` / `view_bg_color` | `{{background \| lighten(0.05)}}` | Input/list bg |
| `theme_text_color` / `view_fg_color` | `{{foreground}}` | Input/list text |
| `headerbar_bg_color` | `{{background \| lighten(0.08)}}` | Headerbar bg |
| `headerbar_fg_color` | `{{foreground}}` | Headerbar text |
| `card_bg_color` / `popover_bg_color` | `{{background \| lighten(0.08)}}` | Elevated surfaces |
| `accent_bg_color` / `selected_bg_color` | `{{color4}}` | Accent/selection |
| `accent_fg_color` / `selected_fg_color` | `{{background}}` | Text on accent |
| `destructive_bg_color` | `{{color1}}` | Red/error actions |
| `warning_bg_color` | `{{color3}}` | Yellow/warning |
| `success_bg_color` | `{{color2}}` | Green/success |

### Widget Coverage

Both templates cover:
- Window, headerbar, titlebar
- Button (normal, hover, active, checked, disabled, suggested-action, destructive-action)
- Entry, search entry (focus ring using accent)
- Treeview, listview, iconview (rows, selection, hover)
- Scrollbar (slider, trough)
- Switch, checkbutton, radiobutton (accent for checked)
- Scale, progressbar (trough, fill)
- Popover, menu, menuitem
- Tooltip (inverted)
- Sidebar (slightly different shade)
- Notebook tabs
- Separator, frame

### Code Changes

| File | Change |
|---|---|
| `data/config/templates/gtk3-theme.css` | New template |
| `data/config/templates/gtk4-theme.css` | New template |
| `data/config/templates/gtk-index.theme` | New static file |
| `variety/smart_selection/theming.py` | Add `gsettings` to `ALLOWED_RELOAD_COMMANDS`; add `gtk-dynamic` to `DEFAULT_RELOADS`; add `_ensure_gtk_theme_scaffold()` |

### Reload Mechanism

```python
# Force GTK to re-read theme files even though the name hasn't changed:
gsettings set org.gnome.desktop.interface gtk-theme ''
gsettings set org.gnome.desktop.interface gtk-theme 'Variety-Dynamic'
```

Also updates `~/.config/gtk-3.0/settings.ini` `gtk-theme-name` for non-GNOME environments.

### Security

- Target dir `~/.local/share/themes/` already under `~/.local` (allowed)
- `gsettings` added to reload command whitelist
- No path traversal — theme name is hardcoded, not user-supplied

## What Doesn't Change

- TemplateProcessor, ColorTransformer — unchanged
- ThemeEngine.apply() flow — unchanged
- ThemeOverride — palette flows through same path
- wallust.toml `[templates]` — user adds entries for the new templates
- Existing colors.css generation — can coexist or be replaced
