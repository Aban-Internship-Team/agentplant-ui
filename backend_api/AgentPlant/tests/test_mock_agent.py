"""Pure unit tests for MockPlantModelAgent (no HTTP, no LLM, no network)."""

from __future__ import annotations

from unittest.mock import patch

from backend_api.AgentPlant.mock_agent import MockPlantModelAgent
from backend_api.AgentPlant.schemas import PlantModelResult
from backend_core.AgentPlant import apply_session_state, export_session_state


def _history(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in pairs]


def test_continue_is_deterministic():
    first = MockPlantModelAgent()
    second = MockPlantModelAgent()
    reply_a, final_a = first.step([], "hello")
    reply_b, final_b = second.step([], "hello")
    assert reply_a == reply_b
    assert final_a == final_b is None

    again_reply, again_final = first.step(_history(("user", "hello")), "hello")
    assert again_reply == reply_a
    assert again_final is None


def test_continue_includes_hitl():
    agent = MockPlantModelAgent()
    reply, final = agent.step([], "hello")
    assert final is None
    hitl = agent.last_hitl
    assert hitl is not None
    assert hitl.question == "What physical system should I model?"
    assert reply == hitl.question
    assert len(hitl.options) == 3
    assert hitl.allow_free_text is True
    assert hitl.timeout_sec == 30
    labels = [option.label for option in hitl.options]
    assert labels == ["DC motor", "Cart-pole", "Simple integrator"]
    joined = " ".join(labels).lower()
    assert "pid" not in joined
    assert "mpc" not in joined
    assert "adaptive" not in joined
    assert "controller" not in joined


def test_resolve_hitl_to_draft():
    agent = MockPlantModelAgent()
    agent.step([], "hello")
    reply, final = agent.step(_history(("user", "hello")), "DC motor")
    assert final is None
    assert reply == "Draft: dc_motor"
    assert agent._draft_count == 1
    assert agent.last_hitl is None
    assert agent._latest_draft is not None
    assert "def dynamics" in agent._latest_draft["python_code"]


def test_deterministic_draft_payload():
    first = MockPlantModelAgent()
    second = MockPlantModelAgent()
    first.step([], "DC motor")
    second.step([], "DC motor")
    assert first._latest_draft is not None
    assert second._latest_draft is not None
    assert first._latest_draft["system_name"] == second._latest_draft["system_name"]
    assert first._latest_draft["python_code"] == second._latest_draft["python_code"]
    assert first._latest_draft["metadata"] == second._latest_draft["metadata"]


def test_finish_without_draft_stays_continue():
    agent = MockPlantModelAgent()
    reply, final = agent.step([], "finish")
    assert final is None
    assert agent.last_hitl is not None
    assert agent._draft_count == 0
    assert reply == agent.last_hitl.question


def test_finish_after_draft_completes():
    agent = MockPlantModelAgent()
    agent.step([], "DC motor")
    reply, final = agent.step(_history(("user", "DC motor")), "finish")
    assert final is not None
    assert final["system_name"] == "dc_motor"
    assert "def dynamics" in final["python_code"]
    PlantModelResult.model_validate(final)
    assert reply == "Model ready — dc_motor."
    assert final is not agent._latest_draft

    again = MockPlantModelAgent()
    again.step([], "DC motor")
    _, done_final = again.step(_history(("user", "DC motor")), "done")
    assert done_final is not None

    looks = MockPlantModelAgent()
    looks.step([], "DC motor")
    _, looks_final = looks.step(_history(("user", "DC motor")), "looks good")
    assert looks_final is not None


def test_session_state_roundtrip():
    first = MockPlantModelAgent()
    first.step([], "DC motor")
    state = export_session_state(first)
    second = MockPlantModelAgent()
    apply_session_state(second, state)
    assert second._draft_count == 1
    assert second._latest_draft is not None
    reply, final = second.step(_history(("user", "DC motor")), "finish")
    assert final is not None
    assert final["system_name"] == "dc_motor"
    assert reply == "Model ready — dc_motor."


def test_draft_count_increments():
    agent = MockPlantModelAgent()
    agent.step([], "DC motor")
    assert agent._draft_count == 1
    agent.step(_history(("user", "DC motor")), "please change the damping")
    assert agent._draft_count == 2


def test_max_drafts_auto_completes():
    agent = MockPlantModelAgent(max_drafts=1)
    reply, final = agent.step([], "DC motor")
    assert agent._draft_count == 1
    assert final is not None
    assert final["system_name"] == "dc_motor"
    assert reply == "Model ready — dc_motor."


