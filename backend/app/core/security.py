import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return password_hash.verify(value, hashed)


def create_access_token(subject: str, organization_id: str, role: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "org": organization_id,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_oidc_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


def _fernet() -> Fernet:
    return Fernet(get_settings().credential_key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
