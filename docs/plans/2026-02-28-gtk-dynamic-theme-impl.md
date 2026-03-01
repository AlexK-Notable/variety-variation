# GTK Dynamic Theme Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate a standalone `Variety-Dynamic` GTK3+4 theme from wallpaper/theme palettes, auto-switched via gsettings on every wallpaper change.

**Architecture:** Ship two template files (GTK3 and GTK4) processed by the existing ThemeEngine. Templates output to `~/.local/share/themes/Variety-Dynamic/gtk-{3,4}.0/gtk.css`. A scaffold method creates the directory + `index.theme` on first run. A gsettings reload command switches the active theme.

**Tech Stack:** Python 3, GTK3 CSS, GTK4/libadwaita CSS, gsettings (GSettings), existing `TemplateProcessor` with `{{variable | filter}}` syntax.

---

### Task 1: Create GTK3 theme template

**Files:**
- Create: `data/config/templates/gtk3-theme.css`

**Step 1: Write the GTK3 theme template**

Create `data/config/templates/gtk3-theme.css` — a full widget theme template using the `{{variable | filter}}` syntax. This is the template that TemplateProcessor renders with palette data.

Color mapping:
- `background` → `theme_bg_color`, `window_bg_color`, `dialog_bg_color`
- `{{background | lighten(0.05)}}` → `theme_base_color`, `view_bg_color` (inputs, lists)
- `{{background | lighten(0.08)}}` → `headerbar_bg_color`, `card_bg_color`, `popover_bg_color` (elevated surfaces)
- `foreground` → all `*_fg_color` variants
- `color4` → accent/selection colors
- `color1` → destructive, `color2` → success, `color3` → warning

Widget selectors needed (all using `@define-color` references):
- `*` — base color inheritance
- `window` — bg + fg
- `headerbar`, `.titlebar` — elevated surface bg
- `button` — normal, `:hover` (lighten bg 5%), `:active` (darken 5%), `:checked` (accent), `:disabled` (opacity), `.suggested-action` (accent), `.destructive-action` (destructive)
- `entry`, `searchentry` — base color bg, focus ring with accent
- `treeview.view`, `iconview`, `list`, `listview` — row bg, `:selected` (accent), `:hover` (alpha accent)
- `scrollbar slider` — foreground at 0.3 alpha, trough at 0.1 alpha
- `switch` — `:checked` accent, unchecked bg
- `checkbutton check:checked`, `radiobutton radio:checked` — accent
- `scale trough`, `scale highlight` — accent fill
- `progressbar progress` — accent fill
- `popover > contents`, `menu`, `menuitem` — elevated bg, hover state
- `tooltip` — inverted (fg bg, bg fg)
- `notebook > header > tabs > tab` — inactive muted, `:checked` base color
- `separator` — fg at 0.15 alpha
- `placessidebar`, `.sidebar` — slightly different shade from main

**Step 2: Verify template parses**

```bash
python -c "
from variety.smart_selection.theming import TemplateProcessor
palette = {f'color{i}': f'#{"aa" if i < 8 else "cc"}{i:02x}{i:02x}' for i in range(16)}
palette.update({'background': '#1a1b26', 'foreground': '#c0caf5', 'cursor': '#c0caf5'})
p = TemplateProcessor(palette)
with open('data/config/templates/gtk3-theme.css') as f:
    result = p.process(f.read())
assert '@define-color theme_bg_color #1a1b26' in result
assert 'window {' in result
print('OK: Template parses, %d bytes output' % len(result))
"
```

**Step 3: Commit**

```bash
git add data/config/templates/gtk3-theme.css
git commit -m "feat(theming): add GTK3 dynamic theme template"
```

---

### Task 2: Create GTK4 theme template

**Files:**
- Create: `data/config/templates/gtk4-theme.css`

**Step 1: Write the GTK4 theme template**

GTK4 template uses `:root { }` CSS custom properties alongside `@define-color` for backward compat. Widget selectors differ slightly from GTK3:
- No `treeview.view` → use `listview > row`, `columnview > row`
- No `.sidebar` class → use `placessidebar`, `stacksidebar`
- Use `button.flat` for flat button variants
- GTK4 supports standard CSS `border-radius`, `box-shadow`, `transition`

The template should define the same `@define-color` variables as GTK3 (libadwaita reads these), plus `:root { --accent-bg-color: ...; }` variables for apps using CSS vars.

Same color mapping as Task 1.

**Step 2: Verify template parses**

```bash
python -c "
from variety.smart_selection.theming import TemplateProcessor
palette = {f'color{i}': f'#{"aa" if i < 8 else "cc"}{i:02x}{i:02x}' for i in range(16)}
palette.update({'background': '#1a1b26', 'foreground': '#c0caf5', 'cursor': '#c0caf5'})
p = TemplateProcessor(palette)
with open('data/config/templates/gtk4-theme.css') as f:
    result = p.process(f.read())
assert ':root {' in result
assert 'window' in result
print('OK: GTK4 template parses, %d bytes output' % len(result))
"
```

**Step 3: Commit**

