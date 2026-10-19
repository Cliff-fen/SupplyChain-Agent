from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import DEVELOPMENT_CREDENTIAL_KEY, DEVELOPMENT_JWT_SECRET, Settings
from app.services.task_watchdog import _expired


def test_trial_runtime_rejects_development_secrets() -> None:
    settings = Settings(
        env="trial",
        jwt_secret=DEVELOPMENT_JWT_SECRET,
        credential_key=DEVELOPMENT_CREDENTIAL_KEY,
    )
    with pytest.raises(ValueError, match="SUPPLYMIND_JWT_SECRET"):
        settings.validate_trial_runtime()


def test_trial_runtime_accepts_explicit_secrets() -> None:
    settings = Settings(
        env="trial",
        jwt_secret="x" * 40,
        credential_key="custom-trial-credential-key",
        s3_endpoint="http://minio:9000",
        s3_access_key="trial-user",
        s3_secret_key="trial-secret",
        mcp_service_secret="trial-mcp-secret-that-is-long-enough",
    )
    settings.validate_trial_runtime()


def test_watchdog_handles_sqlite_naive_timestamps() -> None:
    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    assert _expired((datetime.now(UTC) - timedelta(minutes=10)).replace(tzinfo=None), cutoff)
    assert not _expired((datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None), cutoff)
