from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db import get_session, set_tenant_context
from app.models import Membership
from app.schemas import Principal

bearer = HTTPBearer(auto_error=False)


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    claims = decode_access_token(credentials.credentials)
    membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == claims["sub"],
            Membership.organization_id == claims["org"],
            Membership.is_active.is_(True),
        )
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied"
        )
    await set_tenant_context(session, claims["org"])
    return Principal(user_id=claims["sub"], tenant_id=claims["org"], role=membership.role)  # type: ignore[arg-type]


def require_role(*roles: str) -> Callable:
    async def check(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return check