```bash
git add data/config/templates/gtk4-theme.css
git commit -m "feat(theming): add GTK4 dynamic theme template"
```

---

### Task 3: Create index.theme static file

**Files:**
- Create: `data/config/templates/gtk-index.theme`

**Step 1: Write the index.theme file**

```ini
[Desktop Entry]
Type=X-GNOME-Metatheme
Name=Variety-Dynamic
Comment=Dynamically generated theme from wallpaper colors
Encoding=UTF-8

[X-GNOME-Metatheme]
GtkTheme=Variety-Dynamic
MetacityTheme=Adwaita
IconTheme=hicolor
CursorTheme=default
```

**Step 2: Commit**

```bash
git add data/config/templates/gtk-index.theme
git commit -m "feat(theming): add index.theme for Variety-Dynamic GTK theme"
```

---

### Task 4: Add gsettings to reload infrastructure

**Files:**
- Modify: `variety/smart_selection/theming.py:382-434`

**Step 1: Write test for gsettings in allowlist**

Create test in existing test file or verify inline:

```bash
python -c "
from variety.smart_selection.theming import SAFE_RELOAD_EXECUTABLES, DEFAULT_RELOADS
assert 'gsettings' in SAFE_RELOAD_EXECUTABLES, 'gsettings not in allowlist'
assert 'gtk3-dynamic' in DEFAULT_RELOADS, 'gtk3-dynamic not in DEFAULT_RELOADS'
assert 'gtk4-dynamic' in DEFAULT_RELOADS, 'gtk4-dynamic not in DEFAULT_RELOADS'
assert 'gsettings' in DEFAULT_RELOADS['gtk3-dynamic'], 'Wrong reload command'
print('OK')
"
```

Expected: FAIL (not added yet).

**Step 2: Add gsettings to `SAFE_RELOAD_EXECUTABLES` and add reload entries**

In `variety/smart_selection/theming.py`:

1. Add `"gsettings"` to `SAFE_RELOAD_EXECUTABLES` (line 382-386)
2. Replace the `"gtk3": None` and `"gtk4": None` entries in `DEFAULT_RELOADS` with:

```python
    # GTK dynamic theme (gsettings toggle forces reload)
    "gtk3": None,  # Legacy: color-only override, no reload needed
    "gtk4": None,
    "gtk3-dynamic": "gsettings set org.gnome.desktop.interface gtk-theme Variety-Dynamic",
    "gtk4-dynamic": "gsettings set org.gnome.desktop.interface gtk-theme Variety-Dynamic",
```

Both GTK3 and GTK4 entries point to the same gsettings command since one setting controls both.

**Step 3: Run verification**

```bash
python -c "
from variety.smart_selection.theming import SAFE_RELOAD_EXECUTABLES, DEFAULT_RELOADS
assert 'gsettings' in SAFE_RELOAD_EXECUTABLES
assert 'gtk3-dynamic' in DEFAULT_RELOADS
print('OK')
"
```

**Step 4: Commit**

```bash
git add variety/smart_selection/theming.py
git commit -m "feat(theming): add gsettings to reload allowlist for GTK dynamic theme"
```

---

### Task 5: Add scaffold method to ThemeEngine

**Files:**
- Modify: `variety/smart_selection/theming.py` (ThemeEngine class)
- Test: verify scaffold creates correct directory structure

**Step 1: Write test**

```bash
python -c "
import tempfile, os
from unittest.mock import patch, MagicMock

# Test that scaffold creates the directory structure
theme_dir = tempfile.mkdtemp() + '/Variety-Dynamic'
with patch.object(
    __import__('variety.smart_selection.theming', fromlist=['ThemeEngine']).ThemeEngine,
    'GTK_THEME_DIR', theme_dir
):
    from variety.smart_selection.theming import ThemeEngine
    engine = ThemeEngine.__new__(ThemeEngine)
    engine.GTK_THEME_DIR = theme_dir
    engine._ensure_gtk_theme_scaffold()

    assert os.path.isdir(os.path.join(theme_dir, 'gtk-3.0')), 'gtk-3.0 dir missing'
    assert os.path.isdir(os.path.join(theme_dir, 'gtk-4.0')), 'gtk-4.0 dir missing'
    assert os.path.isfile(os.path.join(theme_dir, 'index.theme')), 'index.theme missing'
    with open(os.path.join(theme_dir, 'index.theme')) as f:
        content = f.read()
    assert 'Variety-Dynamic' in content
    print('OK: scaffold creates correct structure')
"
```

