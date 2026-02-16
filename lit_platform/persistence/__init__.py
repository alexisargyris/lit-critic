"""Platform-owned persistence layer (database and stores)."""

from .database import SCHEMA_VERSION, get_connection, get_db_path, init_db
from .finding_store import FindingStore
from .learning_store import (
    ALL_CATEGORIES,
    CATEGORY_AMBIGUITY_ACCIDENTAL,
    CATEGORY_AMBIGUITY_INTENTIONAL,
    CATEGORY_BLIND_SPOT,
    CATEGORY_PREFERENCE,
    CATEGORY_RESOLUTION,
    LearningStore,
)
from .session_store import SessionStore
