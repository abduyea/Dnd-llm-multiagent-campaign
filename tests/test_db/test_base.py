from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.db.base import get_db


def _make_mock_session_factory(mock_session: AsyncMock) -> MagicMock:
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False
    return MagicMock(return_value=mock_cm)


class TestGetDb:
    @pytest.mark.asyncio
    async def test_happy_path_commits_and_closes(self) -> None:
        mock_session = AsyncMock()
        mock_factory = _make_mock_session_factory(mock_session)

        with patch("backend.app.db.base.async_session_factory", mock_factory):
            async for session in get_db():
                assert session is mock_session

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_path_rolls_back_and_closes(self) -> None:
        mock_session = AsyncMock()
        mock_factory = _make_mock_session_factory(mock_session)

        with patch("backend.app.db.base.async_session_factory", mock_factory):
            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session

            with pytest.raises(ValueError):
                await gen.athrow(ValueError("simulated db error"))

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()
