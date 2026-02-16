"""Legacy compatibility wrapper for database persistence APIs.

This module preserves the historical ``server.db`` import surface while
delegating implementation to the Platform-owned persistence layer.
"""

from lit_platform.persistence import (
    ALL_CATEGORIES,
    CATEGORY_AMBIGUITY_ACCIDENTAL,
    CATEGORY_AMBIGUITY_INTENTIONAL,
    CATEGORY_BLIND_SPOT,
    CATEGORY_PREFERENCE,
    CATEGORY_RESOLUTION,
    FindingStore,
    LearningStore,
    SCHEMA_VERSION,
    SessionStore,
    get_connection,
    get_db_path,
    init_db,
)

__all__ = [
    "SCHEMA_VERSION",
    "get_db_path",
    "get_connection",
    "init_db",
    "SessionStore",
    "FindingStore",
    "LearningStore",
    "CATEGORY_PREFERENCE",
    "CATEGORY_BLIND_SPOT",
    "CATEGORY_RESOLUTION",
    "CATEGORY_AMBIGUITY_INTENTIONAL",
    "CATEGORY_AMBIGUITY_ACCIDENTAL",
    "ALL_CATEGORIES",
]
