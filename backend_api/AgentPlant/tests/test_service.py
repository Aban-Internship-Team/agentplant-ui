"""Unit tests for the AgentPlant FastAPI service adapter (no live LLM)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend_api.AgentPlant.schemas import (
    ChatMessage,
    PlantModelChatRequest,
    PlantModelSessionStateOut,
)
from backend_api.AgentPlant.service import run_plant_model_chat
from backend_core.AgentPlant import (
    PlantModelSessionState,
    apply_session_state,
    export_session_state,
)


def test_session_state_roundtrip():
    agent = MagicMock()
    agent._draft_count = 0
    agent._latest_draft = None
    agent.reset_conversation_state = MagicMock()

    apply_session_state(
        agent,
        PlantModelSessionState(
            draft_count=2,
            latest_draft={
                "system_name": "motor",
                "python_code": "def dynamics(t, x, u):\n    return x",
            },
        ),
    )
    assert agent._draft_count == 2
    assert agent._latest_draft["system_name"] == "motor"

    snap = export_session_state(agent)
    assert snap.draft_count == 2
    assert snap.latest_draft["python_code"].startswith("def dynamics")


def test_run_plant_model_chat_continue():
    mock_agent = MagicMock()
    mock_agent._draft_count = 0
    mock_agent._latest_draft = None
    mock_agent.step.return_value = ("What kind of plant is it?", None)
    mock_agent.total_usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    mock_agent.total_cost = 0.001

    with patch("backend_api.AgentPlant.service.PlantModelAgent", return_value=mock_agent):
        with patch(
            "backend_api.AgentPlant.service.export_session_state",
            return_value=PlantModelSessionState(draft_count=0, latest_draft=None),
        ):
            response = run_plant_model_chat(
                PlantModelChatRequest(user_message="hello", messages=[])
            )

    assert response.status == "continue"
    assert response.final_result is None
    assert response.reply == "What kind of plant is it?"
    assert response.usage is not None
    assert response.usage.input_tokens == 10


def test_run_plant_model_chat_draft_and_complete():
    draft_payload = {
        "system_name": "dc_motor",
        "python_code": "def dynamics(t, x, u):\n    return x",
    }

    mock_agent = MagicMock()
    mock_agent._draft_count = 0
    mock_agent._latest_draft = None
    mock_agent.total_usage = SimpleNamespace(input_tokens=20, output_tokens=40)
    mock_agent.total_cost = 0.002

    def _step_draft(history, user_message):
        # Simulate agent bumping draft count during step (after apply_session_state).
        mock_agent._draft_count = 1
        mock_agent._latest_draft = draft_payload
        return ("Here is a draft.", None)

    mock_agent.step.side_effect = _step_draft

    with patch("backend_api.AgentPlant.service.PlantModelAgent", return_value=mock_agent):
        with patch(
            "backend_api.AgentPlant.service.export_session_state",
            return_value=PlantModelSessionState(
                draft_count=1,
                latest_draft=draft_payload,
            ),
        ):
            response = run_plant_model_chat(
                PlantModelChatRequest(
                    user_message="a DC motor",
                    messages=[ChatMessage(role="user", content="hi")],
                    session_state=PlantModelSessionStateOut(draft_count=0),
                )
            )

    assert response.status == "draft"
    assert response.session_state.draft_count == 1
    assert response.session_state.latest_draft is not None
    assert response.session_state.latest_draft.system_name == "dc_motor"

    # Complete path — status is inferred from a non-null final_payload
    def _step_complete(history, user_message):
        mock_agent._draft_count = 1
        mock_agent._latest_draft = draft_payload
        return (
            "Model ready — **dc_motor**.",
            dict(draft_payload),
        )

    mock_agent.step.side_effect = _step_complete
    with patch("backend_api.AgentPlant.service.PlantModelAgent", return_value=mock_agent):
        with patch(
            "backend_api.AgentPlant.service.export_session_state",
            return_value=PlantModelSessionState(
                draft_count=1,
                latest_draft=draft_payload,
            ),
        ):
            done = run_plant_model_chat(
                PlantModelChatRequest(user_message="finish", messages=[])
            )

    assert done.status == "complete"
    assert done.final_result is not None
    assert done.final_result.system_name == "dc_motor"


def test_conversation_store_persist_and_list():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore
    from backend_api.AgentPlant.schemas import PlantModelResult, PlantModelSessionStateOut

    store = InMemoryConversationStore()
    state = PlantModelSessionStateOut(draft_count=1)
    c1 = store.persist_turn(
        user_id=7,
        conversation_id=None,
        user_message="hello motor",
        assistant_reply="What voltage?",
        llm_model="gpt-4o-mini",
        session_state=state,
        final_result=None,
    )
    assert c1.id == 1
    assert c1.status == "active"
    assert len(c1.messages) == 2

    c2 = store.persist_turn(
        user_id=7,
        conversation_id=c1.id,
        user_message="finish",
        assistant_reply="done",
        llm_model="gpt-4o-mini",
        session_state=state,
        final_result=PlantModelResult(
            system_name="motor",
            python_code="def dynamics(t, x, u):\n    return x",
        ),
    )
    assert c2.id == 1
    assert c2.status == "complete"
    assert c2.final_result is not None
    assert c2.title == "motor"

    listed = store.list_for_user(7)
    assert len(listed) == 1
    assert store.get(1) is not None
    assert store.delete(1) is True
    assert store.get(1) is None


def _legacy_persist_kwargs(**overrides):
    from backend_api.AgentPlant.schemas import PlantModelSessionStateOut

    kwargs = {
        "user_id": None,
        "conversation_id": None,
        "user_message": "hello",
        "assistant_reply": "What system?",
        "llm_model": "gpt-4o-mini",
        "session_state": PlantModelSessionStateOut(draft_count=0),
        "final_result": None,
    }
    kwargs.update(overrides)
    return kwargs


def test_persist_turn_legacy_omits_structured_fields():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore

    store = InMemoryConversationStore()
    store.persist_turn(**_legacy_persist_kwargs())
    loaded = store.get(1)
    assert loaded is not None
    user, assistant = loaded.messages
    assert user.role == "user"
    assert user.content == "hello"
    assert user.attachment_ids == []
    assert assistant.role == "assistant"
    assert assistant.content == "What system?"
    assert assistant.status is None
    assert assistant.hitl is None
    assert assistant.tool_results == []


def test_persist_turn_status_round_trip():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore

    store = InMemoryConversationStore()
    store.persist_turn(**_legacy_persist_kwargs(assistant_status="draft"))
    loaded = store.get(1)
    assert loaded is not None
    assert loaded.messages[1].status == "draft"


def test_persist_turn_hitl_round_trip():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore
    from backend_api.AgentPlant.schemas import HitlOption, HitlPrompt

    hitl = HitlPrompt(
        question="What system are you modelling?",
        options=[HitlOption(label="DC motor"), HitlOption(label="CSTR")],
        allow_free_text=False,
        timeout_sec=30,
    )
    store = InMemoryConversationStore()
    store.persist_turn(**_legacy_persist_kwargs(assistant_hitl=hitl))
    loaded = store.get(1)
    assert loaded is not None
    saved = loaded.messages[1].hitl
    assert saved is not None
    assert saved.question == "What system are you modelling?"
    assert [opt.label for opt in saved.options] == ["DC motor", "CSTR"]
    assert saved.allow_free_text is False
    assert saved.timeout_sec == 30


def test_persist_turn_tool_results_round_trip():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore
    from backend_api.AgentPlant.schemas import SearchHit, ToolResult

    tools = [
        ToolResult(
            kind="rag",
            items=[SearchHit(source="notes.pdf", snippet="state-space form")],
        ),
        ToolResult(
            kind="search",
            items=[
                SearchHit(
                    source="Wikipedia · Boost",
                    snippet="steps up DC voltage",
                    url="https://example.com/boost",
                )
            ],
        ),
    ]
    store = InMemoryConversationStore()
    store.persist_turn(**_legacy_persist_kwargs(assistant_tool_results=tools))
    loaded = store.get(1)
    assert loaded is not None
    saved = loaded.messages[1].tool_results
    assert len(saved) == 2
    assert saved[0].kind == "rag"
    assert saved[0].items[0].source == "notes.pdf"
    assert saved[0].items[0].url is None
    assert saved[1].kind == "search"
    assert saved[1].items[0].url == "https://example.com/boost"


def test_persist_turn_attachment_ids_round_trip():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore

    store = InMemoryConversationStore()
    store.persist_turn(
        **_legacy_persist_kwargs(user_attachment_ids=["file-a", "file-b"])
    )
    loaded = store.get(1)
    assert loaded is not None
    assert loaded.messages[0].attachment_ids == ["file-a", "file-b"]
    assert loaded.messages[1].attachment_ids == []


def test_persist_turn_combined_structured_assistant_message():
    from backend_api.AgentPlant.conversation_store import InMemoryConversationStore
    from backend_api.AgentPlant.schemas import HitlPrompt, SearchHit, ToolResult

    hitl = HitlPrompt(question="Confirm states?")
    tools = [
        ToolResult(kind="rag", items=[SearchHit(source="ch4.pdf", snippet="ẋ = Ax + Bu")]),
    ]
    store = InMemoryConversationStore()
    store.persist_turn(
        **_legacy_persist_kwargs(
            assistant_status="continue",
            assistant_hitl=hitl,
            assistant_tool_results=tools,
        )
    )
    loaded = store.get(1)
    assert loaded is not None
    assistant = loaded.messages[1]
    assert assistant.status == "continue"
    assert assistant.hitl is not None
    assert assistant.hitl.question == "Confirm states?"
    assert assistant.tool_results[0].kind == "rag"
    assert assistant.tool_results[0].items[0].source == "ch4.pdf"
