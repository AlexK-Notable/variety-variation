# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Theming engine for pre-generating wallust templates.

Pre-generates wallust templates from cached palette data for instant
theme switching on wallpaper change.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List, Callable

# TOML parsing - try stdlib first (Python 3.11+), then tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore

from variety.smart_selection.palette import hex_to_hsl, hsl_to_hex

logger = logging.getLogger(__name__)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple.

    Args:
        hex_color: Hex color string like "#FF0000" or "FF0000".

    Returns:
        Tuple of (r, g, b) integers 0-255.
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex color string.

    Args:
        r: Red value 0-255.
        g: Green value 0-255.
        b: Blue value 0-255.

    Returns:
        Hex color string like "#ff0000".
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class ColorTransformer:
    """Applies color transformations/filters to hex colors.

    Supports all wallust filter operations:
    - strip: Remove # prefix
    - darken(n): Reduce lightness by n (0-1)
    - lighten(n): Increase lightness by n (0-1)
    - saturate(n): Increase saturation by n (0-1.5)
    - desaturate(n): Decrease saturation by n (0-1)
    - blend(colorN): Average RGB with another palette color
    """

    def __init__(self, palette: Dict[str, str]):
        """Initialize with a palette for color references.

        Args:
            palette: Dict mapping color names to hex values.
                     Keys like 'color0', 'background', 'foreground', etc.
        """
        self.palette = palette

    def strip(self, color: str) -> str:
        """Remove # prefix from color.

        Args:
            color: Hex color string.

        Returns:
            Color without # prefix.
        """
        return color.lstrip('#')

    def darken(self, color: str, amount: float) -> str:
        """Reduce lightness of a color.

        Args:
            color: Hex color string.
            amount: Amount to reduce lightness (0-1).

        Returns:
            Darkened hex color.
        """
        h, s, l = hex_to_hsl(color)
        l = max(0.0, l - amount)
        return hsl_to_hex(h, s, l)

    def lighten(self, color: str, amount: float) -> str:
        """Increase lightness of a color.

        Args:
            color: Hex color string.
            amount: Amount to increase lightness (0-1).

        Returns:
            Lightened hex color.
        """
        h, s, l = hex_to_hsl(color)
        l = min(1.0, l + amount)
        return hsl_to_hex(h, s, l)

    def saturate(self, color: str, amount: float) -> str:
        """Increase saturation of a color.

        Args:
            color: Hex color string.
            amount: Amount to increase saturation (0-1.5).

        Returns:
            More saturated hex color.
        """
        h, s, l = hex_to_hsl(color)
        s = min(1.0, s + amount)
        return hsl_to_hex(h, s, l)

    def desaturate(self, color: str, amount: float) -> str:
        """Decrease saturation of a color.

        Args:
            color: Hex color string.
            amount: Amount to decrease saturation (0-1).

        Returns:
            Less saturated hex color.
        """
        h, s, l = hex_to_hsl(color)
        s = max(0.0, s - amount)
        return hsl_to_hex(h, s, l)

    def blend(self, color: str, other_color_name: str) -> str:
        """Blend color with another palette color by averaging RGB.

        Args:
            color: Hex color string.
            other_color_name: Name of palette color to blend with
                             (e.g., 'color2', 'background').

        Returns:
            Blended hex color. If other_color not found, returns original.
        """
        other_hex = self.palette.get(other_color_name)
        if not other_hex:
            logger.warning(f"Blend: color '{other_color_name}' not in palette")
            return color

        r1, g1, b1 = hex_to_rgb(color)
        r2, g2, b2 = hex_to_rgb(other_hex)

        r = (r1 + r2) // 2
        g = (g1 + g2) // 2
        b = (b1 + b2) // 2

        return rgb_to_hex(r, g, b)

    def apply_filter(self, color: str, filter_expr: str) -> str:
        """Apply a single filter expression to a color.

        Args:
            color: Hex color string.
            filter_expr: Filter expression like 'darken(0.2)' or 'strip'.

        Returns:
            Transformed color.
        """
        filter_expr = filter_expr.strip()

        # Handle strip (no arguments)
        if filter_expr == 'strip':
            return self.strip(color)

        # Parse filter with argument: name(arg)
        match = re.match(r'(\w+)\s*\(\s*([^)]+)\s*\)', filter_expr)
        if not match:
            logger.warning(f"Invalid filter expression: {filter_expr}")
            return color

        name = match.group(1)
        arg = match.group(2).strip()

        try:
            if name == 'darken':
                return self.darken(color, float(arg))
            elif name == 'lighten':
                return self.lighten(color, float(arg))
            elif name == 'saturate':
                return self.saturate(color, float(arg))
            elif name == 'desaturate':
                return self.desaturate(color, float(arg))
            elif name == 'blend':
                return self.blend(color, arg)
            else:
                logger.warning(f"Unknown filter: {name}")
                return color
        except ValueError as e:
            logger.warning(f"Invalid filter argument: {filter_expr} ({e})")
            return color

    def apply_filters(self, color: str, filters: list) -> str:
        """Apply multiple filters in sequence (left to right).

        Args:
            color: Hex color string.
            filters: List of filter expressions.

        Returns:
            Final transformed color.
        """
        result = color
        for f in filters:
            result = self.apply_filter(result, f)
        return result


