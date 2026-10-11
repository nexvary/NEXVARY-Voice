import time
from pathlib import Path

from fastapi.testclient import TestClient
from voice_engine.api import app
from voice_engine.video_jobs import JobQueue, MAX_UPLOAD_BYTES


def test_video_job_lifecycle(tmp_path, monkeypatch):
    import voice_engine.api as api
    queue = JobQueue(parent=tmp_path)
    def fake_perform(video, output, source, target):
        assert video.read_bytes() == b"fake mp4"
        assert (source, target) == ("ar", "en")
        output.write_bytes(b"fake output")
    monkeypatch.setattr(queue, "_perform", fake_perform)
    monkeypatch.setattr(api, "get_job_queue", lambda: queue)
    monkeypatch.delenv("NEXVARY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        r = client.post("/v1/dub/jobs", data={"source_language": "ar", "target_language": "en"},
                        files={"file": ("sample.mp4", b"fake mp4", "video/mp4")})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        for _ in range(100):
            state = client.get(f"/v1/dub/jobs/{job_id}").json()
            if state["status"] == "complete": break
            time.sleep(0.01)
        assert state["status"] == "complete"
        assert client.get(f"/v1/dub/jobs/{job_id}/video").content == b"fake output"
        assert client.delete(f"/v1/dub/jobs/{job_id}").json() == {"deleted": True}
        assert client.get(f"/v1/dub/jobs/{job_id}").status_code == 404


def test_video_requires_mp4_and_different_languages(tmp_path, monkeypatch):
    import voice_engine.api as api
    monkeypatch.setattr(api, "get_job_queue", lambda: JobQueue(parent=tmp_path))
    monkeypatch.delenv("NEXVARY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        r = client.post("/v1/dub/jobs", data={"source_language": "ar", "target_language": "ar"},
                        files={"file": ("x.mp4", b"fake", "video/mp4")})
        assert r.status_code == 422
        r = client.post("/v1/dub/jobs", data={"source_language": "ar", "target_language": "en"},
                        files={"file": ("secret.txt", b"fake", "text/plain")})
        assert r.status_code == 415
