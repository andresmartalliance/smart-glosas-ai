"""Persistent demo-only glosa history. No real patient or IPS data permitted."""
import csv
import hashlib
import io
import os
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import SyntheticGlosa

router = APIRouter(prefix="/api/v1/clara/synthetic", tags=["clara-demonstration"])
DEMO_CSV_HASH = "ac0f7d90cb4709bb024ded2fdb69ed9f70ba237128eb4ae5a596f598db5182aa"
STATES = ("POR_ANALIZAR", "ANALIZADA", "PROPUESTA", "RESPONDIDA")
WEIGHTS = {"POR_ANALIZAR": 0, "ANALIZADA": 50, "PROPUESTA": 75, "RESPONDIDA": 100}


def only_demo():
    if os.getenv("APP_ENV") != "development":
        raise HTTPException(404, "Historial sintético no disponible.")


def now():
    return datetime.now(timezone.utc)


def serialize(row: SyntheticGlosa):
    return {
        "objection_ref": row.objection_ref, "account_ref": row.account_ref,
        "kind": row.kind, "code": row.code, "payer": row.payer,
        "description": row.description, "amount": row.amount,
        "support_state": row.support_state,
        "status": row.status, "findings": row.findings or [],
        "ai_review": row.ai_review,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/history")
def history(db: Session = Depends(get_db)):
    only_demo()
    rows = db.scalars(select(SyntheticGlosa).order_by(SyntheticGlosa.objection_ref)).all()
    counts = {k: sum(1 for row in rows if row.status == k) for k in STATES}
    progress = round(sum(WEIGHTS.get(row.status, 0) for row in rows) / len(rows)) if rows else 0
    return {"synthetic": True, "total": len(rows), "counts": counts,
            "progress": progress, "items": [serialize(row) for row in rows],
            "note": "Avance operacional: 0% cargada, 50% analizada documentalmente, 75% con propuesta y 100% solo al registrar respuesta formal. El demo no marca respuestas como enviadas."}


@router.post("/import")
async def import_demo_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    only_demo()
    content = await file.read(20_000)
    if not file.filename or not file.filename.lower().endswith(".csv") or hashlib.sha256(content).hexdigest() != DEMO_CSV_HASH:
        raise HTTPException(403, "Solo se admite el CSV original de 40 glosas sintéticas.")
    data = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    rows = list(data)
    if len(rows) != 40:
        raise HTTPException(422, "Este banco de prueba debe contener 40 objeciones.")
    fresh = 0
    for row in rows:
        ref = row["objection_ref"]
        if not ref.startswith("OBJ-SYN-") or not row["account_ref"].startswith("CTA-SYN-"):
            raise HTTPException(422, "Identificadores de prueba inválidos.")
        item = db.get(SyntheticGlosa, ref)
        if item is None:
            item = SyntheticGlosa(objection_ref=ref, account_ref=row["account_ref"],
                kind=row["kind"], code=row["code"], payer=row["payer"],
                description=row["description"], amount=int(row["amount"]),
                support_state=row.get("Estado_Soporte", ""), status="POR_ANALIZAR")
            db.add(item)
            fresh += 1
        else:
            item.support_state = row.get("Estado_Soporte", item.support_state)
    db.commit()
    return {"total": 40, "new": fresh, "already_present": 40-fresh,
            "notice": "Las glosas sintéticas ahora quedan guardadas en PostgreSQL sin duplicarse."}


def save_dossier_cases(db: Session, cases: list[dict]):
    """Upsert only evidence from the allowlisted synthetic six-case ZIP."""
    for case in cases:
        ref = case["objection_ref"]
        if not ref or not str(ref).startswith("OBJ-SYN-"):
            continue
        item = db.get(SyntheticGlosa, ref)
        if item is None:
            item = SyntheticGlosa(
                objection_ref=ref, account_ref=case["account_ref"],
                kind=case.get("objection_kind") or "GLOSA", code=case.get("objection_code") or "",
                payer=case.get("payer") or "", description=case.get("objection_description") or "",
                amount=case.get("objected_amount") or 0,
                support_state="REVISADO_EN_EXPEDIENTE", status="POR_ANALIZAR")
            db.add(item)
        item.findings = case.get("findings") or []
        # Never downgrade a later state after re-upload.
        if item.status == "POR_ANALIZAR":
            item.status = "ANALIZADA"
        item.updated_at = now()
    db.commit()


def save_clara_review(db: Session, ref: str, ai: dict):
    item = db.get(SyntheticGlosa, ref)
    if item is None:
        return
    item.ai_review = ai
    # A Gemini summary is not a formal response; a draft advances only to proposal.
    if ai.get("draft"):
        if item.status not in ("RESPONDIDA",):
            item.status = "PROPUESTA"
    elif item.status == "POR_ANALIZAR":
        item.status = "ANALIZADA"
    item.updated_at = now()
    db.commit()
