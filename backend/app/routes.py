"""IPS-first endpoints. No transmission to EPS, no autonomous legal acceptance."""
import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .auth import Actor, current_email, actor, require_admin
from .db import get_db
from .models import Tenant, Membership, RuleVersion, MappingProfile, Analysis, AuditEvent
from .schemas import (TenantInput, RuleDefinition, MappingDefinition,
                      AccountInput, ObjectionInput, PreventBatch, RespondBatch)
from .engine import apply_rules, respond
from .importers import read_rows, normalize, normalize_objections

router = APIRouter(prefix="/api/v1", tags=["smart-glosas"])

def log(db: Session, user: Actor, action: str, subject_id: str, details: dict | None = None):
    db.add(AuditEvent(tenant_id=user.tenant_id, actor=user.email, action=action,
                      subject_id=subject_id, details=details or {}))

def active_rules(db: Session, tenant_id: str):
    versions = db.scalars(select(RuleVersion).where(
        RuleVersion.tenant_id == tenant_id, RuleVersion.active.is_(True))).all()
    return [(RuleDefinition.model_validate(r.body), r.version) for r in versions], versions

@router.get("/config")
def config():
    return {"google_client_id": os.getenv("SMART_GOOGLE_CLIENT_ID", ""),
            "product": "Smart Glosas AI", "version": "0.1.0",
            "autonomous_submission": False}

@router.get("/session")
def session(email: str = Depends(current_email), db: Session = Depends(get_db)):
    memberships = db.scalars(select(Membership).join(Tenant, Tenant.id == Membership.tenant_id).where(
        Membership.email == email, Membership.active.is_(True), Tenant.active.is_(True))).all()
    names = {t.id: t.name for t in db.scalars(select(Tenant).where(Tenant.id.in_([m.tenant_id for m in memberships]))).all()}
    return {"email": email,
            "institutions": [{"id": m.tenant_id, "name": names[m.tenant_id], "roles": m.roles} for m in memberships],
            "can_create_institution": os.getenv("APP_ENV", "development") == "development"
            and email in {x.strip().lower() for x in os.getenv("SMART_GLOSAS_BOOTSTRAP_EMAILS", "").split(",")}}

@router.post("/institutions", status_code=201)
def create_institution(body: TenantInput, email: str = Depends(current_email), db: Session = Depends(get_db)):
    permitted = {x.strip().lower() for x in os.getenv("SMART_GLOSAS_BOOTSTRAP_EMAILS", "").split(",") if x.strip()}
    if os.getenv("APP_ENV", "development") != "development" or email not in permitted:
        raise HTTPException(403, "Creación de instituciones no habilitada para esta cuenta")
    tenant = Tenant(name=body.name.strip())
    db.add(tenant); db.flush()
    db.add(Membership(tenant_id=tenant.id, email=email, roles=["ADMIN", "CONFIGURADOR", "AUDITOR"]))
    db.add(AuditEvent(tenant_id=tenant.id, actor=email, action="TENANT_CREATED", subject_id=tenant.id, details={}))
    db.commit()
    return {"id": tenant.id, "name": tenant.name}

@router.get("/rules")
def list_rules(user: Actor = Depends(actor), db: Session = Depends(get_db)):
    rows = db.scalars(select(RuleVersion).where(
        RuleVersion.tenant_id == user.tenant_id, RuleVersion.active.is_(True))
        .order_by(RuleVersion.rule_key)).all()
    return [{**r.body, "id": r.id, "version": r.version} for r in rows]

