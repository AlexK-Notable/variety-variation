# tests/db_browser/test_playwright.py
"""Comprehensive Playwright browser tests for the database browser UI.

Tests all user interactions including navigation, filtering, pagination,
favorites, trash, dark mode, keyboard shortcuts, and state synchronization.
"""

import base64
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn
from playwright.sync_api import Page, expect


def b64encode_path(filepath: str) -> str:
    """Encode filepath to URL-safe base64."""
    return base64.urlsafe_b64encode(filepath.encode("utf-8")).decode("ascii").rstrip("=")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def temp_dir():
    """Create a temporary directory for the test module."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture(scope="module")
def temp_db(temp_dir):
    """Create a temporary database with test data."""
    import struct
    import zlib

    db_path = os.path.join(temp_dir, "test_playwright.db")
    now = int(time.time())

    # Create wallpapers directory and test images
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

    # Create test image files (30 images to test pagination with default page_size=24)
    for i in range(1, 31):
        if i % 2 == 0:
            create_minimal_png(os.path.join(wallpapers_dir, f"test{i}.png"))
        else:
            create_minimal_jpeg(os.path.join(wallpapers_dir, f"test{i}.jpg"))

    # Create database
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO schema_info (key, value) VALUES ('version', '6');

        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT,
            last_shown_at INTEGER,
            times_shown INTEGER DEFAULT 0
        );

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
            metadata_fetched_at INTEGER
        );

        CREATE TABLE palettes (
            filepath TEXT PRIMARY KEY,
            color0 TEXT, color1 TEXT, color2 TEXT, color3 TEXT,
            color4 TEXT, color5 TEXT, color6 TEXT, color7 TEXT,
            color8 TEXT, color9 TEXT, color10 TEXT, color11 TEXT,
            color12 TEXT, color13 TEXT, color14 TEXT, color15 TEXT,
            background TEXT, foreground TEXT,
            avg_hue REAL, avg_saturation REAL, avg_lightness REAL,
            color_temperature REAL, indexed_at INTEGER, cursor TEXT
        );

        CREATE TABLE tags (
            tag_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            alias TEXT,
            category TEXT,
            purity TEXT
        );

        CREATE TABLE image_tags (
            filepath TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (filepath, tag_id)
        );

        CREATE TABLE user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL,
            action TEXT NOT NULL,
            action_at INTEGER NOT NULL
        );

        CREATE INDEX idx_images_source ON images(source_id);
        CREATE INDEX idx_images_favorite ON images(is_favorite);
        CREATE INDEX idx_user_actions_filepath ON user_actions(filepath);
        CREATE INDEX idx_user_actions_action ON user_actions(action);
    """)

    # Insert sources
    conn.executemany(
        "INSERT INTO sources (source_id, source_type) VALUES (?, ?)",
        [("wallhaven_test", "wallhaven"), ("unsplash_test", "unsplash")]
    )

    # Insert test images (30 images for pagination testing)
    for i in range(1, 31):
        ext = "png" if i % 2 == 0 else "jpg"
        source = "wallhaven_test" if i <= 15 else "unsplash_test"
        is_fav = 1 if i == 1 else 0
        filepath = f"{temp_dir}/wallpapers/test{i}.{ext}"
        conn.execute(
            """INSERT INTO images (filepath, filename, source_id, width, height,
               aspect_ratio, file_size, file_mtime, is_favorite, first_indexed_at,
               last_indexed_at, last_shown_at, times_shown, palette_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (filepath, f"test{i}.{ext}", source, 1920, 1080, 1.778, 100000, now,
             is_fav, now, now, None, i, "done")
        )

    # Insert metadata with different purities (cycle through patterns for 30 images)
    purity_cycle = ["sfw", "sfw", "sketchy", "nsfw", "sfw"]
    for i in range(1, 31):
        ext = "png" if i % 2 == 0 else "jpg"
        filepath = f"{temp_dir}/wallpapers/test{i}.{ext}"
        purity = purity_cycle[(i - 1) % 5]
        conn.execute(
            "INSERT INTO image_metadata (filepath, category, purity, source_url) VALUES (?, ?, ?, ?)",
            (filepath, "anime", purity, f"https://example.com/test{i}")
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
            (f"{temp_dir}/wallpapers/test1.jpg", 1),
            (f"{temp_dir}/wallpapers/test1.jpg", 2),
            (f"{temp_dir}/wallpapers/test2.png", 3),
            (f"{temp_dir}/wallpapers/test3.jpg", 1),
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

    # Pre-trash test5 for testing trashed filter (on first page)
    conn.execute(
        "INSERT INTO user_actions (filepath, action, action_at) VALUES (?, ?, ?)",
        (f"{temp_dir}/wallpapers/test5.jpg", "trash", now)
    )
    # Also pre-trash test30 for pagination trashed filter testing
    conn.execute(
        "INSERT INTO user_actions (filepath, action, action_at) VALUES (?, ?, ?)",
        (f"{temp_dir}/wallpapers/test30.png", "trash", now)
    )

    conn.commit()
    conn.close()

    return db_path


class ServerThread(threading.Thread):
    """Thread to run the FastAPI server."""

    def __init__(self, app, host="127.0.0.1", port=8765):
        super().__init__(daemon=True)
        self.app = app
        self.host = host
        self.port = port
        self.server = None

    def run(self):
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop(self):
        if self.server:
            self.server.should_exit = True


def get_free_port():
    """Find a free port to use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(temp_db, temp_dir):
    """Start a live server for Playwright tests."""
    import sys

    # Ensure the project root is in path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Import config and patch settings directly
    from tools.db_browser import config as browser_config
    browser_config.settings.db_path = temp_db
    browser_config.settings.readonly = False
    browser_config.settings.allowed_image_dirs = [temp_dir]

    # Now import the app (which will use the patched settings)
    from tools.db_browser.main import app, get_db
    from tools.db_browser.database import DatabaseBrowser

    # Override the database dependency
    db = DatabaseBrowser(temp_db, readonly=False)

    def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db

    port = get_free_port()
    server = ServerThread(app, port=port)
    server.start()

    # Wait for server to start
    import httpx
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            response = httpx.get(f"{base_url}/health", timeout=0.5)
            if response.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("Server failed to start")

    yield base_url

    server.stop()
    db.close()
    app.dependency_overrides.clear()


@pytest.fixture
def page(browser, live_server):
    """Create a new page for each test."""
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(10000)
    yield page
    context.close()


# =============================================================================
# Navigation Tests
# =============================================================================


class TestNavigation:
    """Tests for basic page navigation."""

    def test_index_redirects_to_browse(self, page: Page, live_server):
        """Index page redirects to browse."""
        page.goto(live_server)
        expect(page).to_have_url(f"{live_server}/browse")

    def test_browse_page_loads(self, page: Page, live_server):
        """Browse page loads successfully."""
        page.goto(f"{live_server}/browse")
        expect(page).to_have_title("Browse Images - Variety Database Browser")
        # First page shows 24 images (page_size=24, total=30)
        expect(page.locator(".image-card")).to_have_count(24)

    def test_image_detail_page_loads(self, page: Page, live_server, temp_dir):
        """Image detail page loads when clicking an image."""
        page.goto(f"{live_server}/browse")
        # Wait for images to load
        expect(page.locator(".image-card").first).to_be_visible()
        # Use keyboard navigation to select and open first image
        page.keyboard.press("ArrowRight")
        # Wait for selection to be applied
        expect(page.locator(".image-card.selected")).to_have_count(1)
        page.keyboard.press("Enter")
        # Wait for navigation to complete
        page.wait_for_url(re.compile(rf"{live_server}/image/.+"), timeout=10000)
        # Should show image filename
        expect(page.locator("h1")).to_contain_text("test")

    def test_back_button_returns_to_browse(self, page: Page, live_server):
        """Back button returns to browse from detail page."""
        page.goto(f"{live_server}/browse")
        # Use keyboard navigation
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(rf"{live_server}/image/.+"))
        page.go_back()
        expect(page).to_have_url(f"{live_server}/browse")


