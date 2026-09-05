"""Deterministic PlantModelAgent stand-in (no LLM, no network, no API key).

Duck-compatible with apply_session_state / export_session_state / service
status inference. Selected by A4; this module does not read env or HTTP.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable

from backend_api.AgentPlant.schemas import (
    HitlOption,
    HitlPrompt,
    SearchHit,
    ToolResult,
)
from backend_core.AgentPlant.agent import (
    DEFAULT_MAX_DRAFTS,
    DEFAULT_MIN_USER_TURNS_BEFORE_COMPLETION,
    _FINISH_RE,
)

_GREETINGS = frozenset({"hi", "hello", "hey", "help", "what", "who", "?"})
_PLANT_KEYWORDS = frozenset(
    {
        "motor",
        "cart",
        "pole",
        "pendulum",
        "integrator",
        "cstr",
        "tank",
        "boost",
        "converter",
        "dynamics",
        "plant",
        "beam",
        "quadrotor",
    }
)

_HITL_QUESTION = "What physical system should I model?"
_HITL_OPTIONS = (
    HitlOption(label="DC motor"),
    HitlOption(label="Cart-pole"),
    HitlOption(label="Simple integrator"),
)

_RAG_HIT = SearchHit(
    source="attached-document",
    snippet="State-space form xdot = A x + B u is standard for linear plants.",
)
_SEARCH_HIT = SearchHit(
    source="Mock catalog · plant models",
    snippet="Open-loop step checks are used before accepting a draft.",
    url=None,
)

_FIXTURE_DC_MOTOR: dict[str, Any] = {
    "system_name": "dc_motor",
    "python_code": (
        "import numpy as np\n"
        "\n"
        "def dynamics(t, x, u):\n"
        "    theta = x[0]  # shaft angle (rad)\n"
        "    omega = x[1]  # angular rate (rad/s)\n"
        "    v = float(u[0] if hasattr(u, '__len__') else u)  # armature voltage (V)\n"
        "    R, Kt, J, b = 1.0, 0.01, 0.01, 0.1  # labelled assumptions\n"
        "    return np.array([omega, (Kt * v - b * omega) / J])\n"
    ),
    "metadata": {
        "states": ["theta", "omega"],
        "state_meanings": ["shaft angle (rad)", "angular rate (rad/s)"],
        "inputs": ["v"],
        "outputs": ["theta"],
        "state_equations": ["omega", "(Kt*v - b*omega)/J"],
        "parameters": {"R": 1.0, "Kt": 0.01, "J": 0.01, "b": 0.1},
        "system_type": "SISO",
        "assumptions": ["R = 1.0 ohm (assumed)", "electrical pole neglected"],
    },
}

_FIXTURE_CART_POLE: dict[str, Any] = {
    "system_name": "cart_pole",
    "python_code": (
        "import numpy as np\n"
        "\n"
        "def dynamics(t, x, u):\n"
        "    # x = [cart pos, cart vel, pole angle, pole rate]\n"
        "    mc, mp, l, g = 1.0, 0.1, 0.5, 9.81\n"
        "    x1, x2, x3, x4 = x\n"
        "    force = float(u[0] if hasattr(u, '__len__') else u)\n"
        "    s, c = np.sin(x3), np.cos(x3)\n"
        "    den = mc + mp * s**2\n"
        "    dx2 = (force + mp * l * x4**2 * s - mp * g * s * c) / den\n"
        "    dx4 = (-force * c - mp * l * x4**2 * s * c + (mc + mp) * g * s) / (l * den)\n"
        "    return np.array([x2, dx2, x4, dx4])\n"
    ),
    "metadata": {
        "states": ["x1", "x2", "x3", "x4"],
        "state_meanings": [
            "cart position (m)",
            "cart velocity (m/s)",
            "pole angle (rad)",
            "pole angular rate (rad/s)",
        ],
        "inputs": ["u"],
        "outputs": ["x3"],
        "state_equations": [
            "x2",
            "(u + m_p*l*x4**2*sin(x3) - m_p*g*sin(x3)*cos(x3))/(m_c + m_p*sin(x3)**2)",
            "x4",
            "(-u*cos(x3) - m_p*l*x4**2*sin(x3)*cos(x3) + (m_c+m_p)*g*sin(x3))/(l*(m_c + m_p*sin(x3)**2))",
        ],
        "parameters": {"m_c": 1.0, "m_p": 0.1, "l": 0.5, "g": 9.81},
        "system_type": "SISO",
        "assumptions": ["g = 9.81 m/s^2 (assumed)", "frictionless cart"],
    },
}

_FIXTURE_INTEGRATOR: dict[str, Any] = {
    "system_name": "simple_integrator",
    "python_code": (
        "import numpy as np\n"
        "\n"
        "def dynamics(t, x, u):\n"
        "    uu = float(u[0] if hasattr(u, '__len__') else u)\n"
        "    return np.array([uu])\n"
    ),
    "metadata": {
        "states": ["x1"],
        "state_meanings": ["integrated output"],
        "inputs": ["u"],
        "outputs": ["x1"],
        "state_equations": ["u"],
        "parameters": {},
        "system_type": "SISO",
        "assumptions": ["single integrator, gain 1"],
    },
}


def _normalize(message: str) -> str:
    return " ".join(message.strip().lower().split())


def _has_plant_keyword(normalized: str) -> bool:
    tokens = set(normalized.split())
    return any(keyword in tokens for keyword in _PLANT_KEYWORDS)


def _is_insufficient(message: str) -> bool:
    normalized = _normalize(message)
    if not normalized:
        return True
    greeting = normalized in _GREETINGS
    few_words = len(normalized.split()) < 3
    return (greeting or few_words) and not _has_plant_keyword(normalized)


def _copy_draft(draft: dict[str, Any]) -> dict[str, Any]:
    copied = dict(draft)
    metadata = draft.get("metadata")
    if isinstance(metadata, dict):
        copied["metadata"] = dict(metadata)
    return copied


def _select_fixture(user_message: str) -> dict[str, Any]:
    normalized = _normalize(user_message)
    if normalized == "dc motor":
        return _copy_draft(_FIXTURE_DC_MOTOR)
    if normalized == "cart-pole":
        return _copy_draft(_FIXTURE_CART_POLE)
    if normalized == "simple integrator":
        return _copy_draft(_FIXTURE_INTEGRATOR)
    if "motor" in normalized.split():
        return _copy_draft(_FIXTURE_DC_MOTOR)
    tokens = normalized.split()
    if any(token in {"cart", "pole", "pendulum"} for token in tokens):
        return _copy_draft(_FIXTURE_CART_POLE)
    if "integrator" in tokens:
        return _copy_draft(_FIXTURE_INTEGRATOR)
    return _copy_draft(_FIXTURE_INTEGRATOR)


class MockPlantModelAgent:
    """Deterministic continue / draft / complete stand-in for PlantModelAgent."""

    def __init__(
        self,
        *,
        model: str = "mock",
        max_drafts: int = DEFAULT_MAX_DRAFTS,
        min_user_turns_before_completion: int = DEFAULT_MIN_USER_TURNS_BEFORE_COMPLETION,
        **_ignored: Any,
    ) -> None:
        self.model = model
        self.max_drafts = max(1, max_drafts)
        self.min_user_turns_before_completion = max(1, min_user_turns_before_completion)
        self._draft_count = 0
        self._latest_draft: dict[str, Any] | None = None
        self.last_hitl: HitlPrompt | None = None
        self.last_tool_results: list[ToolResult] = []
        self.request_attachment_ids: list[str] = []
        self.request_web_search: bool = False

    def reset_conversation_state(self) -> None:
        self._draft_count = 0
        self._latest_draft = None
        self.last_hitl = None
        self.last_tool_results = []

    @property
    def total_usage(self) -> SimpleNamespace:
        return SimpleNamespace(input_tokens=0, output_tokens=0)

    @property
    def total_cost(self) -> float:
        return 0.0

    def step(
        self,
        history_messages: Iterable[dict[str, str]],
        user_message: str,
    ) -> tuple[str, dict[str, Any] | None]:
        self.last_hitl = None
        self.last_tool_results = []

        history = list(history_messages)
        user_turns = sum(1 for message in history if message.get("role") == "user") + 1
        _ = user_turns  # reserved for parity with the real agent; unused in the mock FSM
        text = user_message.strip()
        user_accepts = bool(_FINISH_RE.search(text))

        if user_accepts and self._latest_draft is not None:
            result = self._complete()
        elif user_accepts and self._latest_draft is None:
            result = self._continue_with_hitl()
        elif self._latest_draft is None and _is_insufficient(text):
            result = self._continue_with_hitl()
        else:
            result = self._emit_draft(text)

        self._fill_tool_results()
        return result

    def _continue_with_hitl(self) -> tuple[str, None]:
        self.last_hitl = HitlPrompt(
            question=_HITL_QUESTION,
            options=list(_HITL_OPTIONS),
            allow_free_text=True,
            timeout_sec=30,
        )
        return _HITL_QUESTION, None

    def _emit_draft(self, user_message: str) -> tuple[str, dict[str, Any] | None]:
        self._latest_draft = _select_fixture(user_message)
        self._draft_count += 1
        name = str(self._latest_draft["system_name"])
        display = f"Draft: {name}"
        if self._draft_count >= self.max_drafts:
            return f"Model ready — {name}.", _copy_draft(self._latest_draft)
        return display, None

    def _complete(self) -> tuple[str, dict[str, Any]]:
        assert self._latest_draft is not None
        name = str(self._latest_draft["system_name"])
        return f"Model ready — {name}.", _copy_draft(self._latest_draft)

    def _fill_tool_results(self) -> None:
        if self.request_attachment_ids:
            self.last_tool_results.append(
                ToolResult(kind="rag", items=[SearchHit.model_validate(_RAG_HIT.model_dump())])
            )
        if self.request_web_search:
            self.last_tool_results.append(
                ToolResult(kind="search", items=[SearchHit.model_validate(_SEARCH_HIT.model_dump())])
            )
