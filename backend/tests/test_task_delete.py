"""DELETE /api/v1/tasks/{task_id} — permanently removes a task, distinct
from marking it done (which keeps the task and its `result` as the record
of what happened). Isolated from real state via the autouse
isolate_real_user_state fixture in conftest.py."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_task(subject: str = "do the thing") -> dict:
    resp = client.post(
        "/api/v1/tasks",
        json={"department_id": "engineering", "subject": subject},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_delete_task_removes_it_from_the_board() -> None:
    task = _create_task()

    resp = client.delete(f"/api/v1/tasks/{task['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"taskId": task["id"], "status": "deleted"}

    listing = client.get("/api/v1/tasks", params={"department_id": "engineering"})
    assert task["id"] not in [t["id"] for t in listing.json()]


def test_delete_missing_task_is_404() -> None:
    resp = client.delete("/api/v1/tasks/task-does-not-exist")
    assert resp.status_code == 404


def test_delete_does_not_affect_other_tasks() -> None:
    keep = _create_task("keep me")
    remove = _create_task("remove me")

    resp = client.delete(f"/api/v1/tasks/{remove['id']}")
    assert resp.status_code == 200

    listing = client.get("/api/v1/tasks", params={"department_id": "engineering"}).json()
    ids = [t["id"] for t in listing]
    assert keep["id"] in ids
    assert remove["id"] not in ids
