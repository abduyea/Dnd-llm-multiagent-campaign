from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.ollama_client import (
    _call_ollama,
    _static_fallback,
    _strip_think_tags,
    generate,
    generate_stream,
)


class TestStripThinkTags:
    def test_strips_single_think_block(self) -> None:
        result = _strip_think_tags("<think>I should narrate this.</think>The goblin falls.")
        assert result == "The goblin falls."
        assert "<think>" not in result

    def test_strips_multiline_think_block(self) -> None:
        raw = "<think>\nReasoning line 1\nReasoning line 2\n</think>Narration here."
        result = _strip_think_tags(raw)
        assert "Reasoning" not in result
        assert "Narration here." in result

    def test_no_think_block_unchanged(self) -> None:
        text = "The dragon roars and breathes fire."
        assert _strip_think_tags(text) == text

    def test_strips_leading_whitespace_after_think(self) -> None:
        result = _strip_think_tags("<think>reason</think>\n\nThe outcome.")
        assert result == "The outcome."

    def test_empty_string(self) -> None:
        assert _strip_think_tags("") == ""

    def test_think_block_with_nested_content(self) -> None:
        raw = "<think>step 1: think\nstep 2: more thinking</think>Real narration."
        result = _strip_think_tags(raw)
        assert result == "Real narration."


class TestGenerateStripsThinkTags:
    def test_generate_strips_think_tags_from_model_output(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "<think>My reasoning</think>The axe bites deep."
        }

        mock_http_client = MagicMock()
        mock_http_client.post.return_value = mock_response

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_http_client
            mock_client_cls.return_value.__exit__.return_value = False

            result = _call_ollama(model="qwen3", prompt="test", timeout=5)

        assert result == "The axe bites deep."
        assert "<think>" not in (result or "")


class TestGenerateStreamThinkStripping:
    @pytest.mark.asyncio
    async def test_stream_strips_think_block_before_narration(self) -> None:
        import json

        async def fake_aiter_lines():  # type: ignore[return]
            yield json.dumps({"response": "<think>I should attack", "done": False})
            yield json.dumps({"response": " the goblin.</think>", "done": False})
            yield json.dumps({"response": "The blade ", "done": False})
            yield json.dumps({"response": "finds its mark.", "done": False})
            yield json.dumps({"response": "", "done": True})

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = fake_aiter_lines
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate_stream("test prompt")]

        full = "".join(tokens)
        assert "<think>" not in full
        assert "think" not in full.lower() or "The blade" in full
        assert "The blade" in full
        assert "finds its mark." in full

    @pytest.mark.asyncio
    async def test_stream_no_think_block_yields_normally(self) -> None:
        import json

        async def fake_aiter_lines():  # type: ignore[return]
            for token in ["The ", "dragon ", "roars."]:
                yield json.dumps({"response": token, "done": False})
            yield json.dumps({"response": "", "done": True})

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = fake_aiter_lines
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate_stream("test prompt")]

        assert "".join(tokens) == "The dragon roars."


class TestStaticFallback:
    def test_static_fallback_output(self) -> None:
        result = _static_fallback("attack the goblin")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_static_fallback_empty_action(self) -> None:
        result = _static_fallback("")
        assert isinstance(result, str)
        assert len(result) > 10

    def test_static_fallback_is_deterministic(self) -> None:
        assert _static_fallback("test") == _static_fallback("test")

    def test_static_fallback_varies_by_input(self) -> None:
        results = {_static_fallback(f"action {i}") for i in range(10)}
        assert len(results) > 1