class TemplateProcessor:
    """Processes wallust templates, replacing variables with colors.

    Handles syntax:
    - {{variable}} - simple color substitution
    - {{variable | filter1 | filter2}} - color with filter chain
    - {# comment #} - template comments (stripped from output)
    """

    # Regex patterns (compiled for performance)
    COMMENT_PATTERN = re.compile(r'\{#.*?#\}', re.DOTALL)
    VARIABLE_PATTERN = re.compile(r'\{\{\s*([^}|]+?)(?:\s*\|\s*([^}]+))?\s*\}\}')

    def __init__(self, palette: Dict[str, str]):
        """Initialize with a palette.

        Args:
            palette: Dict mapping color names to hex values.
        """
        self.palette = palette
        self.transformer = ColorTransformer(palette)

    def _resolve_variable(self, var_name: str) -> Optional[str]:
        """Resolve a variable name to its color value.

        Args:
            var_name: Variable name like 'color0', 'background'.

        Returns:
            Hex color value or None if not found.
        """
        var_name = var_name.strip()
        return self.palette.get(var_name)

    def _parse_filters(self, filter_str: str) -> list:
        """Parse a filter chain string into individual filters.

        Args:
            filter_str: String like 'saturate(0.3) | darken(0.2) | strip'.

        Returns:
            List of filter expressions.
        """
        if not filter_str:
            return []
        return [f.strip() for f in filter_str.split('|') if f.strip()]

    def _replace_variable(self, match: re.Match) -> str:
        """Replace a single {{variable | filters}} match.

        Args:
            match: Regex match object.

        Returns:
            Processed color value.
        """
        var_name = match.group(1)
        filter_str = match.group(2)

        color = self._resolve_variable(var_name)
        if color is None:
            logger.warning(f"Unknown variable: {var_name}")
            # Return original placeholder for unknown variables
            return match.group(0)

        # Apply filters if any
        if filter_str:
            filters = self._parse_filters(filter_str)
            color = self.transformer.apply_filters(color, filters)

        return color

    def process(self, template: str) -> str:
        """Process a template string, replacing all variables.

        Args:
            template: Template content with {{variable}} placeholders.

        Returns:
            Processed template with colors substituted.
        """
        # Strip comments first
        result = self.COMMENT_PATTERN.sub('', template)

        # Replace all variables
        result = self.VARIABLE_PATTERN.sub(self._replace_variable, result)

        return result

    def process_file(self, template_path: str) -> Optional[str]:
        """Process a template file.

        Args:
            template_path: Path to template file.

        Returns:
            Processed content or None if file not found.
        """
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            return self.process(template)
        except FileNotFoundError:
            logger.warning(f"Template file not found: {template_path}")
            return None
        except Exception as e:
            logger.error(f"Error processing template {template_path}: {e}")
            return None


