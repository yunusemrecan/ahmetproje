"""{{t:tests_doc}}"""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def setup_function() -> None:
    main.tasks.clear()
    main.next_id = 1


def test_home() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_add_complete_delete() -> None:
    response = client.post("/tasks", json={"title": "{{t:api_sample_task}}"})
    assert response.status_code == 201
    task_id = response.json()["id"]

    assert client.get("/tasks").json()[0]["title"] == "{{t:api_sample_task}}"
    assert client.post(f"/tasks/{task_id}/done").json()["done"] is True
    assert client.delete(f"/tasks/{task_id}").status_code == 204
    assert client.get("/tasks").json() == []


def test_missing_task() -> None:
    assert client.post("/tasks/99/done").status_code == 404
    assert client.delete("/tasks/99").status_code == 404
