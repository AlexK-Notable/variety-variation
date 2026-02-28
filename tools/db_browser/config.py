# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Configuration settings for the database browser."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Database
    db_path: str = str(Path.home() / ".config/variety/smart_selection.db")
    readonly: bool = False  # Set True for safe browsing-only mode

    # Server
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False

    # Pagination
    default_page_size: int = 24
    max_page_size: int = 100

    # Variety config directory (for banned.txt integration)
    variety_config_dir: str = str(Path.home() / ".config/variety")

    # Security: Allowed directories for serving images
    # Images outside these directories will be rejected
    # Default: Variety's standard wallpaper locations
    allowed_image_dirs: List[str] = [
        str(Path.home() / "Pictures/Wallpapers"),
        str(Path.home() / ".config/variety/Favorites"),
        str(Path.home() / ".config/variety/Downloaded"),
        str(Path.home() / ".config/variety/Fetched"),
    ]

    class Config:
        env_prefix = "VARIETY_BROWSER_"
        env_file = ".env"


settings = Settings()