def colors_equivalent(hex1: str, hex2: str, tolerance: int = 1) -> bool:
    """Check if two colors are equivalent within RGB tolerance.

    Used for comparison testing to allow ±1 rounding differences.

    Args:
        hex1: First hex color.
        hex2: Second hex color.
        tolerance: Maximum difference per channel (default 1).

    Returns:
        True if colors are within tolerance.
    """
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    return (
        abs(r1 - r2) <= tolerance and
        abs(g1 - g2) <= tolerance and
        abs(b1 - b2) <= tolerance
    )


# Default reload commands for common applications
DEFAULT_RELOADS: Dict[str, Optional[str]] = {
    # Window managers / Compositors
    "hyprland": "hyprctl reload",
    "sway": "swaymsg reload",
    "i3": "i3-msg reload",

    # Bars
    "waybar": "killall -SIGUSR2 waybar",
    "polybar": "polybar-msg cmd restart",

    # Terminals (auto-reload on file change)
    "alacritty": None,
    "kitty": "killall -SIGUSR1 kitty",
    "foot": None,
    "ghostty": None,

    # GTK (apps pick up on next window open)
    "gtk3": None,
    "gtk4": None,

    # Qt theming
    "qt5ct": None,      # Apps pick up on next launch
    "qt6ct": None,
    "kvantum": "kvantummanager --set Wallust",
    "kdeglobals": None,  # KDE apps pick up dynamically

    # Launchers
    "rofi": None,       # Picks up on next launch
    "wofi": None,
    "walker": None,

    # Notifications
    "dunst": "killall dunst; dunst &",
    "mako": "makoctl reload",

    # App-specific
    "zed_theme": None,  # Zed watches theme files
    "vesktop": None,    # Discord clients need manual reload or restart
    "discord": None,
    "hyprswitch": None,
    "launcher_panels": None,
    "ignomi": None,
    "zathura": None,
}


@dataclass
class TemplateConfig:
    """Configuration for a single template."""
    name: str                    # Template identifier (e.g., 'hyprland')
    template_path: str           # Path to template file
    target_path: str             # Path to write output
    reload_command: Optional[str] = None  # Command to reload app
    enabled: bool = True         # Whether to process this template


@dataclass
class CachedTemplate:
    """Cached template content with mtime for invalidation."""
    content: str
    mtime: float


