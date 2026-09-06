"""Restricted plant-dynamics execution for A7.

Isolation model (honest):
    AST allowlist + short-lived subprocess + wall-clock timeout.
    This is development/demo isolation and validation, NOT a true
    security boundary. The child runs as the same OS user and can still
    use that user's filesystem/network privileges if it slips past AST.
    There is no container, VM, or portable memory/CPU cgroup here.

Generated ``plant.python_code`` is never executed in the API process.
"""

from __future__ import annotations

import os
import sys

# Shared with the parent validator. Defined here so the worker process can
# enforce them before any oversized allocation of *our* state vector.
MAX_STATE_DIM = 32
MAX_SOURCE_BYTES = 50 * 1024
MAX_INPUT_DIM = 8
MAX_STDOUT_BYTES = 5 * 1024 * 1024
SANDBOX_TIMEOUT_SEC = 2.0


def _worker_main() -> None:
    """Child-only entry. Imports stay minimal; no FastAPI / store / keys."""
    import json
    import math

    import numpy as np

    try:
        raw = sys.stdin.buffer.read()
        job = json.loads(raw.decode("utf-8"))
        source = job["source"]
        times = [float(v) for v in job["t"]]
        dt = float(job["dt"])
        inputs = job["u"]
        x0 = [float(v) for v in job["x0"]]
        nx_hint = job.get("nx_hint")
    except Exception as exc:  # noqa: BLE001 — worker reports typed failure
        _worker_fail("output", f"invalid worker input: {exc}")
        return

    namespace: dict[str, object] = {
        "np": np,
        "numpy": np,
        "math": math,
        "__builtins__": {
            "abs": abs,
            "min": min,
            "max": max,
            "float": float,
            "int": int,
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "list": list,
            "tuple": tuple,
            "bool": bool,
            "sum": sum,
            "pow": pow,
            "round": round,
            "isinstance": isinstance,
            "hasattr": hasattr,
            "__import__": __import__,
            "True": True,
            "False": False,
            "None": None,
        },
    }
    try:
        exec(source, namespace, namespace)  # noqa: S102 — child process only
    except Exception as exc:  # noqa: BLE001
        _worker_fail("dynamics", f"executing dynamics failed: {exc}")
        return

    fn = namespace.get("dynamics")
    if not callable(fn):
        _worker_fail("dynamics", "python_code must define dynamics(t, x, u)")
        return

    try:
        state = np.asarray(x0, dtype=float).reshape(-1)
        if int(state.size) > MAX_STATE_DIM:
            raise ValueError(f"state dimension {int(state.size)} exceeds {MAX_STATE_DIM}")
        nx = int(nx_hint) if nx_hint is not None else None
        if nx is not None:
            if nx > MAX_STATE_DIM:
                raise ValueError(f"state dimension {nx} exceeds {MAX_STATE_DIM}")
            if state.size == 1 and nx > 1 and float(state[0]) == 0.0:
                state = np.zeros(nx, dtype=float)
            elif int(state.size) != nx:
                raise ValueError("initial_state length does not match the plant dimension")
        u0 = np.atleast_1d(np.asarray(inputs[0], dtype=float).reshape(-1))
        dx0 = _as_finite_vector(fn(float(times[0]), state, u0), nx)
        if nx is None:
            nx = int(dx0.size)
            if nx > MAX_STATE_DIM:
                raise ValueError(f"state dimension {nx} exceeds {MAX_STATE_DIM}")
            if state.size == 1 and nx > 1 and float(state[0]) == 0.0:
                state = np.zeros(nx, dtype=float)
            elif int(state.size) != nx:
                raise ValueError("initial_state length does not match dynamics output")
        series: list[list[float]] = [state.astype(float).tolist()]

        for index in range(1, len(times)):
            t_prev = float(times[index - 1])
            u_prev = np.atleast_1d(np.asarray(inputs[index - 1], dtype=float).reshape(-1))
            dx = _as_finite_vector(fn(t_prev, state, u_prev), nx)
            state = state + dt * dx
            if not np.all(np.isfinite(state)):
                raise ValueError("non-finite state after Euler step")
            series.append(state.astype(float).tolist())

        sys.stdout.write(json.dumps({"ok": True, "x": series}, allow_nan=False))
    except Exception as exc:  # noqa: BLE001
        _worker_fail("dynamics", str(exc))


