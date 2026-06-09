from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from backend.app.models.error import ProblemDetail

logger = logging.getLogger(__name__)


def _cors_headers(request: Request) -> dict[str, str]:
    """CORS headers for an error response that honour the configured allowlist.

    Echo the request Origin only when it is actually allowed (or a wildcard is
    configured); never reflect an arbitrary origin together with
    Access-Control-Allow-Credentials, which would defeat the allowlist.
    """
    # Imported lazily to avoid a circular import (main imports this module).
    from backend.app.main import _cors_allow_credentials, _cors_origins

    origin = request.headers.get("origin")
    if "*" in _cors_origins:
        return {"Access-Control-Allow-Origin": "*"}
    if origin and origin in _cors_origins:
        headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        if _cors_allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"
        return headers
    return {}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Format FastAPI HTTPException as an RFC 7807 application/problem+json response."""
    problem = ProblemDetail(
        title=_status_title(exc.status_code),
        status=exc.status_code,
        detail=str(exc.detail),
        instance=str(request.url),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(),
        headers={"Content-Type": "application/problem+json"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 RFC 7807 response for any unhandled exception."""
    logger.error("Unhandled exception at %s: %s", request.url, exc, exc_info=True)
    problem = ProblemDetail(
        title="Internal Server Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
        instance=str(request.url),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=problem.model_dump(),
        headers={
            "Content-Type": "application/problem+json",
            **_cors_headers(request),
        },
    )


def _status_title(status_code: int) -> str:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }
    return titles.get(status_code, "Unknown Error")
