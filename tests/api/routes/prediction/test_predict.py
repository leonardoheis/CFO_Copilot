import pytest
from fastapi import status
from fastapi.testclient import TestClient


def test_predict_before_training_is_a_conflict(client: TestClient) -> None:
    response = client.post("/prediction/predict", json={"input": 3.0})

    assert response.status_code == status.HTTP_409_CONFLICT


def test_predict_after_training_returns_a_result(client: TestClient) -> None:
    client.post(
        "/prediction/train",
        json={"age": [[1.0], [2.0], [3.0]], "timeForFailure": [2.0, 4.0, 6.0]},
    )

    response = client.post("/prediction/predict", json={"input": 4.0})

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["result"] == pytest.approx(8.0)
