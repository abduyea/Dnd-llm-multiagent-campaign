from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "dnd-multi-ai-agent-storytelling-system"
    assert data["version"] == "0.1.0"
    assert data["database"] == "ok"
    assert data["ollama"] in ("ok", "unavailable")


def test_lifespan_creates_tables():
    """Verify the lifespan handler runs create_all without error."""
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
