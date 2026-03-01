"""Tests for the Wallhaven tag scraping pipeline.

Tests cover:
- Schema v7 migration
- Tag resolution (name/alias -> tag_id)
- Scrape job CRUD operations
- Tag scrape status tracking
- Pipeline configuration validation
"""

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from variety.smart_selection.database import ImageDatabase


class TestSchemaV7Migration(unittest.TestCase):
    """Test schema v7 migration."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

    def tearDown(self):
        os.unlink(self.db_path)

    def test_migration_creates_new_columns(self):
        """Test that v7 migration adds new columns to tags table."""
        db = ImageDatabase(self.db_path)

        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(tags)")
        columns = {row[1] for row in cursor.fetchall()}

        expected = {
            'tag_id', 'name', 'alias', 'category', 'purity',
            'popularity_rank', 'wallpaper_count', 'alias_source',
            'alias_updated_at', 'scraped_at', 'detail_fetched_at'
        }
        self.assertEqual(columns, expected)
        db.close()

    def test_migration_creates_scrape_jobs_table(self):
        """Test that v7 migration creates scrape_jobs table."""
        db = ImageDatabase(self.db_path)

        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(scrape_jobs)")
        columns = {row[1] for row in cursor.fetchall()}

        expected = {
            'job_id', 'job_type', 'status', 'started_at', 'completed_at',
            'progress_cursor', 'items_total', 'items_completed',
            'credits_budget', 'credits_used', 'error_message', 'metadata'
        }
        self.assertEqual(columns, expected)
        db.close()

    def test_migration_creates_tag_scrape_status_table(self):
        """Test that v7 migration creates tag_scrape_status table."""
        db = ImageDatabase(self.db_path)

        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(tag_scrape_status)")
        columns = {row[1] for row in cursor.fetchall()}

        expected = {
            'tag_id', 'list_scraped', 'firecrawl_status', 'firecrawl_job_id',
            'firecrawl_attempted_at', 'api_status', 'api_attempted_at', 'last_error'
        }
        self.assertEqual(columns, expected)
        db.close()

    def test_migration_is_idempotent(self):
        """Test that migration can run multiple times without error."""
        db1 = ImageDatabase(self.db_path)
        db1.close()

        # Open again - should not fail
        db2 = ImageDatabase(self.db_path)
        self.assertEqual(db2.SCHEMA_VERSION, 8)
        db2.close()


class TestTagResolution(unittest.TestCase):
    """Test tag name/alias resolution."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_file.close()
        self.db = ImageDatabase(self.temp_file.name)

        # Add test tags
        self.db.upsert_tag(1, 'landscape', alias='scenery', popularity_rank=1)
        self.db.upsert_tag(2, 'anime', alias='animation', popularity_rank=2)
        self.db.upsert_tag(3, 'dark', alias=None, popularity_rank=3)
        self.db.upsert_tag(4, 'nature photography', alias='outdoor shots', popularity_rank=4)

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_resolve_by_exact_name(self):
        """Test resolving by exact tag name."""
        result = self.db.resolve_tag('landscape')
        self.assertIsNotNone(result)
        self.assertEqual(result['tag_id'], 1)

    def test_resolve_by_exact_alias(self):
        """Test resolving by exact alias."""
        result = self.db.resolve_tag('scenery')
        self.assertIsNotNone(result)
        self.assertEqual(result['tag_id'], 1)

    def test_resolve_case_insensitive(self):
        """Test case-insensitive resolution."""
        result = self.db.resolve_tag('LANDSCAPE')
        self.assertIsNotNone(result)
        self.assertEqual(result['tag_id'], 1)

        result = self.db.resolve_tag('Scenery')
        self.assertIsNotNone(result)
        self.assertEqual(result['tag_id'], 1)

    def test_resolve_partial_name(self):
        """Test resolving by partial name match."""
        result = self.db.resolve_tag('land')
        self.assertIsNotNone(result)
        self.assertEqual(result['tag_id'], 1)

    def test_resolve_partial_alias(self):
        """Test resolving by partial alias match."""
        result = self.db.resolve_tag('outdoor')
        self.assertIsNotNone(result)
        self.assertEqual(result['tag_id'], 4)

    def test_resolve_not_found(self):
        """Test resolution returns None for unknown tags."""
        result = self.db.resolve_tag('nonexistent')
        self.assertIsNone(result)

    def test_resolve_multiple(self):
        """Test resolving multiple tags at once."""
        results = self.db.resolve_tags(['landscape', 'scenery', 'unknown'])
        self.assertEqual(len(results), 3)
        self.assertEqual(results['landscape']['tag_id'], 1)
        self.assertEqual(results['scenery']['tag_id'], 1)
        self.assertIsNone(results['unknown'])


