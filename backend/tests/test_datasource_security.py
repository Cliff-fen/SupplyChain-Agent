import pytest

from app.services.datasource import DataSourceError, validate_source_host


def test_allows_explicitly_configured_host(monkeypatch) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATASOURCE_ALLOWED_HOSTS", "analytics.internal")
    from app.core.config import get_settings

    get_settings.cache_clear()
    validate_source_host("analytics.internal")


def test_allows_ip_in_configured_cidr(monkeypatch) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATASOURCE_ALLOWED_HOSTS", "")
    monkeypatch.setenv("SUPPLYMIND_DATASOURCE_ALLOWED_CIDRS", "10.24.0.0/16")
    from app.core.config import get_settings

    get_settings.cache_clear()
    validate_source_host("10.24.18.9")


def test_rejects_unapproved_host(monkeypatch) -> None:
    monkeypatch.setenv("SUPPLYMIND_DATASOURCE_ALLOWED_HOSTS", "analytics.internal")
    monkeypatch.setenv("SUPPLYMIND_DATASOURCE_ALLOWED_CIDRS", "10.24.0.0/16")
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(DataSourceError):
        validate_source_host("public.example.com")
