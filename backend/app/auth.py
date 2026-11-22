"""Google identity verification; authorization always consults persisted membership."""
import os
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Tenant, Membership

@dataclass(frozen=True)
class Actor:
    email: str
    tenant_id: str
    roles: frozenset[str]

def current_email(authorization: str | None = Header(default=None)) -> str:
    client_id = os.getenv("SMART_GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
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
          email: str = Depends(current_email), db: Session = Depends(get_db)) -> Actor:
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
