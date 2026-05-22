import pytest

from backend.app.db.chroma import (
    delete_collection,
    reset,
    retrieve,
    store_summary,
)


@pytest.fixture(autouse=True)
def setup_chroma():
    reset()
    yield
    reset()


def test_store_and_retrieve_summary():
    store_summary(
        summary_id="test-1",
        text="The party fought a dragon in the cavern.",
        session_id="session-1",
        scene_number=3,
        campaign_id="campaign-1",
    )
    store_summary(
        summary_id="test-2",
        text="Thorn negotiated with the innkeeper for a room.",
        session_id="session-1",
        scene_number=1,
        campaign_id="campaign-1",
    )

    results = retrieve("dragon fight", k=2)
    assert len(results) >= 1
    assert "dragon" in results[0].text.lower() or "fought" in results[0].text.lower()


def test_retrieve_with_filter():
    store_summary(
        summary_id="filter-test",
        text="Goblins ambushed the party on the trail.",
        session_id="session-2",
        scene_number=1,
        campaign_id="campaign-2",
    )
    results = retrieve("ambush", k=5, filters={"campaign_id": "campaign-2"})
    assert len(results) >= 1
    assert results[0].metadata["campaign_id"] == "campaign-2"


def test_retrieve_empty_on_no_match():
    results = retrieve("nonexistent query with no matches", k=5)
    assert len(results) == 0


def test_delete_collection():
    store_summary(summary_id="del-test", text="Test content.", session_id="s1")
    delete_collection()
    results = retrieve("test", k=5)
    assert len(results) == 0
