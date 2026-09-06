"""HTTP-level tests for AgentPlant FastAPI routes (no live LLM)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend_api.AgentPlant.app import app
from backend_api.AgentPlant.conversation_store import InMemoryConversationStore
from backend_api.AgentPlant.files import MAX_UPLOAD_SIZE_BYTES, default_file_store
from backend_api.AgentPlant.schemas import (
    HitlOption,
    HitlPrompt,
    PlantModelChatResponse,
    PlantModelResult,
    PlantModelSessionStateOut,
    SearchHit,
    TokenUsageOut,
    ToolResult,
)


@pytest.fixture
def client():
    store = InMemoryConversationStore()
    with patch("backend_api.AgentPlant.router.default_store", store):
        yield TestClient(app)


def _enable_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABCD_MOCK_MODE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def _assert_error_body(response, *, status: int, contains: str | None = None) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    if contains is not None:
        blob = (body["message"] + " " + " ".join(body["errors"])).lower()
        assert contains.lower() in blob
    return body


def _hello_then_dc_motor(client: TestClient) -> tuple[dict, dict]:
    """Two real mock-mode turns. Does not patch chat or seed the store."""
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        hello = client.post(
            "/api/plant-model/chat",
            json={"user_message": "hello", "messages": []},
        )
        assert hello.status_code == 200, hello.text
        hello_body = hello.json()
        cid = hello_body["conversation_id"]
        draft = client.post(
            "/api/plant-model/chat",
            json={
                "user_message": "DC motor",
                "conversation_id": cid,
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": hello_body["reply"]},
                ],
                "session_state": hello_body["session_state"],
            },
        )
        create.assert_not_called()
    assert draft.status_code == 200, draft.text
    return hello_body, draft.json()


def _fake_chat_response(*, reply="ok", status="continue", conversation_id=None):
    return PlantModelChatResponse(
        reply=reply,
        status=status,
        final_result=None,
        session_state=PlantModelSessionStateOut(draft_count=0),
        usage=TokenUsageOut(input_tokens=1, output_tokens=1, estimated_cost=0.0),
        conversation_id=conversation_id,
    )


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "agent-plant"


def test_chat_continue(client: TestClient):
    fake = _fake_chat_response(reply="What kind of plant is it?", status="continue")
    with patch(
        "backend_api.AgentPlant.router.run_plant_model_chat",
        return_value=fake,
    ) as mock_run:
        r = client.post(
            "/api/plant-model/chat",
            json={"user_message": "hello", "messages": []},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "continue"
    assert data["reply"] == "What kind of plant is it?"
    assert data["conversation_id"] is not None
    mock_run.assert_called_once()


def test_chat_complete_and_list(client: TestClient):
    complete = PlantModelChatResponse(
        reply="Model ready — **dc_motor**.",
        status="complete",
        final_result=PlantModelResult(
            system_name="dc_motor",
            python_code="def dynamics(t, x, u):\n    return x",
        ),
        session_state=PlantModelSessionStateOut(
            draft_count=1,
            latest_draft=PlantModelResult(
                system_name="dc_motor",
                python_code="def dynamics(t, x, u):\n    return x",
            ),
        ),
        usage=TokenUsageOut(input_tokens=10, output_tokens=20, estimated_cost=0.001),
    )
    with patch(
        "backend_api.AgentPlant.router.run_plant_model_chat",
        return_value=complete,
    ):
        r = client.post(
            "/api/plant-model/chat",
            json={"user_message": "finish", "messages": []},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "complete"
    assert data["final_result"]["system_name"] == "dc_motor"
    cid = data["conversation_id"]

    listed = client.get("/api/plant-model/conversations")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == cid
    assert items[0]["status"] == "complete"
    assert items[0]["system_name"] == "dc_motor"

    detail = client.get(f"/api/plant-model/conversations/{cid}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["messages"]) == 2
    assert body["final_result"]["system_name"] == "dc_motor"

    deleted = client.delete(f"/api/plant-model/conversations/{cid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/plant-model/conversations/{cid}").status_code == 404


def test_chat_unknown_conversation(client: TestClient):
    r = client.post(
        "/api/plant-model/chat",
        json={
            "user_message": "hi",
            "messages": [],
            "conversation_id": 99999,
        },
    )
    assert r.status_code == 404
    body = r.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    assert body["message"] == "Conversation not found"
    assert body["errors"] == ["Conversation not found"]
    assert body["warnings"] == []


def test_chat_persists_structured_fields_for_reload(client: TestClient):
    fake = PlantModelChatResponse(
        reply="Need one detail.",
        status="draft",
        final_result=None,
        session_state=PlantModelSessionStateOut(draft_count=1),
        usage=TokenUsageOut(input_tokens=1, output_tokens=1, estimated_cost=0.0),
        hitl=HitlPrompt(
            question="Which input is the duty cycle?",
            options=[HitlOption(label="d"), HitlOption(label="Vin")],
            allow_free_text=True,
            timeout_sec=45,
        ),
        tool_results=[
            ToolResult(
                kind="rag",
                items=[SearchHit(source="ch4.pdf", snippet="averaged CCM model")],
            ),
            ToolResult(
                kind="search",
                items=[
                    SearchHit(
                        source="Wikipedia · Boost converter",
                        snippet="steps up DC voltage",
                        url="https://example.com/boost",
                    )
                ],
            ),
        ],
    )
    with patch(
        "backend_api.AgentPlant.router.run_plant_model_chat",
        return_value=fake,
    ):
        r = client.post(
            "/api/plant-model/chat",
            json={
                "user_message": "boost converter",
                "messages": [],
                "attachment_ids": ["file-1", "file-2"],
            },
        )
    assert r.status_code == 200
    cid = r.json()["conversation_id"]

    detail = client.get(f"/api/plant-model/conversations/{cid}")
    assert detail.status_code == 200
    body = detail.json()
    user, assistant = body["messages"]
    assert user["role"] == "user"
    assert user["attachment_ids"] == ["file-1", "file-2"]
    assert assistant["status"] == "draft"
    assert assistant["hitl"]["question"] == "Which input is the duty cycle?"
    assert [opt["label"] for opt in assistant["hitl"]["options"]] == ["d", "Vin"]
    assert assistant["hitl"]["allow_free_text"] is True
    assert assistant["hitl"]["timeout_sec"] == 45
    kinds = [item["kind"] for item in assistant["tool_results"]]
    assert kinds == ["rag", "search"]
    assert assistant["tool_results"][0]["items"][0]["url"] is None
    assert assistant["tool_results"][1]["items"][0]["url"] == "https://example.com/boost"


def test_mock_mode_chat_hello_persists_hitl(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LABCD_MOCK_MODE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        r = client.post(
            "/api/plant-model/chat",
            json={"user_message": "hello", "messages": []},
        )
        create.assert_not_called()
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "continue"
    assert data["hitl"] is not None
    assert data["hitl"]["question"]
    assert len(data["hitl"]["options"]) == 3
    cid = data["conversation_id"]
    assert cid is not None

    detail = client.get(f"/api/plant-model/conversations/{cid}")
    assert detail.status_code == 200
    body = detail.json()
    assistant = body["messages"][1]
    assert assistant["status"] == "continue"
    assert assistant["hitl"] is not None
    assert assistant["hitl"]["question"] == data["hitl"]["question"]


def test_upload_then_mock_chat_returns_rag(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LABCD_MOCK_MODE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        uploaded = client.post(
            "/api/plant-model/files",
            files={
                "file": ("paper.pdf", b"%PDF-1.4 fake-bytes", "application/pdf"),
            },
        )
        assert uploaded.status_code == 200
        body = uploaded.json()
        assert body["file_id"]
        assert body["name"] == "paper.pdf"

        chat = client.post(
            "/api/plant-model/chat",
            json={
                "user_message": "hello",
                "messages": [],
                "attachment_ids": [body["file_id"]],
            },
        )
        create.assert_not_called()
    assert chat.status_code == 200
    data = chat.json()
    kinds = [item["kind"] for item in data["tool_results"]]
    assert kinds == ["rag"]
    assert data["tool_results"][0]["items"][0]["source"] == "attached-document"
    stored = default_file_store._refs[body["file_id"]]
    assert stored.name == "paper.pdf"
    assert set(stored.model_dump()) == {"file_id", "name"}


def test_simulate_step_returns_timeseries(client: TestClient):
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        r = client.post(
            "/api/plant-model/simulate",
            json={
                "total_simulation_time": 1.0,
                "solver_sample_time": 0.25,
                "input_type": "step",
            },
        )
        create.assert_not_called()
    assert r.status_code == 200
    data = r.json()
    assert data["t"][0] == 0.0
    assert data["t"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert len(data["x"]) == len(data["t"])
    assert len(data["u"]) == len(data["t"])
    assert all(len(row) == 1 for row in data["u"])
    assert data["warnings"] == []


def test_simulate_unknown_conversation(client: TestClient):
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "conversation_id": 99999,
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.1,
        },
    )
    assert r.status_code == 404
    body = r.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    assert body["message"] == "Conversation not found"
    assert body["warnings"] == []


def test_simulate_invalid_horizon_unprocessable(client: TestClient):
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "total_simulation_time": 0,
            "solver_sample_time": 0.1,
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    assert body["message"] == "Request validation failed"
    assert any("body.total_simulation_time:" in item for item in body["errors"])
    assert body["warnings"] == []


_INTEGRATOR_PLANT = {
    "system_name": "simple_integrator",
    "python_code": (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        "    return np.array([float(u[0])])\n"
    ),
}


def _seed_sim_conversation(*, user_id=None, draft=None, final=None):
    import importlib

    router_mod = importlib.import_module("backend_api.AgentPlant.router")
    return router_mod.default_store.persist_turn(
        user_id=user_id,
        conversation_id=None,
        user_message="hi",
        assistant_reply="draft",
        llm_model="mock",
        session_state=PlantModelSessionStateOut(draft_count=1, latest_draft=draft),
        final_result=final,
    )


def test_simulate_explicit_plant_sandboxed(client: TestClient):
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        r = client.post(
            "/api/plant-model/simulate",
            json={
                "total_simulation_time": 1.0,
                "solver_sample_time": 0.25,
                "amplitude": 1.0,
                "initial_state": [0.0],
                "plant": _INTEGRATOR_PLANT,
            },
        )
        create.assert_not_called()
    assert r.status_code == 200
    data = r.json()
    assert data["x"][-1][0] > data["x"][0][0]


def test_simulate_mock_mode_does_not_force_mock(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LABCD_MOCK_MODE", "1")
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.25,
            "initial_state": [0.0],
            "plant": _INTEGRATOR_PLANT,
        },
    )
    assert r.status_code == 200
    assert r.json()["x"][-1][0] > 0


def test_simulate_conversation_draft(client: TestClient):
    draft = PlantModelResult.model_validate(_INTEGRATOR_PLANT)
    conversation = _seed_sim_conversation(draft=draft)
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "conversation_id": conversation.id,
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.25,
            "initial_state": [0.0],
        },
    )
    assert r.status_code == 200
    assert r.json()["x"][-1][0] > 0


def test_simulate_conversation_final_without_draft(client: TestClient):
    final = PlantModelResult.model_validate(_INTEGRATOR_PLANT)
    conversation = _seed_sim_conversation(final=final)
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "conversation_id": conversation.id,
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.25,
            "initial_state": [0.0],
        },
    )
    assert r.status_code == 200
    assert r.json()["x"][-1][0] > 0


def test_simulate_explicit_plant_overrides_draft(client: TestClient):
    draft = PlantModelResult.model_validate(_INTEGRATOR_PLANT)
    conversation = _seed_sim_conversation(draft=draft)
    hold = {
        "system_name": "hold",
        "python_code": (
            "import numpy as np\n"
            "def dynamics(t, x, u):\n"
            "    return np.array([0.0 * x[0]])\n"
        ),
    }
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "conversation_id": conversation.id,
            "plant": hold,
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.25,
            "initial_state": [3.0],
        },
    )
    assert r.status_code == 200
    assert r.json()["x"][-1] == [3.0]


def test_simulate_access_denied(client: TestClient):
    conversation = _seed_sim_conversation(user_id=1)
    r = client.post(
        "/api/plant-model/simulate",
        params={"user_id": 2},
        json={
            "conversation_id": conversation.id,
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.25,
        },
    )
    assert r.status_code == 403
    body = r.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    assert body["message"] == "Conversation access denied"
    assert body["errors"] == ["Conversation access denied"]
    assert body["warnings"] == []


def test_simulate_sandbox_failure_is_http_400(client: TestClient):
    r = client.post(
        "/api/plant-model/simulate",
        json={
            "total_simulation_time": 1.0,
            "solver_sample_time": 0.25,
            "plant": {
                "system_name": "evil",
                "python_code": "import os\ndef dynamics(t, x, u):\n    return x\n",
            },
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    blob = (body["message"] + " " + " ".join(body["errors"])).lower()
    assert "os" in blob or "import" in blob
    assert body["warnings"] == []


# ---------------------------------------------------------------------------
# Artifact routes
# ---------------------------------------------------------------------------


def _minimal_plant_json():
    return {
        "system_name": "simple_integrator",
        "python_code": "def dynamics(t, x, u):\n    return [u[0]]",
    }


def _minimal_pre_launch(n_states: int = 0):
    return {
        "total_simulation_time": 10.0,
        "solver_sample_time": 0.001,
        "initial_state": [0.0] * n_states,
        "default_target": [0.0] * n_states,
    }


@pytest.fixture
def artifact_client(tmp_path):
    """TestClient with isolated conversation store and artifact directory."""
    store = InMemoryConversationStore()
    with patch("backend_api.AgentPlant.router.default_store", store):
        with patch(
            "backend_api.AgentPlant.service.default_artifacts_dir",
            return_value=str(tmp_path),
        ):
            yield TestClient(app), store, tmp_path


def test_create_list_get_artifact(artifact_client):
    client, _store, tmp_path = artifact_client
    body = {
        "plant": _minimal_plant_json(),
        "pre_launch": _minimal_pre_launch(0),
    }
    r = client.post("/api/plant-model/artifacts", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["artifact_id"]
    assert data["system_name"] == "simple_integrator"
    artifact_id = data["artifact_id"]

    listed = client.get("/api/plant-model/artifacts")
    assert listed.status_code == 200
    ids = [item["artifact_id"] for item in listed.json()]
    assert artifact_id in ids

    detail = client.get(f"/api/plant-model/artifacts/{artifact_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["artifact_id"] == artifact_id
    assert payload["plant"]["python_code"].startswith("def dynamics")
    assert payload["pre_launch"]["total_simulation_time"] == 10.0

    plugin = client.get(f"/api/plant-model/artifacts/{artifact_id}/plugin")
    assert plugin.status_code == 200
    plugin_body = plugin.json()
    assert "BaseDynamics" in plugin_body["source"]
    assert plugin_body["plugin_path"].endswith(".py")

    adaptive = client.get(f"/api/plant-model/artifacts/{artifact_id}/adaptive-spec")
    assert adaptive.status_code == 200
    spec = adaptive.json()
    assert spec["system_name"] == "simple_integrator"
    assert "dynamics" in spec


def test_create_artifact_from_conversation(artifact_client):
    client, store, _tmp = artifact_client
    complete = PlantModelChatResponse(
        reply="done",
        status="complete",
        final_result=PlantModelResult(
            system_name="simple_integrator",
            python_code="def dynamics(t, x, u):\n    return [u[0]]",
        ),
        session_state=PlantModelSessionStateOut(draft_count=1),
        usage=TokenUsageOut(input_tokens=1, output_tokens=1, estimated_cost=0.0),
    )
    with patch(
        "backend_api.AgentPlant.router.run_plant_model_chat",
        return_value=complete,
    ):
        chat = client.post(
            "/api/plant-model/chat",
            json={"user_message": "finish", "messages": []},
        )
    assert chat.status_code == 200
    cid = chat.json()["conversation_id"]

    r = client.post(
        "/api/plant-model/artifacts",
        json={
            "conversation_id": cid,
            "pre_launch": _minimal_pre_launch(0),
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["system_name"] == "simple_integrator"


def test_create_artifact_validation_error(artifact_client):
    client, _store, _tmp = artifact_client
    r = client.post(
        "/api/plant-model/artifacts",
        json={
            "plant": {"system_name": "", "python_code": "no dynamics here"},
            "pre_launch": _minimal_pre_launch(0),
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    assert body["message"] == "Plant or pre-launch validation failed"
    assert body["errors"]
    assert isinstance(body["warnings"], list)


def test_validate_endpoint(artifact_client):
    client, _store, _tmp = artifact_client
    ok = client.post(
        "/api/plant-model/validate",
        json={
            "plant": _minimal_plant_json(),
            "pre_launch": _minimal_pre_launch(0),
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True

    bad = client.post(
        "/api/plant-model/validate",
        json={
            "plant": {"system_name": "x", "python_code": "pass"},
        },
    )
    assert bad.status_code == 200
    assert bad.json()["ok"] is False
    assert bad.json()["errors"]


def test_artifact_not_found(artifact_client):
    client, _store, _tmp = artifact_client
    assert client.get("/api/plant-model/artifacts/does-not-exist").status_code == 404
    assert (
        client.get("/api/plant-model/artifacts/does-not-exist/plugin").status_code == 404
    )
    assert (
        client.get(
            "/api/plant-model/artifacts/does-not-exist/adaptive-spec"
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# A9 — real mock-mode HTTP integration
# ---------------------------------------------------------------------------


def test_mock_chat_draft_persists_on_get(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    hello_body, draft_body = _hello_then_dc_motor(client)
    cid = draft_body["conversation_id"]
    assert cid == hello_body["conversation_id"]
    assert draft_body["status"] == "draft"
    assert draft_body["session_state"]["latest_draft"]["system_name"] == "dc_motor"
    assert draft_body["hitl"] is None
    assert draft_body["final_result"] is None

    detail = client.get(f"/api/plant-model/conversations/{cid}")
    assert detail.status_code == 200
    stored = detail.json()
    assert stored["status"] == "active"
    assert stored["session_state"]["latest_draft"]["system_name"] == "dc_motor"
    assert stored["session_state"]["draft_count"] == 1
    assert stored["final_result"] is None
    assert len(stored["messages"]) == 4
    draft_assistant = stored["messages"][3]
    assert draft_assistant["role"] == "assistant"
    assert draft_assistant["status"] == "draft"
    assert draft_assistant["content"] == draft_body["reply"]
    assert draft_assistant["hitl"] is None


def test_mock_chat_draft_simulate_uses_sandbox(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    _hello_body, draft_body = _hello_then_dc_motor(client)
    cid = draft_body["conversation_id"]
    payload = {
        "conversation_id": cid,
        "total_simulation_time": 1.0,
        "solver_sample_time": 0.25,
        "amplitude": 1.0,
    }
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        live = client.post("/api/plant-model/simulate", json=payload)
        no_plant = client.post(
            "/api/plant-model/simulate",
            json={
                "total_simulation_time": 1.0,
                "solver_sample_time": 0.25,
                "amplitude": 1.0,
            },
        )
        create.assert_not_called()
    assert live.status_code == 200, live.text
    assert no_plant.status_code == 200
    data = live.json()
    mock = no_plant.json()
    assert len(data["t"]) == len(data["x"]) == len(data["u"])
    assert len(data["x"][0]) == 2
    assert len(mock["x"][0]) == 1
    assert data["x"] != mock["x"]
    assert data["t"] == mock["t"]


def test_mock_chat_draft_then_finish_completes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    hello_body, draft_body = _hello_then_dc_motor(client)
    cid = draft_body["conversation_id"]
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        finished = client.post(
            "/api/plant-model/chat",
            json={
                "user_message": "finish",
                "conversation_id": cid,
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": hello_body["reply"]},
                    {"role": "user", "content": "DC motor"},
                    {"role": "assistant", "content": draft_body["reply"]},
                ],
                "session_state": draft_body["session_state"],
            },
        )
        create.assert_not_called()
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "complete"
    assert body["final_result"] is not None
    assert "def dynamics" in body["final_result"]["python_code"]

    detail = client.get(f"/api/plant-model/conversations/{cid}")
    assert detail.status_code == 200
    stored = detail.json()
    assert stored["status"] == "complete"
    assert stored["final_result"] is not None
    assert stored["final_result"]["system_name"] == "dc_motor"
    assert "def dynamics" in stored["final_result"]["python_code"]


def test_mock_chat_web_search_http(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        r = client.post(
            "/api/plant-model/chat",
            json={"user_message": "hello", "messages": [], "web_search": True},
        )
        create.assert_not_called()
    assert r.status_code == 200
    kinds = [item["kind"] for item in r.json()["tool_results"]]
    assert kinds == ["search"]


def test_chat_access_denied_is_error_body(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        owned = client.post(
            "/api/plant-model/chat",
            params={"user_id": 1},
            json={"user_message": "hello", "messages": []},
        )
        create.assert_not_called()
    assert owned.status_code == 200
    cid = owned.json()["conversation_id"]
    denied = client.post(
        "/api/plant-model/chat",
        params={"user_id": 2},
        json={
            "user_message": "DC motor",
            "conversation_id": cid,
            "messages": [],
        },
    )
    _assert_error_body(denied, status=403, contains="access denied")


def test_conversation_get_access_denied_is_error_body(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        owned = client.post(
            "/api/plant-model/chat",
            params={"user_id": 1},
            json={"user_message": "hello", "messages": []},
        )
        create.assert_not_called()
    cid = owned.json()["conversation_id"]
    denied = client.get(
        f"/api/plant-model/conversations/{cid}",
        params={"user_id": 2},
    )
    _assert_error_body(denied, status=403, contains="access denied")


def test_upload_empty_file_is_error_body(client: TestClient):
    r = client.post(
        "/api/plant-model/files",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    _assert_error_body(r, status=400, contains="empty file")


def test_upload_oversized_file_is_error_body(client: TestClient):
    r = client.post(
        "/api/plant-model/files",
        files={
            "file": (
                "big.pdf",
                b"x" * (MAX_UPLOAD_SIZE_BYTES + 1),
                "application/pdf",
            ),
        },
    )
    _assert_error_body(r, status=400, contains="file too large")


def test_artifact_incomplete_conversation_is_error_body(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_mock_mode(monkeypatch)
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        hello = client.post(
            "/api/plant-model/chat",
            json={"user_message": "hello", "messages": []},
        )
        create.assert_not_called()
    assert hello.status_code == 200
    r = client.post(
        "/api/plant-model/artifacts",
        json={
            "conversation_id": hello.json()["conversation_id"],
            "pre_launch": _minimal_pre_launch(0),
        },
    )
    body = _assert_error_body(r, status=400, contains="not complete")
    assert body["warnings"] == []