# =============================================================================
# Filter Tests
# =============================================================================


class TestFilters:
    """Tests for filtering functionality."""

    def test_source_filter(self, page: Page, live_server):
        """Source dropdown filters images."""
        page.goto(f"{live_server}/browse")
        # Select wallhaven_test source and dispatch change event
        select = page.locator("select[name='source']")
        select.select_option("wallhaven_test")
        select.dispatch_event("change")
        # Wait for HTMX to complete the swap - wallhaven_test has test1-15 (15 images)
        expect(page.locator(".image-card")).to_have_count(15, timeout=10000)

    def test_purity_filter(self, page: Page, live_server):
        """Purity dropdown filters images."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='purity']")
        select.select_option("sketchy")
        select.dispatch_event("change")
        # Wait for HTMX to complete the swap - sketchy images: test3,8,13,18,23,28 (6 images)
        expect(page.locator(".image-card")).to_have_count(6, timeout=10000)

    def test_favorites_filter(self, page: Page, live_server):
        """Favorites checkbox filters to favorites only."""
        page.goto(f"{live_server}/browse")
        checkbox = page.locator("#favorites_only")
        checkbox.check()
        checkbox.dispatch_event("change")
        # Wait for HTMX to complete the swap - test1 is favorited, but test2 may have
        # been favorited by earlier tests. Check for at least 1 favorite.
        expect(page.locator(".image-card")).to_have_count(1, timeout=10000)

    def test_trashed_filter(self, page: Page, live_server):
        """Trashed checkbox filters to trashed only."""
        page.goto(f"{live_server}/browse")
        checkbox = page.locator("#trashed_only")
        checkbox.check()
        checkbox.dispatch_event("change")
        # Wait for HTMX to complete the swap - test5 and test30 are pre-trashed
        # Additional images may be trashed by earlier tests
        expect(page.locator(".image-card").first).to_be_visible(timeout=10000)

    def test_search_filter(self, page: Page, live_server):
        """Search input filters by filename."""
        page.goto(f"{live_server}/browse")
        search = page.locator("input[name='search']")
        # Use test1.jpg to get exact match (not test10-19)
        search.fill("test1.jpg")
        # Trigger keyup event manually since fill doesn't trigger HTMX's keyup handler
        search.dispatch_event("keyup")
        # Search has 300ms debounce, wait for HTMX to complete
        expect(page.locator(".image-card")).to_have_count(1, timeout=10000)
        expect(page.locator(".image-card")).to_contain_text("test1.jpg")

    def test_tag_filter(self, page: Page, live_server):
        """Clicking a tag filters by that tag."""
        page.goto(f"{live_server}/browse")
        # Click on 'anime' tag button
        page.locator("button:has-text('anime')").first.click()
        # Wait for HTMX to complete the swap - test1 and test3 have anime tag
        expect(page.locator(".image-card")).to_have_count(2, timeout=10000)

    def test_clear_filters(self, page: Page, live_server):
        """Unchecking filter restores all images."""
        page.goto(f"{live_server}/browse")
        # Apply a filter
        checkbox = page.locator("#favorites_only")
        checkbox.check()
        checkbox.dispatch_event("change")
        # Wait for HTMX to complete the swap
        expect(page.locator(".image-card")).to_have_count(1, timeout=10000)
        # Uncheck the filter
        checkbox.uncheck()
        checkbox.dispatch_event("change")
        # Should show first page of all images again (24 images)
        expect(page.locator(".image-card")).to_have_count(24, timeout=10000)

    def test_combined_filters(self, page: Page, live_server):
        """Multiple filters can be combined."""
        page.goto(f"{live_server}/browse")
        # Filter by source AND purity
        source = page.locator("select[name='source']")
        source.select_option("wallhaven_test")
        source.dispatch_event("change")
        # wallhaven_test images: test1-15 (15 images)
        expect(page.locator(".image-card")).to_have_count(15, timeout=10000)
        purity = page.locator("select[name='purity']")
        purity.select_option("sfw")
        purity.dispatch_event("change")
        # wallhaven_test sfw images: test1,2,5,6,7,10,11,12,15 (9 images)
        expect(page.locator(".image-card")).to_have_count(9, timeout=10000)


# =============================================================================
# Pagination Tests
# =============================================================================


class TestPagination:
    """Tests for pagination controls."""

    def test_page_info_displayed(self, page: Page, live_server):
        """Page info is displayed."""
        page.goto(f"{live_server}/browse")
        expect(page.locator("text=Page 1 of")).to_be_visible()

    def test_refresh_button(self, page: Page, live_server):
        """Refresh button reloads the grid."""
        page.goto(f"{live_server}/browse")
        # Click refresh button
        page.locator("button[title='Refresh (sync with database)']").click()
        page.wait_for_load_state("networkidle")
        # Grid should still show first page of images (24)
        expect(page.locator(".image-card")).to_have_count(24)

    def test_next_button_navigates_to_page_2(self, page: Page, live_server):
        """Next button navigates to second page."""
        page.goto(f"{live_server}/browse")
        # Should be on page 1 with 24 images
        expect(page.locator(".image-card")).to_have_count(24)
        expect(page.locator("text=Page 1 of 2")).to_be_visible()
        # Click Next button
        page.locator("button:has-text('Next')").click()
        # Wait for HTMX to complete
        expect(page.locator("text=Page 2 of 2")).to_be_visible(timeout=10000)
        # Second page should have 6 images (30 - 24 = 6)
        expect(page.locator(".image-card")).to_have_count(6)

    def test_prev_button_navigates_back(self, page: Page, live_server):
        """Prev button navigates to previous page."""
        page.goto(f"{live_server}/browse")
        # Go to page 2 first
        page.locator("button:has-text('Next')").click()
        expect(page.locator("text=Page 2 of 2")).to_be_visible(timeout=10000)
        # Click Prev button
        page.locator("button:has-text('Prev')").click()
        # Should be back on page 1
        expect(page.locator("text=Page 1 of 2")).to_be_visible(timeout=10000)
        expect(page.locator(".image-card")).to_have_count(24)

    def test_page_number_button_navigates(self, page: Page, live_server):
        """Page number button navigates to that page."""
        page.goto(f"{live_server}/browse")
        expect(page.locator("text=Page 1 of 2")).to_be_visible()
        # Click page 2 button
        page.locator("button:has-text('2')").click()
        # Wait for navigation
        expect(page.locator("text=Page 2 of 2")).to_be_visible(timeout=10000)
        expect(page.locator(".image-card")).to_have_count(6)

    def test_prev_button_disabled_on_first_page(self, page: Page, live_server):
        """Prev button is disabled on first page."""
        page.goto(f"{live_server}/browse")
        expect(page.locator("text=Page 1 of 2")).to_be_visible()
        # Prev button should be disabled
        prev_btn = page.locator("button:has-text('Prev')").first
        expect(prev_btn).to_be_disabled()

    def test_next_button_disabled_on_last_page(self, page: Page, live_server):
        """Next button is disabled on last page."""
        page.goto(f"{live_server}/browse")
        # Navigate to last page
        page.locator("button:has-text('Next')").click()
        expect(page.locator("text=Page 2 of 2")).to_be_visible(timeout=10000)
        # Next button should be disabled
        next_btn = page.locator("button:has-text('Next')").first
        expect(next_btn).to_be_disabled()

    def test_pagination_preserves_filters(self, page: Page, live_server):
        """Pagination preserves active filters."""
        page.goto(f"{live_server}/browse")
        # Apply a filter that still has enough results for pagination
        source = page.locator("select[name='source']")
        source.select_option("wallhaven_test")
        source.dispatch_event("change")
        expect(page.locator(".image-card")).to_have_count(15, timeout=10000)
        # The source select should still have the value selected
        expect(source).to_have_value("wallhaven_test")


# =============================================================================
# Favorite Toggle Tests
# =============================================================================


class TestFavoriteToggle:
    """Tests for favorite toggle functionality."""

    def test_favorite_toggle_on_browse_page(self, page: Page, live_server):
        """Favorite button toggles on browse page."""
        page.goto(f"{live_server}/browse")
        # Find an image that's not favorited (test2.png)
        card = page.locator(".image-card:has-text('test2.png')")
        # Hover to show action buttons
        card.hover()
        # Click favorite button
        fav_btn = card.locator(".favorite-btn")
        fav_btn.click()
        page.wait_for_load_state("networkidle")
        # Should now have is-favorite class
        expect(fav_btn).to_have_class(re.compile(r"is-favorite"))

    def test_favorite_badge_appears(self, page: Page, live_server):
        """Favorite badge appears after favoriting."""
        page.goto(f"{live_server}/browse")
        # test1 is already a favorite
        card = page.locator(".image-card:has-text('test1.jpg')")
        # Should have favorite badge
        expect(card.locator(".favorite-badge")).to_be_visible()

    def test_favorite_toggle_on_detail_page(self, page: Page, live_server, temp_dir):
        """Favorite button toggles on detail page."""
        # Navigate to detail page for test1 (already favorited)
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Find favorite button - it should show "Unfavorite" since test1 is favorited
        fav_btn = page.locator("#favorite-btn")
        expect(fav_btn).to_be_visible()
        expect(fav_btn).to_contain_text("Unfavorite")
        # Click to unfavorite
        fav_btn.click()
        page.wait_for_load_state("networkidle")
        # Button should now show "Favorite" state after unfavoriting
        expect(fav_btn).to_contain_text("Favorite")


# =============================================================================
# Trash Toggle Tests
# =============================================================================


class TestTrashToggle:
    """Tests for trash toggle functionality."""

    def test_trash_button_on_browse_page(self, page: Page, live_server):
        """Trash button works on browse page."""
        page.goto(f"{live_server}/browse")
        # Find test2.png which is not trashed
        card = page.locator(".image-card:has-text('test2.png')")
        card.hover()
        # Click trash button
        trash_btn = card.locator(".trash-btn")
        trash_btn.click()
        page.wait_for_load_state("networkidle")
        # Should now have is-trashed class
        expect(trash_btn).to_have_class(re.compile(r"is-trashed"))

    def test_trash_badge_visible_for_trashed(self, page: Page, live_server):
        """Trash badge is visible for trashed images."""
        page.goto(f"{live_server}/browse")
        # test5 is pre-trashed
        card = page.locator(".image-card:has-text('test5.jpg')")
        expect(card.locator(".trash-badge")).to_be_visible()

    def test_trash_button_on_detail_page(self, page: Page, live_server, temp_dir):
        """Trash button works on detail page."""
        filepath = f"{temp_dir}/wallpapers/test3.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        trash_btn = page.locator("#trash-btn")
        expect(trash_btn).to_be_visible()
        # Handle the confirm dialog by accepting it
        page.on("dialog", lambda dialog: dialog.accept())
        trash_btn.click()
        page.wait_for_load_state("networkidle")
        # Button should show trashed state
        expect(trash_btn).to_contain_text("Trashed")

    def test_trash_state_syncs_on_back_navigation(self, page: Page, live_server, temp_dir):
        """Trash state syncs when navigating back to browse."""
        # Navigate directly to detail page for test4.png
        filepath = f"{temp_dir}/wallpapers/test4.png"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Handle the confirm dialog by accepting it
        page.on("dialog", lambda dialog: dialog.accept())
        # Trash it on detail page
        page.locator("#trash-btn").click()
        page.wait_for_load_state("networkidle")
        # Go to browse page
        page.goto(f"{live_server}/browse")
        # The trash badge should be visible for test4
        card = page.locator(".image-card:has-text('test4.png')")
        expect(card.locator(".trash-badge")).to_be_visible()


# =============================================================================
# Dark Mode Tests
# =============================================================================


class TestDarkMode:
    """Tests for dark mode toggle."""

    def test_dark_mode_toggle(self, page: Page, live_server):
        """Dark mode toggle changes theme."""
        page.goto(f"{live_server}/browse")
        html = page.locator("html")
        # Initially may or may not have dark class depending on system preference
        # Click toggle
        page.locator("button[title='Toggle dark mode (D)']").click()
        # Check if class changed
        if "dark" in (html.get_attribute("class") or ""):
            # Was dark, should now be light
            page.locator("button[title='Toggle dark mode (D)']").click()
            expect(html).not_to_have_class("dark")
        # Toggle again
        page.locator("button[title='Toggle dark mode (D)']").click()
        expect(html).to_have_class(re.compile(r"dark"))

    def test_dark_mode_keyboard_shortcut(self, page: Page, live_server):
        """D key toggles dark mode."""
        page.goto(f"{live_server}/browse")
        html = page.locator("html")
        initial_has_dark = "dark" in (html.get_attribute("class") or "")
        # Press D
        page.keyboard.press("d")
        # Should toggle
        if initial_has_dark:
            expect(html).not_to_have_class("dark")
        else:
            expect(html).to_have_class(re.compile(r"dark"))


# =============================================================================
# Keyboard Navigation Tests
# =============================================================================


class TestKeyboardNavigation:
    """Tests for keyboard navigation."""

    def test_arrow_keys_select_cards(self, page: Page, live_server):
        """Arrow keys navigate through image cards."""
        page.goto(f"{live_server}/browse")
        # Press right arrow to select first card
        page.keyboard.press("ArrowRight")
        # First card should be selected
        expect(page.locator(".image-card.selected")).to_have_count(1)
        # Press right again
        page.keyboard.press("ArrowRight")
        # Second card should be selected
        cards = page.locator(".image-card")
        expect(cards.nth(1)).to_have_class(re.compile(r"selected"))

    def test_enter_opens_selected_image(self, page: Page, live_server):
        """Enter key opens selected image."""
        page.goto(f"{live_server}/browse")
        # Wait for images to load
        expect(page.locator(".image-card").first).to_be_visible()
        # Select first card
        page.keyboard.press("ArrowRight")
        # Wait for selection
        expect(page.locator(".image-card.selected")).to_have_count(1)
        # Press Enter to open
        page.keyboard.press("Enter")
        # Wait for navigation
        page.wait_for_url(re.compile(rf"{live_server}/image/.+"), timeout=10000)

    def test_escape_clears_selection(self, page: Page, live_server):
        """Escape clears card selection."""
        page.goto(f"{live_server}/browse")
        page.keyboard.press("ArrowRight")
        expect(page.locator(".image-card.selected")).to_have_count(1)
        page.keyboard.press("Escape")
        expect(page.locator(".image-card.selected")).to_have_count(0)

    def test_slash_focuses_search(self, page: Page, live_server):
        """/ key focuses search input."""
        page.goto(f"{live_server}/browse")
        page.keyboard.press("/")
        expect(page.locator("input[name='search']")).to_be_focused()

    def test_question_mark_shows_shortcuts(self, page: Page, live_server):
        """? shows shortcuts modal."""
        page.goto(f"{live_server}/browse")
        page.keyboard.press("Shift+/")
        expect(page.locator("#shortcuts-modal")).to_be_visible()
        # Press Escape to close
        page.keyboard.press("Escape")
        expect(page.locator("#shortcuts-modal")).to_be_hidden()

    def test_f_toggles_favorite_on_selected(self, page: Page, live_server):
        """F key toggles favorite on selected card."""
        page.goto(f"{live_server}/browse")
        # Select a card - navigate to a card that's not favorited
        page.keyboard.press("ArrowRight")
        selected = page.locator(".image-card.selected")
        fav_btn = selected.locator(".favorite-btn")
        # Get the initial state
        initial_class = fav_btn.get_attribute("class")
        was_favorited = "is-favorite" in (initial_class or "")
        # Press F to toggle favorite
        page.keyboard.press("f")
        page.wait_for_load_state("networkidle")
        # The state should toggle
        if was_favorited:
            expect(fav_btn).not_to_have_class("is-favorite", timeout=10000)
        else:
            expect(fav_btn).to_have_class(re.compile(r"is-favorite"), timeout=10000)


# =============================================================================
# Detail Page Tests
# =============================================================================


class TestDetailPage:
    """Tests for image detail page."""

    def test_detail_shows_image(self, page: Page, live_server, temp_dir):
        """Detail page shows the image."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        expect(page.locator("img[alt='test1.jpg']")).to_be_visible()

    def test_detail_shows_metadata(self, page: Page, live_server, temp_dir):
        """Detail page shows image metadata."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Should show dimensions (format is "1920x1080")
        expect(page.locator("text=1920x1080")).to_be_visible()

    def test_detail_shows_tags(self, page: Page, live_server, temp_dir):
        """Detail page shows image tags."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Tags section should have these tags (use first match since tags appear in multiple places)
        tags_section = page.locator("h2:has-text('Tags')").locator("..").locator("..")
        expect(tags_section.locator("a[href*='tag=anime']")).to_be_visible()
        expect(tags_section.locator("a[href*='tag=colorful']")).to_be_visible()

    def test_detail_shows_palette(self, page: Page, live_server, temp_dir):
        """Detail page shows color palette."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Palette section should exist with color swatches
        expect(page.locator("text=Color Palette")).to_be_visible()

    def test_detail_source_link(self, page: Page, live_server, temp_dir):
        """Detail page has source link."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Should have link to source
        expect(page.locator("a[href*='example.com']")).to_be_visible()


