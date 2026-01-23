# tests/db_browser/test_e2e.py
"""End-to-end tests for the database browser web application."""

import base64
import pytest


def b64encode_path(filepath: str) -> str:
    """Encode filepath to URL-safe base64."""
    return base64.urlsafe_b64encode(filepath.encode("utf-8")).decode("ascii").rstrip("=")


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, test_client):
        """Health endpoint returns status ok."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["db_exists"] is True
        assert "image_count" in data
        assert "source_count" in data

    def test_health_shows_correct_counts(self, test_client):
        """Health endpoint shows correct image/source counts."""
        response = test_client.get("/health")
        data = response.json()
        assert data["image_count"] == 3
        assert data["source_count"] == 2  # wallhaven_test and unsplash_test


class TestBrowsePage:
    """Tests for /browse page."""

    def test_browse_returns_html(self, test_client):
        """Browse page returns HTML."""
        response = test_client.get("/browse")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_browse_contains_images(self, test_client):
        """Browse page contains image cards."""
        response = test_client.get("/browse")
        assert "image-card" in response.text
        assert "test1.jpg" in response.text

    def test_browse_htmx_returns_partial(self, test_client):
        """HTMX request returns grid partial only."""
        response = test_client.get("/browse", headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Partial should not contain full HTML structure
        assert "<!DOCTYPE html>" not in response.text
        assert "image-card" in response.text

    def test_browse_filter_by_source(self, test_client):
        """Browse can filter by source."""
        response = test_client.get("/browse?source=wallhaven_test")
        assert response.status_code == 200
        assert "test1.jpg" in response.text
        assert "test3.jpg" in response.text
        # test2.png is from unsplash, should not appear
        assert "test2.png" not in response.text

    def test_browse_filter_by_purity(self, test_client):
        """Browse can filter by purity."""
        response = test_client.get("/browse?purity=sketchy")
        assert response.status_code == 200
        assert "test3.jpg" in response.text
        # Other images are sfw
        assert "test1.jpg" not in response.text
        assert "test2.png" not in response.text

    def test_browse_filter_favorites_only(self, test_client):
        """Browse can filter to favorites only."""
        response = test_client.get("/browse?favorites_only=1")
        assert response.status_code == 200
        assert "test1.jpg" in response.text
        # Others are not favorites
        assert "test2.png" not in response.text
        assert "test3.jpg" not in response.text

    def test_browse_search(self, test_client):
        """Browse can search by filename."""
        response = test_client.get("/browse?search=test1")
        assert response.status_code == 200
        assert "test1.jpg" in response.text
        assert "test2.png" not in response.text

    def test_browse_filter_by_tag(self, test_client):
        """Browse can filter by tag."""
        response = test_client.get("/browse?tag=anime")
        assert response.status_code == 200
        assert "test1.jpg" in response.text
        assert "test2.png" not in response.text

    def test_browse_pagination(self, test_client):
        """Browse supports pagination."""
        response = test_client.get("/browse?page=1")
        assert response.status_code == 200
        assert "Page 1" in response.text

    def test_browse_sort_options(self, test_client):
        """Browse supports different sort options."""
        for sort_by in ["last_indexed_at", "filename", "times_shown"]:
            response = test_client.get(f"/browse?sort_by={sort_by}")
            assert response.status_code == 200


class TestImagePreview:
    """Tests for /preview/{path} endpoint."""

    def test_preview_serves_image(self, test_client, temp_dir):
        """Preview endpoint serves image files."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/preview/{encoded}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"

    def test_preview_serves_png(self, test_client, temp_dir):
        """Preview endpoint serves PNG files."""
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/preview/{encoded}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_preview_inline_disposition(self, test_client, temp_dir):
        """Preview sets inline content-disposition."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/preview/{encoded}")
        assert "inline" in response.headers["content-disposition"]

    def test_preview_caching_headers(self, test_client, temp_dir):
        """Preview sets cache headers."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/preview/{encoded}")
        assert "max-age" in response.headers.get("cache-control", "")

    def test_preview_invalid_encoding(self, test_client):
        """Preview returns 400 for invalid base64."""
        response = test_client.get("/preview/not-valid-base64!!!")
        assert response.status_code == 400

    def test_preview_image_not_in_db(self, test_client, temp_dir):
        """Preview returns 404 for image not in database."""
        filepath = f"{temp_dir}/wallpapers/nonexistent.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/preview/{encoded}")
        assert response.status_code == 404

    def test_preview_path_traversal_blocked(self, test_client):
        """Preview blocks path traversal attempts."""
        # Try to access /etc/passwd
        filepath = "/etc/passwd"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/preview/{encoded}")
        # Should fail - either not in DB or path not allowed
        assert response.status_code in (403, 404)


