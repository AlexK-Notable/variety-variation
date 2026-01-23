# tests/db_browser/conftest.py
"""Shared fixtures for database browser tests."""

import json
import os
import shutil
import sqlite3
import tempfile
import time
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "db_browser: tests for the database browser web app"
    )


@pytest.fixture
def temp_dir():
    """Create a temporary directory, cleanup after test."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


def _create_schema(conn):
    """Create the database schema matching production (v6)."""
    conn.executescript("""
        -- Schema info
        CREATE TABLE schema_info (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        INSERT INTO schema_info (key, value) VALUES ('version', '6');

        -- Sources table
        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT,
            last_shown_at INTEGER,
            times_shown INTEGER DEFAULT 0
        );

        -- Images table
        CREATE TABLE images (
            filepath TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            source_id TEXT,
            width INTEGER,
            height INTEGER,
            aspect_ratio REAL,
            file_size INTEGER,
            file_mtime INTEGER,
            is_favorite INTEGER DEFAULT 0,
            first_indexed_at INTEGER,
            last_indexed_at INTEGER,
            last_shown_at INTEGER,
            times_shown INTEGER DEFAULT 0,
            palette_status TEXT DEFAULT 'pending',
            stale_at INTEGER
        );

        -- Image metadata table
        CREATE TABLE image_metadata (
            filepath TEXT PRIMARY KEY,
            category TEXT,
            purity TEXT,
            sfw_rating INTEGER,
            source_colors TEXT,
            uploader TEXT,
            source_url TEXT,
            views INTEGER,
            favorites INTEGER,
            uploaded_at INTEGER,
            metadata_fetched_at INTEGER,
            FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE
        );

        -- Palettes table
        CREATE TABLE palettes (
            filepath TEXT PRIMARY KEY,
            color0 TEXT, color1 TEXT, color2 TEXT, color3 TEXT,
            color4 TEXT, color5 TEXT, color6 TEXT, color7 TEXT,
            color8 TEXT, color9 TEXT, color10 TEXT, color11 TEXT,
            color12 TEXT, color13 TEXT, color14 TEXT, color15 TEXT,
            background TEXT,
            foreground TEXT,
            avg_hue REAL,
            avg_saturation REAL,
            avg_lightness REAL,
            color_temperature REAL,
            indexed_at INTEGER,
            cursor TEXT,
            FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE
        );

        -- Tags table
        CREATE TABLE tags (
            tag_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            alias TEXT,
            category TEXT,
            purity TEXT,
            UNIQUE(name)
        );

        -- Image-tag junction table
        CREATE TABLE image_tags (
            filepath TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (filepath, tag_id),
            FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
        );

        -- User actions table
        CREATE TABLE user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL,
            action TEXT NOT NULL,
            action_at INTEGER NOT NULL,
            FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE
        );

        -- Indexes
        CREATE INDEX idx_images_source ON images(source_id);
        CREATE INDEX idx_images_last_shown ON images(last_shown_at);
        CREATE INDEX idx_images_favorite ON images(is_favorite);
        CREATE INDEX idx_images_palette_status ON images(palette_status);
        CREATE INDEX idx_palettes_lightness ON palettes(avg_lightness);
        CREATE INDEX idx_palettes_temperature ON palettes(color_temperature);
        CREATE INDEX idx_tags_name ON tags(name);
        CREATE INDEX idx_image_tags_filepath ON image_tags(filepath);
        CREATE INDEX idx_image_tags_tag_id ON image_tags(tag_id);
        CREATE INDEX idx_user_actions_filepath ON user_actions(filepath);
        CREATE INDEX idx_user_actions_action ON user_actions(action);
    """)
    conn.commit()


@pytest.fixture
def temp_db(temp_dir):
    """Create a temporary database with test data."""
    db_path = os.path.join(temp_dir, "test_browser.db")
    now = int(time.time())

    conn = sqlite3.connect(db_path)
    _create_schema(conn)

    # Insert sources
    conn.executemany(
        "INSERT INTO sources (source_id, source_type) VALUES (?, ?)",
        [
            ("wallhaven_test", "wallhaven"),
            ("unsplash_test", "unsplash"),
        ]
    )

    # Insert test images
    test_images = [
        (f"{temp_dir}/wallpapers/test1.jpg", "test1.jpg", "wallhaven_test",
         1920, 1080, 1.778, 100000, now, 1, now, now, None, 0, "done", None),
        (f"{temp_dir}/wallpapers/test2.png", "test2.png", "unsplash_test",
         1920, 1080, 1.778, 100000, now, 0, now, now, None, 0, "pending", None),
        (f"{temp_dir}/wallpapers/test3.jpg", "test3.jpg", "wallhaven_test",
         1920, 1080, 1.778, 100000, now, 0, now, now, None, 0, "pending", None),
    ]
    conn.executemany(
        """INSERT INTO images (filepath, filename, source_id, width, height,
           aspect_ratio, file_size, file_mtime, is_favorite, first_indexed_at,
           last_indexed_at, last_shown_at, times_shown, palette_status, stale_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        test_images
    )

    # Insert metadata with source_url
    conn.executemany(
        """INSERT INTO image_metadata (filepath, category, purity, source_url)
           VALUES (?, ?, ?, ?)""",
        [
            (f"{temp_dir}/wallpapers/test1.jpg", "anime", "sfw", "https://wallhaven.cc/w/test1"),
            (f"{temp_dir}/wallpapers/test2.png", "nature", "sfw", "https://unsplash.com/photos/test2"),
            (f"{temp_dir}/wallpapers/test3.jpg", "people", "sketchy", "https://wallhaven.cc/w/test3"),
        ]
    )

    # Insert tags
    conn.executemany(
        "INSERT INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
        [(1, "anime", "general"), (2, "colorful", "general"),
         (3, "nature", "general"), (4, "landscape", "general")]
    )

    # Link tags to images
    conn.executemany(
        "INSERT INTO image_tags (filepath, tag_id) VALUES (?, ?)",
        [
            (f"{temp_dir}/wallpapers/test1.jpg", 1),  # anime
            (f"{temp_dir}/wallpapers/test1.jpg", 2),  # colorful
            (f"{temp_dir}/wallpapers/test2.png", 3),  # nature
            (f"{temp_dir}/wallpapers/test2.png", 4),  # landscape
        ]
    )

    # Insert palette for test1.jpg
    conn.execute(
        """INSERT INTO palettes (filepath, color0, color1, color2, background, foreground,
           avg_hue, avg_saturation, avg_lightness, color_temperature, indexed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"{temp_dir}/wallpapers/test1.jpg", "#ff0000", "#00ff00", "#0000ff",
         "#000000", "#ffffff", 120.0, 0.8, 0.5, 5500.0, now)
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def temp_images(temp_dir):
    """Create actual test image files."""
    import struct
    import zlib

    wallpapers_dir = os.path.join(temp_dir, "wallpapers")
    os.makedirs(wallpapers_dir, exist_ok=True)

    def create_minimal_png(filepath, color=(255, 0, 0)):
        """Create a minimal valid PNG file."""
        signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        raw_data = b"\x00" + bytes(color)
        compressed = zlib.compress(raw_data)
        idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
        idat_chunk = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        with open(filepath, "wb") as f:
            f.write(signature + ihdr_chunk + idat_chunk + iend_chunk)

    def create_minimal_jpeg(filepath):
        """Create a minimal valid JPEG file."""
        jpeg_data = bytes([
            0xFF, 0xD8,  # SOI
            0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,  # APP0
            0xFF, 0xDB, 0x00, 0x43, 0x00,  # DQT
        ] + [16] * 64 + [  # Quantization table
            0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00,  # SOF0
            0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,  # DHT
            0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7F, 0xFF,  # SOS + minimal data
            0xFF, 0xD9,  # EOI
        ])
        with open(filepath, "wb") as f:
            f.write(jpeg_data)

    create_minimal_jpeg(os.path.join(wallpapers_dir, "test1.jpg"))
    create_minimal_png(os.path.join(wallpapers_dir, "test2.png"), (0, 255, 0))
    create_minimal_jpeg(os.path.join(wallpapers_dir, "test3.jpg"))

    return wallpapers_dir


@pytest.fixture
def test_client(temp_db, temp_images, temp_dir, monkeypatch):
    """Create a FastAPI test client with test database."""
    from fastapi.testclient import TestClient
    from tools.db_browser import config as browser_config

    monkeypatch.setattr(browser_config.settings, "db_path", temp_db)
    monkeypatch.setattr(browser_config.settings, "readonly", False)
    monkeypatch.setattr(browser_config.settings, "allowed_image_dirs", [temp_dir])

    from tools.db_browser.main import app, get_db
    from tools.db_browser.database import DatabaseBrowser

    db = DatabaseBrowser(temp_db, readonly=False)

    def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    yield client

    db.close()
    app.dependency_overrides.clear()


@pytest.fixture
def readonly_client(temp_db, temp_images, temp_dir, monkeypatch):
    """Create a FastAPI test client in readonly mode."""
    from fastapi.testclient import TestClient
    from tools.db_browser import config as browser_config

    monkeypatch.setattr(browser_config.settings, "db_path", temp_db)
    monkeypatch.setattr(browser_config.settings, "readonly", True)
    monkeypatch.setattr(browser_config.settings, "allowed_image_dirs", [temp_dir])

    from tools.db_browser.main import app, get_db
    from tools.db_browser.database import DatabaseBrowser

    db = DatabaseBrowser(temp_db, readonly=True)

    def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    yield client

    db.close()
    app.dependency_overrides.clear()
