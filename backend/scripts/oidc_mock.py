"""Local OIDC provider for integration testing only."""

import os
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI(title="SupplyMind OIDC Mock")
issuer = os.getenv("SUPPLYMIND_OIDC_MOCK_ISSUER", "http://localhost:8081").rstrip("/")
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
public_jwk = {**__import__("json").loads(public_jwk), "kid": "supplymind-mock"}
issued_nonces: dict[str, str] = {}


@app.get("/.well-known/openid-configuration")
async def discovery() -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
    }


@app.get("/authorize")
async def authorize(request: Request) -> RedirectResponse:
    query = request.query_params
    redirect_uri = query.get("redirect_uri", "http://localhost:5173/auth/callback")
    issued_nonces["mock-code"] = query.get("nonce", "")
    location = f"{redirect_uri}?{urlencode({'code': 'mock-code', 'state': query.get('state', '')})}"
    return RedirectResponse(location)


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    form = await request.form()
    claims = {
        "iss": issuer,
        "aud": str(form.get("client_id", "supplymind-local")),
        "sub": "mock-user-001",
        "email": "oidc-admin@demo.local",
        "name": "OIDC Mock Admin",
        "nonce": issued_nonces.get(str(form.get("code")), ""),
    }
    encoded = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "supplymind-mock"})
    return JSONResponse(
        {"access_token": "mock-access-token", "id_token": encoded, "token_type": "Bearer"}
    )


@app.get("/jwks")
async def jwks() -> dict:
    return {"keys": [public_jwk]}
