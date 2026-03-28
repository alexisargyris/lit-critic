"""Platform-owned persistence layer (database and stores)."""

from .database import SCHEMA_VERSION, get_connection, get_db_path, init_db
from .finding_store import FindingStore
from .index_projection_store import IndexProjectionStore
from .knowledge_override_store import KnowledgeOverrideStore
from .learning_store import (
    ALL_CATEGORIES,
    CATEGORY_AMBIGUITY_ACCIDENTAL,
    CATEGORY_AMBIGUITY_INTENTIONAL,
    CATEGORY_BLIND_SPOT,
    CATEGORY_PREFERENCE,
    CATEGORY_RESOLUTION,
    LearningStore,
)
from .scene_projection_store import SceneProjectionStore
from .session_store import SessionStore
from .extraction_store import ExtractionStore
