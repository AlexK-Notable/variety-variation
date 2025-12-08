# Smart Selection Engine for Variety
# Provides intelligent wallpaper selection with recency weighting,
# source rotation, and color palette awareness.

from variety.smart_selection.models import (
    ImageRecord,
    SourceRecord,
    PaletteRecord,
    SelectionConstraints,
)
from variety.smart_selection.config import SelectionConfig
from variety.smart_selection.database import ImageDatabase
from variety.smart_selection.indexer import ImageIndexer
from variety.smart_selection.selector import SmartSelector
from variety.smart_selection.statistics import CollectionStatistics
from variety.smart_selection.weights import (
    recency_factor,
    source_factor,
    favorite_boost,
    new_image_boost,
    calculate_weight,
)
from variety.smart_selection.palette import (
    hex_to_hsl,
    calculate_temperature,
    parse_wallust_json,
    PaletteExtractor,
    create_palette_record,
    palette_similarity,
)

__all__ = [
    # Models
    'ImageRecord',
    'SourceRecord',
    'PaletteRecord',
    'SelectionConstraints',
    # Config
    'SelectionConfig',
    # Database
    'ImageDatabase',
    # Indexer
    'ImageIndexer',
    # Selector
    'SmartSelector',
    # Statistics
    'CollectionStatistics',
    # Weight functions
    'recency_factor',
    'source_factor',
    'favorite_boost',
    'new_image_boost',
    'calculate_weight',
    # Palette functions
    'hex_to_hsl',
    'calculate_temperature',
    'parse_wallust_json',
    'PaletteExtractor',
    'create_palette_record',
    'palette_similarity',
]
