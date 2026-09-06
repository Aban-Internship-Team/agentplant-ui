"""Central HTTP error envelope for AgentPlant.

All error responses are a top-level ``ErrorBody`` JSON object. Routes keep
raising ``HTTPException``; these handlers only reshape the wire format.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend_api.AgentPlant.schemas import ErrorBody

logger = logging.getLogger(__name__)

_SAFE_FAILED = "Request failed"


def error_response(
    status: int,
    *,
    message: str,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> JSONResponse:
    """Return ``ErrorBody`` as the top-level JSON object (no ``detail`` wrapper)."""
    body = ErrorBody(
        message=message,
        errors=list(errors or []),
        warnings=list(warnings or []),
    )
    return JSONResponse(status_code=status, content=body.model_dump())


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def envelope_from_http_detail(detail: object) -> ErrorBody:
    """Map an ``HTTPException.detail`` to ``ErrorBody``. Unknown shapes fail closed."""
    if isinstance(detail, str):
        text = detail.strip()
        if not text:
            return ErrorBody(message=_SAFE_FAILED, errors=[_SAFE_FAILED], warnings=[])
        return ErrorBody(message=text, errors=[text], warnings=[])
    if isinstance(detail, dict):
        message = detail.get("message")
        errors = _string_list(detail.get("errors"))
        warnings_raw = detail.get("warnings", [])
        warnings = _string_list(warnings_raw)
        if isinstance(message, str) and message and errors is not None and warnings is not None:
            return ErrorBody(message=message, errors=errors, warnings=warnings)
    return ErrorBody(message=_SAFE_FAILED, errors=[_SAFE_FAILED], warnings=[])


def flatten_validation_errors(exc: RequestValidationError) -> list[str]:
    """Keep loc + msg only. Never include raw ``input`` values."""
    lines: list[str] = []
    for item in exc.errors():
        msg = item.get("msg")
        if not isinstance(msg, str) or not msg.strip():
            msg = "Invalid value"
        loc = item.get("loc")
        if loc:
            location = ".".join(str(part) for part in loc)
        else:
            location = "request"
        lines.append(f"{location}: {msg}")
    return lines or ["request: Invalid request"]


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return error_response(
        422,
        message="Request validation failed",
        errors=flatten_validation_errors(exc),
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    body = envelope_from_http_detail(exc.detail)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return error_response(
        500,
        message="Internal server error",
        errors=["An unexpected error occurred"],
    )


def register_exception_handlers(app: Any) -> None:
    """Attach envelope handlers. Register the generic handler last."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
