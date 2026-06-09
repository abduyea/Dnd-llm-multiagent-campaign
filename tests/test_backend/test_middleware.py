from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from backend.app.middleware.error_handler import unhandled_exception_handler


def _request_with_origin(origin: str | None) -> Request:
    """Build a minimal Starlette Request carrying an Origin header."""
    headers: list[tuple[bytes, bytes]] = []
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/test",
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)


class TestUnhandledExceptionHandler:
    @pytest.mark.asyncio
    async def test_returns_500_status(self) -> None:
        mock_request = MagicMock()
        mock_request.url = "http://localhost/api/v1/test"

        response = await unhandled_exception_handler(mock_request, RuntimeError("unexpected"))

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_response_body_is_problem_json(self) -> None:
        mock_request = MagicMock()
        mock_request.url = "http://localhost/api/v1/campaigns"

        response = await unhandled_exception_handler(mock_request, ValueError("db exploded"))

        body = json.loads(response.body)
        assert body["status"] == 500
        assert body["title"] == "Internal Server Error"
        assert body["detail"] == "An unexpected error occurred"
        assert "localhost" in body["instance"]

    @pytest.mark.asyncio
    async def test_content_type_header(self) -> None:
        mock_request = MagicMock()
        mock_request.url = "http://localhost/"

        response = await unhandled_exception_handler(mock_request, Exception("any error"))

        assert response.headers.get("content-type") == "application/problem+json"


class TestErrorHandlerCors:
    @pytest.mark.asyncio
    async def test_allowed_origin_is_reflected(self) -> None:
        request = _request_with_origin("http://localhost:3000")
        response = await unhandled_exception_handler(request, RuntimeError("boom"))
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_disallowed_origin_is_not_reflected(self) -> None:
        # A disallowed origin must not be echoed back with credentials — that would
        # defeat the CORS allowlist.
        request = _request_with_origin("http://evil.example")
        response = await unhandled_exception_handler(request, RuntimeError("boom"))
        assert response.headers.get("access-control-allow-origin") is None
        assert response.headers.get("access-control-allow-credentials") is None
