from fastapi import status
from fastapi.testclient import TestClient


def test_train_returns_ok(client: TestClient) -> None:
    response = client.post(
        "/prediction/train",
        json={"age": [[1.0], [2.0], [3.0]], "timeForFailure": [2.0, 4.0, 6.0]},
    )

    assert response.status_code == status.HTTP_200_OK


def test_train_with_mismatched_lengths_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/prediction/train",
        json={"age": [[1.0], [2.0], [3.0]], "timeForFailure": [2.0, 4.0]},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
