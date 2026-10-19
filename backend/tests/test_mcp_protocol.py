import pytest

from app.core.config import get_settings
from app.mcp_runtime.client import validate_mcp_endpoint
from app.mcp_runtime.security import issue_tool_context, verify_tool_context
from app.schemas import Principal


def test_mcp_context_is_signed_and_tenant_scoped(monkeypatch) -> None:
    monkeypatch.setenv("SUPPLYMIND_MCP_SERVICE_SECRET", "test-mcp-secret-that-is-long-enough")
    get_settings.cache_clear()
    principal = Principal(user_id="u1", tenant_id="t1", role="analyst")
    decoded = verify_tool_context(issue_tool_context(principal))
    assert decoded == principal


def test_mcp_endpoint_requires_allowlisted_host(monkeypatch) -> None:
    monkeypatch.setenv("SUPPLYMIND_MCP_ALLOWED_HOSTS", "mcp-server,localhost")
    get_settings.cache_clear()
    assert validate_mcp_endpoint("http://mcp-server:8001/mcp").startswith("http://")
    with pytest.raises(ValueError, match="not in"):
        validate_mcp_endpoint("http://169.254.169.254/latest/meta-data")
