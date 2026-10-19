from datetime import UTC, datetime, timedelta

import jwt
from opentelemetry.propagate import inject

from app.core.config import get_settings
from app.schemas import Principal


def issue_tool_context(principal: Principal, *, expires_seconds: int = 90, run_id: str | None = None) -> str:
    now = datetime.now(UTC)
    carrier = {}
    inject(carrier)
    return jwt.encode(
        {
            "sub": principal.user_id,
            "tenant_id": principal.tenant_id,
            "role": principal.role,
            "aud": "supplymind-mcp",
            "iat": now,
            "exp": now + timedelta(seconds=expires_seconds),
            "run_id": run_id,
            "traceparent": carrier.get("traceparent"),
        },
        get_settings().mcp_service_secret,
        algorithm="HS256",
    )


def verify_tool_context(token: str) -> Principal:
    try:
        payload = jwt.decode(
            token,
            get_settings().mcp_service_secret,
            algorithms=["HS256"],
            audience="supplymind-mcp",
        )
        return Principal(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            role=payload["role"],
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise PermissionError("Invalid or expired MCP tool context") from exc
