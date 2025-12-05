# tests/smart_selection/benchmarks/conftest.py
"""Shared fixtures for benchmark tests.

Uses module-scoped fixtures to reduce setup overhead for repeated runs.
"""

import os
import shutil
import tempfile
import pytest

# Path to fixture images (shared with e2e tests)
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'wallpapers')


def pytest_configure(config):
    """Register benchmark marker."""
    config.addinivalue_line(
        "markers", "benchmark: performance benchmark tests"
    )


@pytest.fixture(scope='module')
def fixtures_dir():
    """Return path to fixture wallpapers (module-scoped for benchmark efficiency)."""
    if not os.path.isdir(FIXTURES_DIR):
        pytest.skip(f"Fixtures directory not found: {FIXTURES_DIR}")
    images = [f for f in os.listdir(FIXTURES_DIR)
              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    if not images:
        pytest.skip("No fixture images found")
    return FIXTURES_DIR


@pytest.fixture(scope='module')
def fixture_images(fixtures_dir):
    """Return list of fixture image paths (module-scoped)."""
    images = []
    for f in os.listdir(fixtures_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            images.append(os.path.join(fixtures_dir, f))
    return images


@pytest.fixture(scope='module')
def bench_db(fixtures_dir):
    """Create a database indexed with fixtures (module-scoped for benchmark efficiency)."""
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.indexer import ImageIndexer

    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'bench.db')

    with ImageDatabase(db_path) as db:
        indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
        indexer.index_directory(fixtures_dir)

    yield db_path

    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture(scope='module')
def bench_db_with_palettes(bench_db, fixtures_dir):
    """Database with images and palettes (module-scoped)."""
    if not shutil.which('wallust'):
        pytest.skip("wallust not installed")

    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.palette import PaletteExtractor, create_palette_record

    extractor = PaletteExtractor()

    with ImageDatabase(bench_db) as db:
        for img in db.get_all_images():
            palette_data = extractor.extract_palette(img.filepath)
            if palette_data:
                record = create_palette_record(img.filepath, palette_data)
                db.upsert_palette(record)

    return bench_db


@pytest.fixture
def temp_bench_db():
    """Create a fresh temporary database for each benchmark run."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'bench_temp.db')
    yield db_path
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
