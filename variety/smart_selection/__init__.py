# Smart Selection Engine for Variety
# Provides intelligent wallpaper selection with recency weighting,
# source rotation, and color palette awareness.

from variety.smart_selection.models import (
    ImageRecord,
    SourceRecord,
    PaletteRecord,
    SelectionConstraints,
    IndexingResult,
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
    color_affinity_factor,
    calculate_time_affinity,
    calculate_weight,
)
from variety.smart_selection.palette import (
    hex_to_hsl,
    calculate_temperature,
    parse_wallust_json,
    PaletteExtractor,
    create_palette_record,
    palette_similarity,
    palette_similarity_hsl,
)
from variety.smart_selection.color_science import (
    rgb_to_oklab,
    hex_to_oklab,
    oklab_distance,
    color_distance_oklab,
    palette_similarity_oklab,
    get_oklab_lightness,
    get_oklab_chroma,
    get_oklab_hue,
)
from variety.smart_selection.time_adapter import (
    PaletteTarget,
    PALETTE_PRESETS,
    TimeAdapter,
    parse_time_string,
    get_system_theme_preference,
    get_sun_times,
    ASTRAL_AVAILABLE,
)

__all__ = [
    # Models
    'ImageRecord',
    'SourceRecord',
    'PaletteRecord',
    'SelectionConstraints',
    'IndexingResult',
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
    'color_affinity_factor',
    'calculate_time_affinity',
    'calculate_weight',
    # Palette functions
    'hex_to_hsl',
    'calculate_temperature',
    'parse_wallust_json',
    'PaletteExtractor',
    'create_palette_record',
    'palette_similarity',
    'palette_similarity_hsl',
    # Color science (OKLAB)
    'rgb_to_oklab',
    'hex_to_oklab',
    'oklab_distance',
    'color_distance_oklab',
    'palette_similarity_oklab',
    'get_oklab_lightness',
    'get_oklab_chroma',
    'get_oklab_hue',
    # Time adaptation
    'PaletteTarget',
    'PALETTE_PRESETS',
    'TimeAdapter',
    'parse_time_string',
    'get_system_theme_preference',
    'get_sun_times',
    'ASTRAL_AVAILABLE',
]
