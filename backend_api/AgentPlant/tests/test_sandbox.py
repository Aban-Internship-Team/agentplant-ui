"""Sandbox AST gate and subprocess worker tests (no LLM)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend_api.AgentPlant.sandbox import (
    MAX_SOURCE_BYTES,
    MAX_STATE_DIM,
    MAX_STDOUT_BYTES,
    SANDBOX_TIMEOUT_SEC,
    SandboxDynamicsError,
    SandboxOutputError,
    SandboxRejected,
    SandboxSyntaxError,
    SandboxTimeout,
    validate_plant_source,
)
from backend_api.AgentPlant.schemas import PlantPayload, SimulateRequest
from backend_api.AgentPlant.simulate import (
    generate_mock_trajectory,
    plant_from_conversation,
    run_simulation,
)

INTEGRATOR = (
    "import numpy as np\n"
    "def dynamics(t, x, u):\n"
    "    return np.array([float(u[0])])\n"
)
TWO_STATE = (
    "import numpy as np\n"
    "def dynamics(t, x, u):\n"
    "    v = float(u[0])\n"
    "    return np.array([x[1], v - x[1]])\n"
)
DC_MOTOR = (
    "import numpy as np\n"
    "def dynamics(t, x, u):\n"
    "    omega = x[1]\n"
    "    v = float(u[0] if hasattr(u, '__len__') else u)\n"
    "    Kt, J, b = 0.01, 0.01, 0.1\n"
    "    return np.array([omega, (Kt * v - b * omega) / J])\n"
)


def _req(**overrides) -> SimulateRequest:
    payload = {
        "total_simulation_time": 1.0,
        "solver_sample_time": 0.25,
        "plant": PlantPayload(system_name="p", python_code=INTEGRATOR),
    }
    payload.update(overrides)
    return SimulateRequest.model_validate(payload)


def test_valid_integrator():
    response = run_simulation(_req(initial_state=[0.0], amplitude=1.0))
    assert response.x[0] == [0.0]
    assert response.x[-1][0] > response.x[0][0]
    assert all(row == [1.0] for row in response.u)


def test_valid_multi_state_and_dc_motor():
    multi = run_simulation(
        _req(
            plant=PlantPayload(system_name="two", python_code=TWO_STATE),
            initial_state=[0.0, 0.0],
        )
    )
    assert all(len(row) == 2 for row in multi.x)
    motor = run_simulation(
        _req(
            plant=PlantPayload(system_name="dc_motor", python_code=DC_MOTOR),
            initial_state=[0.0, 0.0],
        )
    )
    assert all(len(row) == 2 for row in motor.x)
    assert motor.x[0] == [0.0, 0.0]


def test_sandboxed_calls_are_deterministic():
    request = _req(initial_state=[0.2])
    assert run_simulation(request).x == run_simulation(request).x


def test_missing_dynamics_rejected():
    with pytest.raises(SandboxRejected):
        validate_plant_source("import numpy as np\nx = 1\n")


def test_syntax_error():
    with pytest.raises(SandboxSyntaxError):
        validate_plant_source("def dynamics(t, x, u)\n    return x\n")


def test_wrong_derivative_dimension():
    code = (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        "    return np.array([1.0, 2.0])\n"
    )
    with pytest.raises(SandboxDynamicsError):
        run_simulation(_req(plant=PlantPayload(system_name="bad", python_code=code), initial_state=[0.0]))


def test_runtime_exception():
    code = (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        "    raise RuntimeError('boom')\n"
    )
    with pytest.raises(SandboxDynamicsError, match="boom"):
        run_simulation(_req(plant=PlantPayload(system_name="bad", python_code=code)))


def test_timeout_infinite_loop():
    code = (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        "    while True:\n"
        "        pass\n"
        "    return np.array([0.0])\n"
    )
    with patch("backend_api.AgentPlant.sandbox.SANDBOX_TIMEOUT_SEC", 0.4):
        with pytest.raises(SandboxTimeout):
            run_simulation(_req(plant=PlantPayload(system_name="loop", python_code=code)))


def test_oversized_state_dimension():
    with pytest.raises(SandboxRejected):
        run_simulation(_req(initial_state=[0.0] * (MAX_STATE_DIM + 1)))


def test_oversized_source():
    body = "    return np.array([0.0])\n"
    padding = "    x = x\n" * 8000
    source = "import numpy as np\ndef dynamics(t, x, u):\n" + padding + body
    assert len(source.encode()) > MAX_SOURCE_BYTES
    with pytest.raises(SandboxRejected, match="exceeds"):
        validate_plant_source(source)


def test_rejected_imports_and_builtins():
    cases = [
        "import os\ndef dynamics(t, x, u):\n    return x\n",
        "import sys\ndef dynamics(t, x, u):\n    return x\n",
        "import socket\ndef dynamics(t, x, u):\n    return x\n",
        "import subprocess\ndef dynamics(t, x, u):\n    return x\n",
        "import pathlib\ndef dynamics(t, x, u):\n    return x\n",
        "import shutil\ndef dynamics(t, x, u):\n    return x\n",
        "import unknownmod\ndef dynamics(t, x, u):\n    return x\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return eval('x')\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    exec('x')\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return open('x')\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return x.__class__\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return (0).__class__\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return getattr(x, 'n')\n",
        "from os import path\ndef dynamics(t, x, u):\n    return x\n",
    ]
    for source in cases:
        with pytest.raises((SandboxRejected, SandboxSyntaxError)):
            validate_plant_source(source)


def test_no_plant_uses_a6_mock():
    mock = generate_mock_trajectory(
        SimulateRequest(total_simulation_time=1.0, solver_sample_time=0.25)
    )
    live = run_simulation(
        SimulateRequest(total_simulation_time=1.0, solver_sample_time=0.25)
    )
    assert live.x == mock.x
    assert live.u == mock.u


def test_explicit_plant_uses_sandbox_not_mock():
    mock = generate_mock_trajectory(
        SimulateRequest(total_simulation_time=1.0, solver_sample_time=0.25, amplitude=1.0)
    )
    live = run_simulation(_req(amplitude=1.0, initial_state=[0.0]))
    assert live.x != mock.x


def test_explicit_plant_overrides_conversation_draft():
    draft = PlantPayload(system_name="draft", python_code=INTEGRATOR)
    conversation = SimpleNamespace(
        session_state=SimpleNamespace(latest_draft=draft),
        final_result=None,
    )
    resolved = plant_from_conversation(conversation)
    hold = (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        "    return np.array([0.0 * x[0]])\n"
    )
    response = run_simulation(
        _req(
            plant=PlantPayload(system_name="hold", python_code=hold),
            initial_state=[4.0],
        ),
        resolved_plant=resolved,
    )
    assert response.x[0] == [4.0]
    assert response.x[-1] == [4.0]


def test_plant_from_draft_then_final():
    draft = PlantPayload(system_name="draft", python_code=INTEGRATOR)
    final = PlantPayload(system_name="final", python_code=TWO_STATE, metadata={"states": ["a", "b"]})
    assert plant_from_conversation(
        SimpleNamespace(session_state=SimpleNamespace(latest_draft=draft), final_result=final)
    ).system_name == "draft"
    assert plant_from_conversation(
        SimpleNamespace(session_state=SimpleNamespace(latest_draft=None), final_result=final)
    ).system_name == "final"


def test_sandbox_failure_does_not_fallback_to_mock():
    with pytest.raises(SandboxRejected):
        run_simulation(
            _req(plant=PlantPayload(system_name="evil", python_code="import os\ndef dynamics(t, x, u):\n    return x\n"))
        )


def test_parent_process_does_not_exec_plant():
    with patch("builtins.exec") as mocked_exec:
        run_simulation(_req())
    mocked_exec.assert_not_called()


def test_timeout_constant_is_two_seconds():
    assert SANDBOX_TIMEOUT_SEC == 2.0


def test_oversized_worker_output_rejected():
    huge = b"{" + b"x" * (MAX_STDOUT_BYTES + 10)
    completed = type("R", (), {"stdout": huge, "stderr": b"", "returncode": 0})()
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(SandboxOutputError, match="size limit"):
            run_simulation(_req())


def test_safe_numpy_and_from_import_still_work():
    trig = (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        "    return np.array([np.sin(x[0]) + np.cos(u[0])])\n"
    )
    response = run_simulation(
        _req(plant=PlantPayload(system_name="trig", python_code=trig), initial_state=[0.0])
    )
    assert len(response.x[0]) == 1

    imported = (
        "from numpy import array, sin\n"
        "def dynamics(t, x, u):\n"
        "    return array([sin(x[0])])\n"
    )
    response = run_simulation(
        _req(plant=PlantPayload(system_name="imp", python_code=imported), initial_state=[0.0])
    )
    assert response.x[0] == [0.0]


def test_dangerous_numpy_attributes_rejected():
    cases = [
        "import numpy as np\ndef dynamics(t, x, u):\n    return np.loadtxt('x')\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return np.fromfile('x')\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return np.memmap('x')\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return np.ctypeslib.load_library('c', None)\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return np.save('x', x)\n",
        "import numpy as np\ndef dynamics(t, x, u):\n    return np.savetxt('x', x)\n",
    ]
    for source in cases:
        with pytest.raises(SandboxRejected):
            validate_plant_source(source)


def test_dangerous_from_numpy_import_rejected():
    cases = [
        "from numpy import loadtxt\ndef dynamics(t, x, u):\n    return x\n",
        "from numpy import fromfile\ndef dynamics(t, x, u):\n    return x\n",
        "from numpy import memmap\ndef dynamics(t, x, u):\n    return x\n",
        "from numpy import ctypeslib\ndef dynamics(t, x, u):\n    return x\n",
        "from numpy import save\ndef dynamics(t, x, u):\n    return x\n",
    ]
    for source in cases:
        with pytest.raises(SandboxRejected, match="not allowed"):
            validate_plant_source(source)


def test_worker_rejects_inferred_state_above_max_dim():
    code = (
        "import numpy as np\n"
        "def dynamics(t, x, u):\n"
        f"    return np.zeros({MAX_STATE_DIM + 1})\n"
    )
    with pytest.raises(SandboxDynamicsError, match="exceeds"):
        run_simulation(
            SimulateRequest(
                total_simulation_time=0.5,
                solver_sample_time=0.25,
                plant=PlantPayload(system_name="wide", python_code=code),
            )
        )