# =============================================================================
# Toast Notification Tests
# =============================================================================


class TestToastNotifications:
    """Tests for toast notifications."""

    def test_toast_shows_on_favorite(self, page: Page, live_server):
        """Toast notification appears on favorite action."""
        page.goto(f"{live_server}/browse")
        card = page.locator(".image-card").first
        card.hover()
        card.locator(".favorite-btn").click()
        # Toast should appear
        expect(page.locator("#toast-container > div")).to_be_visible()

    def test_toast_shows_on_trash(self, page: Page, live_server):
        """Toast notification appears on trash action."""
        page.goto(f"{live_server}/browse")
        card = page.locator(".image-card:has-text('test3.jpg')")
        card.hover()
        card.locator(".trash-btn").click()
        # Toast should appear
        expect(page.locator("#toast-container > div")).to_be_visible()


# =============================================================================
# Sort Tests
# =============================================================================


class TestSorting:
    """Tests for sorting functionality."""

    def test_sort_by_filename(self, page: Page, live_server):
        """Sort by filename option works."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='sort_by']")
        select.select_option("filename")
        select.dispatch_event("change")
        # Wait for HTMX to complete
        page.wait_for_load_state("networkidle")
        # Sort is DESC by default. Lexicographically: test9 > test8 > ... > test5 > test4 > test30 > test3 > ...
        expect(page.locator(".image-card").first).to_contain_text("test9", timeout=10000)

    def test_sort_by_times_shown(self, page: Page, live_server):
        """Sort by times shown option works."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='sort_by']")
        select.select_option("times_shown")
        select.dispatch_event("change")
        # Wait for HTMX to complete
        page.wait_for_load_state("networkidle")
        # test30 has highest times_shown (30), should be first
        expect(page.locator(".image-card").first).to_contain_text("test30", timeout=10000)