@router.post("/rules", status_code=201)
def put_rule(body: RuleDefinition, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    require_admin(user)
    current = db.scalar(select(RuleVersion).where(
        RuleVersion.tenant_id == user.tenant_id, RuleVersion.rule_key == body.rule_key,
        RuleVersion.active.is_(True)).with_for_update())
    latest = db.scalar(select(func.max(RuleVersion.version)).where(
        RuleVersion.tenant_id == user.tenant_id, RuleVersion.rule_key == body.rule_key)) or 0
    if current:
        current.active = False
    record = RuleVersion(tenant_id=user.tenant_id, rule_key=body.rule_key, version=latest + 1,
                         body=body.model_dump(mode="json"), created_by=user.email)
    db.add(record); db.flush()
    log(db, user, "RULE_VERSION_CREATED", record.id, {"key": body.rule_key, "version": record.version})
    db.commit()
    return {"id": record.id, "key": body.rule_key, "version": record.version, "active": True}

@router.get("/mappings")
def list_mappings(user: Actor = Depends(actor), db: Session = Depends(get_db)):
    profiles = db.scalars(select(MappingProfile).where(
        MappingProfile.tenant_id == user.tenant_id, MappingProfile.active.is_(True))).all()
    return [{"id": p.id, "name": p.name, "version": p.version,
             "source_type": p.source_type, "columns": p.columns} for p in profiles]

@router.post("/mappings", status_code=201)
def save_mapping(body: MappingDefinition, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    require_admin(user)
    if "account_ref" not in body.columns:
        raise HTTPException(422, "Debes mapear account_ref")
    for target in body.columns:
        if target not in {"account_ref", "payer", "modality", "service_type", "issued_on"} and not target.startswith("facts."):
            raise HTTPException(422, "Destino no soportado: " + target)
    prior = db.scalars(select(MappingProfile).where(
        MappingProfile.tenant_id == user.tenant_id, MappingProfile.name == body.name)
        .with_for_update()).all()
    for p in prior: p.active = False
    version = max((p.version for p in prior), default=0) + 1
    row = MappingProfile(tenant_id=user.tenant_id, name=body.name, version=version,
                         source_type=body.source_type, columns=body.columns)
    db.add(row); db.flush()
    log(db, user, "MAPPING_VERSION_CREATED", row.id, {"name": row.name, "version": version})
    db.commit()
    return {"id": row.id, "name": row.name, "version": version}

@router.post("/imports/preview")
async def import_preview(file: UploadFile = File(...), mapping_id: str | None = Form(default=None),
                         mapping_json: str | None = Form(default=None),
                         user: Actor = Depends(actor), db: Session = Depends(get_db)):
    content = await file.read(4_000_001)
    keys, rows = read_rows(content, file.filename or "")
    if mapping_id:
        profile = db.scalar(select(MappingProfile).where(
            MappingProfile.id == mapping_id, MappingProfile.tenant_id == user.tenant_id,
            MappingProfile.active.is_(True)))
        if not profile: raise HTTPException(404, "Mapeo no encontrado")
        columns = profile.columns
    elif mapping_json:
        try:
            columns = json.loads(mapping_json)
            if not isinstance(columns, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in columns.items()):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Mapeo JSON inválido") from None
    else:
        # Introspection never silently guesses a field mapping.
        return {"columns": keys, "rows_detected": len(rows), "requires_mapping": True,
                "example": {"account_ref": "Columna ID de cuenta", "facts.authorization.number": "Columna autorización"}}
    result = normalize(rows, columns)
    return {"columns": keys, "requires_mapping": False, "mapping": columns, **result}

@router.post("/imports/objections/preview")
async def objections_import_preview(file: UploadFile = File(...), mapping_json: str | None = Form(default=None),
                                    user: Actor = Depends(actor)):
    data = await file.read(4_000_001)
    keys, rows = read_rows(data, file.filename or "")
    if not mapping_json:
        return {"columns": keys, "rows_detected": len(rows), "requires_mapping": True,
                "mandatory": ["objection_ref", "kind", "description", "account_ref"]}
    try:
        columns = json.loads(mapping_json)
        if not isinstance(columns, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in columns.items()):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Mapeo JSON inválido") from None
    return {"columns": keys, "requires_mapping": False, "mapping": columns,
            **normalize_objections(rows, columns)}

def write_analysis(db: Session, user: Actor, phase: str, result: dict, rule_rows: list[RuleVersion]):
    used = {(v["key"], v["version"]) for v in result["rules_applied"]}
    snapshot = [r.body | {"version": r.version} for r in rule_rows if (r.rule_key, r.version) in used]
    row = Analysis(tenant_id=user.tenant_id, phase=phase,
                   account_ref=result["account_ref"], payer=result.get("payer"),
                   objection_ref=result.get("objection_ref"), rules_snapshot=snapshot,
                   result=result, status="PENDING_REVIEW", created_by=user.email)
    db.add(row); db.flush()
    log(db, user, "ANALYSIS_CREATED", row.id, {"phase": phase,
        "rules_count": len(snapshot), "summary": result["summary"]})
    return row

@router.post("/analyses/prevent", status_code=201)
def analyze_prevent(body: PreventBatch, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    versions, rows = active_rules(db, user.tenant_id)
    outputs = []
    for account in body.accounts:
        outcome = apply_rules(account, versions, "PREVENT")
        record = write_analysis(db, user, "PREVENT", outcome, rows)
        outputs.append({"id": record.id, "status": record.status, **outcome})
    db.commit()
    return {"total": len(outputs), "analyses": outputs}

@router.post("/analyses/respond", status_code=201)
def analyze_respond(body: RespondBatch, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    versions, rows = active_rules(db, user.tenant_id)
    outputs = []
    for objection in body.objections:
        outcome = respond(objection, versions)
        record = write_analysis(db, user, "RESPOND", outcome, rows)
        outputs.append({"id": record.id, "status": record.status, **outcome})
    db.commit()
    return {"total": len(outputs), "analyses": outputs}

@router.get("/analyses")
def analyses(phase: str | None = None, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    statement = select(Analysis).where(Analysis.tenant_id == user.tenant_id)
    if phase in {"PREVENT", "RESPOND"}:
        statement = statement.where(Analysis.phase == phase)
    rows = db.scalars(statement.order_by(Analysis.created_at.desc()).limit(100)).all()
    return [{"id": x.id, "phase": x.phase, "account_ref": x.account_ref,
             "payer": x.payer, "objection_ref": x.objection_ref,
             "status": x.status, "summary": x.result.get("summary"),
             "counts": x.result.get("counts"), "created_at": x.created_at.isoformat()} for x in rows]

@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    row = db.scalar(select(Analysis).where(Analysis.id == analysis_id,
        Analysis.tenant_id == user.tenant_id))
    if row is None: raise HTTPException(404, "Análisis no encontrado")
    return {"id": row.id, "status": row.status, "rules_snapshot": row.rules_snapshot,
            "created_at": row.created_at.isoformat(), **row.result}

@router.post("/analyses/{analysis_id}/approve")
def approve_analysis(analysis_id: str, user: Actor = Depends(actor), db: Session = Depends(get_db)):
    if not user.roles.intersection({"ADMIN", "AUDITOR"}):
        raise HTTPException(403, "Se requiere un auditor o administrador")
    row = db.scalar(select(Analysis).where(Analysis.id == analysis_id,
        Analysis.tenant_id == user.tenant_id).with_for_update())
    if row is None: raise HTTPException(404, "Análisis no encontrado")
    if row.status != "PENDING_REVIEW": raise HTTPException(409, "El análisis ya fue revisado")
    row.status = "APPROVED"
    log(db, user, "ANALYSIS_APPROVED", row.id, {"phase": row.phase})
    db.commit()
    return {"id": row.id, "status": row.status,
            "notice": "Aprobación interna registrada. No se ha enviado nada a la EPS."}

def safe_cell(value: Any):
    raw = "" if value is None else str(value)
    # Prevent spreadsheet formula execution on untrusted EPS/IPS text.
    if raw and raw.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + raw
    return raw

@router.get("/exports/analyses.csv")
def export_analyses(user: Actor = Depends(actor), db: Session = Depends(get_db)):
    rows = db.scalars(select(Analysis).where(
        Analysis.tenant_id == user.tenant_id).order_by(Analysis.created_at.desc()).limit(5000)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "fase", "cuenta", "eps", "objecion", "estado", "resultado", "revision", "informacion_insuficiente"])
    for a in rows:
        writer.writerow([safe_cell(a.id), safe_cell(a.phase), safe_cell(a.account_ref),
                         safe_cell(a.payer), safe_cell(a.objection_ref), safe_cell(a.status),
                         safe_cell(a.result.get("summary")), a.result.get("counts", {}).get("review", 0),
                         a.result.get("counts", {}).get("insufficient", 0)])
    output.seek(0)
    return StreamingResponse(iter(["\ufeff" + output.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="smart_glosas_analisis.csv"'})
