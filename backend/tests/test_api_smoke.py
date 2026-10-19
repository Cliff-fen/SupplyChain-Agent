from pathlib import Path

from fastapi.testclient import TestClient


def test_seeded_user_can_log_in_and_read_dashboard(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SUPPLYMIND_JWT_SECRET", "test-secret-that-is-long-enough-for-tests")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@demo.local",
                "password": "ChangeMe123!",
                "organization_slug": "demo-factory",
            },
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        dashboard = client.get(
            "/api/v1/dashboards/supply-chain", headers={"Authorization": f"Bearer {token}"}
        )
        assert dashboard.status_code in {200, 503}
        if dashboard.status_code == 200:
            assert len(dashboard.json()["cards"]) == 5
        else:
            assert dashboard.json()["detail"]
        config = client.get(
            "/api/v1/dashboards/supply-chain/config", headers={"Authorization": f"Bearer {token}"}
        )
        assert config.status_code == 200
        saved_config = client.patch(
            "/api/v1/dashboards/supply-chain/config",
            headers={"Authorization": f"Bearer {token}"},
            json={"refresh_interval_seconds": 900, "visible_widgets": ["production", "trend"]},
        )
        assert saved_config.status_code == 200
        assert saved_config.json()["refresh_interval_seconds"] == 900
        analyst_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "analyst@demo.local",
                "password": "ChangeMe123!",
                "organization_slug": "demo-factory",
            },
        )
        assert analyst_login.status_code == 200
        denied_config = client.patch(
            "/api/v1/dashboards/supply-chain/config",
            headers={"Authorization": f"Bearer {analyst_login.json()['access_token']}"},
            json={"refresh_interval_seconds": 900, "visible_widgets": []},
        )
        assert denied_config.status_code == 403
        refreshed = client.post(
            "/api/v1/dashboards/supply-chain/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert refreshed.status_code in {200, 202, 503}
        refresh_token = response.json()["refresh_token"]
        rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert rotated.status_code == 200
        assert rotated.json()["refresh_token"] != refresh_token
        assert (
            client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}).status_code
            == 401
        )
        members = client.get("/api/v1/members", headers={"Authorization": f"Bearer {token}"})
        assert members.status_code == 200
        assert members.json()[0]["role"] == "org_admin"
        hermes = client.get("/api/v1/hermes/runtime", headers={"Authorization": f"Bearer {token}"})
        assert hermes.status_code == 200
        assert hermes.json()["framework"] == "Hermes"
        assert hermes.json()["mode"] == "guarded_self_evolution"
        assert len(hermes.json()["candidates"]) >= 2
        audit = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
        assert audit.status_code == 200
        assert any(event["action"] == "auth.login" for event in audit.json())
        assert (
            client.post(
                "/api/v1/auth/logout", json={"refresh_token": rotated.json()["refresh_token"]}
            ).status_code
            == 204
        )
        assert client.get("/api/v1/auth/oidc/callback?code=unused&state=bad").status_code == 400
