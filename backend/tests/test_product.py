import io
from sqlalchemy import select
from app.main import app
from app.auth import current_email
from app.models import RuleVersion, Analysis, AuditEvent

RULE = {
    "rule_key": "contract.tariff.review", "name": "Validación tarifaria contra contrato disponible",
    "phase": "BOTH", "category": "TARIFAS", "scope": {"payer": "EPS X", "modality": "ESPECIAL"},
    "check": {"field": "tariff.matches_contract", "operator": "eq", "value": True},
    "evidence_kinds": ["CONTRATO"], "severity": "HIGH",
    "finding": "El valor facturado no coincide con el valor contractual verificado",
    "recommendation": "Solicitar auditoría de la tarifa y verificar vigencia y anexos",
    "source_ref": "Cláusula contractual verificable, cuando exista"
}

def headers(tenant="ips-a"):
    return {"X-Tenant-Id": tenant}

def account(**options):
    value = {"account_ref": "C-001", "payer": "EPS X", "modality": "ESPECIAL",
             "facts": {"tariff": {"matches_contract": False}},
             "evidence": [{"id": "doc-contrato", "kind": "CONTRATO", "reference": "Doc A"}]}
    value.update(options)
    return value

def create_rule(client, body=None):
    result = client.post("/api/v1/rules", headers=headers(), json=body or RULE)
    assert result.status_code == 201, result.text
    return result.json()

def test_prevention_and_response_share_rule_engine(env):
    client, _ = env
    create_rule(client)
    result = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [account()]})
    assert result.status_code == 201, result.text
    item = result.json()["analyses"][0]
    assert item["summary"] == "REVIEW_REQUIRED"
    assert item["findings"][0]["rule_key"] == RULE["rule_key"]
    assert item["probability"] is None
    assert item["requires_human_review"] is True
    response = client.post("/api/v1/analyses/respond", headers=headers(), json={"objections": [
        {"objection_ref": "G-1", "kind": "GLOSA", "code": "TA-example",
         "description": "Diferencia tarifaria", "account": account()}]})
    assert response.status_code == 201, response.text
    obj = response.json()["analyses"][0]
    assert obj["summary"] == "REVIEW_REQUIRED"
    assert obj["response_draft"] is None
    assert obj["suggested_action"] == "HUMAN_REVIEW"
    assert obj["evidence_references"][0]["id"] == "doc-contrato"


def test_contract_missing_is_insufficient_not_tariff_error(env):
    client, _ = env
    create_rule(client)
    result = client.post("/api/v1/analyses/prevent", headers=headers(), json={
        "accounts": [account(evidence=[])]})
    analysis = result.json()["analyses"][0]
    assert analysis["summary"] == "INSUFFICIENT_EVIDENCE"
    assert analysis["findings"][0]["status"] == "INSUFFICIENT"


def test_new_eps_or_modality_does_not_pick_another_contract_rule(env):
    client, _ = env
    create_rule(client)
    for modified in [account(payer="EPS Z"), account(modality="OTRA")]:
        result = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [modified]})
        assert result.json()["analyses"][0]["summary"] == "NO_RULES"


def test_rules_are_versioned_and_snapshot_immutable(env):
    client, _ = env
    first = create_rule(client)
    prev = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [account()]}).json()
    revised = {**RULE, "finding": "Regla revisada desde el configurador"}
    second = create_rule(client, revised)
    assert first["version"] == 1 and second["version"] == 2
    rows = client.get("/api/v1/rules", headers=headers()).json()
    assert len(rows) == 1 and rows[0]["version"] == 2
    old = client.get("/api/v1/analyses/" + prev["analyses"][0]["id"], headers=headers()).json()
    assert old["rules_snapshot"][0]["version"] == 1
    assert old["rules_snapshot"][0]["finding"] == RULE["finding"]


def test_tenants_cannot_read_each_others_cases_or_rules(env):
    client, _ = env
    create_rule(client)
    ident = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [account()]}).json()["analyses"][0]["id"]
    app.dependency_overrides[current_email] = lambda: "other@example.com"
    assert client.get("/api/v1/rules", headers=headers("ips-b")).json() == []
    assert client.get("/api/v1/analyses/"+ident, headers=headers("ips-b")).status_code == 404
    assert client.get("/api/v1/analyses", headers=headers("ips-a")).status_code == 403


def test_account_requires_auth_and_tenant(env):
    client, _ = env
    assert client.get("/api/v1/rules").status_code == 400
    app.dependency_overrides[current_email] = lambda: "unknown@example.com"
    assert client.get("/api/v1/rules", headers=headers()).status_code == 403


def test_import_arbitrary_csv_mapping_without_eps_hardcodes(env):
    client, _ = env
    data = b"Referencia,PAGADOR,TIPO,URL\nF-111,EPS NO PREDEFINIDA,Paquete,ABC\n"
    preliminary = client.post("/api/v1/imports/preview", headers=headers(), files={"file": ("archivo.csv", data)})
    assert preliminary.status_code == 200
    assert preliminary.json()["requires_mapping"] is True
    import json
    mapping = {"account_ref": "Referencia", "payer": "PAGADOR", "modality": "TIPO", "facts.authorization.code": "URL"}
    converted = client.post("/api/v1/imports/preview", headers=headers(),
        files={"file": ("archivo.csv", data)}, data={"mapping_json": json.dumps(mapping)})
    assert converted.status_code == 200, converted.text
    row = converted.json()["rows"][0]
    assert row["payer"] == "EPS NO PREDEFINIDA"
    assert row["facts"]["authorization"]["code"] == "ABC"
    result = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": converted.json()["rows"]})
    assert result.status_code == 201


