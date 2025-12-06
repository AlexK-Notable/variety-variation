# tests/smart_selection/benchmarks/bench_indexing.py
"""Benchmarks for image indexing operations."""

import os
import shutil
import tempfile
import pytest


class TestIndexingBenchmarks:
    """Benchmark image indexing operations."""

    @pytest.mark.benchmark
    def test_bench_index_directory(self, benchmark, fixtures_dir, temp_bench_db):
        """Benchmark indexing a directory of images."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        def index_dir():
            with ImageDatabase(temp_bench_db) as db:
                # Clear previous data to ensure fresh indexing each iteration
                db.delete_all_images()
                indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
                return indexer.index_directory(fixtures_dir)

        result = benchmark(index_dir)
        assert result > 0

    @pytest.mark.benchmark
    def test_bench_scan_directory(self, benchmark, fixtures_dir, temp_bench_db):
        """Benchmark scanning a directory without indexing."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        with ImageDatabase(temp_bench_db) as db:
            indexer = ImageIndexer(db)

            def scan_dir():
                return indexer.scan_directory(fixtures_dir)

            result = benchmark(scan_dir)
            assert len(result) > 0

    @pytest.mark.benchmark
    def test_bench_index_single_file(self, benchmark, fixture_images, temp_bench_db):
        """Benchmark indexing a single image file."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer
        import os

        test_image = fixture_images[0]
        test_dir = os.path.dirname(test_image)

        # Create a directory with just one image for isolated benchmark
        import tempfile
        import shutil
        single_dir = tempfile.mkdtemp()
        shutil.copy(test_image, single_dir)

        try:
            def index_single():
                with ImageDatabase(temp_bench_db) as db:
                    # Clear previous data to ensure fresh indexing each iteration
                    db.delete_all_images()
                    indexer = ImageIndexer(db)
                    return indexer.index_directory(single_dir)

            result = benchmark(index_single)
            assert result == 1
        finally:
            shutil.rmtree(single_dir)

    @pytest.mark.benchmark
    def test_bench_reindex_existing(self, benchmark, fixtures_dir, temp_bench_db):
        """Benchmark re-indexing already-indexed images (should be faster due to no changes)."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.indexer import ImageIndexer

        # First index
        with ImageDatabase(temp_bench_db) as db:
            indexer = ImageIndexer(db)
            indexer.index_directory(fixtures_dir)

        def reindex():
            with ImageDatabase(temp_bench_db) as db:
                indexer = ImageIndexer(db)
                return indexer.index_directory(fixtures_dir)

        result = benchmark(reindex)
        assert result >= 0  # May be 0 if no changes
