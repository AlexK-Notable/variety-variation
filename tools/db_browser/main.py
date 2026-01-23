#!/usr/bin/env python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Variety Smart Selection Database Browser.

A standalone web application for browsing and editing the Smart Selection
database. Built with FastAPI + HTMX.

Usage:
    python -m tools.db_browser.main
    # or
    uvicorn tools.db_browser.main:app --reload --port 8765
"""

import os
import base64
import math
import mimetypes
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List
from urllib.parse import quote, unquote

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response, RedirectResponse, FileResponse

from . import __version__
from .config import settings
from .database import DatabaseBrowser
from .models import HealthResponse


# --- URL-safe filepath encoding ---

def b64encode_filepath(filepath: str) -> str:
    """Encode a filepath to URL-safe base64."""
    return base64.urlsafe_b64encode(filepath.encode("utf-8")).decode("ascii")


def b64decode_filepath(encoded: str) -> str:
    """Decode a URL-safe base64 filepath."""
    # Add padding if needed
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding
    return base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")


def is_path_allowed(filepath: str) -> bool:
    """Check if a filepath is within allowed directories.

    This prevents path traversal attacks by ensuring we only serve
    files from Variety's wallpaper directories.
    """
    try:
        # Resolve to absolute path, following symlinks
        resolved = Path(filepath).resolve()

        # Check if path is under any allowed directory
        for allowed_dir in settings.allowed_image_dirs:
            allowed_path = Path(allowed_dir).resolve()
            try:
                resolved.relative_to(allowed_path)
                return True
            except ValueError:
                # Not under this directory
                continue

        return False
    except Exception:
        return False


def get_content_type(filepath: str) -> str:
    """Get MIME type for a file based on extension."""
    content_type, _ = mimetypes.guess_type(filepath)
    return content_type or "application/octet-stream"

# --- Application State ---

db: Optional[DatabaseBrowser] = None


def get_db() -> DatabaseBrowser:
    """Dependency to get database connection."""
    if db is None:
        raise HTTPException(500, "Database not initialized")
    return db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    global db

    # Startup
    db_path = os.path.expanduser(settings.db_path)
    if not os.path.exists(db_path):
        print(f"Warning: Database not found at {db_path}")
        print("The browser will start but most features won't work.")
        print("Run Variety to create the database first.")
    else:
        db = DatabaseBrowser(db_path, readonly=settings.readonly)
        print(f"Connected to database: {db_path}")
        print(f"Mode: {'read-only' if settings.readonly else 'read-write'}")
        print(f"Images: {db.get_image_count()}")
        print(f"Sources: {db.get_source_count()}")

    yield

    # Shutdown
    if db:
        db.close()
        print("Database connection closed.")


# --- Application Setup ---

app = FastAPI(
    title="Variety Database Browser",
    description="Browse and edit the Smart Selection database",
    version=__version__,
    lifespan=lifespan,
)

# Static files and templates
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Add custom Jinja2 filters
templates.env.filters["b64encode"] = b64encode_filepath
templates.env.filters["urlencode"] = lambda s: quote(str(s), safe="")
templates.env.globals["ceil"] = math.ceil


# --- Routes ---

@app.get("/health", response_model=HealthResponse)
async def health_check(database: DatabaseBrowser = Depends(get_db)):
    """Health check endpoint with database status."""
    db_path = os.path.expanduser(settings.db_path)
    return HealthResponse(
        status="ok",
        db_path=db_path,
        db_exists=os.path.exists(db_path),
        image_count=database.get_image_count(),
        source_count=database.get_source_count(),
        readonly=settings.readonly,
        version=__version__,
    )


@app.get("/api/sources")
async def list_sources(database: DatabaseBrowser = Depends(get_db)):
    """Get all sources with image counts."""
    return database.get_sources()


@app.post("/api/images/{encoded_path:path}/favorite")
async def toggle_favorite(
    encoded_path: str,
    database: DatabaseBrowser = Depends(get_db),
):
    """Toggle favorite status for an image.

    Returns JSON with new favorite state and triggers HTMX events.
    """
    # Check readonly mode
    if settings.readonly:
        raise HTTPException(403, "Database is in read-only mode")

    # Decode path
    try:
        filepath = b64decode_filepath(encoded_path)
    except Exception:
        raise HTTPException(400, "Invalid path encoding")

    # Get current image to check favorite status
    image = database.get_image(filepath)
    if not image:
        raise HTTPException(404, "Image not found")

    # Toggle favorite
    new_status = not image.is_favorite
    success = database.set_favorite(filepath, new_status)

    if not success:
        raise HTTPException(500, "Failed to update favorite status")

    # Return JSON response with HTMX trigger header for toast
    action = "favorited" if new_status else "unfavorited"
    return Response(
        content=f'{{"is_favorite": {str(new_status).lower()}, "message": "Image {action}"}}',
        media_type="application/json",
        headers={
            "HX-Trigger": f'{{"showToast": {{"message": "Image {action}", "type": "success"}}}}'
        },
    )


@app.post("/api/images/{encoded_path:path}/trash")
async def mark_trash(
    encoded_path: str,
    database: DatabaseBrowser = Depends(get_db),
):
    """Mark an image as trashed.

    This records a trash action in user_actions and clears favorite status.
    It does NOT delete the image from disk or database.
    """
    # Check readonly mode
    if settings.readonly:
        raise HTTPException(403, "Database is in read-only mode")

    # Decode path
    try:
        filepath = b64decode_filepath(encoded_path)
    except Exception:
        raise HTTPException(400, "Invalid path encoding")

    # Check image exists
    if not database.image_exists(filepath):
        raise HTTPException(404, "Image not found")

    # Record trash action
    success = database.record_trash(filepath)

    if not success:
        raise HTTPException(500, "Failed to record trash action")

    return Response(
        content='{"success": true, "message": "Image marked as trashed"}',
        media_type="application/json",
        headers={
            "HX-Trigger": '{"showToast": {"message": "Image marked as trashed", "type": "success"}}'
        },
    )


@app.get("/api/tags")
async def list_tags(
    limit: int = 100,
    database: DatabaseBrowser = Depends(get_db),
):
    """Get popular tags."""
    return database.get_tags(limit=limit)


@app.get("/")
async def index():
    """Redirect to browse page."""
    return RedirectResponse(url="/browse", status_code=302)


@app.get("/browse", response_class=HTMLResponse)
async def browse(
    request: Request,
    page: int = 1,
    source: Optional[str] = None,
    purity: Optional[str] = None,
    favorites_only: bool = False,
    search: Optional[str] = None,
    sort_by: str = "last_indexed_at",
    tag: Optional[str] = None,
    database: DatabaseBrowser = Depends(get_db),
):
    """Browse images with filtering and pagination."""
    page_size = settings.default_page_size

    # Get filtered images
    images, total = database.get_images(
        page=page,
        page_size=page_size,
        source_id=source,
        tag_name=tag,
        purity=purity,
        favorites_only=favorites_only,
        search=search,
        sort_by=sort_by,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    # Get sources and tags for sidebar
    sources = database.get_sources()
    tags = database.get_tags(limit=50)

    # Stats for header
    stats = {
        "image_count": database.get_image_count(),
        "source_count": database.get_source_count(),
    }

    # Current filter state for UI
    current_filters = {
        "source": source,
        "purity": purity,
        "favorites_only": favorites_only,
        "search": search,
        "sort_by": sort_by,
        "tag": tag,
    }

    context = {
        "request": request,
        "images": images,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "sources": sources,
        "tags": tags,
        "stats": stats,
        "current_filters": current_filters,
    }

    # If HTMX request, return just the grid partial
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/image_grid.html", context)

    # Full page render
    return templates.TemplateResponse("index.html", context)


@app.get("/preview/{encoded_path:path}")
async def preview_image(encoded_path: str, database: DatabaseBrowser = Depends(get_db)):
    """Serve image file.

    Security:
    - Validates base64 encoding
    - Checks image exists in database (not just on disk)
    - Validates path is within allowed directories
    """
    # Decode the base64 path
    try:
        filepath = b64decode_filepath(encoded_path)
    except Exception:
        raise HTTPException(400, "Invalid path encoding")

    # Check if image exists in database (defense in depth)
    if not database.image_exists(filepath):
        raise HTTPException(404, "Image not found in database")

    # Security: Validate path is within allowed directories
    if not is_path_allowed(filepath):
        raise HTTPException(403, "Access denied: path outside allowed directories")

    # Check file exists on disk
    if not os.path.isfile(filepath):
        raise HTTPException(404, "Image file not found on disk")

    # Serve the file
    content_type = get_content_type(filepath)
    filename = os.path.basename(filepath)

    return FileResponse(
        path=filepath,
        media_type=content_type,
        # Enable browser caching (1 hour) and inline display (not download)
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f"inline; filename=\"{filename}\"",
        },
    )


@app.get("/image/{encoded_path:path}", response_class=HTMLResponse)
async def image_detail(
    request: Request,
    encoded_path: str,
    database: DatabaseBrowser = Depends(get_db),
):
    """Display detailed view of a single image."""
    # Decode the base64 path
    try:
        filepath = b64decode_filepath(encoded_path)
    except Exception:
        raise HTTPException(400, "Invalid path encoding")

    # Get image from database
    image = database.get_image(filepath)
    if not image:
        raise HTTPException(404, "Image not found")

    # Get additional data
    tags = database.get_tags_for_image(filepath)
    palette = database.get_palette(filepath)

    # Check if file exists on disk
    file_exists = os.path.isfile(filepath)

    # Format file size for display
    def format_file_size(size_bytes):
        if not size_bytes:
            return "Unknown"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    # Stats for header
    stats = {
        "image_count": database.get_image_count(),
        "source_count": database.get_source_count(),
    }

    context = {
        "request": request,
        "image": image,
        "tags": tags,
        "palette": palette,
        "file_exists": file_exists,
        "encoded_path": encoded_path,
        "file_size_display": format_file_size(image.file_size),
        "stats": stats,
    }

    return templates.TemplateResponse("detail.html", context)


# --- Main Entry Point ---

def main():
    """Run the application with uvicorn."""
    import uvicorn

    print(f"\n🖼️  Variety Database Browser v{__version__}")
    print(f"   Database: {settings.db_path}")
    print(f"   Server: http://{settings.host}:{settings.port}")
    print(f"   Docs: http://{settings.host}:{settings.port}/docs\n")

    uvicorn.run(
        "tools.db_browser.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
