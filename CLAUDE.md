# Variety Wallpaper Manager - Claude Code Instructions

## Project Overview

Variety is a wallpaper manager for Linux that automatically downloads and rotates desktop wallpapers from various online sources. This is a fork of the original [varietywalls/variety](https://github.com/varietywalls/variety) project.

**Tech Stack:**
- Python 3
- GTK3/GObject (PyGObject) for GUI
- PIL/Pillow for image processing
- D-Bus for IPC and CLI control
- ConfigObj for configuration management
- ImageMagick (external) for filters and effects

## MCP Servers for Knowledge Management

When working on this project, use these MCP servers to maintain and update the knowledge base:

### Required Before Starting Work

```
# 1. Check episodic memory for prior conversations about this project
mcp__plugin_episodic-memory_episodic-memory__search
  query: "variety wallpaper"

# 2. Ensure codebase intelligence is current
mcp__in-memoria__auto_learn_if_needed
  path: /home/komi/repos/variety-variation

# 3. Get project blueprint for quick orientation
mcp__in-memoria__get_project_blueprint
  path: /home/komi/repos/variety-variation
```

### For Code Understanding

```
# Extract code structure from specific files
mcp__ai-distiller__distill_file
mcp__ai-distiller__distill_directory
mcp__ai-distiller__distill_with_dependencies

# Find where to make changes
mcp__in-memoria__predict_coding_approach
  problemDescription: "describe what you want to do"

# Search for code patterns
mcp__in-memoria__search_codebase
```

### For Knowledge Persistence

```
# Search existing notes about Variety
mcp__zettelkasten__zk_search_notes
  tags: "variety"

# Save new discoveries/decisions
mcp__zettelkasten__zk_create_note
  tags: "variety, [topic]"

# Link related notes
mcp__zettelkasten__zk_create_link
```

### For Documentation Lookup

```
# PyGObject/GTK documentation
mcp__context7__resolve-library-id
  libraryName: "pygobject"

# Python library docs
mcp__context7__get-library-docs
```

## Architecture Overview

```
variety-variation/
├── bin/variety              # CLI entry point
├── variety/                 # Main application
│   ├── __init__.py         # D-Bus service, main()
│   ├── VarietyWindow.py    # Central controller (LARGEST FILE)
│   ├── Options.py          # Configuration schema
│   ├── indicator.py        # System tray menu
│   ├── QuotesEngine.py     # Quote rotation
│   ├── ThumbsManager.py    # Thumbnail display
│   ├── Util.py             # Utilities, decorators
│   └── plugins/            # Plugin system
│       ├── builtin/
│       │   ├── downloaders/  # Image sources
│       │   ├── quotes/       # Quote sources
│       │   └── display_modes/
│       └── downloaders/      # Base classes
├── variety_lib/             # Library helpers
├── jumble/                  # Plugin loader framework
├── data/
│   ├── scripts/            # set_wallpaper, get_wallpaper
│   ├── ui/                 # GTK .ui files
│   └── config/             # Default configs
└── tests/                  # Unit tests
```

## Key Files

| File | Purpose | Modify For |
|------|---------|------------|
| `variety/VarietyWindow.py` | Central controller | Core behavior changes |
| `variety/Options.py` | Config schema | New settings |
| `variety/indicator.py` | Tray menu | Menu changes |
| `data/scripts/set_wallpaper` | Sets wallpaper | Desktop environment support |
| `variety/plugins/builtin/downloaders/` | Image sources | New download sources |
| `variety/plugins/builtin/quotes/` | Quote sources | New quote providers |

## Plugin System

### Adding a New Image Source

Simple source (no user configuration):
```python
# variety/plugins/builtin/downloaders/MyDownloader.py
from variety.plugins.downloaders.SimpleDownloader import SimpleDownloader
from variety.plugins.downloaders.DefaultDownloader import QueueItem

class MyDownloader(SimpleDownloader):
    @classmethod
    def get_info(cls):
        return {"name": "My Source", "version": "1.0"}

    def get_source_type(self): return "my-source"
    def get_source_name(self): return "My Source"

    def fill_queue(self):
        # Fetch images and add to queue
        self.queue.append(QueueItem(origin_url, image_url, extra_metadata))
```

Configurable source (user provides query/URL):
```python
# Extend ConfigurableImageSource instead
# Implement validate(), create_downloader(), get_ui_*() methods
```

### Adding a New Quote Source

```python
# variety/plugins/builtin/quotes/MyQuoteSource.py
from variety.plugins.IQuoteSource import IQuoteSource

class MyQuoteSource(IQuoteSource):
    @classmethod
    def get_info(cls):
        return {"name": "My Quotes", "version": "1.0"}

    def get_random(self):
        return {"quote": "...", "author": "...", "link": "..."}
```

## Design Patterns in Use

1. **Observer** - `update_status_message()` pattern throughout
2. **Factory** - `create_downloader()` methods
3. **Strategy** - Different download/display strategies per source
4. **Builder** - GTK UI construction via `variety_lib.Builder`
5. **Command** - `process_command()` for CLI via D-Bus

## Common Tasks

### Running the Application
```bash
# From source
python -m variety

# Or use the bin script
./bin/variety
```

### Running Tests
```bash
python -m pytest tests/
python -m pytest tests/TestWallhavenDownloader.py -v
```

### Debugging
```bash
# Enable debug logging
variety -v

# Check D-Bus communication
variety --next  # Send command to running instance
```

## Configuration

User config location: `~/.config/variety/variety.conf`

Key config sections:
- `[sources]` - Enabled image sources
- `[filters]` - ImageMagick filters
- Wallpaper rotation settings
- Quote settings
- Download folder paths

## Active Development: Smart Selection Engine

A new intelligent wallpaper selection system is being developed. See zettelkasten note:
- **"Variety Smart Selection Engine - Implementation Plan"** (ID: 20251203T210011280589000)

### Key Features (Planned)
- **Image recency penalty**: Don't repeat wallpapers for N days
- **Source rotation**: Balance selection across wallpaper sources
- **Favorites boost**: Higher probability for favorited images
- **Wallust integration**: Index color palettes for each image
- **Color-aware selection**: Choose wallpapers by palette similarity, temperature, lightness

### Module Location
```
variety/smart_selection/
  __init__.py, models.py, database.py, config.py,
  indexer.py, palette.py, weights.py, selector.py
```

### Implementation Phases
1. ✅ **Foundation**: Database + basic indexing (Favorites) - COMPLETE
2. ✅ **Weighted Selection**: Recency-based selection replacing random - COMPLETE
3. **Wallust Integration**: Color palette extraction and storage
4. **Color-Aware Selection**: Palette similarity, filtering by color characteristics
5. **Full Collection + UI**: Index all wallpapers, preferences UI

### Phase 2 Integration Points (VarietyWindow.py)
- `_init_smart_selector()` - Initializes SmartSelector on startup
- `select_random_images()` - Uses weighted selection with fallback
- `set_wallpaper()` - Records shown images for recency tracking
- `on_quit()` - Cleans up SmartSelector resources

## Existing Zettelkasten Notes

Search for related notes before making major changes:
```
mcp__zettelkasten__zk_search_notes
  tags: "variety"
```

Current notes:
- "Variety Wallpaper Manager - Architecture Overview"
- "Variety - Plugin System Deep Dive"
- "Variety - Key Files for Modification"
- "Variety - Automatic Wallpaper Switching Logic"
- "Variety Smart Selection Engine - Implementation Plan"

## Workflow for Changes

1. **Start:** Run `in-memoria auto_learn_if_needed` to ensure intelligence is current
2. **Research:** Use `predict_coding_approach` to find relevant files
3. **Understand:** Use `ai-distiller distill_file` on key files
4. **Check notes:** Search zettelkasten for prior decisions
5. **Implement:** Make changes following existing patterns
6. **Test:** Run relevant tests in `tests/`
7. **Document:** Create/update zettelkasten notes for significant discoveries
