# tests/smart_selection/benchmarks/bench_database.py
"""Benchmarks for database operations."""

import pytest


class TestDatabaseBenchmarks:
    """Benchmark database operations."""

    @pytest.mark.benchmark
    def test_bench_get_all_images(self, benchmark, bench_db):
        """Benchmark retrieving all images from database."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            def get_all():
                return db.get_all_images()

            result = benchmark(get_all)
            assert len(result) > 0

    @pytest.mark.benchmark
    def test_bench_get_image_by_path(self, benchmark, bench_db):
        """Benchmark retrieving a single image by path."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            images = db.get_all_images()
            test_path = images[0].filepath

            def get_one():
                return db.get_image(test_path)

            result = benchmark(get_one)
            assert result is not None
            assert result.filepath == test_path

    @pytest.mark.benchmark
    def test_bench_get_favorite_images(self, benchmark, bench_db):
        """Benchmark retrieving favorite images."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            def get_favs():
                return db.get_favorite_images()

            result = benchmark(get_favs)
            # All fixture images are favorites
            assert len(result) > 0

    @pytest.mark.benchmark
    def test_bench_upsert_image(self, benchmark, bench_db):
        """Benchmark upserting an image record."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            images = db.get_all_images()
            test_image = images[0]

            def upsert():
                db.upsert_image(test_image)

            benchmark(upsert)

    @pytest.mark.benchmark
    def test_bench_record_image_shown(self, benchmark, bench_db):
        """Benchmark recording an image as shown."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            images = db.get_all_images()
            test_path = images[0].filepath

            def record():
                db.record_image_shown(test_path)

            benchmark(record)

    @pytest.mark.benchmark
    def test_bench_get_all_sources(self, benchmark, bench_db):
        """Benchmark retrieving all sources."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            def get_sources():
                return db.get_all_sources()

            result = benchmark(get_sources)
            assert isinstance(result, list)

    @pytest.mark.benchmark
    def test_bench_get_source(self, benchmark, bench_db):
        """Benchmark retrieving a single source."""
        from variety.smart_selection.database import ImageDatabase

        with ImageDatabase(bench_db) as db:
            sources = db.get_all_sources()
            if not sources:
                pytest.skip("No sources in database")

            test_source_id = sources[0].source_id

            def get_source():
                return db.get_source(test_source_id)

            result = benchmark(get_source)
            assert result is not None

    @pytest.mark.benchmark
    def test_bench_upsert_palette(self, benchmark, bench_db):
        """Benchmark upserting a palette record."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import PaletteRecord

        with ImageDatabase(bench_db) as db:
            images = db.get_all_images()
            test_path = images[0].filepath

            palette = PaletteRecord(
                filepath=test_path,
                color0='#ff0000',
                color1='#00ff00',
                color2='#0000ff',
                avg_hue=120.0,
                avg_saturation=0.8,
                avg_lightness=0.5,
                color_temperature=5500.0,
            )

            def upsert():
                db.upsert_palette(palette)

            benchmark(upsert)

    @pytest.mark.benchmark
    def test_bench_get_palette(self, benchmark, bench_db):
        """Benchmark retrieving a palette."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.models import PaletteRecord

        with ImageDatabase(bench_db) as db:
            images = db.get_all_images()
            test_path = images[0].filepath

            # Insert a palette first
            palette = PaletteRecord(
                filepath=test_path,
                color0='#ff0000',
                avg_hue=120.0,
            )
            db.upsert_palette(palette)

            def get_palette():
                return db.get_palette(test_path)

            result = benchmark(get_palette)
            assert result is not None