class TestScrapeJobCRUD(unittest.TestCase):
    """Test scrape job CRUD operations."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_file.close()
        self.db = ImageDatabase(self.temp_file.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_create_job(self):
        """Test creating a scrape job."""
        job_id = self.db.create_scrape_job('smoke_test', credits_budget=5)
        self.assertIsNotNone(job_id)
        self.assertGreater(job_id, 0)

    def test_get_job(self):
        """Test retrieving a scrape job."""
        job_id = self.db.create_scrape_job('tag_list', credits_budget=200)
        job = self.db.get_scrape_job(job_id)

        self.assertIsNotNone(job)
        self.assertEqual(job['job_type'], 'tag_list')
        self.assertEqual(job['credits_budget'], 200)
        self.assertEqual(job['status'], 'pending')

    def test_update_job_status(self):
        """Test updating job status."""
        job_id = self.db.create_scrape_job('tag_list')

        self.db.update_scrape_job(job_id, status='in_progress')
        job = self.db.get_scrape_job(job_id)
        self.assertEqual(job['status'], 'in_progress')

        self.db.update_scrape_job(job_id, status='completed')
        job = self.db.get_scrape_job(job_id)
        self.assertEqual(job['status'], 'completed')
        self.assertIsNotNone(job['completed_at'])

    def test_update_job_progress(self):
        """Test updating job progress."""
        job_id = self.db.create_scrape_job('tag_list')

        self.db.update_scrape_job(
            job_id,
            items_total=200,
            items_completed=50,
            credits_used=50
        )

        job = self.db.get_scrape_job(job_id)
        self.assertEqual(job['items_total'], 200)
        self.assertEqual(job['items_completed'], 50)
        self.assertEqual(job['credits_used'], 50)

    def test_get_latest_job_by_type(self):
        """Test getting latest job of a type."""
        self.db.create_scrape_job('tag_list')
        job_id_2 = self.db.create_scrape_job('tag_list')

        latest = self.db.get_latest_job_by_type('tag_list')
        self.assertEqual(latest['job_id'], job_id_2)

    def test_get_resumable_job(self):
        """Test finding resumable jobs."""
        job_id = self.db.create_scrape_job('tag_list')
        self.db.update_scrape_job(job_id, status='in_progress')

        resumable = self.db.get_resumable_job('tag_list')
        self.assertIsNotNone(resumable)
        self.assertEqual(resumable['job_id'], job_id)

        # Completed jobs are not resumable
        self.db.update_scrape_job(job_id, status='completed')
        resumable = self.db.get_resumable_job('tag_list')
        self.assertIsNone(resumable)


class TestTagScrapeStatus(unittest.TestCase):
    """Test tag scrape status tracking."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_file.close()
        self.db = ImageDatabase(self.temp_file.name)

        # Add test tags
        self.db.upsert_tag(1, 'landscape')
        self.db.upsert_tag(2, 'anime')
        self.db.upsert_tag(3, 'dark')

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_update_list_scraped(self):
        """Test marking tags as list-scraped."""
        self.db.update_tag_scrape_status(1, list_scraped=True)

        cursor = self.db.conn.cursor()
        cursor.execute('SELECT list_scraped FROM tag_scrape_status WHERE tag_id = 1')
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)

    def test_update_firecrawl_status(self):
        """Test updating Firecrawl status."""
        job_id = self.db.create_scrape_job('tag_detail_firecrawl')
        self.db.update_tag_scrape_status(
            1,
            firecrawl_status='success',
            firecrawl_job_id=job_id
        )

        cursor = self.db.conn.cursor()
        cursor.execute('SELECT firecrawl_status, firecrawl_job_id FROM tag_scrape_status WHERE tag_id = 1')
        row = cursor.fetchone()
        self.assertEqual(row[0], 'success')
        self.assertEqual(row[1], job_id)

    def test_batch_update(self):
        """Test batch updating scrape status."""
        self.db.update_tag_scrape_status_batch([1, 2, 3], list_scraped=True)

        cursor = self.db.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM tag_scrape_status WHERE list_scraped = 1')
        count = cursor.fetchone()[0]
        self.assertEqual(count, 3)

    def test_get_tags_needing_detail(self):
        """Test getting tags that need detail fetching."""
        # All tags need detail (no alias)
        tags = self.db.get_tags_needing_detail()
        self.assertEqual(len(tags), 3)

        # Add alias to one
        self.db.upsert_tag(1, 'landscape', alias='scenery')
        tags = self.db.get_tags_needing_detail()
        self.assertEqual(len(tags), 2)

    def test_get_tags_for_api_fallback(self):
        """Test getting tags that failed Firecrawl."""
        # Mark as failed
        self.db.update_tag_scrape_status(1, firecrawl_status='failed')
        self.db.update_tag_scrape_status(2, firecrawl_status='success')

        tags = self.db.get_tags_for_api_fallback()
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['tag_id'], 1)

    def test_get_scrape_statistics(self):
        """Test getting scrape statistics."""
        self.db.update_tag_scrape_status(1, list_scraped=True, firecrawl_status='success')
        self.db.update_tag_scrape_status(2, list_scraped=True, firecrawl_status='failed')

        stats = self.db.get_scrape_statistics()
        self.assertEqual(stats['total_tags'], 3)
        self.assertEqual(stats['list_scraped'], 2)
        self.assertEqual(stats['firecrawl']['success'], 1)
        self.assertEqual(stats['firecrawl']['failed'], 1)