def _as_finite_vector(value: object, nx: int | None):
    import numpy as np

    if np.isscalar(value):
        arr = np.asarray([value], dtype=float).reshape(-1)
    else:
        arr = np.asarray(value, dtype=float).reshape(-1)
    if int(arr.size) > MAX_STATE_DIM:
        raise ValueError(f"state dimension {int(arr.size)} exceeds {MAX_STATE_DIM}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("dynamics returned non-finite values")
    if nx is not None and int(arr.size) != nx:
        raise ValueError(f"dynamics returned shape ({int(arr.size)},), expected ({nx},)")
    if nx is None and arr.size < 1:
        raise ValueError("dynamics returned an empty derivative")
    return arr


def _worker_fail(kind: str, message: str) -> None:
    import json

    sys.stdout.write(json.dumps({"ok": False, "error": kind, "message": message}))


if __name__ == "__main__" and os.environ.get("AGENTPLANT_SANDBOX_WORKER") == "1":
    _worker_main()
    raise SystemExit(0)


import ast
import json
import subprocess
from pathlib import Path
from typing import Any

from backend_api.AgentPlant.schemas import PlantPayload, SimulateRequest, SimulateResponse

_ALLOWED_MODULES = frozenset({"numpy", "math"})
_ALLOWED_NUMPY_ATTRS = frozenset(
    {
        "array",
        "asarray",
        "asanyarray",
        "atleast_1d",
        "atleast_2d",
        "zeros",
        "ones",
        "full",
        "sin",
        "cos",
        "tan",
        "arcsin",
        "arccos",
        "arctan",
        "arctan2",
        "sinh",
        "cosh",
        "tanh",
        "exp",
        "expm1",
        "log",
        "log10",
        "log2",
        "log1p",
        "sqrt",
        "square",
        "cbrt",
        "power",
        "abs",
        "absolute",
        "fabs",
        "sign",
        "clip",
        "minimum",
        "maximum",
        "dot",
        "inner",
        "vdot",
        "sum",
        "prod",
        "mean",
        "where",
        "reshape",
        "transpose",
        "hypot",
        "floor",
        "ceil",
        "rint",
        "mod",
        "remainder",
        "deg2rad",
        "rad2deg",
        "pi",
        "e",
    }
)
_ALLOWED_MATH_ATTRS = frozenset(
    {
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "sinh",
        "cosh",
        "tanh",
        "exp",
        "log",
        "log10",
        "sqrt",
        "pow",
        "hypot",
        "degrees",
        "radians",
        "floor",
        "ceil",
        "fabs",
        "pi",
        "e",
        "copysign",
    }
)
_DENIED_NUMPY_ATTRS = frozenset(
    {
        "loadtxt",
        "savetxt",
        "save",
        "savez",
        "savez_compressed",
        "load",
        "fromfile",
        "tofile",
        "memmap",
        "ctypeslib",
        "lib",
        "testing",
        "f2py",
        "frombuffer",
        "fromstring",
        "fromregex",
        "genfromtxt",
        "DataSource",
    }
)
_ALLOWED_CALL_NAMES = frozenset(
    {
        "abs",
        "min",
        "max",
        "float",
        "int",
        "len",
        "range",
        "enumerate",
        "zip",
        "list",
        "tuple",
        "bool",
        "sum",
        "pow",
        "round",
        "isinstance",
        "hasattr",
    }
)
_DENIED_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "__import__",
        "breakpoint",
        "exit",
        "quit",
        "help",
        "memoryview",
        "bytearray",
        "print",
        "type",
        "super",
        "classmethod",
        "staticmethod",
        "property",
        "object",
    }
)
_ALLOWED_STMT = (
    ast.FunctionDef,
    ast.Return,
    ast.Assign,
    ast.AugAssign,
    ast.For,
    ast.While,
    ast.If,
    ast.Break,
    ast.Continue,
    ast.Raise,
    ast.Assert,
    ast.Pass,
    ast.Expr,
    ast.Import,
    ast.ImportFrom,
)
_ALLOWED_EXPR = (
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Compare,
    ast.Call,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.Name,
    ast.List,
    ast.Tuple,
    ast.Slice,
    ast.ListComp,
    ast.comprehension,
    ast.keyword,
    ast.Load,
    ast.Store,
    ast.Del,
    ast.And,
    ast.Or,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.MatMult,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.BitAnd,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.Invert,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)


