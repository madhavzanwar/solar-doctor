"""401 responses from the auth middleware must still carry CORS headers (else browsers see a network error)."""
from fastapi.testclient import TestClient

from solardoctor.api.app import app


def test_401_has_cors_headers(monkeypatch):
    monkeypatch.setenv("SOLARDOCTOR_AUTH_MODE", "users")
    c = TestClient(app)
    r = c.get("/api/v1/plants", headers={"Origin": "http://localhost:3000", "Authorization": "Bearer bogus-token-bogus-token-1"})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_preflight_ok():
    c = TestClient(app)
    r = c.options("/api/v1/plants", headers={"Origin": "http://localhost:3000",
                                            "Access-Control-Request-Method": "GET",
                                            "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
