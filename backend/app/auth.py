"""Google identity verification; authorization always consults persisted membership."""
import os
import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Tenant, Membership

def platform_claims(authorization: str | None) -> dict:
    """Short lived HMAC-signed actor and IPS context from Smart platform."""
    secret = os.getenv("SMART_PLATFORM_JWT_SECRET", "")
    if len(secret.encode()) < 32:
        raise HTTPException(503, "Integracion con plataforma Smart no configurada")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Abre Smart Glosas AI desde la plataforma Smart")
    try:
        segments = authorization[7:].strip().split(".")
        if len(segments) != 3:
            raise ValueError()
        header, body, signature = segments
        decode = lambda v: base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))
        meta, claims = json.loads(decode(header)), json.loads(decode(body))
        expected = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
        if meta != {"alg": "HS256", "typ": "JWT"} or not hmac.compare_digest(expected, decode(signature)):
            raise ValueError()
        now = int(time.time())
        if (claims.get("iss") != "smart-platform" or claims.get("aud") != "smart-glosas-ai"
                or type(claims.get("exp")) is not int or claims["exp"] <= now
                or claims["exp"] > now + 900 or not claims.get("sub")
                or not isinstance(claims.get("roles"), list) or not claims.get("tenant_id")
                or len(str(claims["tenant_id"])) > 36):
            raise ValueError()
        if claims.get("nbf", 0) > now or not isinstance(claims["sub"], str) or not isinstance(claims["tenant_id"], str):
            raise ValueError()
        if not all(isinstance(role, str) for role in claims["roles"]):
            raise ValueError()
        return claims
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeDecodeError):
        raise HTTPException(401, "Contexto de Smart invalido o vencido") from None


@dataclass(frozen=True)
class Actor:
    email: str
    tenant_id: str
    roles: frozenset[str]

def optional_platform_claims(authorization: str | None) -> dict | None:
    """Accept verified host context; other bearer tokens must pass Google verification."""
    if os.getenv("SMART_AUTH_MODE", "google") != "platform":
        return None
    try:
        return platform_claims(authorization)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        return None


def current_email(authorization: str | None = Header(default=None)) -> str:
    claims = optional_platform_claims(authorization)
    if claims:
        return str(claims["sub"]).strip().lower()
    # Google SSO uses the same corporate identity when the Smart host is not embedded.
    client_id = os.getenv("SMART_GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        if os.getenv("SMART_AUTH_MODE", "google") == "platform":
            raise HTTPException(status_code=401, detail="Contexto de Smart inválido o vencido")
        raise HTTPException(status_code=503, detail="Inicio de sesión Google no configurado")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Inicia sesión con Google")
    try:
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request
        claims = id_token.verify_oauth2_token(authorization[7:].strip(), Request(), client_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Credencial Google inválida o vencida") from None
    email = str(claims.get("email", "")).strip().lower()
    if not email or str(claims.get("email_verified", "")).lower() != "true":
        raise HTTPException(status_code=401, detail="Cuenta Google sin correo verificado")
    return email

def actor(tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
          email: str = Depends(current_email), db: Session = Depends(get_db),
          authorization: str | None = Header(default=None)) -> Actor:
    claims = optional_platform_claims(authorization)
    if claims:
        if tenant_id != claims["tenant_id"]:
            raise HTTPException(403, "El contexto de IPS no coincide con el firmado por Smart")
        tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id, Tenant.active.is_(True)))
        if not tenant:
            raise HTTPException(403, "IPS no habilitada en Smart Glosas AI")
        allowed = frozenset({"SUPERADMIN", "ADMIN", "CONFIGURADOR", "AUDITOR", "ANALISTA"})
        granted = frozenset(claims["roles"]) & allowed
        if not granted:
            raise HTTPException(403, "El usuario no tiene un rol autorizado en esta institución")
        return Actor(email=email, tenant_id=tenant_id, roles=granted)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Selecciona una institución")
    membership = db.scalar(select(Membership).join(Tenant, Tenant.id == Membership.tenant_id).where(
        Membership.email == email, Membership.tenant_id == tenant_id,
        Membership.active.is_(True), Tenant.active.is_(True)))
    if membership is None:
        raise HTTPException(status_code=403, detail="Sin permiso para esta institución")
    return Actor(email=email, tenant_id=tenant_id, roles=frozenset(membership.roles))

def require_admin(user: Actor):
    if "ADMIN" not in user.roles and "CONFIGURADOR" not in user.roles:
        raise HTTPException(status_code=403, detail="Se requiere rol administrador o configurador")
