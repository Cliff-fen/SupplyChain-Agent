from pathlib import Path

from fastapi.testclient import TestClient


def test_organization_summary_quota_and_permissions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "SUPPLYMIND_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'organization.db'}"
    )
    monkeypatch.setenv("SUPPLYMIND_JWT_SECRET", "test-secret-that-is-long-enough-for-tests")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@demo.local",
                "password": "ChangeMe123!",
                "organization_slug": "demo-factory",
            },
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        summary = client.get("/api/v1/organization", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["slug"] == "demo-factory"
        assert summary.json()["member_count"] >= 1
        assert summary.json()["quota"]["daily_analysis_runs"] == 100

        updated = client.patch(
            "/api/v1/organization/quotas",
            headers=headers,
            json={
                "max_concurrent_analyses": 8,
                "daily_analysis_runs": 200,
                "max_document_size_mb": 20,
                "retention_days": 180,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["max_concurrent_analyses"] == 8

        matrix = client.get("/api/v1/organization/permissions", headers=headers)
        assert matrix.status_code == 200
        assert matrix.json()["roles"]["viewer"]["run_analysis"] is False


def test_member_invitation_acceptance_and_one_time_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'members.db'}")
    monkeypatch.setenv("SUPPLYMIND_JWT_SECRET", "test-secret-that-is-long-enough-for-tests")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@demo.local",
                "password": "ChangeMe123!",
                "organization_slug": "demo-factory",
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        invitation = client.post(
            "/api/v1/members/invitations",
            headers=headers,
            json={
                "email": "analyst@example.com",
                "role": "analyst",
                "expires_in_days": 2,
            },
        )
        assert invitation.status_code == 201
        body = invitation.json()
        assert body["status"] == "pending"
        assert body["token"]

        accepted = client.post(
            "/api/v1/members/invitations/accept",
            json={
                "token": body["token"],
                "display_name": "New Analyst",
                "password": "ChangeMe456!",
            },
        )
        assert accepted.status_code == 200
        assert (
            client.post(
                "/api/v1/members/invitations/accept",
                json={
                    "token": body["token"],
                    "display_name": "New Analyst",
                    "password": "ChangeMe456!",
                },
            ).status_code
            == 400
        )
        members = client.get("/api/v1/members", headers=headers)
        assert any(
            item["email"] == "analyst@example.com" and item["role"] == "analyst"
            for item in members.json()
        )


def test_member_invitation_can_be_revoked(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'revoke.db'}")
    monkeypatch.setenv("SUPPLYMIND_JWT_SECRET", "test-secret-that-is-long-enough-for-tests")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@demo.local",
                "password": "ChangeMe123!",
                "organization_slug": "demo-factory",
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        invitation = client.post(
            "/api/v1/members/invitations",
            headers=headers,
            json={
                "email": "revoke@example.com",
                "role": "viewer",
            },
        )
        assert invitation.status_code == 201
        invitation_id = invitation.json()["id"]

        revoked = client.post(
            f"/api/v1/members/invitations/{invitation_id}/revoke", headers=headers
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert (
            client.post(
                f"/api/v1/members/invitations/{invitation_id}/revoke", headers=headers
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/v1/members/invitations/accept",
                json={
                    "token": invitation.json()["token"],
                    "display_name": "Revoked User",
                    "password": "ChangeMe456!",
                },
            ).status_code
            == 400
        )


def test_resending_an_invitation_invalidates_its_previous_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'resend.db'}")
    monkeypatch.setenv("SUPPLYMIND_JWT_SECRET", "test-secret-that-is-long-enough-for-tests")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@demo.local",
                "password": "ChangeMe123!",
                "organization_slug": "demo-factory",
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        invitation = client.post(
            "/api/v1/members/invitations",
            headers=headers,
            json={"email": "resend@example.com", "role": "analyst"},
        ).json()
        resent = client.post(
            f"/api/v1/members/invitations/{invitation['id']}/resend", headers=headers
        )
        assert resent.status_code == 200
        assert resent.json()["token"] != invitation["token"]
        old_token = client.post(
            "/api/v1/members/invitations/accept",
            json={
                "token": invitation["token"],
                "display_name": "Old Token",
                "password": "ChangeMe456!",
            },
        )
        assert old_token.status_code == 400
        accepted = client.post(
            "/api/v1/members/invitations/accept",
            json={
                "token": resent.json()["token"],
                "display_name": "New Token",
                "password": "ChangeMe456!",
            },
        )
        assert accepted.status_code == 200
        analyst_headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
        assert client.get("/api/v1/members", headers=analyst_headers).status_code == 403


def test_member_admin_guards_and_cross_organization_resources_are_hidden(
    monkeypatch, tmp_path: Path
) -> None:
    """Management endpoints must distinguish forbidden roles from hidden tenants."""
    monkeypatch.setenv("SUPPLYMIND_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'isolation.db'}")
    monkeypatch.setenv("SUPPLYMIND_JWT_SECRET", "test-secret-that-is-long-enough-for-tests")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        def login(email: str, slug: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": "ChangeMe123!",
                    "organization_slug": slug,
                },
            )
            assert response.status_code == 200
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        admin = login("admin@demo.local", "demo-factory")
        south_admin = login("south-admin@demo.local", "demo-south")
        own_member = next(item for item in client.get("/api/v1/members", headers=admin).json() if item["email"] == "admin@demo.local")

        # The final active org admin cannot demote or deactivate themselves.
        assert client.patch(
            f"/api/v1/members/{own_member['user_id']}", headers=admin, json={"role": "analyst"}
        ).status_code == 400
        assert client.patch(
            f"/api/v1/members/{own_member['user_id']}/status", headers=admin, json={"is_active": False}
        ).status_code == 400

        south_member = next(
            item
            for item in client.get("/api/v1/members", headers=south_admin).json()
            if item["email"] == "south-admin@demo.local"
        )
        south_invitation = client.post(
            "/api/v1/members/invitations",
            headers=south_admin,
            json={"email": "south-only@example.com", "role": "viewer"},
        )
        assert south_invitation.status_code == 201

        # A valid admin in another organization gets 404, never an ownership hint.
        assert client.patch(
            f"/api/v1/members/{south_member['user_id']}", headers=admin, json={"role": "viewer"}
        ).status_code == 404
        assert client.post(
            f"/api/v1/members/invitations/{south_invitation.json()['id']}/revoke", headers=admin
        ).status_code == 404
