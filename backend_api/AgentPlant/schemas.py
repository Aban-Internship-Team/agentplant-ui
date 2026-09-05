"""Plant-model chat and artifact API schemas.

Pydantic request/response models for the AgentPlant FastAPI layer.
Artifact shapes align with backend_core.artifact_store / plant_compiler and
the Streamlit unified flow.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend_core.AgentPlant import (
    DEFAULT_MAX_DRAFTS,
    DEFAULT_MIN_USER_TURNS_BEFORE_COMPLETION,
)


class HitlOption(BaseModel):
    """One clarifier option. The UI sends ``label`` back as ``user_message``."""

    label: str


class HitlPrompt(BaseModel):
    """Optional HITL overlay on a ``continue`` turn (wire field: ``hitl``)."""

    question: str
    options: list[HitlOption] = Field(default_factory=list)
    allow_free_text: bool = True
    timeout_sec: int | None = None


class SearchHit(BaseModel):
    """One RAG citation or web-search row."""

    source: str
    snippet: str
    url: str | None = None


class ToolResult(BaseModel):
    """In-thread tool card payload (RAG or web search)."""

    kind: Literal["rag", "search"]
    items: list[SearchHit] = Field(default_factory=list)


class FileRef(BaseModel):
    """Handle returned by file upload (A5). ``attachment_ids`` lists ``file_id``."""

    file_id: str
    name: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    status: Literal["continue", "draft", "complete"] | None = None
    hitl: HitlPrompt | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    attachment_ids: list[str] = Field(default_factory=list)


class PlantModelResult(BaseModel):
    system_name: str
    python_code: str
    metadata: dict[str, Any] | None = None


class PlantModelSessionStateOut(BaseModel):
    draft_count: int = 0
    latest_draft: PlantModelResult | None = None


class PlantModelChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    user_message: str
    model: str = "gpt-4o-mini"
    session_state: PlantModelSessionStateOut | None = None
    conversation_id: int | None = None
    max_drafts: int = Field(default=DEFAULT_MAX_DRAFTS, ge=1, le=10)
    min_user_turns_before_completion: int = Field(
        default=DEFAULT_MIN_USER_TURNS_BEFORE_COMPLETION,
        ge=1,
        le=5,
    )
    attachment_ids: list[str] = Field(default_factory=list)
    web_search: bool = False


class TokenUsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    estimated_cost: float


class PlantModelChatResponse(BaseModel):
    reply: str
    status: Literal["continue", "draft", "complete"]
    final_result: PlantModelResult | None = None
    session_state: PlantModelSessionStateOut
    usage: Optional[TokenUsageOut] = None
    conversation_id: int | None = None
    hitl: HitlPrompt | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)


class PlantModelConversationSummary(BaseModel):
    id: int
    title: str
    status: Literal["active", "complete"]
    llm_model: str
    system_name: str | None = None
    user_id: int | None = None
    owner_email: str | None = None
    created_at: datetime
    updated_at: datetime


class PlantModelConversationDetail(BaseModel):
    id: int
    title: str
    status: Literal["active", "complete"]
    llm_model: str
    messages: list[ChatMessage]
    session_state: PlantModelSessionStateOut | None = None
    final_result: PlantModelResult | None = None
    user_id: int | None = None
    owner_email: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Artifact / pre-launch (unified hand-off)
# ---------------------------------------------------------------------------


class PreLaunchConfig(BaseModel):
    """Module-agnostic simulation knobs shared by AgentMPC and AgentAdaptive."""

    total_simulation_time: float = Field(gt=0, description="Total simulation horizon (s)")
    solver_sample_time: float = Field(gt=0, description="Integrator / solver step (s)")
    initial_state: list[float] = Field(default_factory=list)
    default_target: list[float] = Field(default_factory=list)


class PlantPayload(BaseModel):
    """Plant output as produced by AgentPlant (status=complete)."""

    system_name: str
    python_code: str
    metadata: dict[str, Any] | None = None


class ArtifactCreateRequest(BaseModel):
    """Compile + persist an artifact from plant + pre-launch.

    Provide either ``conversation_id`` (completed plant conversation) or an
    explicit ``plant`` payload. ``pre_launch`` is always required.
    """

    pre_launch: PreLaunchConfig
    plant: PlantPayload | None = None
    conversation_id: int | None = None


class ArtifactSummary(BaseModel):
    artifact_id: str
    system_name: str = ""
    created_at: str = ""
    version: str = ""


class ArtifactCreateResponse(BaseModel):
    artifact_id: str
    system_name: str
    created_at: str
    version: str = "1.0"
    warnings: list[str] = Field(default_factory=list)


class ArtifactDetail(BaseModel):
    """Full artifact JSON as stored by ArtifactStore (passthrough-friendly)."""

    artifact_id: str
    system_name: str
    created_at: str = ""
    version: str = "1.0"
    plant: dict[str, Any] = Field(default_factory=dict)
    pre_launch: dict[str, Any] = Field(default_factory=dict)
    module_specific: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ArtifactPluginResponse(BaseModel):
    artifact_id: str
    plugin_path: str
    source: str


class ValidationRequest(BaseModel):
    """Validate plant and/or pre-launch without persisting."""

    plant: PlantPayload | None = None
    pre_launch: PreLaunchConfig | None = None
    conversation_id: int | None = None


class ValidationResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SimulateRequest(BaseModel):
    """Open-loop simulate request. Source plant via ``conversation_id`` or ``plant``."""

    conversation_id: int | None = None
    plant: PlantPayload | None = None
    input_type: Literal["step", "pulse", "sine"] = "step"
    amplitude: float = 1.0
    total_simulation_time: float = Field(gt=0)
    solver_sample_time: float = Field(gt=0)
    initial_state: list[float] = Field(default_factory=list)
    pulse_width: float | None = None
    frequency: float | None = None


class SimulateResponse(BaseModel):
    """Open-loop timeseries: samples of time, states, and inputs."""

    t: list[float]
    x: list[list[float]]
    u: list[list[float]]
    warnings: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    """Named form of the existing artifact-validation HTTP ``detail`` object."""

    message: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
