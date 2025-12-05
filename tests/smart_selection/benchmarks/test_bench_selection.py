# tests/smart_selection/benchmarks/bench_selection.py
"""Benchmarks for image selection operations."""

import pytest


class TestSelectionBenchmarks:
    """Benchmark image selection operations."""

    @pytest.mark.benchmark
    def test_bench_select_single(self, benchmark, bench_db):
        """Benchmark selecting a single image."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(bench_db, SelectionConfig()) as selector:
            def select_one():
                return selector.select_images(count=1)

            result = benchmark(select_one)
            assert len(result) == 1

    @pytest.mark.benchmark
    def test_bench_select_batch(self, benchmark, bench_db):
        """Benchmark selecting multiple images at once."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(bench_db, SelectionConfig()) as selector:
            def select_batch():
                return selector.select_images(count=5)

            result = benchmark(select_batch)
            assert len(result) <= 5

    @pytest.mark.benchmark
    def test_bench_select_with_constraints(self, benchmark, bench_db):
        """Benchmark selection with constraints applied."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.models import SelectionConstraints

        constraints = SelectionConstraints(
            min_width=500,
            min_aspect_ratio=1.0,
        )

        with SmartSelector(bench_db, SelectionConfig()) as selector:
            def select_constrained():
                return selector.select_images(count=3, constraints=constraints)

            result = benchmark(select_constrained)
            # May return fewer if constraints filter out some images
            assert isinstance(result, list)

    @pytest.mark.benchmark
    def test_bench_weight_calculation(self, benchmark, bench_db):
        """Benchmark weight calculation for all images."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.config import SelectionConfig
        from variety.smart_selection.weights import calculate_weight

        config = SelectionConfig()

        with ImageDatabase(bench_db) as db:
            images = db.get_all_images()

            def calc_weights():
                weights = []
                for img in images:
                    source_last = None
                    if img.source_id:
                        source = db.get_source(img.source_id)
                        if source:
                            source_last = source.last_shown_at
                    w = calculate_weight(img, source_last, config)
                    weights.append(w)
                return weights

            result = benchmark(calc_weights)
            assert len(result) == len(images)

    @pytest.mark.benchmark
    def test_bench_record_shown(self, benchmark, bench_db):
        """Benchmark recording an image as shown."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        with SmartSelector(bench_db, SelectionConfig()) as selector:
            images = selector.db.get_all_images()
            test_image = images[0].filepath

            def record_shown():
                selector.record_shown(test_image)

            benchmark(record_shown)

    @pytest.mark.benchmark
    def test_bench_disabled_selection(self, benchmark, bench_db):
        """Benchmark selection with smart selection disabled (uniform random)."""
        from variety.smart_selection.selector import SmartSelector
        from variety.smart_selection.config import SelectionConfig

        config = SelectionConfig(enabled=False)

        with SmartSelector(bench_db, config) as selector:
            def select_uniform():
                return selector.select_images(count=3)

            result = benchmark(select_uniform)
            assert len(result) == 3
