from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_cannot_delete_default_bearer():
    # create UE
    client.post("/ues", json={"ue_id": 1})

    # try deleting default bearer
    response = client.delete("/ues/1/bearers/9")

    # assertions
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot remove default bearer"