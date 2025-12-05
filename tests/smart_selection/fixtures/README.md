# Test Fixtures

This directory contains curated wallpaper images for end-to-end testing.

## Setup

The `wallpapers/` directory should contain 10+ diverse images.

**Option 1: Copy from Variety Favorites (recommended)**
```bash
./setup_fixtures.sh
```

**Option 2: Manual setup**
Copy any 10+ wallpaper images (jpg/png) to `wallpapers/`.

## Selection Criteria

Images should provide diversity in:
- Color temperature (warm, cool, neutral)
- Aspect ratios (landscape, portrait, square)
- File sizes (small to large)
- Sources (wallhaven, APOD, reddit, unsplash)

## Usage

These fixtures are used by:
- `tests/smart_selection/e2e/` - End-to-end workflow tests
- `tests/smart_selection/benchmarks/` - Performance benchmarks

## Note

The `wallpapers/` directory is gitignored due to size (~50MB).
Run the setup script after cloning to populate fixtures.
