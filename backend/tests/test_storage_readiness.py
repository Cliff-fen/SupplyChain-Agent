import pytest
from botocore.stub import Stubber

from app.services import storage


def test_bucket_readiness_checks_existing_bucket_and_propagates_failure(monkeypatch):
    import boto3

    from app.core.config import get_settings

    for name, value in {
        "SUPPLYMIND_S3_ENDPOINT": "http://127.0.0.1:9000",
        "SUPPLYMIND_S3_BUCKET": "test-bucket",
        "SUPPLYMIND_S3_ACCESS_KEY": "test-access",
        "SUPPLYMIND_S3_SECRET_KEY": "test-secret",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    client = boto3.client(
        "s3", endpoint_url="http://127.0.0.1:9000",
        aws_access_key_id="test-access", aws_secret_access_key="test-secret",
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, {"Bucket": "test-bucket"})
        storage.check_ready()
        stubber.add_client_error("head_bucket", service_error_code="AccessDenied", http_status_code=403)
        from botocore.exceptions import ClientError

        with pytest.raises(ClientError):
            storage.check_ready()
        stubber.assert_no_pending_responses()
    get_settings.cache_clear()
