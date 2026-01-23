# Variety Database Browser

A standalone web application for browsing and editing the Variety Smart Selection database.

## Features

- Browse indexed images with filtering (source, tag, purity, favorites)
- Preview images directly in the browser
- View color palettes and metadata
- One-click favorite/trash actions
- Link to original source URLs

## Quick Start

```bash
# From the variety-variation repository root:

# Install dependencies (using uv)
uv pip install -r tools/db_browser/requirements.txt

# Or with pip
pip install -r tools/db_browser/requirements.txt

# Run the server
python -m tools.db_browser.main

# Open in browser
# http://127.0.0.1:8765
```

## Configuration

Environment variables (prefix `VARIETY_BROWSER_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `VARIETY_BROWSER_DB_PATH` | `~/.config/variety/smart_selection.db` | Database location |
| `VARIETY_BROWSER_READONLY` | `false` | Enable read-only mode |
| `VARIETY_BROWSER_HOST` | `127.0.0.1` | Server host |
| `VARIETY_BROWSER_PORT` | `8765` | Server port |
| `VARIETY_BROWSER_DEBUG` | `false` | Enable debug/reload mode |

Or create a `.env` file:

```env
VARIETY_BROWSER_PORT=8080
VARIETY_BROWSER_READONLY=true
```

## API Endpoints

- `GET /health` - Health check with database stats
- `GET /api/sources` - List all wallpaper sources
- `GET /api/tags` - List popular tags
- `GET /docs` - Interactive API documentation (Swagger UI)

## Development Status

- [x] Phase 1: Project scaffold, database connection, health endpoint
- [ ] Phase 2: Image grid with pagination
- [ ] Phase 3: Image preview (static file serving)
- [ ] Phase 4: Filtering UI
- [ ] Phase 5: Image detail view
- [ ] Phase 6: Favorite/trash actions
- [ ] Phase 7: Polish (keyboard nav, dark mode)

## Tech Stack

- **FastAPI** - Modern async Python web framework
- **HTMX** - Server-rendered interactivity without heavy JS
- **Jinja2** - Template engine
- **SQLite** - Direct database access (same DB as Variety)
- **Tailwind CSS** - Utility-first styling (via CDN)
