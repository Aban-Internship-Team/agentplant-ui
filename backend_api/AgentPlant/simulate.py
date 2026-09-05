"""Deterministic open-loop mock trajectories for POST /simulate (A6).

Does not execute plant code. A7 may sit beside this function later.
"""

from __future__ import annotations

import math

from backend_api.AgentPlant.schemas import SimulateRequest, SimulateResponse

MAX_SIM_SAMPLES = 5000
_DEFAULT_FREQUENCY_HZ = 0.5
_CAPPED_WARNING = (
    "Sample count was capped; solver_sample_time was increased to stay within the limit."
)
_PLANT_IGNORED_WARNING = "Mock simulation does not execute plant code."


def _pulse_width(pulse_width: float | None, t_sim: float) -> float:
    if pulse_width is None or pulse_width <= 0:
        return min(1.0, t_sim)
    return float(pulse_width)


def _frequency(frequency: float | None) -> float:
    if frequency is None or frequency <= 0:
        return _DEFAULT_FREQUENCY_HZ
    return float(frequency)


def _input_value(
    t: float,
    *,
    input_type: str,
    amplitude: float,
    pulse_width: float,
    frequency: float,
) -> float:
    if input_type == "pulse":
        return amplitude if t < pulse_width else 0.0
    if input_type == "sine":
        return amplitude * math.sin(2.0 * math.pi * frequency * t)
    return amplitude


def _time_grid(t_sim: float, dt: float) -> tuple[list[float], float, list[str]]:
    """Return (t, euler_dt, warnings). Always includes t=0."""
    if dt > t_sim:
        return [0.0, t_sim], t_sim, []

    n = math.floor(t_sim / dt) + 1
    if n > MAX_SIM_SAMPLES:
        n = MAX_SIM_SAMPLES
        dt_eff = t_sim / (n - 1)
        times = [i * dt_eff for i in range(n)]
        return times, dt_eff, [_CAPPED_WARNING]

    return [i * dt for i in range(n)], dt, []


def generate_mock_trajectory(request: SimulateRequest) -> SimulateResponse:
    """Build a deterministic mock timeseries. Never executes ``plant.python_code``."""
    t_sim = float(request.total_simulation_time)
    dt_req = float(request.solver_sample_time)
    times, dt, warnings = _time_grid(t_sim, dt_req)
    if request.plant is not None:
        warnings.append(_PLANT_IGNORED_WARNING)

    amplitude = float(request.amplitude)
    pulse_width = _pulse_width(request.pulse_width, t_sim)
    frequency = _frequency(request.frequency)
    input_type = request.input_type

    if request.initial_state:
        state = [float(value) for value in request.initial_state]
    else:
        state = [0.0]

    x: list[list[float]] = [list(state)]
    u: list[list[float]] = [
        [
            _input_value(
                times[0],
                input_type=input_type,
                amplitude=amplitude,
                pulse_width=pulse_width,
                frequency=frequency,
            )
        ]
    ]

    for index in range(1, len(times)):
        u_prev = u[-1][0]
        state[0] = state[0] + dt * (-state[0] + u_prev)
        x.append(list(state))
        u.append(
            [
                _input_value(
                    times[index],
                    input_type=input_type,
                    amplitude=amplitude,
                    pulse_width=pulse_width,
                    frequency=frequency,
                )
            ]
        )

    return SimulateResponse(t=times, x=x, u=u, warnings=warnings)
