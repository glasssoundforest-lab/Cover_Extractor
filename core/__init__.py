"""TRPGシナリオ管理アプリ コアパッケージ (core)

データ層（SQLite）および Rust コア連携（DLL FFI・シナリオ解析）を
GUIフレームワーク非依存で提供するモジュール群です。
"""

from .database import (
    Database,
    BOOKMARK_ITEMS,
    BOOKMARK_COLORS,
    GLOBAL_TAG_PRIORITY,
    global_tag_sort_key,
    SORT_OPTIONS,
    canonical_tag,
    canonical_system,
    auto_reading,
    to_hiragana,
    reading_key,
    first_number,
    is_excluded_tag,
    sort_items,
)

from .extractor import (
    CoverExtractorError,
    RustDllExtractor,
    parse_info,
    is_scenario_file,
    collect_scenario_targets,
    collect_scenario_files,
    parse_name_clues,
    search_fallback_cover,
    search_fallback_texts,
    extract_scenario_data,
)

__all__ = [
    "Database",
    "BOOKMARK_ITEMS",
    "BOOKMARK_COLORS",
    "SORT_OPTIONS",
    "canonical_tag",
    "canonical_system",
    "auto_reading",
    "to_hiragana",
    "reading_key",
    "first_number",
    "is_excluded_tag",
    "sort_items",
    "CoverExtractorError",
    "RustDllExtractor",
    "parse_info",
    "is_scenario_file",
    "collect_scenario_targets",
    "collect_scenario_files",
    "parse_name_clues",
    "search_fallback_cover",
    "search_fallback_texts",
    "extract_scenario_data",
]
