from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert "supplymind_http_requests_total" in response.text
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["x-trace-id"]