class TestGenerate:
    def test_generate_returns_static_fallback_when_all_models_fail(self) -> None:
        with patch("backend.app.services.ollama_client._call_ollama", return_value=None):
            result = generate(
                prompt="test prompt",
                system_prompt="test system",
                action_text="test action",
            )
            assert isinstance(result, str)
            assert len(result) > 20

    def test_generate_returns_first_successful_model(self) -> None:
        call_count = 0

        def mock_call(model: str, **kwargs: object) -> str | None:
            nonlocal call_count
            call_count += 1
            if model == "qwen3":
                return "qwen3 response"
            return None

        with patch("backend.app.services.ollama_client._call_ollama", side_effect=mock_call):
            result = generate(prompt="test")
            assert result == "qwen3 response"

    def test_generate_falls_through_on_first_model_failure(self) -> None:
        call_count = 0

        def mock_call(model: str, **kwargs: object) -> str | None:
            nonlocal call_count
            call_count += 1
            if model == "mistral-nemo":
                return "mistral response"
            return None

        with patch("backend.app.services.ollama_client._call_ollama", side_effect=mock_call):
            result = generate(prompt="test")
            assert result == "mistral response"

    def test_generate_uses_all_three_models_before_fallback(self) -> None:
        results: list[str] = []

        def mock_call(model: str, **kwargs: object) -> str | None:
            results.append(model)
            return None

        with patch("backend.app.services.ollama_client._call_ollama", side_effect=mock_call):
            result = generate(prompt="test", action_text="final")
            assert result == _static_fallback("final")
            assert results == ["qwen3", "mistral-nemo", "llama3.2:3b"]


class TestCallOllama:
    def test_call_ollama_returns_none_on_connection_error(self) -> None:
        result = _call_ollama(
            model="nonexistent-model",
            prompt="test",
            timeout=1,
        )
        assert result is None

    def test_call_ollama_success_with_system_prompt(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "The goblin falls!"}

        mock_http_client = MagicMock()
        mock_http_client.post.return_value = mock_response

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_http_client
            mock_client_cls.return_value.__exit__.return_value = False

            result = _call_ollama(
                model="qwen3",
                prompt="What happens?",
                system_prompt="You are a Dungeon Master.",
                timeout=5,
            )

        assert result == "The goblin falls!"

    def test_call_ollama_non_string_response_returns_empty(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": 42}

        mock_http_client = MagicMock()
        mock_http_client.post.return_value = mock_response

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_http_client
            mock_client_cls.return_value.__exit__.return_value = False

            result = _call_ollama(model="qwen3", prompt="test", timeout=5)

        assert result == ""

    def test_is_ollama_available_returns_true_when_reachable(self) -> None:
        from backend.app.services.ollama_client import is_ollama_available

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_http_client = MagicMock()
        mock_http_client.get.return_value = mock_resp

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_http_client
            mock_client_cls.return_value.__exit__.return_value = False

            result = is_ollama_available()

        assert result is True

    def test_is_ollama_available_returns_false_on_error(self) -> None:
        import httpx

        from backend.app.services.ollama_client import is_ollama_available

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__exit__.return_value = False

            result = is_ollama_available()

        assert result is False


class TestGenerateStream:
    """Tests for the async generate_stream generator."""

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens_from_model(self) -> None:
        """Tokens from a successful model are yielded and the generator stops."""
        import json

        async def fake_aiter_lines():  # type: ignore[return]
            for token in ["The ", "dragon ", "roars."]:
                yield json.dumps({"response": token, "done": False})
            yield json.dumps({"response": "", "done": True})

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = fake_aiter_lines
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate_stream("test prompt")]

        assert tokens == ["The ", "dragon ", "roars."]

    @pytest.mark.asyncio
    async def test_generate_stream_falls_back_to_static_on_all_failures(self) -> None:
        """If all models raise, static fallback text is yielded word-by-word."""
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(side_effect=_httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate_stream("test", action_text="stab the goblin")]

        full = "".join(tokens)
        assert len(full) > 20

    @pytest.mark.asyncio
    async def test_generate_stream_skips_empty_response_fields(self) -> None:
        """Lines with empty ``response`` values are silently skipped."""
        import json

        async def fake_aiter_lines():  # type: ignore[return]
            yield json.dumps({"response": "", "done": False})
            yield json.dumps({"response": "Hello", "done": False})
            yield json.dumps({"response": "", "done": True})

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = fake_aiter_lines
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate_stream("p")]

        assert tokens == ["Hello"]
