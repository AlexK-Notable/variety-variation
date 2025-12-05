#!/bin/bash
# Setup test fixture images from Variety Favorites

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/wallpapers"
FAVORITES_DIR="$HOME/.config/variety/Favorites"

mkdir -p "$FIXTURES_DIR"

if [ ! -d "$FAVORITES_DIR" ]; then
    echo "Error: Variety Favorites folder not found at $FAVORITES_DIR"
    echo "Please copy 10+ wallpaper images manually to $FIXTURES_DIR"
    exit 1
fi

# Get count of images in Favorites
AVAIL=$(find "$FAVORITES_DIR" -maxdepth 1 -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) | wc -l)

if [ "$AVAIL" -lt 10 ]; then
    echo "Warning: Only $AVAIL images found in Favorites. Need at least 10."
    echo "Copying all available images..."
fi

# Copy a diverse selection (first 15 by name for reproducibility)
echo "Copying fixture images from $FAVORITES_DIR..."
find "$FAVORITES_DIR" -maxdepth 1 -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) | \
    sort | head -15 | while read img; do
    cp "$img" "$FIXTURES_DIR/"
    echo "  $(basename "$img")"
done

COUNT=$(ls -1 "$FIXTURES_DIR"/*.{jpg,jpeg,png} 2>/dev/null | wc -l)
SIZE=$(du -sh "$FIXTURES_DIR" | cut -f1)

echo ""
echo "Done! Copied $COUNT images ($SIZE total)"
echo "Fixtures ready in: $FIXTURES_DIR"
