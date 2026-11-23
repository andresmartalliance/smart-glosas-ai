"""Clara: document-backed synthetic glosa pilot, with bounded Gemini use.

Strictly limited to the exact, public-to-the-user synthetic ZIP generated for this pilot.
No real account ingestion, no persistent storage, no anonymous general-purpose AI.
"""
import hashlib
import io
import json
import os
import re
import threading
import time
import zipfile
from collections import defaultdict
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from .db import get_db
from .synthetic_history import save_dossier_cases, save_clara_review
from pypdf import PdfReader
from .gemini import generate_review

router = APIRouter(prefix="/api/v1/clara", tags=["clara"])
ALLOWED_ZIP_SHA256 = "f0947959cdaa5f8e9c79472480bb05c74baf8496a58b25ed7babbe7043c1b843"
ZIP_LIMIT = 4_000_000
PER_IP_HOUR = 12
GLOBAL_HOUR = 32
_usage = defaultdict(list)
_lock = threading.Lock()


def _guard():
    if os.getenv("APP_ENV") != "development":
        raise HTTPException(404, "La prueba sintética solo está habilitada en desarrollo.")


async def _archive(file: UploadFile):
    _guard()
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(415, "Selecciona el ZIP de armado de cuentas sintético.")
    payload = await file.read(ZIP_LIMIT + 1)
    if len(payload) > ZIP_LIMIT or hashlib.sha256(payload).hexdigest() != ALLOWED_ZIP_SHA256:
        raise HTTPException(403, "Solo se acepta el paquete sintético de seis cuentas autorizado.")
    try:
        z = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise HTTPException(422, "ZIP no legible.") from None
    members = z.infolist()
    if len(members) > 120 or sum(x.file_size for x in members) > 15_000_000:
        z.close()
        raise HTTPException(422, "Límites de seguridad de documentos excedidos.")
    return z


def _pdf(z: zipfile.ZipFile, name: str) -> str:
    if name not in z.namelist() or z.getinfo(name).file_size > 300_000:
        return ""
    try:
        pdf = PdfReader(io.BytesIO(z.read(name)))
        if pdf.is_encrypted or len(pdf.pages) > 4:
            return ""
        return "\n".join((p.extract_text() or "") for p in pdf.pages)[:9000]
    except (OSError, KeyError, ValueError, TypeError):
        return ""


def _int_match(pattern: str, text: str):
    match = re.search(pattern, text, re.I)
    return int(match.group(1).replace(".", "")) if match else None