def test_approval_is_audited_but_does_not_send_to_eps(env):
    client, db_factory = env
    result = client.post("/api/v1/analyses/respond", headers=headers(), json={"objections": [
        {"objection_ref": "G1", "kind": "DEVOLUCION", "description": "Revisión documental", "account": account()}]})
    identifier = result.json()["analyses"][0]["id"]
    approval = client.post(f"/api/v1/analyses/{identifier}/approve", headers=headers())
    assert approval.status_code == 200
    assert approval.json()["status"] == "APPROVED"
    assert "No se ha enviado" in approval.json()["notice"]
    assert client.post(f"/api/v1/analyses/{identifier}/approve", headers=headers()).status_code == 409
    with next(db_factory()) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "ANALYSIS_APPROVED")) is not None


def test_no_predicted_probability_for_empty_rule_catalog(env):
    client, _ = env
    response = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [account()]})
    assert response.json()["analyses"][0]["summary"] == "NO_RULES"
    assert response.json()["analyses"][0]["probability"] is None


def test_batch_500_supported_and_excess_rejected(env):
    client, _ = env
    batch = [account(account_ref=f"C-{i}") for i in range(500)]
    assert client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": batch}).status_code == 201
    assert client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": batch+[account()]}).status_code == 422


def test_csv_formula_injection_not_exported_as_formula(env):
    client, _ = env
    client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [account(account_ref="=1+1")]})
    csv_download = client.get("/api/v1/exports/analyses.csv", headers=headers())
    assert csv_download.status_code == 200
    assert "'=1+1" in csv_download.text


def test_bootstrap_requires_authorized_google_user(env, monkeypatch):
    client, _ = env
    monkeypatch.setenv("SMART_GLOSAS_BOOTSTRAP_EMAILS", "admin@example.com")
    created = client.post("/api/v1/institutions", json={"name": "Nueva IPS"})
    assert created.status_code == 201
    app.dependency_overrides[current_email] = lambda: "unknown@example.com"
    assert client.post("/api/v1/institutions", json={"name": "IPS Falsa"}).status_code == 403


def test_massive_eps_objection_import_and_response(env):
    client, _ = env
    data = b"ID,CLASE,MOTIVO,CUNTA,EPS\nG-77,G,Observacion,CA-7,EPS 1\nD-78,D,Datos erroneos,CA-8,EPS 2\n"
    import json
    mapping = {"objection_ref": "ID", "kind": "CLASE", "description": "MOTIVO",
               "account_ref": "CUNTA", "payer": "EPS"}
    res = client.post("/api/v1/imports/objections/preview", headers=headers(),
        files={"file": ("glosas.csv", data)}, data={"mapping_json": json.dumps(mapping)})
    assert res.status_code == 200, res.text
    parsed = res.json()["rows"]
    assert [r["kind"] for r in parsed] == ["GLOSA", "DEVOLUCION"]
    run = client.post("/api/v1/analyses/respond", headers=headers(), json={"objections": parsed})
    assert run.status_code == 201 and run.json()["total"] == 2


def test_response_template_requires_audited_source_and_evidence(env):
    client, _ = env
    with_template = {**RULE, "response_action": "CONTROVERTIR",
                     "response_template": "Cuenta {{account_ref}}, revisar glosa {{objection_ref}} según contrato"}
    create_rule(client, with_template)
    objection = {"objection_ref": "G-02", "kind": "GLOSA", "description": "Objeción tarifaria",
                 "account": account()}
    res = client.post("/api/v1/analyses/respond", headers=headers(), json={"objections": [objection]})
    result = res.json()["analyses"][0]
    assert result["suggested_action"] == "CONTROVERTIR"
    assert "C-001" in result["response_draft"]
    assert result["draft_options"][0]["supporting_evidence"][0]["id"] == "doc-contrato"
    objection["account"]["evidence"] = []
    missing = client.post("/api/v1/analyses/respond", headers=headers(), json={"objections": [objection]})
    assert missing.json()["analyses"][0]["response_draft"] is None


def test_rule_with_effective_date_never_guesses_missing_invoice_date(env):
    client, _ = env
    rule = {**RULE, "effective_from": "2026-06-01", "effective_until": "2026-12-31"}
    create_rule(client, rule)
    missing = client.post("/api/v1/analyses/prevent", headers=headers(), json={"accounts": [account()]})
    assert missing.json()["analyses"][0]["summary"] == "INSUFFICIENT_EVIDENCE"
    older = client.post("/api/v1/analyses/prevent", headers=headers(), json={
        "accounts": [account(issued_on="2025-12-01")]})
    assert older.json()["analyses"][0]["summary"] == "NO_RULES"
    recent = client.post("/api/v1/analyses/prevent", headers=headers(), json={
        "accounts": [account(issued_on="2026-07-01")]})
    assert recent.json()["analyses"][0]["summary"] == "REVIEW_REQUIRED"


def test_rule_does_not_accept_invalid_in_condition(env):
    client, _ = env
    rule = {**RULE, "check": {"field": "tariff.code", "operator": "in", "value": "ABC"}}
    response = client.post("/api/v1/rules", headers=headers(), json=rule)
    assert response.status_code == 422


def test_objection_parser_rejects_unrecognized_type(env):
    client, _ = env
    import json
    form = {"objection_ref":"ID", "kind":"TIPO", "description":"MOTIVO", "account_ref":"CUENTA"}
    response = client.post('/api/v1/imports/objections/preview',headers=headers(),
        files={"file": ("glosas.csv", b"ID,TIPO,MOTIVO,CUENTA\nA,OTRO,Texto,C1\n")},
        data={"mapping_json":json.dumps(form)})
    assert response.status_code == 200
    assert response.json()["accepted"] == 0
    assert response.json()["errors"][0]["row"] == 1
