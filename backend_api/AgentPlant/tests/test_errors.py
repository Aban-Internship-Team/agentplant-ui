"""HTTP error-envelope tests (A8). No live LLM."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend_api.AgentPlant.app import app
from backend_api.AgentPlant.conversation_store import InMemoryConversationStore
from backend_api.AgentPlant.errors import (
    envelope_from_http_detail,
    error_response,
    register_exception_handlers,
)
from backend_api.AgentPlant.schemas import ErrorBody


def _assert_envelope(body: object) -> dict:
    assert isinstance(body, dict)
    assert set(body) == {"message", "errors", "warnings"}
    assert "detail" not in body
    assert isinstance(body["message"], str)
    assert isinstance(body["errors"], list)
    assert isinstance(body["warnings"], list)
    assert all(isinstance(item, str) for item in body["errors"])
    assert all(isinstance(item, str) for item in body["warnings"])
    return body


class _Horizon(BaseModel):
    total_simulation_time: float = Field(gt=0)


class _PreLaunch(BaseModel):
    solver_sample_time: float = Field(gt=0)


class _ArtifactIn(BaseModel):
    pre_launch: _PreLaunch


def _handler_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/raise-400")
    def raise_400() -> None:
        raise HTTPException(status_code=400, detail="empty file")

    @test_app.get("/raise-403")
    def raise_403() -> None:
        raise HTTPException(status_code=403, detail="Conversation access denied")

    @test_app.get("/raise-404")
    def raise_404() -> None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    @test_app.get("/raise-artifact")
    def raise_artifact() -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Plant or pre-launch validation failed",
                "errors": ["system_name is required"],
                "warnings": ["metadata missing"],
            },
        )

    @test_app.get("/raise-unknown-detail")
    def raise_unknown() -> None:
        raise HTTPException(status_code=400, detail={"unexpected": True, "payload": {"n": 1}})

    @test_app.get("/raise-500")
    def raise_500() -> None:
        raise RuntimeError("leaked-secret /tmp/not-a-real-key")

    @test_app.post("/horizon")
    def horizon(body: _Horizon) -> dict:
        return body.model_dump()

    @test_app.post("/artifact-shape")
    def artifact_shape(body: _ArtifactIn) -> dict:
        return body.model_dump()

    return test_app


@pytest.fixture
def handler_client() -> TestClient:
    return TestClient(_handler_app(), raise_server_exceptions=False)


@pytest.fixture
def api_client():
    store = InMemoryConversationStore()
    from unittest.mock import patch

    with patch("backend_api.AgentPlant.router.default_store", store):
        yield TestClient(app, raise_server_exceptions=False)


def test_error_body_serialization_keys():
    response = error_response(400, message="failed", errors=["failed"])
    body = json.loads(response.body)
    assert list(body) == ["message", "errors", "warnings"]
    assert body == ErrorBody(message="failed", errors=["failed"], warnings=[]).model_dump()
    assert response.media_type == "application/json"


def test_envelope_from_string_and_artifact_dict():
    string_body = envelope_from_http_detail("Conversation not found")
    assert string_body.model_dump() == {
        "message": "Conversation not found",
        "errors": ["Conversation not found"],
        "warnings": [],
    }
    artifact = envelope_from_http_detail(
        {
            "message": "Plant or pre-launch validation failed",
            "errors": ["system_name is required"],
            "warnings": ["metadata missing"],
        }
    )
    assert artifact.model_dump() == {
        "message": "Plant or pre-launch validation failed",
        "errors": ["system_name is required"],
        "warnings": ["metadata missing"],
    }
    unknown = envelope_from_http_detail({"foo": object()})
    assert unknown.model_dump() == {
        "message": "Request failed",
        "errors": ["Request failed"],
        "warnings": [],
    }


@pytest.mark.parametrize(
    ("path", "status", "text"),
    [
        ("/raise-400", 400, "empty file"),
        ("/raise-403", 403, "Conversation access denied"),
        ("/raise-404", 404, "Conversation not found"),
    ],
)
def test_http_exception_string_detail(handler_client: TestClient, path: str, status: int, text: str):
    r = handler_client.get(path)
    assert r.status_code == status
    assert "application/json" in r.headers["content-type"]
    body = _assert_envelope(r.json())
    assert body["message"] == text
    assert body["errors"] == [text]
    assert body["warnings"] == []


def test_http_exception_artifact_dict_detail(handler_client: TestClient):
    r = handler_client.get("/raise-artifact")
    assert r.status_code == 400
    body = _assert_envelope(r.json())
    assert body["message"] == "Plant or pre-launch validation failed"
    assert body["errors"] == ["system_name is required"]
    assert body["warnings"] == ["metadata missing"]


def test_http_exception_unknown_detail_is_safe(handler_client: TestClient):
    r = handler_client.get("/raise-unknown-detail")
    assert r.status_code == 400
    body = _assert_envelope(r.json())
    assert body["message"] == "Request failed"
    assert body["errors"] == ["Request failed"]
    assert body["warnings"] == []


def test_request_validation_error_is_422(handler_client: TestClient):
    r = handler_client.post("/horizon", json={"total_simulation_time": 0})
    assert r.status_code == 422
    assert "application/json" in r.headers["content-type"]
    body = _assert_envelope(r.json())
    assert body["message"] == "Request validation failed"
    assert body["warnings"] == []
    assert any("total_simulation_time" in item for item in body["errors"])
    assert "detail" not in r.json()
    assert '"input"' not in r.text
    assert any(item.startswith("body.total_simulation_time:") for item in body["errors"])


def test_nested_validation_path_pre_launch(handler_client: TestClient):
    r = handler_client.post("/artifact-shape", json={"pre_launch": {"solver_sample_time": 0}})
    assert r.status_code == 422
    body = _assert_envelope(r.json())
    assert body["message"] == "Request validation failed"
    assert any(
        item.startswith("body.pre_launch.solver_sample_time:") for item in body["errors"]
    )
    assert '"input"' not in r.text
    assert all(": {" not in item and "python_code" not in item for item in body["errors"])


def test_simulate_and_artifact_nested_422_on_real_app(api_client: TestClient):
    sim = api_client.post(
        "/api/plant-model/simulate",
        json={"total_simulation_time": 0, "solver_sample_time": 0.1},
    )
    assert sim.status_code == 422
    sim_body = _assert_envelope(sim.json())
    assert sim_body["message"] == "Request validation failed"
    assert any("body.total_simulation_time:" in item for item in sim_body["errors"])

    art = api_client.post(
        "/api/plant-model/artifacts",
        json={
            "plant": {"system_name": "x", "python_code": "def dynamics(t, x, u):\n    return [0]"},
            "pre_launch": {
                "total_simulation_time": 10.0,
                "solver_sample_time": 0,
                "initial_state": [],
                "default_target": [],
            },
        },
    )
    assert art.status_code == 422
    art_body = _assert_envelope(art.json())
    assert any(
        "body.pre_launch.solver_sample_time:" in item for item in art_body["errors"]
    )


def test_malformed_chat_request_is_422(api_client: TestClient):
    r = api_client.post("/api/plant-model/chat", json={})
    assert r.status_code == 422
    body = _assert_envelope(r.json())
    assert body["message"] == "Request validation failed"
    assert any("user_message" in item for item in body["errors"])


def test_generic_500_hides_exception_details(handler_client: TestClient):
    secret = "leaked-secret /tmp/not-a-real-key"
    r = handler_client.get("/raise-500")
    assert r.status_code == 500
    assert "application/json" in r.headers["content-type"]
    body = _assert_envelope(r.json())
    assert body["message"] == "Internal server error"
    assert body["errors"] == ["An unexpected error occurred"]
    assert body["warnings"] == []
    assert secret not in r.text
    assert "/tmp/not-a-real-key" not in r.text
    assert "RuntimeError" not in r.text
    assert "Traceback" not in r.text


def test_real_app_500_from_chat_dependency(api_client: TestClient):
    from unittest.mock import patch

    secret = "leaked-secret /tmp/not-a-real-key"
    with patch(
        "backend_api.AgentPlant.router.run_plant_model_chat",
        side_effect=RuntimeError(secret),
    ):
        r = api_client.post(
            "/api/plant-model/chat",
            json={"user_message": "hi", "messages": []},
        )
    assert r.status_code == 500
    body = _assert_envelope(r.json())
    assert body["message"] == "Internal server error"
    assert secret not in r.text
    assert "/tmp/not-a-real-key" not in r.text


def test_health_and_validate_success_unchanged(api_client: TestClient):
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "agent-plant"}

    validate = api_client.post(
        "/api/plant-model/validate",
        json={"plant": {"system_name": "x", "python_code": "pass"}},
    )
    assert validate.status_code == 200
    body = validate.json()
    assert set(body) >= {"ok", "errors", "warnings"}
    assert body["ok"] is False
    assert "message" not in body


def test_handlers_are_registered_on_app():
    handlers = app.exception_handlers
    assert RequestValidationError in handlers
    assert StarletteHTTPException in handlers
    assert Exception in handlers
