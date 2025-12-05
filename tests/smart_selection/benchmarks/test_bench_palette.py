# tests/smart_selection/benchmarks/bench_palette.py
"""Benchmarks for palette extraction operations."""

import shutil
import pytest


# Skip all palette benchmarks if wallust not available
pytestmark = pytest.mark.skipif(
    not shutil.which('wallust'),
    reason="wallust not installed"
)


class TestPaletteBenchmarks:
    """Benchmark palette extraction operations."""

    @pytest.mark.benchmark
    def test_bench_extract_palette(self, benchmark, fixture_images):
        """Benchmark extracting palette from a single image."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        test_image = fixture_images[0]

        def extract():
            return extractor.extract_palette(test_image)

        result = benchmark(extract)
        assert result is not None
        # Check for expected keys in palette data
        assert 'avg_hue' in result or 'background' in result

    @pytest.mark.benchmark
    def test_bench_palette_similarity(self, benchmark, bench_db_with_palettes):
        """Benchmark palette similarity calculation."""
        from variety.smart_selection.database import ImageDatabase
        from variety.smart_selection.palette import palette_similarity

        with ImageDatabase(bench_db_with_palettes) as db:
            images = db.get_all_images()
            palettes = []
            for img in images:
                p = db.get_palette(img.filepath)
                if p and p.avg_hue is not None:
                    palettes.append({
                        'avg_hue': p.avg_hue,
                        'avg_saturation': p.avg_saturation,
                        'avg_lightness': p.avg_lightness,
                        'color_temperature': p.color_temperature,
                    })

            if len(palettes) < 2:
                pytest.skip("Not enough palettes extracted")

            target = palettes[0]

            def calc_similarity():
                scores = []
                for p in palettes[1:]:
                    scores.append(palette_similarity(target, p))
                return scores

            result = benchmark(calc_similarity)
            assert len(result) == len(palettes) - 1

    @pytest.mark.benchmark
    def test_bench_create_palette_record(self, benchmark, fixture_images):
        """Benchmark creating a palette record from raw data."""
        from variety.smart_selection.palette import PaletteExtractor, create_palette_record

        extractor = PaletteExtractor()
        test_image = fixture_images[0]
        raw_palette = extractor.extract_palette(test_image)

        if not raw_palette:
            pytest.skip("Could not extract palette")

        def create_record():
            return create_palette_record(test_image, raw_palette)

        result = benchmark(create_record)
        assert result is not None
        assert result.filepath == test_image

    @pytest.mark.benchmark
    def test_bench_extract_batch_palettes(self, benchmark, fixture_images):
        """Benchmark extracting palettes for multiple images."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        test_images = fixture_images[:5]  # First 5 images

        def extract_batch():
            results = []
            for img in test_images:
                p = extractor.extract_palette(img)
                if p:
                    results.append(p)
            return results

        result = benchmark(extract_batch)
        assert len(result) > 0