class TestUpsertTagWithNewColumns(unittest.TestCase):
    """Test upsert_tag with new v7 columns."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_file.close()
        self.db = ImageDatabase(self.temp_file.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_upsert_with_popularity(self):
        """Test upserting with popularity data."""
        self.db.upsert_tag(
            tag_id=1,
            name='landscape',
            popularity_rank=5,
            wallpaper_count=50000
        )

        tag = self.db.resolve_tag('landscape')
        self.assertEqual(tag['popularity_rank'], 5)
        self.assertEqual(tag['wallpaper_count'], 50000)

    def test_upsert_with_alias_source(self):
        """Test upserting with alias source."""
        self.db.upsert_tag(
            tag_id=1,
            name='landscape',
            alias='scenery',
            alias_source='firecrawl'
        )

        tag = self.db.resolve_tag('landscape')
        self.assertEqual(tag['alias'], 'scenery')
        self.assertEqual(tag['alias_source'], 'firecrawl')
        self.assertIsNotNone(tag['alias_updated_at'])

    def test_upsert_batch_with_new_columns(self):
        """Test batch upsert with new columns."""
        tags = [
            {'tag_id': 1, 'name': 'landscape', 'popularity_rank': 1, 'wallpaper_count': 50000},
            {'tag_id': 2, 'name': 'anime', 'popularity_rank': 2, 'wallpaper_count': 40000, 'alias': 'animation', 'alias_source': 'firecrawl'},
        ]
        self.db.upsert_tags_batch(tags)

        tag1 = self.db.resolve_tag('landscape')
        self.assertEqual(tag1['popularity_rank'], 1)

        tag2 = self.db.resolve_tag('anime')
        self.assertEqual(tag2['alias'], 'animation')
        self.assertEqual(tag2['alias_source'], 'firecrawl')


class TestPipelineConfig(unittest.TestCase):
    """Test pipeline configuration."""

    def test_phase2_budget_calculation(self):
        """Test phase 2 budget auto-calculation."""
        # Import here to avoid import errors if requests not installed
        try:
            from tools.scrape_wallhaven_tags import PipelineConfig
        except ImportError:
            self.skipTest("scrape_wallhaven_tags not importable")

        config = PipelineConfig(
            total_credits=3000,
            phase1_credits=200,
            credit_reserve=50
        )
        self.assertEqual(config.phase2_budget, 2750)

    def test_phase2_budget_explicit(self):
        """Test explicit phase 2 budget."""
        try:
            from tools.scrape_wallhaven_tags import PipelineConfig
        except ImportError:
            self.skipTest("scrape_wallhaven_tags not importable")

        config = PipelineConfig(
            total_credits=3000,
            phase1_credits=200,
            phase2_credits=1000
        )
        self.assertEqual(config.phase2_budget, 1000)

    def test_validation_requires_api_key(self):
        """Test that validation requires Firecrawl API key."""
        try:
            from tools.scrape_wallhaven_tags import PipelineConfig
        except ImportError:
            self.skipTest("scrape_wallhaven_tags not importable")

        config = PipelineConfig(firecrawl_api_key=None)
        errors = config.validate()
        self.assertIn("Firecrawl API key is required (set FIRECRAWL_API_KEY)", errors)


if __name__ == '__main__':
    unittest.main()
