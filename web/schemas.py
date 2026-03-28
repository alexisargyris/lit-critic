"""
Pydantic request models for the lit-critic Web API.
"""

from pydantic import BaseModel
from typing import Optional


class AnalyzeRequest(BaseModel):
    scene_path: Optional[str] = None
    scene_paths: Optional[list[str]] = None
    project_path: str
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    model: Optional[str] = None
    discussion_model: Optional[str] = None
    mode: Optional[str] = None


class RerunAnalyzeRequest(BaseModel):
    project_path: str
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None


class ResumeRequest(BaseModel):
    project_path: str
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    scene_path_override: Optional[str] = None
    scene_path_overrides: Optional[dict[str, str]] = None


class ResumeSessionByIdRequest(BaseModel):
    project_path: str
    session_id: int
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    scene_path_override: Optional[str] = None
    scene_path_overrides: Optional[dict[str, str]] = None


class ViewSessionRequest(BaseModel):
    project_path: str
    session_id: int
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    scene_path_override: Optional[str] = None
    scene_path_overrides: Optional[dict[str, str]] = None
    reopen: bool = False


class RejectRequest(BaseModel):
    reason: str = ""


class DiscussRequest(BaseModel):
    message: str


class GotoRequest(BaseModel):
    index: int


class AmbiguityRequest(BaseModel):
    intentional: bool


class CheckSessionRequest(BaseModel):
    project_path: str


class ProjectPathRequest(BaseModel):
    project_path: str


class SessionIdRequest(BaseModel):
    project_path: str
    session_id: int


class LearningEntryDeleteRequest(BaseModel):
    project_path: str
    entry_id: int


class IndexRequest(BaseModel):
    scene_path: str
    project_path: str
    api_key: Optional[str] = None
    model: Optional[str] = None


class IndexAuditRequest(BaseModel):
    project_path: str
    deep: bool = False
    api_key: Optional[str] = None
    model: Optional[str] = None


class SceneAuditRequest(BaseModel):
    scene_path: str
    project_path: str
    deep: bool = False
    api_key: Optional[str] = None
    model: Optional[str] = None


class KnowledgeOverrideRequest(BaseModel):
    project_path: str
    category: str
    entity_key: str
    field_name: str
    value: str


class KnowledgeOverrideDeleteRequest(BaseModel):
    project_path: str
    category: str
    entity_key: str
    field_name: str


class KnowledgeEntityDeleteRequest(BaseModel):
    project_path: str
    category: str
    entity_key: str


class KnowledgeExportRequest(BaseModel):
    project_path: str


class KnowledgeLockRequest(BaseModel):
    project_path: str
    category: str
    entity_key: str


class KnowledgeReviewPassRequest(BaseModel):
    value: str


class SceneLockRequest(BaseModel):
    project_path: str
    scene_filename: str


class SceneRenameRequest(BaseModel):
    project_path: str
    old_filename: str
    new_filename: str


class RepoPathUpdateRequest(BaseModel):
    repo_path: str


class ModelSlotsUpdateRequest(BaseModel):
    frontier: str
    deep: str
    quick: str


class SceneDiscoveryConfigUpdateRequest(BaseModel):
    scene_folder: str
    scene_extensions: list[str]