def test_min_turns_does_not_block_explicit_finish():
    agent = MockPlantModelAgent(min_user_turns_before_completion=5)
    agent.step([], "DC motor")
    _, final = agent.step(_history(("user", "DC motor")), "finish")
    assert final is not None


def test_min_turns_does_not_auto_complete_first_draft():
    agent = MockPlantModelAgent(min_user_turns_before_completion=5, max_drafts=5)
    reply, final = agent.step([], "DC motor")
    assert final is None
    assert reply == "Draft: dc_motor"
    assert agent._draft_count == 1


def test_mock_rag_result():
    agent = MockPlantModelAgent()
    agent.request_attachment_ids = ["doc-1"]
    agent.step([], "hello")
    assert len(agent.last_tool_results) == 1
    result = agent.last_tool_results[0]
    assert result.kind == "rag"
    assert result.items[0].source == "attached-document"
    assert result.items[0].snippet == (
        "State-space form xdot = A x + B u is standard for linear plants."
    )


def test_mock_search_result():
    agent = MockPlantModelAgent()
    agent.request_web_search = True
    agent.step([], "hello")
    assert len(agent.last_tool_results) == 1
    result = agent.last_tool_results[0]
    assert result.kind == "search"
    assert result.items[0].source == "Mock catalog · plant models"
    assert result.items[0].snippet == (
        "Open-loop step checks are used before accepting a draft."
    )
    assert result.items[0].url is None


def test_combined_tool_results():
    agent = MockPlantModelAgent()
    agent.request_attachment_ids = ["doc-1"]
    agent.request_web_search = True
    agent.step([], "hello")
    assert [item.kind for item in agent.last_tool_results] == ["rag", "search"]


def test_attachment_ids_tolerated_without_io():
    agent = MockPlantModelAgent()
    agent.request_attachment_ids = ["not-a-real-file.pdf"]
    with patch("builtins.open") as mocked_open:
        reply, final = agent.step([], "hello")
        mocked_open.assert_not_called()
    assert final is None
    assert reply


def test_no_llm_factory_or_network():
    with patch("labcd_agents.providers.LLMFactory.create") as create:
        agent = MockPlantModelAgent()
        agent.step([], "hello")
        create.assert_not_called()
    assert agent.total_usage.input_tokens == 0
    assert agent.total_usage.output_tokens == 0
    assert agent.total_cost == 0.0


def test_motor_fixture():
    agent = MockPlantModelAgent()
    agent.step([], "please model a motor")
    assert agent._latest_draft is not None
    assert agent._latest_draft["system_name"] == "dc_motor"
    assert "def dynamics(t, x, u)" in agent._latest_draft["python_code"]
    PlantModelResult.model_validate(agent._latest_draft)


def test_cart_pole_fixture():
    agent = MockPlantModelAgent()
    agent.step([], "cart pole")
    assert agent._latest_draft is not None
    assert agent._latest_draft["system_name"] == "cart_pole"
    assert "def dynamics(t, x, u)" in agent._latest_draft["python_code"]
    PlantModelResult.model_validate(agent._latest_draft)


def test_default_integrator_fixture():
    agent = MockPlantModelAgent()
    agent.step([], "please model something")
    assert agent._latest_draft is not None
    assert agent._latest_draft["system_name"] == "simple_integrator"
    assert "def dynamics(t, x, u)" in agent._latest_draft["python_code"]
    PlantModelResult.model_validate(agent._latest_draft)


def test_integrator_keyword_fixture():
    agent = MockPlantModelAgent()
    agent.step([], "simple integrator")
    assert agent._latest_draft is not None
    assert agent._latest_draft["system_name"] == "simple_integrator"


def test_reset_conversation_state_returns_to_continue():
    agent = MockPlantModelAgent()
    agent.step([], "DC motor")
    assert agent._draft_count == 1
    assert agent._latest_draft is not None
    agent.reset_conversation_state()
    assert agent._draft_count == 0
    assert agent._latest_draft is None
    reply, final = agent.step([], "hello")
    assert final is None
    assert agent.last_hitl is not None
    assert reply == agent.last_hitl.question
    assert agent._draft_count == 0


def test_hi_motor_keyword_bypasses_hitl():
    agent = MockPlantModelAgent()
    reply, final = agent.step([], "hi motor")
    assert final is None
    assert agent.last_hitl is None
    assert reply == "Draft: dc_motor"
    assert agent._latest_draft is not None
    assert agent._latest_draft["system_name"] == "dc_motor"
