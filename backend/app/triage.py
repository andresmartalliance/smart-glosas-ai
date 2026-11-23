"""Initial objection routing based on EPS metadata.

These are evidence requests, not legal decisions, tariff decisions, or clinical
audits. They are intended to work with any payer, institution and imported file.
Rules and verified supporting documents are evaluated in a separate step.
"""
from .models import ObjectionCase

NEEDS_BY_FAMILY = {
    "FA": ("Facturación", ["Factura detallada", "Detalle de servicios cobrados",
                          "Soportes de prestación relacionados con el ítem objetado"]),
    "TA": ("Tarifas", ["Contrato vigente y su modalidad", "Anexo tarifario aplicable",
                      "Detalle de factura por servicio y valor"]),
    "SO": ("Soportes", ["Documento requerido según la causal", "Constancia de entrega del soporte",
                       "Factura o cuenta a la que corresponde"]),
    "AU": ("Autorizaciones", ["Autorización o evidencia de excepción aplicable",
                            "Solicitud y respuesta del pagador cuando existan",
                            "Servicios y fechas realmente prestados"]),
    "CO": ("Cobertura", ["Derechos vigentes en la fecha de atención",
                       "Responsable contractual del pago", "Datos de la atención"]),
    "CL": ("Auditoría clínica", ["Historia clínica pertinente", "Órdenes y evolución",
                                "Revisión por profesional de auditoría clínica"]),
    "SA": ("Seguimiento contractual", ["Contrato y modalidad de pago", "Actas de seguimiento",
                                      "Criterios de evaluación del acuerdo"]),
    "DE": ("Devolución", ["Comunicación de devolución", "Factura y datos de radicación",
                         "Documentos exigidos y oportunidad de la comunicación"])
}
DEFAULT_NEEDS = [
    "Comunicación original de la objeción",
    "Factura y detalle facturado",
    "Soportes específicos del servicio",
    "Regla y contrato aplicables al caso"
]


def triage_case(case: ObjectionCase) -> list[dict]:
    code = (case.code or "").strip().upper()
    family = code[:2]
    category, needs = NEEDS_BY_FAMILY.get(family, ("Revisión general", DEFAULT_NEEDS))
    if case.kind == "DEVOLUCION":
        category, needs = NEEDS_BY_FAMILY["DE"]
    issues = [{
        "rule_key": "intake.objection",
        "rule_version": 1,
        "status": "INSUFFICIENT",
        "category": category,
        "severity": "MEDIUM",
        "message": (
            f"Glosa recibida con código {code}. "
            if case.kind == "GLOSA" and code else
            f"Devolución recibida con código {code}. "
            if code else "Objeción recibida. "
        ) + "Se requiere contrastar la causal con el expediente y las condiciones aplicables.",
        "recommendation": "Verificar la documentación indicada antes de emitir una respuesta.",
        "source_ref": "Registro de la objeción recibida; soportes por verificar",
        "evidence_verified": False
    }]
    for kind in needs:
        issues.append({
            "rule_key": "intake.missing_evidence",
            "rule_version": 1,
            "status": "INSUFFICIENT",
            "category": "Información requerida",
            "severity": "MEDIUM",
            "message": "Por verificar: " + kind + ".",
            "recommendation": "Asociar y validar el documento cuando sea pertinente al caso.",
            "source_ref": None,
            "evidence_verified": False
        })
    return issues