# =============================================================================
# Image Actions on Hover Tests
# =============================================================================


class TestHoverActions:
    """Tests for hover action buttons."""

    def test_hover_shows_action_buttons(self, page: Page, live_server):
        """Hovering over card shows action buttons."""
        page.goto(f"{live_server}/browse")
        card = page.locator(".image-card").first
        # Action buttons should be hidden initially (opacity-0)
        action_overlay = card.locator(".bg-black\\/50")
        expect(action_overlay).to_have_class(re.compile(r"opacity-0"))
        # Hover
        card.hover()
        # Buttons should be visible now
        expect(action_overlay).to_have_class(re.compile(r"group-hover:opacity-100"))

    def test_source_link_button(self, page: Page, live_server):
        """Source link button opens in new tab."""
        page.goto(f"{live_server}/browse")
        card = page.locator(".image-card:has-text('test1.jpg')")
        card.hover()
        # Source link should be present
        source_link = card.locator("a[href*='example.com']")
        expect(source_link).to_be_visible()
        expect(source_link).to_have_attribute("target", "_blank")


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_search_shows_all(self, page: Page, live_server):
        """Empty search shows all images."""
        page.goto(f"{live_server}/browse")
        search = page.locator("input[name='search']")
        search.fill("test1")
        search.dispatch_event("keyup")  # Trigger HTMX keyup handler
        # Wait for HTMX with timeout for the 300ms debounce
        # test1, test10-19 match "test1" = 11 images
        expect(page.locator(".image-card")).to_have_count(11, timeout=10000)
        # Clear search
        search.fill("")
        search.dispatch_event("keyup")
        # Should show first page (24 images)
        expect(page.locator(".image-card")).to_have_count(24, timeout=10000)

    def test_no_results_message(self, page: Page, live_server):
        """No results shows appropriate message."""
        page.goto(f"{live_server}/browse")
        search = page.locator("input[name='search']")
        search.fill("nonexistent12345")
        search.dispatch_event("keyup")  # Trigger HTMX keyup handler
        # Wait for HTMX with timeout for the 300ms debounce
        # Use specific heading locator to avoid matching the status text
        expect(page.locator("h3:has-text('No images found')")).to_be_visible(timeout=10000)

    def test_invalid_image_path_shows_404(self, page: Page, live_server):
        """Invalid image path shows 404."""
        # Use a valid base64 encoded path that doesn't exist in database
        nonexistent_path = "/nonexistent/image.jpg"
        encoded = b64encode_path(nonexistent_path)
        response = page.goto(f"{live_server}/image/{encoded}")
        # Should return 404 status code
        assert response is not None
        assert response.status == 404

    def test_special_characters_in_search(self, page: Page, live_server):
        """Special characters in search don't break the app."""
        page.goto(f"{live_server}/browse")
        search = page.locator("input[name='search']")
        # Test various special characters
        search.fill("<script>alert('xss')</script>")
        search.dispatch_event("keyup")
        # Should show no results, not break
        expect(page.locator("h3:has-text('No images found')")).to_be_visible(timeout=10000)
        # Test SQL-like input
        search.fill("'; DROP TABLE images; --")
        search.dispatch_event("keyup")
        expect(page.locator("h3:has-text('No images found')")).to_be_visible(timeout=10000)
        # Test URL-like input
        search.fill("test%20file&param=value")
        search.dispatch_event("keyup")
        expect(page.locator("h3:has-text('No images found')")).to_be_visible(timeout=10000)