def _case(z: zipfile.ZipFile, name: str):
    data = json.loads(z.read(name))
    ref = data["cuenta"]
    prefix = name.rsplit("/", 1)[0] + "/"
    obj = data.get("objecion_relacionada") or {}
    docs = data.get("documentos") or []
    doc_states = {d["tipo"]: d for d in docs}
    document_list = []
    texts = {}
    for d in docs:
        filename = d.get("ruta")
        state = d.get("estado", "DESCONOCIDO")
        is_present = bool(filename and prefix + filename in z.namelist())
        document_list.append({
            "name": d["tipo"], "filename": filename, "state": state, "present": is_present
        })
        if is_present and filename.endswith(".pdf"):
            texts[d["tipo"]] = _pdf(z, prefix + filename)
    items = data.get("lineas_factura") or []
    invoice_total = sum(int(x["subtotal"]) for x in items)
    invoice_value = int(data.get("valor_facturado") or 0)
    objection_value = int(obj.get("valor") or 0)
    claims = []

    def finding(category: str, statement: str, sources: list[str], severity="REVISION"):
        claims.append({
            "category": category, "status": "REVIEW",
            "message": statement, "source_ref": " / ".join(sources),
            "severity": severity,
            "recommendation": "Verificar los documentos originales, condiciones aplicables y vigencia antes de responder."
        })

    if invoice_total != invoice_value:
        finding("Facturación", f"Total líneas: {invoice_total}; total de cuenta: {invoice_value}.",
                ["00_cuenta_integrada.json", "01_factura_ilustrativa.pdf"])

    missing = [d for d in document_list if d["state"] == "FALTANTE" or
               (d["state"] not in ("NO_APLICA", "FALTANTE") and not d["present"])]
    for d in missing:
        finding("Soportes", f"El documento {d['name']} figura faltante en el expediente.",
                ["00_cuenta_integrada.json", "12_indice_documental.csv"])

    day_item = next((x for x in items if x.get("codigo_interno") == "OBS_HOSP"), None)
    billed_days = int(day_item["cantidad"]) if day_item else None
    unit_day_value = int(day_item["valor_unitario"]) if day_item else None
    note_refs = set(re.findall(r"NOTA-SYN-\d+-\d+", texts.get("EVOLUCIONES_CLINICAS", "")))
    notes_count = len(note_refs) if note_refs else None
    if billed_days is not None and notes_count is not None and billed_days > notes_count:
        finding("Evoluciones clínicas",
                f"Factura: {billed_days} días; evoluciones halladas en PDF: {notes_count} registros.",
                ["01_factura_ilustrativa.pdf", "08_evoluciones_clinicas.pdf"])
    authorization = data.get("autorizacion") or {}
    days_auth = authorization.get("cantidad_autorizada_dias")
    if (isinstance(days_auth, int) and billed_days is not None
            and billed_days > days_auth):
        finding("Autorizaciones",
                f"Factura: {billed_days} días; autorización adjunta: {days_auth} días. Verificar prórroga o excepciones.",
                ["04_autorizacion.pdf", "01_factura_ilustrativa.pdf"])
    if unit_day_value is not None and obj.get("codigo", "")[:2] in ("FA", "AU", "CL"):
        if unit_day_value != objection_value:
            finding("Conciliación de valores",
                    f"Valor unitario del día: {unit_day_value} COP; valor objetado: {objection_value} COP. No son equivalentes.",
                    ["01_factura_ilustrativa.pdf", "00_cuenta_integrada.json"])

    contract = texts.get("CONTRATO", "")
    annex = texts.get("ANEXO_TARIFARIO", "")
    contract_rate = _int_match(r"Tarifa consulta \(extracto\)\s*COP\s*([\d.]+)", contract)
    annex_rate = _int_match(r"Tarifa de consulta\s*COP\s*([\d.]+)", annex)
    consultation = next((x for x in items if x.get("codigo_interno") == "CONS"), None)
    if contract_rate is not None and annex_rate is not None and contract_rate != annex_rate:
        statement = f"Contrato simulado: {contract_rate} COP; anexo borrador: {annex_rate} COP"
        if consultation:
            statement += f"; consulta facturada: {int(consultation['valor_unitario'])} COP."
        finding("Tarifas", statement + " No existe tarifa firmada verificada.",
                ["13_contrato_sintetico.pdf", "14_anexo_tarifario_sintetico.pdf", "01_factura_ilustrativa.pdf"])

    payers = sorted({v.get("entidad_responsable", "") for v in data.get("componente_derechos", [])
                     if v.get("entidad_responsable")})
    if len(payers) > 1:
        finding("Derechos",
                "Consultas de derechos con pagadores diferentes: " + ", ".join(payers) + ".",
                ["03_validacion_derechos.pdf", "00_cuenta_integrada.json"])

    if str(obj.get("codigo", "")).startswith("CL"):
        finding("Pertinencia clínica", "La pertinencia no se deduce de la ausencia de una evolución; requiere auditor clínico.",
                ["08_evoluciones_clinicas.pdf", "09_epicrisis.pdf"])
    if str(obj.get("tipo", "")) == "DEVOLUCION":
        finding("Devoluciones", "Revisar responsable de pago y fechas; no hay constancia de radicación oficial.",
                ["03_validacion_derechos.pdf", "11_trazabilidad.pdf"])
    if not data.get("cuv_oficial") or not data.get("cufe_oficial"):
        # Informative, not grounds to accept any objection.
        claims.append({
            "category": "Validación oficial", "status": "INSUFFICIENT",
            "message": "Este paquete de prueba no tiene CUFE/CUV ni radicación oficial.",
            "source_ref": "00_cuenta_integrada.json", "severity": "INFORMATIVA",
            "recommendation": "No calcular términos legales ni tratar la factura simulada como radicada."
        })

    if not claims:
        claims.append({
            "category": "Evidencia", "status": "INSUFFICIENT",
            "message": "No se detectó inconsistencia con los controles disponibles.",
            "source_ref": "00_cuenta_integrada.json", "severity": "INFORMATIVA",
            "recommendation": "La ausencia de alertas no comprueba que la objeción sea improcedente."
        })
    return {
        "account_ref": ref, "invoice_ref": data.get("factura"), "payer": data.get("pagador"),
        "objection_ref": obj.get("referencia"), "objection_kind": obj.get("tipo"),
        "objection_code": obj.get("codigo"), "objection_description": obj.get("descripcion"),
        "billed_amount": invoice_value, "objected_amount": objection_value,
        "documents": document_list,
        "findings": claims, "status": "PENDIENTE_AUDITOR", "synthetic": True,
        "case_data": {"phase": "RESPOND", "summary": "REVIEW_REQUIRED",
                      "objection_kind": obj.get("tipo"), "objection_code": obj.get("codigo"),
                      "objection_description": obj.get("descripcion"), "findings": claims,
                      "evidence_references": [
                        {"kind": d["name"]} for d in document_list if d["present"]]},
    }


