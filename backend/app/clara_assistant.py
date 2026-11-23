"""Clara's contextual, read-only assistant across Smart Glosas AI.

Never sends patient records, invoices, uploaded files, names or raw objection text
to Gemini. All database queries are scoped to the authenticated institution.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import Actor, actor
from .db import get_db
from .gemini import VALID_MODEL, redact
from .models import AuditEvent, ObjectionCase, RuleVersion

router = APIRouter(prefix="/api/v1/clara", tags=["clara"])
MAX_CALLS_PER_HOUR = 18
_calls: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()

SCREENS = {
    "resumen": "Inicio y seguimiento general del ciclo de glosas",
    "prevent": "Prevención y control previo a radicar cuentas",
    "respond": "Contestación de glosas y devoluciones",
    "historial": "Seguimiento de estados y respuestas documentadas",
    "reglas": "Configuración de instituciones, catálogos y reglas de validación",
}
# Do not transmit potential clinical identifiers in free-form prompts.
PERSONAL_IDENTIFIERS = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|(?:\+?\d[\d .()-]{7,}\d)"
    r"|\b(?:cc|ti|ce|cedula|cédula|identificaci[oó]n|documento|tel[eé]fono|celular)"
    r"\s*[:#-]?\s*\d{4,}\b", re.IGNORECASE
)


class ClaraQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=700)
    screen: Literal["resumen", "prevent", "respond", "historial", "reglas"]
    objection_ref: str | None = Field(default=None, max_length=120)


def _limit(user: Actor):
    now = time.monotonic()
    key = f"{user.tenant_id}:{user.email}"
    with _lock:
        recent = [stamp for stamp in _calls[key] if now - stamp < 3600]
        if len(recent) >= MAX_CALLS_PER_HOUR:
            raise HTTPException(429, "Clara alcanzó el límite temporal de consultas. Intenta más tarde.")
        recent.append(now)
        _calls[key] = recent


def ask_gemini(payload: dict) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Clara no tiene Gemini configurado.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not VALID_MODEL.fullmatch(model):
        raise HTTPException(503, "El modelo de Gemini no está configurado correctamente.")
    instruction = (
        "Eres Clara, agente de Smart Glosas AI en Colombia. Responde a la pregunta "
        "considerando la pantalla actual y solo los indicadores, codigos y estados autorizados. "
        "Sé práctica, breve y precisa, en español. No inventes información, resultados "
        "de auditoría, documentos, normativa, plazos, pagos ni decisiones. "
        "Distingue una glosa de una devolución y una propuesta de una respuesta enviada. "
        "Si la consulta requiere historia clínica, contrato, factura, soporte o fecha, "
        "explica qué evidencia falta y no concluyas procedencia. "
        "No afirmes haber procesado documentos ni enviado mensajes. "
        "Esta función es de orientación y no puede ejecutar operaciones."
    )
    try:
        with httpx.Client(timeout=24.0) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": instruction}]},
                    "contents": [{"role": "user", "parts": [
                        {"text": json.dumps(payload, ensure_ascii=False)}
                    ]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 850}
                }
            )
            response.raise_for_status()
            raw = response.json()
            answer = "".join(p.get("text", "") for p in raw["candidates"][0]["content"]["parts"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
        raise HTTPException(502, "Clara no pudo completar la consulta con Gemini.") from None
    answer = answer.strip()[:3000]
    if not answer:
        raise HTTPException(502, "Gemini devolvió una respuesta vacía.")
    return {"answer": answer, "agent": "Clara", "model": model, "read_only": True}


@router.post("/assist")
def assist(body: ClaraQuestion, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    question = body.question.strip()
    if PERSONAL_IDENTIFIERS.search(question):
        raise HTTPException(
            422, "Para proteger la privacidad, no incluyas documentos, teléfonos ni correos. Consulta solo la causal o el proceso."
        )
    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise HTTPException(503, "Clara no tiene Gemini configurado.")
    selected = None
    if body.objection_ref:
        selected = db.scalar(select(ObjectionCase).where(
            ObjectionCase.tenant_id == user.tenant_id,
            ObjectionCase.objection_ref == body.objection_ref
        ))
        if selected is None:
            raise HTTPException(404, "Esa glosa no pertenece a la institución activa.")
    counts = db.execute(
        select(ObjectionCase.status, func.count())
        .where(ObjectionCase.tenant_id == user.tenant_id)
        .group_by(ObjectionCase.status)
    ).all()
    stats = dict(counts)
    rules_count = db.scalar(
        select(func.count()).select_from(RuleVersion).where(
            RuleVersion.tenant_id == user.tenant_id, RuleVersion.active.is_(True)
        )
    ) or 0
    context = {
        "screen": body.screen,
        "screen_goal": SCREENS[body.screen],
        "question": redact(question)[:700],
        "objection_counts": {
            key: int(stats.get(key, 0)) for key in
            ("POR_ANALIZAR", "EN_REVISION", "ANALIZADA", "PROPUESTA", "RESPONDIDA")
        },
        "active_rule_count": rules_count,
        "selected_case": {
            "kind": selected.kind,
            "code": redact(selected.code)[:30] if selected.code else None,
            "status": selected.status,
            "number_of_findings": len(selected.findings or []),
            "has_ai_proposal": bool(selected.ai_review and selected.ai_review.get("draft"))
        } if selected else None
    }
    _limit(user)
    answer = ask_gemini(context)
    db.add(AuditEvent(
        tenant_id=user.tenant_id, actor=user.email, action="CLARA_ASSIST_CONSULTED",
        subject_id=selected.id if selected else user.tenant_id,
        details={"screen": body.screen, "model": answer["model"], "case_selected": bool(selected)}
    ))
    db.commit()
    return answer
