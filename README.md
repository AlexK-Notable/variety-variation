# Variety Variation

**Variety, but it remembers which wallpapers you've already seen.**

The original [Variety](https://github.com/varietywalls/variety) is great. It downloads wallpapers from everywhere, rotates them automatically, and stays out of your way. But it picks wallpapers randomly. Completely randomly. So you see the same image three times in a week while hundreds of others gather dust.

This fork fixes that. Variety Variation adds a **Smart Selection Engine** that tracks what you've seen, learns what you like, and (coming soon) picks wallpapers that match your color scheme. Same Variety you know, but smarter about what it shows you.

## Why This Fork?

| Problem | How We Solve It |
|---------|-----------------|
| "I keep seeing the same wallpapers" | **Recency tracking** - won't repeat images for N days |
| "My favorites never come up" | **Favorites boost** - higher probability for images you've liked |
| "Random doesn't feel balanced" | **Source rotation** - balances selection across all your sources |
| "I want wallpapers that match my theme" | **Wallust integration** - color-aware selection (in progress) |
| "Upstream is in maintenance mode" | **Active development** - new features being added |

## What's Different From Upstream

- **Smart Selection Engine**: Weighted selection replaces pure random
- **Recency penalties**: Recently shown images get deprioritized
- **Favorites awareness**: Your favorites are more likely to appear
- **Color palette indexing**: Extract and store dominant colors (Wallust integration)
- **Theme-aware selection**: Pick wallpapers by color temperature, lightness, palette similarity

> **Note**: This is an active fork. Upstream Variety is in [maintenance mode](https://github.com/varietywalls/variety/issues/736).

---

## Smart Selection Status

| Phase | Status | Description |
|-------|--------|-------------|
| Foundation | ✅ Complete | Database, indexing, favorites tracking |
| Weighted Selection | ✅ Complete | Recency-based selection replacing random |
| Wallust Integration | 🚧 In Progress | Color palette extraction and storage |
| Color-Aware Selection | 📋 Planned | Filter by palette, temperature, lightness |
| Preferences UI | 📋 Planned | Configure selection weights in GUI |

---

## Features (from upstream)

- **Automatic wallpaper rotation** on configurable intervals
- **Multiple sources**: Flickr, Wallhaven, Unsplash, Bing, Reddit, local folders
- **Desktop support**: GNOME, KDE, XFCE, Cinnamon, MATE, i3, Sway, Hyprland, and more
- **Quotes overlay**: Display quotes on your wallpaper
- **Filters**: Apply ImageMagick effects to wallpapers
- **Tray icon**: Quick access to next/previous, pause, favorites

## Installation

### From Source (recommended for this fork)

```bash
# Clone this fork
git clone https://github.com/your-username/variety-variation
cd variety-variation

# Install dependencies (Arch)
sudo pacman -S python python-gobject python-pillow python-beautifulsoup4 \
  python-lxml python-cairo python-configobj python-requests imagemagick

# Run from source
python -m variety

# Or install
python setup.py install --prefix ~/.local
```

### Dependencies

- Python 3.9+
- GTK3 + PyGObject
- Pillow, BeautifulSoup4, ConfigObj, Requests
- ImageMagick (optional, for filters)

## Usage

```bash
# Launch GUI
variety

# CLI control (talks to running instance via D-Bus)
variety --next          # Next wallpaper
variety --previous      # Previous wallpaper
variety --favorite      # Mark current as favorite
variety --trash         # Move current to trash
variety --pause         # Pause rotation
variety --resume        # Resume rotation
```

## Configuration

Config file: `~/.config/variety/variety.conf`

Smart Selection settings (when UI is ready):
```ini
[smart_selection]
recency_days = 7        # Don't repeat for N days
favorites_boost = 2.0   # Favorites are 2x more likely
source_balance = true   # Balance across sources
```

## Project Structure

```
variety-variation/
├── variety/
│   ├── VarietyWindow.py      # Main controller
│   ├── smart_selection/      # 🆕 Smart Selection Engine
│   │   ├── database.py       # SQLite tracking
│   │   ├── selector.py       # Weighted selection logic
│   │   ├── indexer.py        # Image indexing
│   │   ├── palette.py        # Color extraction
│   │   ├── theming.py        # Wallust integration
│   │   └── weights.py        # Selection weights
│   └── plugins/
│       └── builtin/
│           ├── downloaders/  # Image sources
│           └── quotes/       # Quote sources
├── data/
│   └── scripts/              # set_wallpaper, get_wallpaper
└── tests/
```

## Development

```bash
# Run from source
python -m variety

# Run with debug logging
variety -v

# Run tests
python -m pytest tests/
```

## Credits

- Original [Variety](https://github.com/varietywalls/variety) by Peter Levi and contributors
- Smart Selection Engine development by this fork

## License

GPL-3.0 (same as upstream)
