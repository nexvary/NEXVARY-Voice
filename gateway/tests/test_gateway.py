import httpx
from fastapi.testclient import TestClient
from voice_gateway.api import app


def _auth():
    return {"Authorization": "Bearer " + "q" * 48}


def test_health_does_not_claim_real_audio(monkeypatch):
    monkeypatch.delenv("NEXVARY_WORKER_URL", raising=False)
    with TestClient(app) as client:
        status = client.get("/health").json()
        assert status["mode"] == "lightweight"
        assert status["worker_configured"] is False


def test_token_is_required(monkeypatch):
    monkeypatch.setenv("NEXVARY_GATEWAY_TOKEN", "q" * 48)
    with TestClient(app) as client:
        assert client.get("/v1/capabilities").status_code == 401
        assert client.get("/v1/capabilities", headers=_auth()).status_code == 200
        assert client.post("/v1/translate", json={"text": "hi"}).status_code == 401


def test_no_worker_returns_503(monkeypatch):
    monkeypatch.setenv("NEXVARY_GATEWAY_TOKEN", "q" * 48)
    monkeypatch.delenv("NEXVARY_WORKER_URL", raising=False)
    with TestClient(app) as client:
        resp = client.post("/v1/translate", json={"text": "hello"}, headers=_auth())
        assert resp.status_code == 503


def test_reject_insecure_remote_worker(monkeypatch):
    monkeypatch.setenv("NEXVARY_GATEWAY_TOKEN", "q" * 48)
    monkeypatch.setenv("NEXVARY_WORKER_URL", "http://example.com:8000")
    monkeypatch.delenv("NEXVARY_ALLOW_PRIVATE_HTTP_WORKER", raising=False)
    with TestClient(app) as client:
        resp = client.post("/v1/translate", json={"text": "hello"}, headers=_auth())
        assert resp.status_code == 503


def test_json_forwarding_with_worker_credentials(monkeypatch):
    import voice_gateway.api as api
    monkeypatch.setenv("NEXVARY_GATEWAY_TOKEN", "q" * 48)
    monkeypatch.setenv("NEXVARY_WORKER_URL", "https://inference.example")
    monkeypatch.setenv("NEXVARY_WORKER_TOKEN", "worker-secret")

    def handler(req: httpx.Request):
        assert req.url.path == "/v1/translate"
        assert req.headers["Authorization"] == "Bearer worker-secret"
        return httpx.Response(200, json={"translated_text": "Hello"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(api, "make_client", lambda **kw: httpx.AsyncClient(transport=transport))
    with TestClient(app) as client:
        r = client.post("/v1/translate", json={"text": "مرحبا"}, headers=_auth())
        assert r.status_code == 200
        assert r.json()["translated_text"] == "Hello"


def test_reject_oversized_json(monkeypatch):
    monkeypatch.setenv("NEXVARY_GATEWAY_TOKEN", "q" * 48)
    monkeypatch.setenv("NEXVARY_WORKER_URL", "https://inference.example")
    with TestClient(app) as client:
        r = client.post("/v1/translate", json={"text": "a" * 600100}, headers=_auth())
        assert r.status_code == 413


def test_video_invalid_identifier(monkeypatch):
    monkeypatch.setenv("NEXVARY_GATEWAY_TOKEN", "q" * 48)
    with TestClient(app) as client:
        assert client.get("/v1/dub/jobs/../../etc/passwd", headers=_auth()).status_code in (404, 422)
        assert client.get("/v1/dub/jobs/nope", headers=_auth()).status_code == 422
