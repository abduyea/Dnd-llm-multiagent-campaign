from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from backend.app.middleware.error_handler import unhandled_exception_handler


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
