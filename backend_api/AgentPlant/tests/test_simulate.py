"""Pure unit tests for mock open-loop trajectories (no HTTP, no LLM)."""

from __future__ import annotations

import math
from unittest.mock import patch

from backend_api.AgentPlant.schemas import PlantPayload, SimulateRequest
from backend_api.AgentPlant.simulate import (
    MAX_SIM_SAMPLES,
    _CAPPED_WARNING,
    _PLANT_IGNORED_WARNING,
    generate_mock_trajectory,
)


def _req(**overrides) -> SimulateRequest:
    payload = {
        "total_simulation_time": 1.0,
        "solver_sample_time": 0.25,
    }
    payload.update(overrides)
    return SimulateRequest.model_validate(payload)


def test_default_step_constant_input():
    response = generate_mock_trajectory(_req())
    assert response.t[0] == 0.0
    assert all(sample == [1.0] for sample in response.u)
    assert response.warnings == []
    assert len(response.t) == len(response.x) == len(response.u)


def test_pulse_then_zero():
    response = generate_mock_trajectory(
        _req(input_type="pulse", amplitude=2.0, pulse_width=0.5)
    )
    # t = [0, 0.25, 0.5, 0.75, 1.0]; high while t < 0.5
    assert [row[0] for row in response.u] == [2.0, 2.0, 0.0, 0.0, 0.0]


def test_sine_matches_formula():
    amp, freq = 3.0, 0.5
    response = generate_mock_trajectory(
        _req(input_type="sine", amplitude=amp, frequency=freq)
    )
    expected = [amp * math.sin(2.0 * math.pi * freq * t) for t in response.t]
    assert [row[0] for row in response.u] == expected


def test_repeated_calls_are_deterministic():
    request = _req(input_type="sine", frequency=0.25, initial_state=[0.2, -1.0])
    first = generate_mock_trajectory(request)
    second = generate_mock_trajectory(request)
    assert first.t == second.t
    assert first.x == second.x
    assert first.u == second.u
    assert first.warnings == second.warnings


def test_initial_state_preserved_at_t0():
    x0 = [0.4, -2.0, 1.5]
    response = generate_mock_trajectory(_req(initial_state=x0))
    assert response.x[0] == x0


def test_multi_state_only_first_evolves():
    x0 = [0.0, 7.0, -3.0]
    response = generate_mock_trajectory(_req(initial_state=x0, amplitude=1.0))
    assert all(len(row) == 3 for row in response.x)
    extras = [row[1:] for row in response.x]
    assert extras == [[7.0, -3.0]] * len(response.x)
    assert response.x[-1][0] != response.x[0][0]


def test_empty_initial_state_is_zero():
    response = generate_mock_trajectory(_req())
    assert response.x[0] == [0.0]
    assert all(len(row) == 1 for row in response.x)


def test_time_grid_floor_formula():
    response = generate_mock_trajectory(
        _req(total_simulation_time=1.0, solver_sample_time=0.25)
    )
    assert response.t == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_dt_greater_than_t_two_samples():
    response = generate_mock_trajectory(
        _req(total_simulation_time=0.5, solver_sample_time=2.0)
    )
    assert response.t == [0.0, 0.5]
    assert len(response.x) == 2
    assert len(response.u) == 2


def test_default_pulse_width():
    response = generate_mock_trajectory(
        _req(input_type="pulse", total_simulation_time=5.0, solver_sample_time=1.0)
    )
    # default pulse_width = min(1, 5) = 1; high while t < 1
    assert [row[0] for row in response.u] == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_default_frequency():
    response = generate_mock_trajectory(_req(input_type="sine", amplitude=1.0))
    expected = [math.sin(2.0 * math.pi * 0.5 * t) for t in response.t]
    assert [row[0] for row in response.u] == expected


def test_malicious_plant_code_is_ignored():
    plant = PlantPayload(
        system_name="evil",
        python_code="raise RuntimeError('executed')\nexec('os.system(1)')",
    )
    response = generate_mock_trajectory(_req(plant=plant, input_type="step"))
    assert response.t
    assert response.x
    assert response.u
    assert _PLANT_IGNORED_WARNING in response.warnings


def test_sample_cap_and_warning():
    response = generate_mock_trajectory(
        _req(total_simulation_time=100.0, solver_sample_time=0.001)
    )
    assert len(response.t) == MAX_SIM_SAMPLES
    assert len(response.x) == MAX_SIM_SAMPLES
    assert len(response.u) == MAX_SIM_SAMPLES
    assert _CAPPED_WARNING in response.warnings


def test_no_exec_eval_or_subprocess():
    plant = PlantPayload(
        system_name="evil",
        python_code="eval('1+1'); exec('pass')",
    )
    with patch("builtins.exec") as mocked_exec:
        with patch("builtins.eval") as mocked_eval:
            with patch("subprocess.run") as mocked_run:
                with patch("subprocess.Popen") as mocked_popen:
                    generate_mock_trajectory(_req(plant=plant, input_type="sine"))
    mocked_exec.assert_not_called()
    mocked_eval.assert_not_called()
    mocked_run.assert_not_called()
    mocked_popen.assert_not_called()