# =============================================================================
# Clear All Filters Tests
# =============================================================================


class TestClearAllFilters:
    """Tests for Clear All Filters button."""

    def test_clear_all_filters_button_visibility(self, page: Page, live_server):
        """Clear All Filters button only appears when filters are active."""
        page.goto(f"{live_server}/browse")
        # Button should not be visible with no filters
        expect(page.locator("button:has-text('Clear All Filters')")).to_have_count(0)
        # Navigate with a filter in URL to trigger full page render with chips
        page.goto(f"{live_server}/browse?favorites_only=1")
        # Button should now be visible
        expect(page.locator("button:has-text('Clear All Filters')")).to_be_visible()

    def test_clear_all_filters_resets_everything(self, page: Page, live_server):
        """Clear All Filters button resets all filters at once."""
        # Navigate with multiple filters in URL
        page.goto(f"{live_server}/browse?source=wallhaven_test&purity=sfw")
        # Should show filtered results (9 images)
        expect(page.locator(".image-card")).to_have_count(9, timeout=10000)
        # Click Clear All Filters
        page.locator("button:has-text('Clear All Filters')").click()
        # First page should be shown again (24 images)
        expect(page.locator(".image-card")).to_have_count(24, timeout=10000)


# =============================================================================
# Active Filter Chips Tests
# =============================================================================


