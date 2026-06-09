"""Tests for environment-driven configuration helpers added for tunability."""
from __future__ import annotations

import pytest

from backend.app.main import _cors_settings
from backend.app.services.ollama_client import (
    CONNECT_TIMEOUT,
    _parse_secondary_models,
    _timeout,
)


class TestCorsSettings:
    def test_default_origins_allow_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        origins, allow_credentials = _cors_settings()
        assert "http://localhost:3000" in origins
        assert allow_credentials is True

    def test_explicit_list_is_parsed_and_trimmed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CORS_ORIGINS", " https://a.example , https://b.example ")
        origins, allow_credentials = _cors_settings()
        assert origins == ["https://a.example", "https://b.example"]
        assert allow_credentials is True

    def test_wildcard_disables_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A wildcard origin cannot be combined with credentials per the CORS spec.
        monkeypatch.setenv("CORS_ORIGINS", "*")
        origins, allow_credentials = _cors_settings()
        assert origins == ["*"]
        assert allow_credentials is False


class TestFallbackModelParsing:
    def test_default_chain_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_FALLBACK_MODELS", raising=False)
        assert _parse_secondary_models() == ["qwen3", "mistral-nemo"]

    def test_override_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_FALLBACK_MODELS", "modelA, modelB ,modelC")
        assert _parse_secondary_models() == ["modelA", "modelB", "modelC"]

    def test_empty_disables_fallbacks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_FALLBACK_MODELS", "")
        assert _parse_secondary_models() == []


class TestTimeoutHelper:
    def test_connect_phase_is_bounded(self) -> None:
        timeout = _timeout(60.0)
        assert timeout.connect == CONNECT_TIMEOUT
        assert timeout.read == 60.0