class TestImageDetail:
    """Tests for /image/{path} detail page."""

    def test_detail_returns_html(self, test_client, temp_dir):
        """Detail page returns HTML."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/image/{encoded}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_detail_shows_filename(self, test_client, temp_dir):
        """Detail page shows filename in title."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/image/{encoded}")
        assert "test1.jpg" in response.text

    def test_detail_shows_tags(self, test_client, temp_dir):
        """Detail page shows image tags."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/image/{encoded}")
        assert "anime" in response.text
        assert "colorful" in response.text

    def test_detail_shows_palette(self, test_client, temp_dir):
        """Detail page shows color palette."""
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/image/{encoded}")
        # Check for palette colors
        assert "#ff0000" in response.text or "ff0000" in response.text.lower()

    def test_detail_invalid_path(self, test_client):
        """Detail page returns 400 for invalid encoding."""
        response = test_client.get("/image/invalid!!!")
        assert response.status_code == 400

    def test_detail_not_found(self, test_client, temp_dir):
        """Detail page returns 404 for missing image."""
        filepath = f"{temp_dir}/wallpapers/nonexistent.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.get(f"/image/{encoded}")
        assert response.status_code == 404


class TestFavoriteAPI:
    """Tests for /api/images/{path}/favorite endpoint."""

    def test_favorite_toggle_on(self, test_client, temp_dir):
        """Favorite endpoint can set favorite to true."""
        # test2.png is not a favorite initially
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/favorite")
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorite"] is True

    def test_favorite_toggle_off(self, test_client, temp_dir):
        """Favorite endpoint can set favorite to false."""
        # test1.jpg is a favorite initially
        filepath = f"{temp_dir}/wallpapers/test1.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/favorite")
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorite"] is False

    def test_favorite_htmx_trigger(self, test_client, temp_dir):
        """Favorite endpoint returns HX-Trigger header."""
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/favorite")
        assert "HX-Trigger" in response.headers
        assert "showToast" in response.headers["HX-Trigger"]

    def test_favorite_not_found(self, test_client, temp_dir):
        """Favorite endpoint returns 404 for missing image."""
        filepath = f"{temp_dir}/wallpapers/nonexistent.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/favorite")
        assert response.status_code == 404

    def test_favorite_readonly_blocked(self, readonly_client, temp_dir):
        """Favorite endpoint blocked in readonly mode."""
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = readonly_client.post(f"/api/images/{encoded}/favorite")
        assert response.status_code == 403


class TestTrashAPI:
    """Tests for /api/images/{path}/trash endpoint."""

    def test_trash_records_action(self, test_client, temp_dir):
        """Trash endpoint records trash action."""
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/trash")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_trash_htmx_trigger(self, test_client, temp_dir):
        """Trash endpoint returns HX-Trigger header."""
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/trash")
        assert "HX-Trigger" in response.headers
        assert "showToast" in response.headers["HX-Trigger"]

    def test_trash_not_found(self, test_client, temp_dir):
        """Trash endpoint returns 404 for missing image."""
        filepath = f"{temp_dir}/wallpapers/nonexistent.jpg"
        encoded = b64encode_path(filepath)
        response = test_client.post(f"/api/images/{encoded}/trash")
        assert response.status_code == 404

    def test_trash_readonly_blocked(self, readonly_client, temp_dir):
        """Trash endpoint blocked in readonly mode."""
        filepath = f"{temp_dir}/wallpapers/test2.png"
        encoded = b64encode_path(filepath)
        response = readonly_client.post(f"/api/images/{encoded}/trash")
        assert response.status_code == 403


class TestSourcesAPI:
    """Tests for /api/sources endpoint."""

    def test_sources_returns_list(self, test_client):
        """Sources endpoint returns list of sources."""
        response = test_client.get("/api/sources")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_sources_has_image_counts(self, test_client):
        """Sources include image counts."""
        response = test_client.get("/api/sources")
        data = response.json()
        # wallhaven_test has 2 images, unsplash_test has 1
        wallhaven = next(s for s in data if s["source_id"] == "wallhaven_test")
        unsplash = next(s for s in data if s["source_id"] == "unsplash_test")
        assert wallhaven["image_count"] == 2
        assert unsplash["image_count"] == 1


class TestTagsAPI:
    """Tests for /api/tags endpoint."""

    def test_tags_returns_list(self, test_client):
        """Tags endpoint returns list of tags."""
        response = test_client.get("/api/tags")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # We have 4 unique tags: anime, colorful, nature, landscape
        assert len(data) == 4

    def test_tags_limit(self, test_client):
        """Tags endpoint respects limit parameter."""
        response = test_client.get("/api/tags?limit=2")
        data = response.json()
        assert len(data) <= 2


class TestIndexRedirect:
    """Tests for / index route."""

    def test_index_redirects_to_browse(self, test_client):
        """Index redirects to browse page."""
        response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/browse"


class TestKeyboardNavigation:
    """Tests for keyboard navigation JavaScript."""

    def test_browse_has_keyboard_script(self, test_client):
        """Browse page includes keyboard navigation code."""
        response = test_client.get("/browse")
        assert "keydown" in response.text
        assert "ArrowRight" in response.text
        assert "ArrowLeft" in response.text
        assert "selectedIndex" in response.text

    def test_browse_has_shortcuts_modal(self, test_client):
        """Browse page includes shortcuts modal."""
        response = test_client.get("/browse")
        assert "shortcuts-modal" in response.text
        assert "Keyboard Shortcuts" in response.text


class TestDarkMode:
    """Tests for dark mode functionality."""

    def test_browse_has_dark_mode_toggle(self, test_client):
        """Browse page includes dark mode toggle."""
        response = test_client.get("/browse")
        assert "toggleDarkMode" in response.text
        assert "localStorage" in response.text

    def test_browse_has_dark_mode_classes(self, test_client):
        """Browse page includes dark mode CSS classes."""
        response = test_client.get("/browse")
        assert "dark:" in response.text
        assert "dark:bg-gray" in response.text
