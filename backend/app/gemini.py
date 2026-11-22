"""Gemini review of sanitized rule findings. Never sends attachments or raw patient facts."""
import json
import os
import re
import httpx
from fastapi import HTTPException

VALID_MODEL = re.compile(r"^[A-Za-z0-9._-]{3,70}$")

def redact(value: str | None) -> str:
    text = str(value or "")[:1500]
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[CORREO]", text)
    text = re.sub(r"(?<!\w)\+?\d[\d .()-]{7,}\d(?!\w)", "[IDENTIFICADOR]", text)
    text = re.sub(r"\b(?:CC|TI|CE|NIT|HC|CEDULA|DOCUMENTO|PACIENTE)\s*[:#-]?\s*\d{4,}\b", "[IDENTIFICADOR]", text, flags=re.I)
    return text

def prepare_context(result: dict) -> dict:
    return {
        "phase": result.get("phase"),
        "summary": result.get("summary"),
        "objection_kind": result.get("objection_kind"),
        "objection_code": redact(result.get("objection_code"))[:30],
        "objection_description": redact(result.get("objection_description")),
        "findings": [
            {"category": redact(f.get("category"))[:80], "status": f.get("status"),
             "message": redact(f.get("message")), "recommendation": redact(f.get("recommendation")),
             "source_ref": redact(f.get("source_ref"))}
            for f in result.get("findings", [])[:30]
        ],
        "evidence_kinds": sorted({redact(e.get("kind"))[:80] for e in result.get("evidence_references", [])}),
    }

def generate_review(result: dict) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Gemini no esta configurado en este servicio")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not VALID_MODEL.fullmatch(model):
        raise HTTPException(503, "Modelo Gemini invalido")
    context = prepare_context(result)
    instruction = (
        "Eres Clara, agente especializado de Smart Glosas AI en Colombia. Apoyas a las IPS en prevencion y contestacion de glosas y gestion de devoluciones. "
        "Solo analiza los hallazgos, referencias y descripcion anonimizada suministrados. "
        "No inventes normas, contratos, tarifas, evidencias, decisiones ni probabilidades. "
        "Distingue devolucion de glosa. No afirmes improcedencia sin una fuente verificada. "
        "Responde estrictamente en JSON: resumen (texto), accion_sugerida "
        "(REVISION, CONTROVERTIR, SUBSANAR, ACEPTAR o ESCALAR), informacion_faltante (lista de textos), "
        "propuesta_borrador (texto o null), advertencias (lista de textos). "
        "Cualquier respuesta propuesta es borrador sujeto a validacion humana.")
    try:
        with httpx.Client(timeout=28.0) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"systemInstruction": {"parts": [{"text": instruction}]},
                      "contents": [{"role": "user", "parts": [{"text": json.dumps(context, ensure_ascii=False)}]}],
                      "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200,
                                           "responseMimeType": "application/json"}})
            response.raise_for_status()
            payload = response.json()
            raw = "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
            parsed = json.loads(raw)
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        raise HTTPException(502, "Gemini no pudo completar el analisis") from None
    if not isinstance(parsed, dict):
        raise HTTPException(502, "Respuesta de Gemini invalida")
    action = str(parsed.get("accion_sugerida", "REVISION")).upper()
    if action not in {"REVISION", "CONTROVERTIR", "SUBSANAR", "ACEPTAR", "ESCALAR"}:
        action = "REVISION"
    grounded = any(f.get("source_ref") and f.get("status") == "REVIEW" for f in context["findings"])
    draft = parsed.get("propuesta_borrador") if context["phase"] == "RESPOND" and grounded else None
    missing = parsed.get("informacion_faltante", [])
    warnings = parsed.get("advertencias", [])
    return {"agent": "Clara", "provider": "gemini", "model": model, "summary": str(parsed.get("resumen", ""))[:2500],
            "suggested_action": action, "draft": str(draft)[:4000] if draft else None,
            "missing_information": [str(v)[:400] for v in missing[:12]] if isinstance(missing, list) else [],
            "warnings": [str(v)[:400] for v in warnings[:12]] if isinstance(warnings, list) else [],
            "requires_human_review": True,
            "note": "Propuesta de IA; no constituye glosa validada ni respuesta enviada."}