Expected: FAIL (method doesn't exist yet).

**Step 2: Add `GTK_THEME_DIR` class constant and `_ensure_gtk_theme_scaffold()` method**

Add to the ThemeEngine class (after the existing class constants around line 463-469):

```python
    # GTK dynamic theme output directory
    GTK_THEME_DIR = os.path.expanduser('~/.local/share/themes/Variety-Dynamic')
    GTK_INDEX_THEME = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'config', 'templates', 'gtk-index.theme'
    )
```

Add method to the class (near `_write_atomic`):

```python
    def _ensure_gtk_theme_scaffold(self) -> None:
        """Create the Variety-Dynamic theme directory and index.theme if missing.

        Called before writing GTK theme CSS files. Creates:
        - ~/.local/share/themes/Variety-Dynamic/gtk-3.0/
        - ~/.local/share/themes/Variety-Dynamic/gtk-4.0/
        - ~/.local/share/themes/Variety-Dynamic/index.theme
        """
        index_path = os.path.join(self.GTK_THEME_DIR, 'index.theme')
        if os.path.exists(index_path):
            return

        for subdir in ('gtk-3.0', 'gtk-4.0'):
            os.makedirs(os.path.join(self.GTK_THEME_DIR, subdir), exist_ok=True)

        # Copy bundled index.theme
        if os.path.exists(self.GTK_INDEX_THEME):
            import shutil
            shutil.copy2(self.GTK_INDEX_THEME, index_path)
        else:
            # Fallback: write minimal index.theme inline
            with open(index_path, 'w') as f:
                f.write(
                    "[Desktop Entry]\n"
                    "Type=X-GNOME-Metatheme\n"
                    "Name=Variety-Dynamic\n"
                    "Comment=Dynamically generated theme from wallpaper colors\n"
                    "Encoding=UTF-8\n\n"
                    "[X-GNOME-Metatheme]\n"
                    "GtkTheme=Variety-Dynamic\n"
                    "MetacityTheme=Adwaita\n"
                    "IconTheme=hicolor\n"
                    "CursorTheme=default\n"
                )
        logger.info("Created GTK theme scaffold at %s", self.GTK_THEME_DIR)
```

**Step 3: Call scaffold from `_apply_immediate()`**

In `_apply_immediate()` (line ~1013), before processing templates, add:

```python
        # Ensure GTK theme directory exists before writing CSS
        self._ensure_gtk_theme_scaffold()
```

This is safe to call on every apply — it returns immediately if `index.theme` exists.

**Step 4: Run verification**

```bash
python -c "
from variety.smart_selection.theming import ThemeEngine
assert hasattr(ThemeEngine, '_ensure_gtk_theme_scaffold')
assert hasattr(ThemeEngine, 'GTK_THEME_DIR')
print('OK')
"
```

**Step 5: Commit**

```bash
git add variety/smart_selection/theming.py
git commit -m "feat(theming): add GTK theme scaffold to ThemeEngine"
```

---

### Task 6: Add unit tests for GTK theme integration

**Files:**
- Create: `tests/smart_selection/test_gtk_theme.py`

**Step 1: Write tests**

Test cases:
1. `test_gtk3_template_renders_all_widget_selectors` — template processing produces expected CSS selectors
2. `test_gtk4_template_renders_root_vars` — GTK4 template produces `:root { }` block
3. `test_scaffold_creates_structure` — directory + index.theme created
4. `test_scaffold_idempotent` — second call is a no-op
5. `test_gsettings_in_allowlist` — gsettings is whitelisted
6. `test_gtk_dynamic_reload_command` — DEFAULT_RELOADS has correct entries

**Step 2: Run tests**

```bash
python -m pytest tests/smart_selection/test_gtk_theme.py -v
```

**Step 3: Commit**

```bash
git add tests/smart_selection/test_gtk_theme.py
git commit -m "test(theming): add GTK dynamic theme tests"
```

---

### Task 7: Install templates and verify end-to-end

**Files:**
- No code changes — manual verification steps

**Step 1: Copy templates to wallust templates dir**

```bash
cp data/config/templates/gtk3-theme.css ~/.config/wallust/templates/gtk3-dynamic.css
cp data/config/templates/gtk4-theme.css ~/.config/wallust/templates/gtk4-dynamic.css
```

**Step 2: Add entries to wallust.toml**

Add to `~/.config/wallust/wallust.toml` under `[templates]`:

```toml
gtk3-dynamic = { template = "gtk3-dynamic.css", target = "~/.local/share/themes/Variety-Dynamic/gtk-3.0/gtk.css" }
gtk4-dynamic = { template = "gtk4-dynamic.css", target = "~/.local/share/themes/Variety-Dynamic/gtk-4.0/gtk.css" }
```

**Step 3: Test template processing manually**

```bash
python -c "
from variety.smart_selection.theming import ThemeEngine
engine = ThemeEngine(lambda p: None)
# Check that gtk3-dynamic and gtk4-dynamic appear in loaded templates
names = [t.name for t in engine._templates]
print('Loaded templates:', names)
assert 'gtk3-dynamic' in names, 'gtk3-dynamic not loaded from wallust.toml'
assert 'gtk4-dynamic' in names, 'gtk4-dynamic not loaded from wallust.toml'
print('OK')
"
```

**Step 4: Run full test suite to verify no regressions**

```bash
python -m pytest tests/ -q --ignore=tests/db_browser --ignore=tests/smart_selection/benchmarks
```

**Step 5: Commit all remaining changes**

```bash
git add -A
git commit -m "feat(theming): complete GTK dynamic theme integration"
```