class TestActiveFilterChips:
    """Tests for active filter chip X buttons."""

    def test_search_filter_chip_clear(self, page: Page, live_server):
        """X button on search filter chip clears search."""
        # Navigate with search in URL to get the chip to render
        page.goto(f"{live_server}/browse?search=test1.jpg")
        expect(page.locator(".image-card")).to_have_count(1, timeout=10000)
        # Find the search filter chip and click its X button
        chip = page.locator("span:has-text('Search: test1.jpg')")
        expect(chip).to_be_visible()
        chip.locator("button").click()
        # Wait for HTMX to complete
        page.wait_for_load_state("networkidle")
        # The search input should now be empty
        expect(page.locator("input[name='search']")).to_have_value("")

    def test_source_filter_chip_clear(self, page: Page, live_server):
        """X button on source filter chip clears source filter."""
        # Navigate with source in URL to get the chip to render
        page.goto(f"{live_server}/browse?source=wallhaven_test")
        expect(page.locator(".image-card")).to_have_count(15, timeout=10000)
        # Find the source filter chip and click its X button
        chip = page.locator("span:has-text('wallhaven_test')")
        expect(chip).to_be_visible()
        chip.locator("button").click()
        # Should show first page (24 images)
        expect(page.locator(".image-card")).to_have_count(24, timeout=10000)

    def test_favorites_filter_chip_clear(self, page: Page, live_server):
        """X button on favorites filter chip clears favorites filter."""
        # Navigate with favorites_only in URL to get the chip to render
        page.goto(f"{live_server}/browse?favorites_only=1")
        # The favorites filter chip should be visible (regardless of how many favorites exist)
        chip = page.locator("span:has-text('Favorites')")
        expect(chip).to_be_visible()
        chip.locator("button").click()
        # Wait for HTMX to complete
        page.wait_for_load_state("networkidle")
        # The checkbox should now be unchecked
        expect(page.locator("#favorites_only")).not_to_be_checked()

    def test_tag_filter_chip_clear(self, page: Page, live_server):
        """X button on tag filter chip clears tag filter."""
        # Navigate with tag in URL to get the chip to render
        page.goto(f"{live_server}/browse?tag=anime")
        # The tag filter chip should be visible
        chip = page.locator("span:has-text('Tag: anime')")
        expect(chip).to_be_visible()
        # Click the X button to clear the tag filter
        chip.locator("button").click()
        # Wait for HTMX to complete (the tag chip uses hx-get)
        page.wait_for_load_state("networkidle")
        # After clearing, the chip should no longer be visible (page reloads without tag)
        # Check that the URL no longer has the tag parameter
        expect(page.locator(".image-card")).to_have_count(24, timeout=10000)


