# tests/smart_selection/e2e/conftest.py
"""Shared fixtures for end-to-end tests."""

import os
import shutil
import tempfile
import pytest

# Path to fixture images
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'wallpapers')


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: end-to-end tests requiring real dependencies"
    )
    config.addinivalue_line(
        "markers", "slow: tests that take more than 5 seconds"
    )
    config.addinivalue_line(
        "markers", "wallust: tests requiring wallust CLI"
    )


@pytest.fixture
def fixtures_dir():
    """Return path to fixture wallpapers."""
    if not os.path.isdir(FIXTURES_DIR):
        pytest.skip(f"Fixtures directory not found: {FIXTURES_DIR}")
    # Check if there are any images
    images = [f for f in os.listdir(FIXTURES_DIR)
              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    if not images:
        pytest.skip(f"No fixture images found. Run: tests/smart_selection/fixtures/setup_fixtures.sh")
    return FIXTURES_DIR


@pytest.fixture
def fixture_images(fixtures_dir):
    """Return list of all fixture image paths."""
    images = []
    for f in os.listdir(fixtures_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            images.append(os.path.join(fixtures_dir, f))
    if not images:
        pytest.skip("No fixture images found")
    return images


@pytest.fixture
def temp_db():
    """Create a temporary database file, cleanup after test."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_e2e.db')
    yield db_path
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def temp_dir():
    """Create a temporary directory, cleanup after test."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def wallust_available():
    """Check if wallust is available, skip if not."""
    if not shutil.which('wallust'):
        pytest.skip("wallust not installed")
    return True


@pytest.fixture
def indexed_database(temp_db, fixtures_dir):
    """Create a database with all fixture images indexed."""
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.indexer import ImageIndexer

    with ImageDatabase(temp_db) as db:
        indexer = ImageIndexer(db, favorites_folder=fixtures_dir)
        indexer.index_directory(fixtures_dir)

    return temp_db


@pytest.fixture
def database_with_palettes(indexed_database, wallust_available):
    """Create a database with images indexed AND palettes extracted."""
    from variety.smart_selection.database import ImageDatabase
    from variety.smart_selection.palette import PaletteExtractor, create_palette_record

    extractor = PaletteExtractor()

    with ImageDatabase(indexed_database) as db:
        for img in db.get_all_images():
            palette_data = extractor.extract_palette(img.filepath)
            if palette_data:
                record = create_palette_record(img.filepath, palette_data)
                db.upsert_palette(record)

    return indexed_database


@pytest.fixture
def selector_with_palettes(database_with_palettes):
    """Create a SmartSelector with indexed images and palettes."""
    from variety.smart_selection.selector import SmartSelector
    from variety.smart_selection.config import SelectionConfig

    config = SelectionConfig(enabled=True)
    selector = SmartSelector(database_with_palettes, config)
    yield selector
    selector.close()
