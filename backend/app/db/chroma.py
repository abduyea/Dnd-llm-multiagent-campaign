import os
from dataclasses import dataclass
from typing import Any, cast

import chromadb
from chromadb import Collection
from chromadb.config import Settings

PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "dnd_memories")


@dataclass
class MemoryResult:
    """A single semantic retrieval result from ChromaDB."""

    id: str
    text: str
    metadata: dict[str, Any]
    distance: float


_client: Any | None = None


def _get_client() -> Any:
    """Return (or lazily create) the shared ChromaDB persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
    return _client


def get_or_create_collection(name: str = COLLECTION_NAME) -> Collection:
    """Get an existing ChromaDB collection or create it if absent."""
    client = _get_client()
    try:
        result = client.get_collection(name)
        return cast(Collection, result)
    except (ValueError, chromadb.errors.NotFoundError):
        result = client.create_collection(name)
        return cast(Collection, result)


def store_summary(
    summary_id: str,
    text: str,
    session_id: str | None = None,
    scene_number: int | None = None,
    campaign_id: str | None = None,
) -> None:
    """Upsert a session summary embedding into ChromaDB."""
    collection = get_or_create_collection()
    metadata: dict[str, Any] = {}
    if session_id is not None:
        metadata["session_id"] = session_id
    if scene_number is not None:
        metadata["scene_number"] = scene_number
    if campaign_id is not None:
        metadata["campaign_id"] = campaign_id
    collection.upsert(ids=[summary_id], documents=[text], metadatas=[metadata])


def retrieve(
    query: str,
    k: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[MemoryResult]:
    """Semantic search over stored summaries; returns up to k results."""
    collection = get_or_create_collection()
    where = filters or None
    results = collection.query(query_texts=[query], n_results=k, where=where)
    if not results["ids"] or not results["ids"][0]:
        return []
    output: list[MemoryResult] = []
    for i in range(len(results["ids"][0])):
        output.append(
            MemoryResult(
                id=results["ids"][0][i],
                text=results["documents"][0][i] if results["documents"] else "",
                metadata=dict(results["metadatas"][0][i]) if results["metadatas"] else {},
                distance=results["distances"][0][i] if results["distances"] else 0.0,
            )
        )
    return output


def delete_collection(name: str = COLLECTION_NAME) -> None:
    """Delete the named ChromaDB collection (idempotent)."""
    client = _get_client()
    try:
        client.delete_collection(name)
    except (ValueError, chromadb.errors.NotFoundError):
        pass


def reset() -> None:
    """Reset the entire ChromaDB client (clears all collections — test use only)."""
    client = _get_client()
    client.reset()