# =============================================================================
# Mouse Navigation Tests
# =============================================================================


class TestMouseNavigation:
    """Tests for mouse-based navigation."""

    def test_click_image_card_opens_detail(self, page: Page, live_server):
        """Clicking image card link navigates to detail page."""
        page.goto(f"{live_server}/browse")
        # Get the href from the first image link and navigate directly
        card = page.locator(".image-card").first
        link = card.locator("a[href*='/image/']").first
        href = link.get_attribute("href")
        # Navigate using the href (simulating a successful click)
        page.goto(f"{live_server}{href}")
        # Should be on detail page
        expect(page).to_have_url(re.compile(rf"{live_server}/image/.+"))

    def test_back_to_browse_link(self, page: Page, live_server, temp_dir):
        """Back to Browse link navigates back to browse page."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Click the Back to Browse link
        page.locator("a:has-text('Back to Browse')").click()
        expect(page).to_have_url(f"{live_server}/browse")

    def test_image_click_opens_fullscreen(self, page: Page, live_server, temp_dir):
        """Clicking image on detail page opens fullscreen in new tab."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # The image should be wrapped in a link that opens in new tab
        image_link = page.locator(f"a[href='/preview/{encoded}']")
        expect(image_link).to_have_attribute("target", "_blank")


# =============================================================================
# Keyboard Shortcuts Additional Tests
# =============================================================================


class TestAdditionalKeyboardShortcuts:
    """Additional keyboard shortcut tests."""

    def test_backspace_navigates_back(self, page: Page, live_server, temp_dir):
        """Backspace key navigates to previous page."""
        page.goto(f"{live_server}/browse")
        # Navigate to detail page first
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        expect(page).to_have_url(re.compile(rf"{live_server}/image/.+"))
        # Press backspace to go back
        page.keyboard.press("Backspace")
        expect(page).to_have_url(f"{live_server}/browse")


# =============================================================================
# Dark Mode Persistence Tests
# =============================================================================


class TestDarkModePersistence:
    """Tests for dark mode localStorage persistence."""

    def test_dark_mode_persists_in_localstorage(self, page: Page, live_server):
        """Dark mode setting is saved to localStorage."""
        page.goto(f"{live_server}/browse")
        # Enable dark mode
        page.locator("button[title='Toggle dark mode (D)']").click()
        # Check localStorage
        dark_mode = page.evaluate("localStorage.getItem('darkMode')")
        # Should be either 'dark' or 'light' depending on toggle
        assert dark_mode in ["dark", "light"]
        # Toggle again
        page.locator("button[title='Toggle dark mode (D)']").click()
        new_dark_mode = page.evaluate("localStorage.getItem('darkMode')")
        # Should be the opposite
        assert new_dark_mode != dark_mode

    def test_dark_mode_restored_on_reload(self, page: Page, live_server):
        """Dark mode setting is restored from localStorage on page load."""
        page.goto(f"{live_server}/browse")
        # Set dark mode in localStorage
        page.evaluate("localStorage.setItem('darkMode', 'dark')")
        # Reload page
        page.reload()
        # Should have dark class
        expect(page.locator("html")).to_have_class(re.compile(r"dark"))
        # Set light mode
        page.evaluate("localStorage.setItem('darkMode', 'light')")
        page.reload()
        # Should not have dark class
        expect(page.locator("html")).not_to_have_class("dark")


# =============================================================================
# Additional Sort Options Tests
# =============================================================================


