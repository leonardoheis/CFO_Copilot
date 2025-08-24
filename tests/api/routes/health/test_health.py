from fastapi import status
from fastapi.testclient import TestClient
from syrupy.assertion import SnapshotAssertion


def test_health_endpoint(client: TestClient, snapshot: SnapshotAssertion) -> None:
    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Type"] == "application/json"
    assert response.json() == snapshot
