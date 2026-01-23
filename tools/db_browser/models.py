# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Pydantic models for API responses.

These models mirror the dataclasses in variety.smart_selection.models
but add Pydantic validation and JSON serialization for the web API.
"""

from pydantic import BaseModel, Field, computed_field
from typing import Optional, List
from datetime import datetime


class ImageResponse(BaseModel):
    """Image record for API responses."""

    filepath: str
    filename: str
    source_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    file_size: Optional[int] = None
    is_favorite: bool = False
    times_shown: int = 0
    last_shown_at: Optional[int] = None
    palette_status: str = "pending"

    # Joined from image_metadata
    category: Optional[str] = None
    purity: Optional[str] = None
    source_url: Optional[str] = None
    uploader: Optional[str] = None
    views: Optional[int] = None

    @computed_field
    @property
    def last_shown_display(self) -> Optional[str]:
        """Human-readable last shown time."""
        if self.last_shown_at:
            dt = datetime.fromtimestamp(self.last_shown_at)
            return dt.strftime("%Y-%m-%d %H:%M")
        return None

    @computed_field
    @property
    def dimensions(self) -> Optional[str]:
        """Display dimensions like '1920x1080'."""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None


class SourceResponse(BaseModel):
    """Source record for API responses."""

    source_id: str
    source_type: Optional[str] = None
    times_shown: int = 0
    image_count: int = 0  # Computed from join


class TagResponse(BaseModel):
    """Tag with usage count."""

    tag_id: int
    name: str
    category: Optional[str] = None
    count: int = 0  # Number of images with this tag


class PaletteResponse(BaseModel):
    """Color palette for an image."""

    filepath: str
    colors: List[str] = Field(default_factory=list)  # color0-color15
    background: Optional[str] = None
    foreground: Optional[str] = None
    avg_hue: Optional[float] = None
    avg_saturation: Optional[float] = None
    avg_lightness: Optional[float] = None
    color_temperature: Optional[float] = None


class ImageDetailResponse(BaseModel):
    """Full image details including palette and tags."""

    image: ImageResponse
    palette: Optional[PaletteResponse] = None
    tags: List[TagResponse] = Field(default_factory=list)


class PaginatedResponse(BaseModel):
    """Paginated list response."""

    items: List[ImageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    db_path: str
    db_exists: bool
    image_count: int
    source_count: int
    readonly: bool
    version: str