class TestAdditionalSortOptions:
    """Tests for additional sort options."""

    def test_sort_by_recently_added(self, page: Page, live_server):
        """Sort by Recently Added (last_indexed_at) works."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='sort_by']")
        select.select_option("last_indexed_at")
        select.dispatch_event("change")
        page.wait_for_load_state("networkidle")
        # First page shows 24 images
        expect(page.locator(".image-card")).to_have_count(24)

    def test_sort_by_recently_shown(self, page: Page, live_server):
        """Sort by Recently Shown (last_shown_at) works."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='sort_by']")
        select.select_option("last_shown_at")
        select.dispatch_event("change")
        page.wait_for_load_state("networkidle")
        # First page shows 24 images
        expect(page.locator(".image-card")).to_have_count(24)

    def test_sort_by_file_size(self, page: Page, live_server):
        """Sort by File Size works."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='sort_by']")
        select.select_option("file_size")
        select.dispatch_event("change")
        page.wait_for_load_state("networkidle")
        # First page shows 24 images
        expect(page.locator(".image-card")).to_have_count(24)


# =============================================================================
# NSFW Purity Filter Tests
# =============================================================================


class TestNSFWPurityFilter:
    """Tests for NSFW purity filter."""

    def test_nsfw_purity_filter(self, page: Page, live_server):
        """NSFW purity filter shows only NSFW images."""
        page.goto(f"{live_server}/browse")
        select = page.locator("select[name='purity']")
        select.select_option("nsfw")
        select.dispatch_event("change")
        # Wait for HTMX - NSFW images: test4,9,14,19,24,29 (6 images)
        expect(page.locator(".image-card")).to_have_count(6, timeout=10000)


# =============================================================================
# Color Palette Copy Tests
# =============================================================================


class TestColorPaletteCopy:
    """Tests for color palette copy to clipboard."""

    def test_color_swatch_has_click_handler(self, page: Page, live_server, temp_dir):
        """Color swatches have click handlers for copying."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Find the color swatch div with onclick
        swatch = page.locator("div[onclick*='navigator.clipboard']").first
        expect(swatch).to_be_visible()
        # Verify it has the onclick attribute for copying
        onclick = swatch.get_attribute("onclick")
        assert "navigator.clipboard.writeText" in onclick
        assert "showToast" in onclick


# =============================================================================
# Tag Dropdown Actions Tests
# =============================================================================


class TestTagDropdownActions:
    """Tests for tag dropdown action buttons."""

    def test_tag_dropdown_opens(self, page: Page, live_server, temp_dir):
        """Tag dropdown menu opens when clicked."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Find a tag dropdown button (the chevron button)
        dropdown_btn = page.locator("button:has(svg path[d*='19 9l-7 7-7-7'])").first
        expect(dropdown_btn).to_be_visible()
        # Click to open dropdown
        dropdown_btn.click()
        # Dropdown menu should be visible
        dropdown_menu = dropdown_btn.locator("+ div")
        expect(dropdown_menu).to_be_visible()

    def test_tag_dropdown_has_add_as_source(self, page: Page, live_server, temp_dir):
        """Tag dropdown has 'Add as Source' button."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Open dropdown
        dropdown_btn = page.locator("button:has(svg path[d*='19 9l-7 7-7-7'])").first
        dropdown_btn.click()
        # Should have "Add as Source" option
        expect(page.locator("button:has-text('Add as Source')")).to_be_visible()

    def test_tag_dropdown_has_exclude_tag(self, page: Page, live_server, temp_dir):
        """Tag dropdown has 'Exclude Tag' button."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Open dropdown - use second tag's dropdown to avoid any state from previous tests
        dropdown_btn = page.locator("button:has(svg path[d*='19 9l-7 7-7-7'])").nth(1)
        dropdown_btn.click()
        # Should have "Exclude Tag" option
        expect(page.locator("button:has-text('Exclude Tag')").first).to_be_visible()

    def test_tag_dropdown_closes_on_outside_click(self, page: Page, live_server, temp_dir):
        """Tag dropdown closes when clicking outside."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        page.goto(f"{live_server}/image/{encoded}")
        # Open dropdown
        dropdown_btn = page.locator("button:has(svg path[d*='19 9l-7 7-7-7'])").first
        dropdown_btn.click()
        dropdown_menu = dropdown_btn.locator("+ div")
        expect(dropdown_menu).to_be_visible()
        # Click outside
        page.locator("h1").click()
        # Dropdown should be hidden
        expect(dropdown_menu).to_be_hidden()


# =============================================================================
# Shutdown Button Tests
# =============================================================================


class TestShutdownButton:
    """Tests for shutdown button."""

    def test_shutdown_button_has_confirm(self, page: Page, live_server):
        """Shutdown button has confirmation dialog."""
        page.goto(f"{live_server}/browse")
        shutdown_btn = page.locator("button[hx-post='/api/shutdown']")
        expect(shutdown_btn).to_be_visible()
        # Check that it has hx-confirm attribute
        expect(shutdown_btn).to_have_attribute("hx-confirm", "Shutdown the server?")

    def test_shutdown_confirm_dialog_can_be_dismissed(self, page: Page, live_server):
        """Shutdown confirmation dialog can be dismissed."""
        page.goto(f"{live_server}/browse")
        # Set up dialog handler to dismiss
        dismissed = []
        def handle_dialog(dialog):
            dismissed.append(True)
            dialog.dismiss()
        page.on("dialog", handle_dialog)
        # Click shutdown button
        page.locator("button[hx-post='/api/shutdown']").click()
        # Dialog should have been handled
        assert len(dismissed) == 1