class ThemeEngine:
    """Orchestrates theme generation from palette data.

    Reads wallust.toml for template definitions, processes templates
    using cached palette data, writes to target paths, and triggers
    reload commands.

    Performance target: <20ms for all templates.
    """

    # Configuration paths
    WALLUST_CONFIG = os.path.expanduser('~/.config/wallust/wallust.toml')
    WALLUST_TEMPLATES_DIR = os.path.expanduser('~/.config/wallust/templates')
    VARIETY_CONFIG = os.path.expanduser('~/.config/variety/theming.json')

    # Debounce window in seconds
    DEBOUNCE_INTERVAL = 0.1

    # Reload command timeout in seconds
    RELOAD_TIMEOUT = 5.0

    def __init__(
        self,
        get_palette_callback: Callable[[str], Optional[Dict[str, str]]],
        wallust_config_path: Optional[str] = None,
        variety_config_path: Optional[str] = None,
    ):
        """Initialize the theme engine.

        Args:
            get_palette_callback: Function that takes an image path and returns
                                  a palette dict (color0-15, background, foreground, cursor).
            wallust_config_path: Override path to wallust.toml (for testing).
            variety_config_path: Override path to theming.json (for testing).
        """
        self.get_palette = get_palette_callback
        self.wallust_config_path = wallust_config_path or self.WALLUST_CONFIG
        self.variety_config_path = variety_config_path or self.VARIETY_CONFIG

        # Template cache: name -> CachedTemplate
        self._template_cache: Dict[str, CachedTemplate] = {}

        # Debouncing state
        self._last_apply_time: float = 0.0
        self._pending_image: Optional[str] = None
        self._debounce_lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None

        # Load configurations
        self._templates: List[TemplateConfig] = []
        self._enabled = True
        self._reload()

    def _reload(self) -> None:
        """Reload all configuration from disk."""
        self._templates = self._load_templates()
        self._load_variety_config()

    def _load_templates(self) -> List[TemplateConfig]:
        """Load template definitions from wallust.toml.

        Returns:
            List of TemplateConfig objects.
        """
        templates = []

        if not os.path.exists(self.wallust_config_path):
            logger.warning(f"Wallust config not found: {self.wallust_config_path}")
            return templates

        try:
            config = self._parse_toml(self.wallust_config_path)
            if config is None:
                return templates

            templates_section = config.get('templates', {})
            for name, entry in templates_section.items():
                if not isinstance(entry, dict):
                    logger.warning(f"Invalid template entry: {name}")
                    continue

                template_file = entry.get('template')
                target_path = entry.get('target')

                if not template_file or not target_path:
                    logger.warning(f"Template {name} missing 'template' or 'target'")
                    continue

                # Resolve template path (relative to wallust templates dir)
                if not os.path.isabs(template_file):
                    template_path = os.path.join(
                        self.WALLUST_TEMPLATES_DIR, template_file
                    )
                else:
                    template_path = template_file

                # Expand ~ in target path
                target_path = os.path.expanduser(target_path)

                # Get reload command from defaults
                reload_cmd = DEFAULT_RELOADS.get(name)

                templates.append(TemplateConfig(
                    name=name,
                    template_path=template_path,
                    target_path=target_path,
                    reload_command=reload_cmd,
                    enabled=True,
                ))

            logger.debug(f"Loaded {len(templates)} templates from wallust.toml")

        except Exception as e:
            logger.error(f"Error loading wallust config: {e}")

        return templates

    def _parse_toml(self, path: str) -> Optional[Dict[str, Any]]:
        """Parse a TOML file.

        Args:
            path: Path to TOML file.

        Returns:
            Parsed dict or None on error.
        """
        if tomllib is None:
            logger.warning("No TOML parser available (install tomli for Python <3.11)")
            return self._parse_toml_fallback(path)

        try:
            with open(path, 'rb') as f:
                return tomllib.load(f)
        except Exception as e:
            logger.error(f"Error parsing TOML {path}: {e}")
            return None

    def _parse_toml_fallback(self, path: str) -> Optional[Dict[str, Any]]:
        """Fallback TOML parser for [templates] section only.

        This is a minimal parser that handles the wallust.toml [templates] format:
            name = { template = "file.conf", target = "/path/to/output" }

        Args:
            path: Path to TOML file.

        Returns:
            Dict with 'templates' key or None on error.
        """
        result: Dict[str, Any] = {'templates': {}}
        in_templates_section = False

        # Patterns for inline table - handle both orders:
        # name = { template = "...", target = "..." }
        # name = { target = "...", template = "..." }
        pattern_template_first = re.compile(
            r'^(\w+)\s*=\s*\{\s*'
            r'template\s*=\s*"([^"]+)"\s*,\s*'
            r'target\s*=\s*"([^"]+)"\s*\}'
        )
        pattern_target_first = re.compile(
            r'^(\w+)\s*=\s*\{\s*'
            r'target\s*=\s*"([^"]+)"\s*,\s*'
            r'template\s*=\s*"([^"]+)"\s*\}'
        )

        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()

                    # Check for section headers
                    if line.startswith('['):
                        in_templates_section = (line == '[templates]')
                        continue

                    if not in_templates_section:
                        continue

                    # Try template-first order
                    match = pattern_template_first.match(line)
                    if match:
                        result['templates'][match.group(1)] = {
                            'template': match.group(2),
                            'target': match.group(3),
                        }
                        continue

                    # Try target-first order
                    match = pattern_target_first.match(line)
                    if match:
                        result['templates'][match.group(1)] = {
                            'template': match.group(3),  # Note: swapped
                            'target': match.group(2),
                        }

            return result
        except Exception as e:
            logger.error(f"Error in fallback TOML parsing: {e}")
            return None

    def _load_variety_config(self) -> None:
        """Load variety theming.json config for enable/disable overrides."""
        if not os.path.exists(self.variety_config_path):
            # No config file = all enabled by default
            return

        try:
            with open(self.variety_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Global enable/disable
            self._enabled = config.get('enabled', True)

            # Per-template enable/disable
            template_overrides = config.get('templates', {})
            for template in self._templates:
                if template.name in template_overrides:
                    template.enabled = bool(template_overrides[template.name])

            # Reload command overrides
            reload_overrides = config.get('reload_commands', {})
            for template in self._templates:
                if template.name in reload_overrides:
                    template.reload_command = reload_overrides[template.name]

            logger.debug(f"Loaded variety theming config: enabled={self._enabled}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {self.variety_config_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading variety config: {e}")

    def _get_cached_template(self, config: TemplateConfig) -> Optional[str]:
        """Get template content, using cache if valid.

        Args:
            config: Template configuration.

        Returns:
            Template content or None if file not found.
        """
        path = config.template_path

        try:
            current_mtime = os.path.getmtime(path)
        except FileNotFoundError:
            logger.warning(f"Template file not found: {path}")
            return None

        # Check cache
        cached = self._template_cache.get(config.name)
        if cached and cached.mtime == current_mtime:
            return cached.content

        # Load and cache
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._template_cache[config.name] = CachedTemplate(
                content=content,
                mtime=current_mtime,
            )
            return content
        except Exception as e:
            logger.error(f"Error reading template {path}: {e}")
            return None

    def _write_atomic(self, path: str, content: str) -> bool:
        """Write content to file atomically using temp file + rename.

        Args:
            path: Target file path.
            content: Content to write.

        Returns:
            True if successful.
        """
        # Ensure parent directory exists
        parent_dir = os.path.dirname(path)
        if parent_dir:
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except PermissionError:
                logger.error(f"Permission denied creating directory: {parent_dir}")
                return False

        # Write to temp file then rename (atomic on POSIX)
        try:
            fd, temp_path = tempfile.mkstemp(dir=parent_dir)
            try:
                os.write(fd, content.encode('utf-8'))
            finally:
                os.close(fd)

            os.rename(temp_path, path)
            return True

        except PermissionError:
            logger.error(f"Permission denied writing to: {path}")
            return False
        except Exception as e:
            logger.error(f"Error writing {path}: {e}")
            # Clean up temp file if it exists
            try:
                if 'temp_path' in locals():
                    os.unlink(temp_path)
            except Exception:
                pass
            return False

    def _run_reload_command(self, command: str, template_name: str) -> None:
        """Run a reload command with timeout.

        Args:
            command: Shell command to execute.
            template_name: Name of template (for logging).
        """
        try:
            subprocess.run(
                command,
                shell=True,
                timeout=self.RELOAD_TIMEOUT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(f"Reload command succeeded for {template_name}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Reload command timed out for {template_name}: {command}")
        except Exception as e:
            logger.warning(f"Reload command failed for {template_name}: {e}")

    def apply(self, image_path: str, debounce: bool = True) -> bool:
        """Apply theme for an image.

        Looks up palette, processes all enabled templates, writes outputs,
        and triggers reload commands.

        Args:
            image_path: Path to the wallpaper image.
            debounce: If True, debounce rapid calls (default True).

        Returns:
            True if at least one template was processed successfully.
        """
        if not self._enabled:
            logger.debug("Theming engine disabled")
            return False

        if debounce:
            return self._apply_debounced(image_path)
        else:
            return self._apply_immediate(image_path)

    def _apply_debounced(self, image_path: str) -> bool:
        """Apply with debouncing for rapid wallpaper changes.

        Args:
            image_path: Path to the wallpaper image.

        Returns:
            True (actual result comes later).
        """
        with self._debounce_lock:
            self._pending_image = image_path

            # Cancel and clean up any existing timer
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                # Don't join here - it could block if timer is executing
                # The timer will clean up on its own
                self._debounce_timer = None

            # Start new timer
            self._debounce_timer = threading.Timer(
                self.DEBOUNCE_INTERVAL,
                self._apply_pending,
            )
            self._debounce_timer.daemon = True  # Don't prevent process exit
            self._debounce_timer.start()

        return True

    def _apply_pending(self) -> None:
        """Apply theme for pending image after debounce interval."""
        with self._debounce_lock:
            image_path = self._pending_image
            self._pending_image = None
            self._debounce_timer = None

        if image_path:
            self._apply_immediate(image_path)

    def _apply_immediate(self, image_path: str) -> bool:
        """Apply theme immediately without debouncing.

        Args:
            image_path: Path to the wallpaper image.

        Returns:
            True if at least one template was processed successfully.
        """
        start_time = time.perf_counter()

        # Get palette
        palette = self.get_palette(image_path)
        if not palette:
            logger.warning(f"No palette available for: {image_path}")
            return False

        # Apply fallbacks for missing colors
        palette = self._apply_palette_fallbacks(palette)

        # Process each enabled template
        processor = TemplateProcessor(palette)
        success_count = 0
        reload_commands: List[Tuple[str, str]] = []

        for config in self._templates:
            if not config.enabled:
                continue

            # Get template content
            template_content = self._get_cached_template(config)
            if template_content is None:
                continue

            # Process template
            try:
                output = processor.process(template_content)
            except Exception as e:
                logger.error(f"Error processing template {config.name}: {e}")
                continue

            # Write to target
            if self._write_atomic(config.target_path, output):
                success_count += 1
                if config.reload_command:
                    reload_commands.append((config.name, config.reload_command))

        # Run reload commands
        for name, command in reload_commands:
            self._run_reload_command(command, name)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Applied theme: {success_count}/{len(self._templates)} templates "
            f"in {elapsed_ms:.1f}ms"
        )

        return success_count > 0

    def _apply_palette_fallbacks(self, palette: Dict[str, str]) -> Dict[str, str]:
        """Apply fallback values for missing palette entries.

        Args:
            palette: Original palette dict.

        Returns:
            Palette with fallbacks applied.
        """
        result = dict(palette)

        # cursor falls back to foreground
        if 'cursor' not in result and 'foreground' in result:
            result['cursor'] = result['foreground']

        # color7 falls back to foreground
        if 'color7' not in result and 'foreground' in result:
            result['color7'] = result['foreground']

        # Missing colors fall back to background
        background = result.get('background', '#000000')
        for i in range(16):
            key = f'color{i}'
            if key not in result:
                result[key] = background

        return result

    def get_enabled_templates(self) -> List[TemplateConfig]:
        """Get list of enabled templates.

        Returns:
            List of enabled TemplateConfig objects.
        """
        return [t for t in self._templates if t.enabled]

    def get_all_templates(self) -> List[TemplateConfig]:
        """Get list of all templates.

        Returns:
            List of all TemplateConfig objects.
        """
        return list(self._templates)

    def reload_config(self) -> None:
        """Reload configuration from disk.

        Call this after modifying wallust.toml or theming.json.
        """
        self._template_cache.clear()
        self._reload()
        logger.info(f"Reloaded config: {len(self._templates)} templates")

    def is_enabled(self) -> bool:
        """Check if theming engine is globally enabled.

        Returns:
            True if enabled.
        """
        return self._enabled

    def cleanup(self) -> None:
        """Clean up resources including pending timers.

        Thread-safe: Acquires debounce lock before modifying timer state.
        Cancels any pending timer and clears pending image path.
        """
        with self._debounce_lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            self._pending_image = None

    def close(self) -> None:
        """Close and clean up resources (alias for cleanup()).

        This method is provided for consistency with other resource
        managers that use close() instead of cleanup().
        """
        self.cleanup()
