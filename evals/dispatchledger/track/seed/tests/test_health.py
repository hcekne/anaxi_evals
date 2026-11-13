from fastapi.testclient import TestClient

from dispatchledger.app import create_app
from dispatchledger.settings import Settings


def settings(tmp_path) -> Settings:
    return Settings("http://external.test", tmp_path, "http://app.test")


def test_health(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))
    assert client.get("/api/health").json() == {"status": "ok"}


def test_validation_errors_use_the_envelope(tmp_path):
    app = create_app(settings(tmp_path))

    @app.get("/api/echo")
    def echo(count: int) -> dict:
        return {"count": count}

    response = TestClient(app).get("/api/echo?count=x")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_clock_file_controls_time(tmp_path):
    clock = tmp_path / "clock"
    clock.write_text("1772442000\n")
    current = Settings("http://external.test", tmp_path, "http://app.test", clock)
    assert current.now() == 1772442000
