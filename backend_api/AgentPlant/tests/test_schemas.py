"""Unit tests for AgentPlant API schemas (no HTTP, no LLM)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend_api.AgentPlant.schemas import (
    ErrorBody,
    FileRef,
    HitlPrompt,
    PlantModelChatRequest,
    PlantModelChatResponse,
    PlantModelResult,
    PlantModelSessionStateOut,
    PlantPayload,
    PreLaunchConfig,
    SearchHit,
    SimulateRequest,
    SimulateResponse,
    TokenUsageOut,
    ToolResult,
    ChatMessage,
)


def test_chat_message_legacy_payload():
    msg = ChatMessage.model_validate({"role": "user", "content": "hi"})
    assert msg.role == "user"
    assert msg.content == "hi"
    assert msg.status is None
    assert msg.hitl is None
    assert msg.tool_results == []
    assert msg.attachment_ids == []


def test_chat_request_legacy_minimal():
    req = PlantModelChatRequest.model_validate(
        {"user_message": "hello", "messages": []}
    )
    assert req.user_message == "hello"
    assert req.messages == []
    assert req.attachment_ids == []
    assert req.web_search is False


def test_chat_request_with_extras():
    req = PlantModelChatRequest.model_validate(
        {
            "user_message": "hello",
            "messages": [],
            "attachment_ids": ["file-1"],
            "web_search": True,
        }
    )
    assert req.attachment_ids == ["file-1"]
    assert req.web_search is True


def test_chat_response_constructor_compatibility():
    response = PlantModelChatResponse(
        reply="ok",
        status="continue",
        final_result=None,
        session_state=PlantModelSessionStateOut(draft_count=0),
        usage=TokenUsageOut(input_tokens=1, output_tokens=1, estimated_cost=0.0),
        conversation_id=None,
    )
    assert response.hitl is None
    assert response.tool_results == []


def test_hitl_prompt_defaults():
    prompt = HitlPrompt(question="What system are you modelling?")
    assert prompt.question == "What system are you modelling?"
    assert prompt.options == []
    assert prompt.allow_free_text is True
    assert prompt.timeout_sec is None


def test_tool_result_rag_and_search():
    rag = ToolResult(
        kind="rag",
        items=[SearchHit(source="notes.pdf", snippet="state-space form")],
    )
    assert rag.kind == "rag"
    assert rag.items[0].url is None

    search = ToolResult(
        kind="search",
        items=[
            SearchHit(
                source="Wikipedia · Boost converter",
                snippet="steps up DC voltage",
                url="https://example.com/boost",
            )
        ],
    )
    assert search.kind == "search"
    assert search.items[0].url == "https://example.com/boost"


def test_file_ref():
    ref = FileRef(file_id="abc", name="paper.pdf")
    assert ref.file_id == "abc"
    assert ref.name == "paper.pdf"


def test_simulate_request_validation():
    for input_type in ("step", "pulse", "sine"):
        req = SimulateRequest(
            input_type=input_type,
            total_simulation_time=10.0,
            solver_sample_time=0.01,
        )
        assert req.input_type == input_type

    with pytest.raises(ValidationError):
        SimulateRequest(total_simulation_time=0, solver_sample_time=0.01)
    with pytest.raises(ValidationError):
        SimulateRequest(total_simulation_time=-1, solver_sample_time=0.01)
    with pytest.raises(ValidationError):
        SimulateRequest(total_simulation_time=10.0, solver_sample_time=0)
    with pytest.raises(ValidationError):
        SimulateRequest(total_simulation_time=10.0, solver_sample_time=-0.001)

    ok = SimulateRequest(
        conversation_id=1,
        plant=PlantPayload(system_name="x", python_code="def dynamics(t, x, u):\n    return x"),
        total_simulation_time=5.0,
        solver_sample_time=0.001,
    )
    assert ok.conversation_id == 1
    assert ok.plant is not None
    assert ok.amplitude == 1.0
    assert ok.initial_state == []
    assert ok.pulse_width is None
    assert ok.frequency is None


def test_simulate_response_timeseries():
    resp = SimulateResponse(
        t=[0.0, 0.1],
        x=[[0.0], [0.1]],
        u=[[1.0], [1.0]],
    )
    assert resp.t == [0.0, 0.1]
    assert resp.x == [[0.0], [0.1]]
    assert resp.u == [[1.0], [1.0]]
    assert resp.warnings == []


def test_error_body():
    body = ErrorBody(message="Plant or pre-launch validation failed")
    assert body.message == "Plant or pre-launch validation failed"
    assert body.errors == []
    assert body.warnings == []

    filled = ErrorBody(
        message="failed",
        errors=["system_name is required"],
        warnings=["metadata missing"],
    )
    assert filled.errors == ["system_name is required"]
    assert filled.warnings == ["metadata missing"]


def test_pre_launch_config_unchanged():
    cfg = PreLaunchConfig(
        total_simulation_time=10.0,
        solver_sample_time=0.001,
        initial_state=[0.0],
        default_target=[0.0],
    )
    assert set(PreLaunchConfig.model_fields) == {
        "total_simulation_time",
        "solver_sample_time",
        "initial_state",
        "default_target",
    }
    dumped = cfg.model_dump()
    assert set(dumped) == {
        "total_simulation_time",
        "solver_sample_time",
        "initial_state",
        "default_target",
    }

    extra = PreLaunchConfig.model_validate(
        {
            "total_simulation_time": 10.0,
            "solver_sample_time": 0.001,
            "initial_state": [],
            "default_target": [],
            "trajectory_mode": "reg",
        }
    )
    assert "trajectory_mode" not in extra.model_dump()
    assert not hasattr(extra, "trajectory_mode") or "trajectory_mode" not in extra.model_fields


def test_plant_model_result_unchanged():
    result = PlantModelResult(
        system_name="dc_motor",
        python_code="def dynamics(t, x, u):\n    return x",
    )
    assert result.system_name == "dc_motor"
    assert result.python_code.startswith("def dynamics")
    assert result.metadata is None

    with_meta = PlantModelResult(
        system_name="dc_motor",
        python_code="def dynamics(t, x, u):\n    return x",
        metadata={"states": ["theta"]},
    )
    assert with_meta.metadata == {"states": ["theta"]}
    assert set(PlantModelResult.model_fields) == {
        "system_name",
        "python_code",
        "metadata",
    }
