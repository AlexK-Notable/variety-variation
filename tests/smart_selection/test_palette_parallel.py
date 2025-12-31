#!/usr/bin/python3
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Tests for parallel palette extraction in smart_selection.palette."""

import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image


class TestParallelPaletteExtraction(unittest.TestCase):
    """Tests for extract_all_palettes_parallel method."""

    def setUp(self):
        """Create temporary directory with test images."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_images = []

        # Create multiple gradient test images with color variety
        for i in range(10):
            image_path = os.path.join(self.temp_dir, f'test_{i}.jpg')
            img = Image.new('RGB', (100, 100))
            pixels = img.load()
            for y in range(100):
                for x in range(100):
                    # Create gradient with variety, shift by i for uniqueness
                    r = int(((x + i * 10) / 110) * 255) % 256
                    g = int(((y + i * 5) / 105) * 255) % 256
                    b = int(((x + y + i * 3) / 210) * 255) % 256
                    pixels[x, y] = (r, g, b)
            img.save(image_path, quality=95)
            self.test_images.append(image_path)

    def tearDown(self):
        """Clean up temporary directory and shutdown any executor."""
        from variety.smart_selection.palette import PaletteExtractor
        # Create extractor and shutdown to clean up any threads
        extractor = PaletteExtractor()
        extractor.shutdown()
        shutil.rmtree(self.temp_dir)

    def test_import_parallel_method(self):
        """extract_all_palettes_parallel can be called on PaletteExtractor."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        self.assertTrue(hasattr(extractor, 'extract_all_palettes_parallel'))
        self.assertTrue(callable(extractor.extract_all_palettes_parallel))

    def test_returns_dict_mapping_filepath_to_result(self):
        """extract_all_palettes_parallel returns dict with filepath keys."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        # Use mock to avoid actually calling wallust
        with patch.object(extractor, 'extract_palette') as mock_extract:
            mock_extract.return_value = {'color0': '#000000', 'avg_hue': 0}

            result = extractor.extract_all_palettes_parallel(
                self.test_images[:3],
                max_workers=2
            )

        self.assertIsInstance(result, dict)
        for path in self.test_images[:3]:
            self.assertIn(path, result)

    def test_results_equivalent_to_sequential(self):
        """Parallel results are equivalent to sequential extraction."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        # Create predictable mock results based on filepath
        def mock_extract(path):
            # Generate deterministic result based on filename
            idx = int(os.path.basename(path).split('_')[1].split('.')[0])
            return {
                'color0': f'#{idx:02x}0000',
                'avg_hue': idx * 10.0,
                'avg_saturation': 0.5,
                'avg_lightness': 0.5,
            }

        with patch.object(extractor, 'extract_palette', side_effect=mock_extract):
            # Get sequential results
            sequential_results = {}
            for path in self.test_images[:5]:
                sequential_results[path] = extractor.extract_palette(path)

        # Reset mock and do parallel
        with patch.object(extractor, 'extract_palette', side_effect=mock_extract):
            parallel_results = extractor.extract_all_palettes_parallel(
                self.test_images[:5],
                max_workers=3
            )

        # Compare results
        self.assertEqual(set(sequential_results.keys()), set(parallel_results.keys()))
        for path in sequential_results:
            self.assertEqual(sequential_results[path], parallel_results[path])

    def test_handles_failed_extractions(self):
        """Failed extractions don't crash the batch; they return None."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        # Some succeed, some fail
        def mock_extract_with_failures(path):
            idx = int(os.path.basename(path).split('_')[1].split('.')[0])
            if idx % 2 == 0:
                return {'color0': '#000000', 'avg_hue': 0}
            else:
                return None  # Simulate failure

        with patch.object(extractor, 'extract_palette', side_effect=mock_extract_with_failures):
            result = extractor.extract_all_palettes_parallel(
                self.test_images[:6],
                max_workers=3
            )

        # All paths should be in result
        self.assertEqual(len(result), 6)

        # Check that failures are None
        for path in self.test_images[:6]:
            idx = int(os.path.basename(path).split('_')[1].split('.')[0])
            if idx % 2 == 0:
                self.assertIsNotNone(result[path])
            else:
                self.assertIsNone(result[path])

    def test_handles_exceptions_in_extraction(self):
        """Exceptions during extraction don't crash the batch."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        # Some succeed, some raise exceptions
        def mock_extract_with_exceptions(path):
            idx = int(os.path.basename(path).split('_')[1].split('.')[0])
            if idx == 3:
                raise RuntimeError("Simulated error")
            return {'color0': '#000000', 'avg_hue': idx}

        with patch.object(extractor, 'extract_palette', side_effect=mock_extract_with_exceptions):
            result = extractor.extract_all_palettes_parallel(
                self.test_images[:6],
                max_workers=2
            )

        # All paths should be in result
        self.assertEqual(len(result), 6)

        # Exception case should be None
        for path in self.test_images[:6]:
            idx = int(os.path.basename(path).split('_')[1].split('.')[0])
            if idx == 3:
                self.assertIsNone(result[path])
            else:
                self.assertIsNotNone(result[path])

    def test_progress_callback(self):
        """Progress callback is called with correct arguments."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        progress_calls = []

        def progress_callback(completed, total):
            progress_calls.append((completed, total))

        with patch.object(extractor, 'extract_palette') as mock_extract:
            mock_extract.return_value = {'color0': '#000000'}

            extractor.extract_all_palettes_parallel(
                self.test_images[:5],
                max_workers=2,
                progress_callback=progress_callback
            )

        # Progress should have been called for each completed item
        self.assertGreater(len(progress_calls), 0)

        # All calls should have total=5
        for completed, total in progress_calls:
            self.assertEqual(total, 5)

        # Last call should have completed=5
        self.assertEqual(progress_calls[-1][0], 5)

        # Should be in increasing order
        completed_values = [c for c, t in progress_calls]
        self.assertEqual(completed_values, sorted(completed_values))

    def test_respects_max_workers(self):
        """Worker limit is enforced."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        concurrent_count = []
        current_count = [0]
        lock = threading.Lock()

        def mock_slow_extract(path):
            with lock:
                current_count[0] += 1
                concurrent_count.append(current_count[0])
            time.sleep(0.05)  # Small delay to allow overlap
            with lock:
                current_count[0] -= 1
            return {'color0': '#000000'}

        max_workers = 2

        with patch.object(extractor, 'extract_palette', side_effect=mock_slow_extract):
            extractor.extract_all_palettes_parallel(
                self.test_images[:8],
                max_workers=max_workers
            )

        # Maximum concurrent should not exceed max_workers
        self.assertLessEqual(max(concurrent_count), max_workers)

    def test_graceful_shutdown(self):
        """Shutdown stops processing without crash."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        shutdown_called = threading.Event()
        extraction_started = threading.Event()

        def mock_slow_extract(path):
            extraction_started.set()
            # Wait a bit but check for shutdown
            for _ in range(10):
                if extractor._shutdown_event.is_set():
                    return None
                time.sleep(0.02)
            return {'color0': '#000000'}

        with patch.object(extractor, 'extract_palette', side_effect=mock_slow_extract):
            # Start parallel extraction in a thread
            results = [None]

            def run_extraction():
                results[0] = extractor.extract_all_palettes_parallel(
                    self.test_images,
                    max_workers=2
                )

            extraction_thread = threading.Thread(target=run_extraction)
            extraction_thread.start()

            # Wait for extraction to start
            extraction_started.wait(timeout=2.0)

            # Call shutdown
            extractor.shutdown()

            # Wait for thread to finish
            extraction_thread.join(timeout=2.0)

            # Thread should have finished
            self.assertFalse(extraction_thread.is_alive())

    def test_shutdown_is_idempotent(self):
        """Calling shutdown multiple times doesn't cause errors."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        # Shutdown without having done anything
        extractor.shutdown()
        extractor.shutdown()  # Should not raise

    def test_empty_image_list(self):
        """Empty image list returns empty dict."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        result = extractor.extract_all_palettes_parallel([], max_workers=2)

        self.assertEqual(result, {})

    def test_single_image(self):
        """Single image works correctly."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        with patch.object(extractor, 'extract_palette') as mock_extract:
            mock_extract.return_value = {'color0': '#123456'}

            result = extractor.extract_all_palettes_parallel(
                [self.test_images[0]],
                max_workers=4
            )

        self.assertEqual(len(result), 1)
        self.assertIn(self.test_images[0], result)
        self.assertEqual(result[self.test_images[0]], {'color0': '#123456'})

    def test_parallel_faster_than_sequential(self):
        """Parallel extraction shows speedup with mocked slow extraction.

        Note: Real wallust extraction may not benefit from parallelism due to
        shared cache file access (timestamp-based cache lookup). This test
        uses mocked slow extraction to verify the parallel infrastructure works.
        """
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()

        # Use mock with artificial delay to simulate slow extraction
        def mock_slow_extract(path):
            time.sleep(0.1)  # 100ms per image
            idx = int(os.path.basename(path).split('_')[1].split('.')[0])
            return {'color0': f'#{idx:02x}0000', 'avg_hue': idx * 10.0}

        with patch.object(extractor, 'extract_palette', side_effect=mock_slow_extract):
            # Sequential timing
            sequential_start = time.time()
            sequential_results = {}
            for path in self.test_images[:8]:
                sequential_results[path] = extractor.extract_palette(path)
            sequential_time = time.time() - sequential_start

        with patch.object(extractor, 'extract_palette', side_effect=mock_slow_extract):
            # Parallel timing
            parallel_start = time.time()
            parallel_results = extractor.extract_all_palettes_parallel(
                self.test_images[:8],
                max_workers=4
            )
            parallel_time = time.time() - parallel_start

        # Parallel should be faster (at least 2x for 8 images with 4 workers)
        speedup = sequential_time / parallel_time if parallel_time > 0 else float('inf')

        # Verify results are equivalent
        self.assertEqual(set(sequential_results.keys()), set(parallel_results.keys()))
        for path in sequential_results:
            self.assertEqual(sequential_results[path], parallel_results[path])

        # With 8 images at 100ms each, sequential = ~800ms
        # With 4 workers, parallel should be ~200-300ms (2.5-4x speedup)
        self.assertGreaterEqual(speedup, 2.0,
            f"Expected at least 2x speedup, got {speedup:.2f}x")


class TestPaletteExtractorShutdown(unittest.TestCase):
    """Tests for PaletteExtractor shutdown functionality."""

    def test_shutdown_method_exists(self):
        """PaletteExtractor has shutdown method."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        self.assertTrue(hasattr(extractor, 'shutdown'))
        self.assertTrue(callable(extractor.shutdown))

    def test_has_shutdown_event(self):
        """PaletteExtractor has _shutdown_event attribute."""
        from variety.smart_selection.palette import PaletteExtractor

        extractor = PaletteExtractor()
        self.assertTrue(hasattr(extractor, '_shutdown_event'))
        self.assertIsInstance(extractor._shutdown_event, threading.Event)


if __name__ == '__main__':
    unittest.main()