class SandboxRejected(Exception):
    """Source failed the AST allowlist or size limit."""


class SandboxSyntaxError(Exception):
    """Generated source is not valid Python."""


class SandboxDynamicsError(Exception):
    """dynamics() is missing, mis-shaped, or raised."""


class SandboxTimeout(Exception):
    """Child exceeded the wall-clock timeout and was killed."""


class SandboxOutputError(Exception):
    """Child stdout was missing, oversized, or not valid result JSON."""


class _Bindings:
    """Names bound to the numpy/math modules or allowlisted symbols."""

    def __init__(self) -> None:
        self.numpy_modules: set[str] = set()
        self.math_modules: set[str] = set()
        self.numpy_symbols: set[str] = set()
        self.math_symbols: set[str] = set()


def _module_allowed(name: str | None) -> bool:
    return name in _ALLOWED_MODULES


def _reject(message: str) -> None:
    raise SandboxRejected(message)


def validate_plant_source(source: str) -> None:
    """Fail-closed AST allowlist. Does not execute the source."""
    if not isinstance(source, str) or not source.strip():
        _reject("python_code is empty")
    encoded = source.encode("utf-8")
    if len(encoded) > MAX_SOURCE_BYTES:
        _reject(f"python_code exceeds {MAX_SOURCE_BYTES} bytes")
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise SandboxSyntaxError(f"invalid python_code: {exc.msg}") from exc

    dynamics_defs = 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            dynamics_defs += 1
            if node.name != "dynamics":
                _reject("only a dynamics(t, x, u) function may be defined")
            _validate_dynamics_def(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            _validate_import(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        else:
            _reject(f"disallowed top-level construct: {type(node).__name__}")
    if dynamics_defs != 1:
        _reject("python_code must define exactly one dynamics(t, x, u) function")
    bindings = _collect_bindings(tree)
    _walk_allowed(tree, bindings)


def _collect_bindings(tree: ast.AST) -> _Bindings:
    bindings = _Bindings()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name
                if alias.name == "numpy":
                    bindings.numpy_modules.add(bound)
                elif alias.name == "math":
                    bindings.math_modules.add(bound)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                if node.module == "numpy":
                    bindings.numpy_symbols.add(bound)
                elif node.module == "math":
                    bindings.math_symbols.add(bound)
    return bindings


def _validate_import(node: ast.AST) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if not _module_allowed(alias.name):
                _reject(f"import of {alias.name!r} is not allowed")
            if alias.asname and alias.asname.startswith("_"):
                _reject("import aliases must not start with '_'")
        return
    if isinstance(node, ast.ImportFrom):
        if node.level:
            _reject("relative imports are not allowed")
        if not _module_allowed(node.module):
            _reject(f"import from {node.module!r} is not allowed")
        for alias in node.names:
            if alias.name == "*":
                _reject("star imports are not allowed")
            if alias.name.startswith("_") or (alias.asname and alias.asname.startswith("_")):
                _reject("imports must not use private names")
            if node.module == "numpy":
                if alias.name in _DENIED_NUMPY_ATTRS or alias.name not in _ALLOWED_NUMPY_ATTRS:
                    _reject(f"from numpy import {alias.name!r} is not allowed")
            elif node.module == "math":
                if alias.name not in _ALLOWED_MATH_ATTRS:
                    _reject(f"from math import {alias.name!r} is not allowed")
        return
    _reject("invalid import")


def _validate_dynamics_def(node: ast.FunctionDef) -> None:
    if node.decorator_list:
        _reject("decorators are not allowed")
    if getattr(node, "type_params", None):
        _reject("type parameters are not allowed")
    args = node.args
    names = [arg.arg for arg in args.posonlyargs] + [arg.arg for arg in args.args]
    if names != ["t", "x", "u"] or args.vararg or args.kwarg or args.kwonlyargs:
        _reject("dynamics must be defined as dynamics(t, x, u)")
    if args.defaults or args.kw_defaults:
        _reject("dynamics must not use argument defaults")
    for arg in list(args.posonlyargs) + list(args.args):
        if arg.annotation is not None and not isinstance(
            arg.annotation, (ast.Name, ast.Constant)
        ):
            _reject("unsupported argument annotation")


def _walk_allowed(node: ast.AST, bindings: _Bindings) -> None:
    if isinstance(node, ast.Module):
        for child in node.body:
            _walk_allowed(child, bindings)
        return
    if isinstance(node, ast.FunctionDef):
        for child in node.body:
            _walk_allowed(child, bindings)
        for arg in node.args.args + node.args.posonlyargs:
            if arg.annotation is not None:
                _walk_allowed(arg.annotation, bindings)
        if node.returns is not None:
            _walk_allowed(node.returns, bindings)
        return
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        _validate_import(node)
        return
    if type(node) not in _ALLOWED_STMT + _ALLOWED_EXPR:
        _reject(f"disallowed construct: {type(node).__name__}")
    if isinstance(node, ast.Name):
        if node.id.startswith("__") or node.id in _DENIED_NAMES:
            _reject(f"use of {node.id!r} is not allowed")
    if isinstance(node, ast.Attribute):
        _validate_attribute(node, bindings)
    if isinstance(node, ast.Call):
        _validate_call(node, bindings)
    for child in ast.iter_child_nodes(node):
        _walk_allowed(child, bindings)


def _validate_attribute(node: ast.Attribute, bindings: _Bindings) -> None:
    if node.attr.startswith("_"):
        _reject("private or dunder attribute access is not allowed")
    if isinstance(node.value, (ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set)):
        _reject("attribute access on literals is not allowed")
    if isinstance(node.value, ast.Attribute):
        _reject("nested attribute access is not allowed")
    if not isinstance(node.value, ast.Name):
        _reject("attribute access is only allowed on numpy or math")
    owner = node.value.id
    if owner in bindings.numpy_modules:
        if node.attr in _DENIED_NUMPY_ATTRS or node.attr not in _ALLOWED_NUMPY_ATTRS:
            _reject(f"numpy.{node.attr} is not allowed")
        return
    if owner in bindings.math_modules:
        if node.attr not in _ALLOWED_MATH_ATTRS:
            _reject(f"math.{node.attr} is not allowed")
        return
    _reject(f"attribute {node.attr!r} is not allowed on {owner!r}")


def _validate_call(node: ast.Call, bindings: _Bindings) -> None:
    if node.keywords and any(item.arg is None for item in node.keywords):
        _reject("**kwargs calls are not allowed")
    if any(isinstance(arg, ast.Starred) for arg in node.args):
        _reject("*args calls are not allowed")
    func = node.func
    if isinstance(func, ast.Name):
        if func.id in _ALLOWED_CALL_NAMES:
            return
        if func.id in bindings.numpy_symbols or func.id in bindings.math_symbols:
            return
        _reject(f"call to {func.id!r} is not allowed")
    if isinstance(func, ast.Attribute):
        return
    _reject("unsupported call target")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _child_env() -> dict[str, str]:
    keep = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "TMP",
        "TEMP",
    )
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["AGENTPLANT_SANDBOX_WORKER"] = "1"
    env["PYTHONPATH"] = str(_repo_root())
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _finite_matrix(rows: Any, *, width: int, name: str) -> list[list[float]]:
    if not isinstance(rows, list) or not rows:
        raise SandboxOutputError(f"{name} must be a non-empty list")
    out: list[list[float]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != width:
            raise SandboxOutputError(f"{name} row width must be {width}")
        converted: list[float] = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SandboxOutputError(f"{name} must contain finite numbers")
            number = float(value)
            if number != number or number in {float("inf"), float("-inf")}:
                raise SandboxOutputError(f"{name} contains non-finite values")
            converted.append(number)
        out.append(converted)
    return out


def _nx_hint(request: SimulateRequest, plant: PlantPayload) -> int | None:
    if request.initial_state:
        hint = len(request.initial_state)
        if hint > MAX_STATE_DIM:
            raise SandboxRejected(f"state dimension {hint} exceeds {MAX_STATE_DIM}")
        return hint
    meta = plant.metadata or {}
    states = meta.get("states")
    if isinstance(states, list) and states:
        hint = len(states)
        if hint > MAX_STATE_DIM:
            raise SandboxRejected(f"state dimension {hint} exceeds {MAX_STATE_DIM}")
        return hint
    return None


def run_sandboxed_trajectory(
    request: SimulateRequest,
    plant: PlantPayload,
    *,
    times: list[float],
    dt: float,
    inputs: list[list[float]],
    warnings: list[str],
) -> SimulateResponse:
    """Validate source, run Euler in a child process, and check the result."""
    source = plant.python_code
    validate_plant_source(source)
    if len(times) != len(inputs) or not times:
        raise SandboxDynamicsError("internal grid/input length mismatch")
    if any(len(row) > MAX_INPUT_DIM for row in inputs):
        raise SandboxRejected(f"input dimension exceeds {MAX_INPUT_DIM}")
    if any(len(row) != 1 for row in inputs):
        raise SandboxDynamicsError("A6/A7 public simulate path is SISO (u = [u_k])")

    if request.initial_state:
        x0 = [float(value) for value in request.initial_state]
    elif _nx_hint(request, plant):
        x0 = [0.0] * int(_nx_hint(request, plant) or 1)
    else:
        x0 = [0.0]
    if len(x0) > MAX_STATE_DIM:
        raise SandboxRejected(f"state dimension {len(x0)} exceeds {MAX_STATE_DIM}")

    payload = {
        "source": source,
        "t": times,
        "dt": dt,
        "u": inputs,
        "x0": x0,
        "nx_hint": _nx_hint(request, plant),
    }
    blob = json.dumps(payload, allow_nan=False).encode("utf-8")
    if len(blob) > MAX_STDOUT_BYTES:
        raise SandboxRejected("simulation job payload is too large")

    kwargs: dict[str, Any] = {
        "args": [sys.executable, "-u", str(Path(__file__).resolve())],
        "input": blob,
        "capture_output": True,
        "timeout": SANDBOX_TIMEOUT_SEC,
        "shell": False,
        "env": _child_env(),
        "cwd": str(Path(__file__).resolve().parent),
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["close_fds"] = True

    try:
        completed = subprocess.run(**kwargs)
    except subprocess.TimeoutExpired as exc:
        if exc.stdout and len(exc.stdout) > MAX_STDOUT_BYTES:
            raise SandboxOutputError("timed-out worker produced oversized output") from exc
        raise SandboxTimeout(
            f"simulation exceeded {SANDBOX_TIMEOUT_SEC:.0f}s and was terminated"
        ) from exc

    stdout = completed.stdout or b""
    if len(stdout) > MAX_STDOUT_BYTES:
        raise SandboxOutputError("worker output exceeds the size limit")
    if completed.returncode != 0 and not stdout.strip():
        stderr = (completed.stderr or b"")[:500].decode("utf-8", errors="replace")
        raise SandboxOutputError(f"worker exited with status {completed.returncode}: {stderr}")

    try:
        body = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SandboxOutputError("worker did not return valid JSON") from exc
    if not isinstance(body, dict):
        raise SandboxOutputError("worker JSON must be an object")
    if body.get("ok") is not True:
        kind = str(body.get("error") or "dynamics")
        message = str(body.get("message") or "sandbox execution failed")
        if kind == "output":
            raise SandboxOutputError(message)
        raise SandboxDynamicsError(message)

    raw_x = body.get("x")
    if not isinstance(raw_x, list):
        raise SandboxOutputError("worker result is missing x")
    if len(raw_x) != len(times):
        raise SandboxOutputError("worker x length does not match the time grid")
    width = len(x0)
    if raw_x and isinstance(raw_x[0], list):
        width = len(raw_x[0])
    if width > MAX_STATE_DIM:
        raise SandboxRejected(f"state dimension {width} exceeds {MAX_STATE_DIM}")
    x = _finite_matrix(raw_x, width=width, name="x")
    if request.initial_state and x[0] != [float(v) for v in request.initial_state]:
        raise SandboxOutputError("worker did not preserve the initial state")
    return SimulateResponse(t=list(times), x=x, u=[list(row) for row in inputs], warnings=list(warnings))
