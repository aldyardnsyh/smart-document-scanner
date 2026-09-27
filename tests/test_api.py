import io
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

import api
from src.jobs import JobManager


def encoded_image() -> bytes:
    image = np.full((240, 360, 3), 90, dtype=np.uint8)
    image[60:180, 80:280] = 245
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    return encoded.tobytes()


def test_health_and_upload_contract(monkeypatch, tmp_path: Path) -> None:
    upload_directory = tmp_path / "uploads"
    upload_directory.mkdir()
    monkeypatch.setattr(api, "UPLOAD_DIR", upload_directory)
    test_manager = JobManager(tmp_path / "jobs", tmp_path / "outputs")
    monkeypatch.setattr(api, "manager", test_manager)
    monkeypatch.setattr(test_manager, "run", lambda job_id: None)
    client = TestClient(api.app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "online"
    response = client.post(
        "/api/process",
        files={"file": ("sample.jpg", io.BytesIO(encoded_image()), "image/jpeg")},
        data={"doc_type": "auto", "cpp_acceleration": "true"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert client.get(f"/api/jobs/{payload['id']}").status_code == 200
    assert client.delete(f"/api/jobs/{payload['id']}").json() == {"deleted": True}
    assert client.get(f"/api/jobs/{payload['id']}").status_code == 404
