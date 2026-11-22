"""Transparent, data-driven checks. No asserted probabilities or invented legal decisions."""
from typing import Any
from .schemas import RuleDefinition, RuleCheck, AccountInput, ObjectionInput

MISSING = object()

def extract(data: dict, path: str):
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value

def check_value(check: RuleCheck, facts: dict) -> bool | None:
    value = extract(facts, check.field)
    if check.operator == "exists":
        return value is not MISSING and value is not None and value != ""
    if value is MISSING or value is None:
        return None
    try:
        expected = check.value
        if check.operator == "eq": return value == expected
        if check.operator == "neq": return value != expected
        if check.operator == "in": return value in expected
        if check.operator == "gte": return value >= expected
        if check.operator == "lte": return value <= expected
        if check.operator == "gt": return value > expected
        if check.operator == "lt": return value < expected
    except (TypeError, ValueError, KeyError):
        return None
    return None

def apply_rules(account: AccountInput, rule_versions: list[tuple[RuleDefinition, int]],
                phase: str, objection: ObjectionInput | None = None) -> dict:
    context = dict(account.facts)
    # Canonical identity attributes are kept separate from arbitrary uploaded facts.
    context.update({"account_ref": account.account_ref, "payer": account.payer,
        "modality": account.modality, "service_type": account.service_type})
    if objection:
        context["objection"] = {"kind": objection.kind, "code": objection.code,
                                  "description": objection.description,
                                  "amount": str(objection.amount) if objection.amount is not None else None,
                                  **objection.facts}
    properties = {"payer": account.payer, "modality": account.modality,
                  "service_type": account.service_type,
                  "objection_kind": objection.kind if objection else None,
                  "objection_code": objection.code if objection else None}
    document_types = {e.kind.casefold() for e in account.evidence}
    findings = []
    seen = []
    for rule, version in rule_versions:
        if rule.phase not in (phase, "BOTH"):
            continue
        if any(properties.get(k) is None or str(properties[k]).casefold() != v.casefold()
               for k, v in rule.scope.items()):
            continue
        day = account.issued_on
        if (rule.effective_from or rule.effective_until) and day is None:
            seen.append({"key": rule.rule_key, "version": version})
            findings.append(_finding(rule, version, "INSUFFICIENT", "Falta fecha de factura para determinar vigencia de la regla"))
            continue
        if day is not None:
            if rule.effective_from and day < rule.effective_from: continue
            if rule.effective_until and day > rule.effective_until: continue
        if rule.when:
            condition = check_value(rule.when, context)
            if condition is False: continue
            if condition is None:
                findings.append(_finding(rule, version, "INSUFFICIENT", "No se puede verificar la condición de aplicación"))
                seen.append({"key": rule.rule_key, "version": version})
                continue
        seen.append({"key": rule.rule_key, "version": version})
        absent = [kind for kind in rule.evidence_kinds if kind.casefold() not in document_types]
        if absent:
            findings.append(_finding(rule, version, "INSUFFICIENT", "Falta evidencia necesaria para evaluar esta regla: " + ", ".join(absent)))
            continue
        passed = check_value(rule.check, context)
        status = "PASSED" if passed is True else "REVIEW" if passed is False else "INSUFFICIENT"
        findings.append(_finding(rule, version, status,
                                 rule.finding if passed is False else "Información insuficiente para verificar esta regla" if passed is None else "Verificación superada"))
    flagged = sum(f["status"] == "REVIEW" for f in findings)
    missing = sum(f["status"] == "INSUFFICIENT" for f in findings)
    summary = "REVIEW_REQUIRED" if flagged else "INSUFFICIENT_EVIDENCE" if missing else "NO_RULES" if not seen else "NO_ALERTS_DETECTED"
    return {"phase": phase, "account_ref": account.account_ref, "payer": account.payer,
            "summary": summary, "findings": findings, "rules_applied": seen,
            "counts": {"review": flagged, "insufficient": missing,
                       "passed": sum(f["status"] == "PASSED" for f in findings)},
            "probability": None, "requires_human_review": True,
            "note": "Un analisis sin alertas no garantiza ausencia de glosas o devoluciones."}

def _finding(rule: RuleDefinition, version: int, status: str, message: str):
    return {"rule_key": rule.rule_key, "rule_version": version,
            "category": rule.category, "severity": rule.severity,
            "status": status, "message": message,
            "recommendation": rule.recommendation if status != "PASSED" else None,
            "source_ref": rule.source_ref}

def respond(objection: ObjectionInput, versions: list[tuple[RuleDefinition, int]]) -> dict:
    result = apply_rules(objection.account, versions, "RESPOND", objection)
    result["objection_ref"] = objection.objection_ref
    result["objection_kind"] = objection.kind
    result["objection_code"] = objection.code
    result["amount"] = str(objection.amount) if objection.amount is not None else None
    result["suggested_action"] = "HUMAN_REVIEW"
    # Generate a draft ONLY from an institutionally authored/versioned response
    # template attached to a matching rule and backed by required evidence.
    # Never turn generic model output into a final accepted/contested legal decision.
    selected = []
    by_key_version = {(r.rule_key, ver): r for r, ver in versions}
    for finding in result["findings"]:
        if finding["status"] != "REVIEW":
            continue
        rule = by_key_version.get((finding["rule_key"], finding["rule_version"]))
        if not rule or not rule.response_template or not rule.response_action:
            continue
        if not rule.source_ref or not rule.evidence_kinds:
            continue
        template = rule.response_template
        replacements = {"account_ref": objection.account.account_ref,
                        "objection_ref": objection.objection_ref,
                        "objection_code": objection.code or "Sin código",
                        "payer": objection.account.payer or "No informado"}
        for key, value in replacements.items():
            template = template.replace("{{" + key + "}}", value)
        selected.append({"action": rule.response_action, "text": template,
                         "rule_key": rule.rule_key,
                         "source_ref": rule.source_ref,
                         "supporting_evidence": [
                           {"id": e.id, "kind": e.kind, "reference": e.reference}
                           for e in objection.account.evidence
                           if e.kind.casefold() in {k.casefold() for k in rule.evidence_kinds}]})
    result["draft_options"] = selected
    result["response_draft"] = selected[0]["text"] if len(selected) == 1 else None
    result["correction_draft"] = None
    if len(selected) == 1:
        result["suggested_action"] = selected[0]["action"]
    result["evidence_references"] = [{"id": e.id, "kind": e.kind, "reference": e.reference}
                                      for e in objection.account.evidence]
    return result
