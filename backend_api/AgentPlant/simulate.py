"""Open-loop simulate: A6 mock fallback and A7 sandboxed dynamics.

No-plant requests keep the deterministic A6 mock. A supplied plant is executed
only in the A7 subprocess worker — never in this process.
"""

from __future__ import annotations

import math

from backend_api.AgentPlant.sandbox import run_sandboxed_trajectory
from backend_api.AgentPlant.schemas import PlantPayload, SimulateRequest, SimulateResponse

MAX_SIM_SAMPLES = 5000
_DEFAULT_FREQUENCY_HZ = 0.5
_CAPPED_WARNING = (
    "Sample count was capped; solver_sample_time was increased to stay within the limit."
)


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


def prepare_open_loop(
    request: SimulateRequest,
) -> tuple[list[float], float, list[list[float]], list[str]]:
    """Shared A6/A7 time grid and SISO input series."""
    t_sim = float(request.total_simulation_time)
    dt_req = float(request.solver_sample_time)
    times, dt, warnings = _time_grid(t_sim, dt_req)
    pulse_width = _pulse_width(request.pulse_width, t_sim)
    frequency = _frequency(request.frequency)
    inputs = [
        [
            _input_value(
                stamp,
                input_type=request.input_type,
                amplitude=float(request.amplitude),
                pulse_width=pulse_width,
                frequency=frequency,
            )
        ]
        for stamp in times
    ]
    return times, dt, inputs, warnings


def generate_mock_trajectory(request: SimulateRequest) -> SimulateResponse:
    """Build a deterministic mock timeseries. Never executes ``plant.python_code``."""
    times, dt, inputs, warnings = prepare_open_loop(request)
    if request.initial_state:
        state = [float(value) for value in request.initial_state]
    else:
        state = [0.0]

    x: list[list[float]] = [list(state)]
    for index in range(1, len(times)):
        u_prev = inputs[index - 1][0]
        state[0] = state[0] + dt * (-state[0] + u_prev)
        x.append(list(state))

    return SimulateResponse(t=times, x=x, u=[list(row) for row in inputs], warnings=warnings)


def plant_from_conversation(conversation: object | None) -> PlantPayload | None:
    """Prefer ``latest_draft``, then ``final_result``. Does not require complete."""
    if conversation is None:
        return None
    session = getattr(conversation, "session_state", None)
    draft = getattr(session, "latest_draft", None) if session is not None else None
    if draft is not None and str(getattr(draft, "python_code", "") or "").strip():
        return PlantPayload(
            system_name=draft.system_name,
            python_code=draft.python_code,
            metadata=draft.metadata,
        )
    final = getattr(conversation, "final_result", None)
    if final is not None and str(getattr(final, "python_code", "") or "").strip():
        return PlantPayload(
            system_name=final.system_name,
            python_code=final.python_code,
            metadata=final.metadata,
        )
    return None


def _explicit_plant(request: SimulateRequest) -> PlantPayload | None:
    plant = request.plant
    if plant is None or not str(plant.python_code or "").strip():
        return None
    return plant


def run_simulation(
    request: SimulateRequest,
    *,
    resolved_plant: PlantPayload | None = None,
) -> SimulateResponse:
    """A6 mock when no plant; otherwise A7 sandbox. Failures do not fall back."""
    plant = _explicit_plant(request) or resolved_plant
    if plant is None or not str(plant.python_code or "").strip():
        return generate_mock_trajectory(request)

    times, dt, inputs, warnings = prepare_open_loop(request)
    return run_sandboxed_trajectory(
        request,
        plant,
        times=times,
        dt=dt,
        inputs=inputs,
        warnings=warnings,
    )
