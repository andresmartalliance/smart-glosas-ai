"""Tenant-scoped glosa lifecycle. No test data, no automatic response submission."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Actor, actor
from .db import get_db
from .models import AuditEvent, ObjectionCase, RuleVersion
from .schemas import RespondBatch, ObjectionInput, RuleDefinition
from .engine import respond
from .gemini import generate_review

router = APIRouter(prefix="/api/v1/objections", tags=["objections"])
STATES = ("POR_ANALIZAR", "ANALIZADA", "PROPUESTA", "RESPONDIDA")
PROGRESS = {"POR_ANALIZAR": 0, "ANALIZADA": 50, "PROPUESTA": 75, "RESPONDIDA": 100}


def serialize(row: ObjectionCase) -> dict:
    return {
        "id": row.id, "objection_ref": row.objection_ref,
        "account_ref": row.account_ref, "kind": row.kind, "code": row.code,
        "payer": row.payer, "amount": row.amount, "description": row.description,
        "status": row.status, "findings": row.findings or [], "ai_review": row.ai_review,
        "response_reference": row.response_reference,
        "response_at": row.response_at.isoformat() if row.response_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None
    }


def case_for_tenant(db: Session, tenant_id: str, ref: str) -> ObjectionCase:
    case = db.scalar(select(ObjectionCase).where(
        ObjectionCase.tenant_id == tenant_id,
        ObjectionCase.objection_ref == ref).with_for_update())
    if case is None:
        raise HTTPException(404, "No se encontró la objeción en esta institución.")
    return case


def audit(db: Session, user: Actor, operation: str, item: ObjectionCase, detail: dict | None = None):
    db.add(AuditEvent(
        tenant_id=user.tenant_id, actor=user.email,
        action=operation, subject_id=item.id, details=detail or {}))


@router.get("")
def list_objections(user: Actor = Depends(actor), db: Session = Depends(get_db)):
    cases = db.scalars(select(ObjectionCase).where(
        ObjectionCase.tenant_id == user.tenant_id
    ).order_by(ObjectionCase.created_at.desc()).limit(2000)).all()
    counts = {state: sum(row.status == state for row in cases) for state in STATES}
    progress = round(sum(PROGRESS.get(row.status, 0) for row in cases)/len(cases)) if cases else 0
    return {
        "total": len(cases), "counts": counts, "progress": progress,
        "items": [serialize(row) for row in cases],
        "note": "Porcentaje de avance del proceso, no de dinero recuperado."
    }


@router.post("/batch", status_code=201)
def import_batch(body: RespondBatch, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    if not user.roles.intersection({"ADMIN", "ANALISTA", "AUDITOR"}):
        raise HTTPException(403, "No tienes permiso para cargar objeciones.")
    existing_refs = set(db.scalars(select(ObjectionCase.objection_ref).where(
        ObjectionCase.tenant_id == user.tenant_id,
        ObjectionCase.objection_ref.in_([row.objection_ref for row in body.objections])
    )).all())
    inserted = 0
    for row in body.objections:
        if row.objection_ref in existing_refs:
            continue
        # The identity of patients and raw clinical facts are not stored in this index.
        source = {
            "objection_ref": row.objection_ref, "kind": row.kind,
            "code": row.code, "description": row.description,
            "amount": str(row.amount) if row.amount is not None else None,
            "account": {
                "account_ref": row.account.account_ref, "payer": row.account.payer,
                "modality": row.account.modality,
                "service_type": row.account.service_type,
                "issued_on": row.account.issued_on.isoformat() if row.account.issued_on else None,
                "facts": {}, "evidence": []
            }
        }
        item = ObjectionCase(
            tenant_id=user.tenant_id, objection_ref=row.objection_ref,
            account_ref=row.account.account_ref, kind=row.kind,
            code=row.code, description=row.description,
            payer=row.account.payer, amount=int(row.amount) if row.amount is not None else None,
            source=source, status="POR_ANALIZAR",
            created_by=user.email, updated_by=user.email
        )
        db.add(item)
        existing_refs.add(row.objection_ref)
        inserted += 1
    db.commit()
    return {"inserted": inserted, "existing": len(body.objections)-inserted,
            "total_received": len(body.objections)}


@router.post("/{ref}/analyze")
def analyze_case(ref: str, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    item = case_for_tenant(db, user.tenant_id, ref)
    if item.status == "RESPONDIDA":
        raise HTTPException(409, "Una respuesta formal registrada no puede analizarse de nuevo aquí.")
    from .schemas import ObjectionInput
    source = ObjectionInput.model_validate(item.source)
    rows = db.scalars(select(RuleVersion).where(
        RuleVersion.tenant_id == user.tenant_id,
        RuleVersion.active.is_(True))).all()
    rules = [(RuleDefinition.model_validate(r.body), r.version) for r in rows]
    result = respond(source, rules)
    item.findings = result.get("findings", [])
    item.status = "ANALIZADA" if result.get("rules_applied") else "POR_ANALIZAR"
    item.ai_review = None
    item.updated_by = user.email
    audit(db, user, "OBJECTION_EVALUATED", item,
          {"summary": result["summary"], "rules": len(result["rules_applied"])})
    db.commit()
    return {"case": serialize(item), "analysis": result,
            "notice": "No se puede afirmar procedencia sin evidencia y reglas vigentes."}


@router.post("/{ref}/clara")
def review_case(ref: str, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    item = case_for_tenant(db, user.tenant_id, ref)
    if item.status in ("POR_ANALIZAR", "RESPONDIDA"):
        raise HTTPException(409, "La objeción necesita un análisis válido antes de solicitar una propuesta.")
    result = {
        "phase": "RESPOND", "summary": "REVIEW_REQUIRED",
        "objection_kind": item.kind, "objection_code": item.code,
        "objection_description": item.description,
        "findings": item.findings or [], "evidence_references": []
    }
    proposal = generate_review(result)
    item.ai_review = proposal
    if proposal.get("draft"):
        item.status = "PROPUESTA"
    item.updated_by = user.email
    audit(db, user, "OBJECTION_REVIEWED_WITH_CLARA", item,
          {"model": proposal.get("model"), "draft": bool(proposal.get("draft"))})
    db.commit()
    return {"case": serialize(item), "review": proposal}


class ResponseConfirmation(BaseModel):
    reference: str = Field(min_length=3, max_length=180)


@router.post("/{ref}/register-response")
def register_response(ref: str, body: ResponseConfirmation,
                      user: Actor = Depends(actor), db: Session = Depends(get_db)):
    if not user.roles.intersection({"ADMIN", "AUDITOR"}):
        raise HTTPException(403, "Solo un auditor puede registrar una respuesta formal.")
    item = case_for_tenant(db, user.tenant_id, ref)
    if item.status not in ("ANALIZADA", "PROPUESTA"):
        raise HTTPException(409, "Debe existir evaluación previa antes de registrar la respuesta.")
    item.status = "RESPONDIDA"
    item.response_reference = body.reference.strip()
    item.response_at = datetime.now(timezone.utc)
    item.updated_by = user.email
    audit(db, user, "RESPONSE_REGISTERED", item, {"reference": item.response_reference})
    db.commit()
    return {"case": serialize(item),
            "notice": "Respuesta formal registrada por auditor. El sistema no envió información a la EPS."}
