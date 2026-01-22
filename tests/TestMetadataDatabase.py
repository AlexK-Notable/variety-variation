#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for the metadata tracking database functionality (v6 schema)."""

import os
import tempfile
import unittest
import time

from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.models import ImageRecord


class TestMetadataDatabase(unittest.TestCase):
    """Tests for image metadata, tags, and user actions in the database."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_metadata.db")
        self.db = ImageDatabase(self.db_path)

        # Insert a test image to work with
        self.test_filepath = "/test/image.jpg"
        self.db.insert_image(ImageRecord(
            filepath=self.test_filepath,
            filename="image.jpg",
            source_id="wallhaven",
            width=1920,
            height=1080,
            aspect_ratio=1.78,
            file_size=100000,
            file_mtime=int(time.time()),
            is_favorite=False,
            first_indexed_at=int(time.time()),
            last_indexed_at=int(time.time()),
        ))

    def tearDown(self):
        """Clean up the temporary database."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        if os.path.exists(self.db_path + "-wal"):
            os.unlink(self.db_path + "-wal")
        if os.path.exists(self.db_path + "-shm"):
            os.unlink(self.db_path + "-shm")
        os.rmdir(self.temp_dir)

    def test_schema_version_is_6(self):
        """Verify schema version is 6 after migration."""
        self.assertEqual(self.db.SCHEMA_VERSION, 6)
        version = self.db._get_schema_version()
        self.assertEqual(version, 6)

    def test_metadata_tables_exist(self):
        """Verify all metadata tables were created."""
        cursor = self.db.conn.cursor()

        # Check image_metadata table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_metadata'")
        self.assertIsNotNone(cursor.fetchone(), "image_metadata table should exist")

        # Check tags table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tags'")
        self.assertIsNotNone(cursor.fetchone(), "tags table should exist")

        # Check image_tags table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_tags'")
        self.assertIsNotNone(cursor.fetchone(), "image_tags table should exist")

        # Check user_actions table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_actions'")
        self.assertIsNotNone(cursor.fetchone(), "user_actions table should exist")

    def test_upsert_and_get_image_metadata(self):
        """Test inserting and retrieving image metadata."""
        self.db.upsert_image_metadata(
            filepath=self.test_filepath,
            category="anime",
            purity="sfw",
            sfw_rating=100,
            source_colors=["#1a2b3c", "#4d5e6f", "#708192"],
            uploader="testuser",
            source_url="https://example.com/original",
            views=1000,
            favorites=50,
            uploaded_at=1700000000,
        )

        metadata = self.db.get_image_metadata(self.test_filepath)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["category"], "anime")
        self.assertEqual(metadata["purity"], "sfw")
        self.assertEqual(metadata["sfw_rating"], 100)
        self.assertEqual(metadata["source_colors"], ["#1a2b3c", "#4d5e6f", "#708192"])
        self.assertEqual(metadata["uploader"], "testuser")
        self.assertEqual(metadata["views"], 1000)
        self.assertEqual(metadata["favorites"], 50)

    def test_metadata_upsert_preserves_existing(self):
        """Test that upsert preserves existing values when new values are None."""
        # First insert
        self.db.upsert_image_metadata(
            filepath=self.test_filepath,
            category="anime",
            purity="sfw",
            views=1000,
        )

        # Second upsert with partial update
        self.db.upsert_image_metadata(
            filepath=self.test_filepath,
            favorites=100,  # Only update favorites
        )

        metadata = self.db.get_image_metadata(self.test_filepath)
        self.assertEqual(metadata["category"], "anime")  # Preserved
        self.assertEqual(metadata["purity"], "sfw")  # Preserved
        self.assertEqual(metadata["views"], 1000)  # Preserved
        self.assertEqual(metadata["favorites"], 100)  # Updated

    def test_upsert_and_get_tags(self):
        """Test inserting and retrieving tags."""
        tag_id = self.db.upsert_tag(
            tag_id=12345,
            name="landscape",
            alias="scenery",
            category="Nature",
            purity="sfw",
        )

        self.assertEqual(tag_id, 12345)

        tag = self.db.get_tag_by_name("landscape")
        self.assertIsNotNone(tag)
        self.assertEqual(tag["tag_id"], 12345)
        self.assertEqual(tag["alias"], "scenery")
        self.assertEqual(tag["category"], "Nature")

    def test_batch_upsert_tags(self):
        """Test batch inserting tags."""
        tags = [
            {"tag_id": 1, "name": "mountains", "category": "Nature"},
            {"tag_id": 2, "name": "ocean", "category": "Nature"},
            {"tag_id": 3, "name": "city", "category": "Urban"},
        ]

        tag_ids = self.db.upsert_tags_batch(tags)
        self.assertEqual(tag_ids, [1, 2, 3])

        # Verify they were inserted
        self.assertIsNotNone(self.db.get_tag_by_name("mountains"))
        self.assertIsNotNone(self.db.get_tag_by_name("ocean"))
        self.assertIsNotNone(self.db.get_tag_by_name("city"))

    def test_link_image_tags(self):
        """Test linking images to tags."""
        # Create some tags
        self.db.upsert_tags_batch([
            {"tag_id": 1, "name": "mountains"},
            {"tag_id": 2, "name": "sunset"},
            {"tag_id": 3, "name": "nature"},
        ])

        # Link to image
        self.db.link_image_tags(self.test_filepath, [1, 2, 3])

        # Retrieve tags for image
        tags = self.db.get_tags_for_image(self.test_filepath)
        self.assertEqual(len(tags), 3)
        tag_names = {t["name"] for t in tags}
        self.assertEqual(tag_names, {"mountains", "sunset", "nature"})

    def test_link_image_tags_replaces_existing(self):
        """Test that linking tags replaces existing links."""
        self.db.upsert_tags_batch([
            {"tag_id": 1, "name": "old_tag"},
            {"tag_id": 2, "name": "new_tag"},
        ])

        # First link
        self.db.link_image_tags(self.test_filepath, [1])
        tags = self.db.get_tags_for_image(self.test_filepath)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["name"], "old_tag")

        # Replace with new link
        self.db.link_image_tags(self.test_filepath, [2])
        tags = self.db.get_tags_for_image(self.test_filepath)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["name"], "new_tag")

    def test_get_images_by_tag(self):
        """Test finding images by tag name."""
        # Create second image
        second_filepath = "/test/image2.jpg"
        self.db.insert_image(ImageRecord(
            filepath=second_filepath,
            filename="image2.jpg",
            source_id="wallhaven",
            width=1920, height=1080, aspect_ratio=1.78,
            file_size=100000, file_mtime=int(time.time()),
            is_favorite=False,
            first_indexed_at=int(time.time()),
            last_indexed_at=int(time.time()),
        ))

        # Create tags
        self.db.upsert_tags_batch([
            {"tag_id": 1, "name": "shared_tag"},
            {"tag_id": 2, "name": "unique_tag"},
        ])

        # Link tags
        self.db.link_image_tags(self.test_filepath, [1, 2])
        self.db.link_image_tags(second_filepath, [1])

        # Find images by shared tag
        images = self.db.get_images_by_tag("shared_tag")
        self.assertEqual(len(images), 2)

        # Find images by unique tag
        images = self.db.get_images_by_tag("unique_tag")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0], self.test_filepath)

    def test_record_user_action(self):
        """Test recording user actions."""
        self.db.record_user_action(self.test_filepath, "favorite")
        time.sleep(0.01)  # Ensure different timestamps
        self.db.record_user_action(self.test_filepath, "trash")

        actions = self.db.get_user_actions(self.test_filepath)
        self.assertEqual(len(actions), 2)

        # Verify both actions are recorded (order depends on timestamp resolution)
        action_types = {a["action"] for a in actions}
        self.assertEqual(action_types, {"favorite", "trash"})

    def test_record_user_action_validates_type(self):
        """Test that invalid action types are rejected."""
        with self.assertRaises(ValueError):
            self.db.record_user_action(self.test_filepath, "invalid_action")

    def test_get_action_counts(self):
        """Test getting action counts."""
        # Record various actions
        self.db.record_user_action(self.test_filepath, "favorite")
        self.db.record_user_action(self.test_filepath, "favorite")
        self.db.record_user_action(self.test_filepath, "trash")

        counts = self.db.get_action_counts()
        self.assertEqual(counts.get("favorite"), 2)
        self.assertEqual(counts.get("trash"), 1)

    def test_tag_statistics(self):
        """Test getting tag usage statistics."""
        # Create tags and images
        self.db.upsert_tags_batch([
            {"tag_id": 1, "name": "popular_tag"},
            {"tag_id": 2, "name": "rare_tag"},
        ])

        # Create more images and link tags
        for i in range(5):
            filepath = f"/test/image{i}.jpg"
            self.db.insert_image(ImageRecord(
                filepath=filepath,
                filename=f"image{i}.jpg",
                source_id="wallhaven",
                width=1920, height=1080, aspect_ratio=1.78,
                file_size=100000, file_mtime=int(time.time()),
                is_favorite=False,
                first_indexed_at=int(time.time()),
                last_indexed_at=int(time.time()),
            ))
            # All images get popular_tag, only first gets rare_tag
            tags = [1] if i > 0 else [1, 2]
            self.db.link_image_tags(filepath, tags)

        stats = self.db.get_tag_statistics()
        self.assertGreater(len(stats), 0)

        # popular_tag should have more occurrences
        popular = next((s for s in stats if s["name"] == "popular_tag"), None)
        rare = next((s for s in stats if s["name"] == "rare_tag"), None)

        self.assertIsNotNone(popular)
        self.assertIsNotNone(rare)
        self.assertEqual(popular["count"], 5)
        self.assertEqual(rare["count"], 1)

    def test_favorite_tag_statistics(self):
        """Test getting tag statistics for favorited images."""
        # Create a favorited image
        fav_filepath = "/test/favorite.jpg"
        self.db.insert_image(ImageRecord(
            filepath=fav_filepath,
            filename="favorite.jpg",
            source_id="wallhaven",
            width=1920, height=1080, aspect_ratio=1.78,
            file_size=100000, file_mtime=int(time.time()),
            is_favorite=True,  # Mark as favorite
            first_indexed_at=int(time.time()),
            last_indexed_at=int(time.time()),
        ))

        self.db.upsert_tags_batch([
            {"tag_id": 1, "name": "fav_tag"},
        ])
        self.db.link_image_tags(fav_filepath, [1])

        stats = self.db.get_favorite_tag_statistics()
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["name"], "fav_tag")
        self.assertEqual(stats[0]["count"], 1)


if __name__ == "__main__":
    unittest.main()