def _all_cases(z):
    names = sorted(n for n in z.namelist() if n.endswith("/00_cuenta_integrada.json")
                   and "/Cuentas/CTA-SYN-" in n)
    if len(names) != 6:
        raise HTTPException(422, "El paquete debe contener exactamente seis cuentas.")
    return [_case(z, n) for n in names]


def _rate_limit(ip: str):
    now = time.monotonic()
    with _lock:
        for key in (ip, "_all"):
            _usage[key] = [x for x in _usage[key] if now-x < 3600]
        if len(_usage[ip]) >= PER_IP_HOUR or len(_usage["_all"]) >= GLOBAL_HOUR:
            raise HTTPException(429, "Se agotó el límite de consultas de esta prueba. Vuelve a intentarlo más tarde.")
        _usage[ip].append(now)
        _usage["_all"].append(now)


@router.get("/status")
def status():
    return {"agent": "Clara", "enabled": os.getenv("APP_ENV") == "development",
            "gemini_available": bool(os.getenv("GEMINI_API_KEY", "").strip()),
            "demo_only": True, "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash")}


@router.post("/synthetic/inspect")
async def inspect(file: UploadFile = File(...), db: Session = Depends(get_db)):
    z = await _archive(file)
    with z:
        cases = _all_cases(z)
    save_dossier_cases(db, cases)
    for item in cases:
        item.pop("case_data", None)
    return {"agent": "Clara", "mode": "evidence_checks", "total": len(cases),
            "accounts": cases, "gemini_used": False,
            "notice": "Revisión documental sintética. Los hallazgos son preliminares y deben ser verificados por auditor."}


@router.post("/synthetic/ai-review")
async def ai_review(request: Request, file: UploadFile = File(...), account_ref: str = Form(...), db: Session = Depends(get_db)):
    z = await _archive(file)
    with z:
        match = next((item for item in _all_cases(z) if item["account_ref"] == account_ref), None)
    if match is None:
        raise HTTPException(404, "Cuenta sintética no encontrada.")
    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise HTTPException(503, "Clara no tiene una clave Gemini configurada.")
    _rate_limit(request.client.host if request.client else "unknown")
    ai = generate_review(match["case_data"])
    ai["agent"] = "Clara"
    save_dossier_cases(db, [match])
    save_clara_review(db, match["objection_ref"], ai)
    return {"account_ref": account_ref, "objection_ref": match["objection_ref"],
            "review": ai, "findings": match["findings"],
            "note": "Borrador generado con Gemini sobre hechos sintéticos extraídos del expediente. Revisión humana obligatoria."}
