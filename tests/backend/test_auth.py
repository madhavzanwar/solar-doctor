from fastapi.testclient import TestClient


def test_health_open_when_api_key_set(monkeypatch, tmp_path):
    from axalon.db.session import init_db

    init_db(f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    from axalon.api.app import app

    with TestClient(app) as client:
        r = client.get("/health")

    assert r.status_code == 200


def test_non_health_requires_api_key(monkeypatch, tmp_path):
    from axalon.db.session import init_db

    init_db(f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    from axalon.api.app import app

    with TestClient(app) as client:
        assert client.get("/parks").status_code == 401
        assert client.get("/parks", headers={"Authorization": "Bearer secret123"}).status_code == 200
