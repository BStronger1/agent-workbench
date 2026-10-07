import os
from fastapi.testclient import TestClient
from ai_service.app import app


def test_internal_api_auth_and_validation_never_echo_secret(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_TOKEN", "test-internal-token-" + "x" * 32)
    c = TestClient(app)
    assert c.get("/health").status_code == 403
    response = c.post(
        "/runs",
        headers={"X-AI-Token": os.environ["AI_SERVICE_TOKEN"]},
        json={"credentials": {"apiKey": "test-private-value"}},
    )
    assert response.status_code == 422 and "test-private-value" not in response.text
    assert (
        c.get("/health", headers={"X-AI-Token": os.environ["AI_SERVICE_TOKEN"]}).json()[
            "engine"
        ]
        == "langgraph"
    )
