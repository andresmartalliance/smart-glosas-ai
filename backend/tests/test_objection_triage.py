"""Proof that batch triage is real, scoped, idempotent and never fabricates evidence."""
from app.main import app
from app.auth import current_email
from sqlalchemy import select
from app.models import ObjectionCase, AuditEvent


def H(tenant="ips-a"):
    return {"X-Tenant-Id":tenant}


def add_cases(client, prefix):
    cases = [
        {"objection_ref":f"{prefix}-{i:04d}","kind":"GLOSA" if i%5 else "DEVOLUCION",
         "code":("FA0101","TA0201","SO0101","CL0101","DE1601")[i%5],
         "description":"La EPS comunica una objeción que requiere verificación.",
         "amount":"10000",
         "account":{"account_ref":f"C-{prefix}-{i}","payer":"EPS Cualquiera"}}
        for i in range(40)
    ]
    r=client.post("/api/v1/objections/batch",headers=H(),json={"objections":cases})
    assert r.status_code==201, r.text


def test_batch_triage_40_updates_real_states_without_drafts(env):
    client, db_factory=env
    add_cases(client,"CASE")
    before=client.get("/api/v1/objections",headers=H()).json()
    assert before["total"]==40 and before["progress"]==0
    run=client.post("/api/v1/objections/triage",headers=H())
    assert run.status_code==200,run.text
    assert run.json()["processed"]==40 and run.json()["pending"]==0
    after=client.get("/api/v1/objections",headers=H()).json()
    assert after["total"]==40 and after["progress"]==20
    assert after["counts"]["EN_REVISION"]==40
    assert after["counts"]["ANALIZADA"]==0 and after["counts"]["RESPONDIDA"]==0
    for item in after["items"]:
        assert item["findings"]
        assert all(f["status"]=="INSUFFICIENT" for f in item["findings"])
        assert all(f["evidence_verified"] is False for f in item["findings"])
        assert item["ai_review"] is None
    repeat=client.post("/api/v1/objections/triage",headers=H())
    assert repeat.status_code==200 and repeat.json()["processed"]==0
    assert client.get("/api/v1/objections",headers=H()).json()["progress"]==20
    with next(db_factory()) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action=="OBJECTIONS_TRIAGED")) is not None


def test_batch_triage_cannot_touch_other_tenant(env):
    client,_=env
    add_cases(client,"CASE")
    app.dependency_overrides[current_email]=lambda:"other@example.com"
    other=client.post("/api/v1/objections/triage",headers=H("ips-b"))
    assert other.status_code==200 and other.json()["processed"]==0
    app.dependency_overrides[current_email]=lambda:"admin@example.com"
    a=client.get("/api/v1/objections",headers=H()).json()
    assert a["counts"]["POR_ANALIZAR"]==40


def test_single_case_without_rules_remains_unverified(env):
    client,_=env
    add_cases(client,"CASE")
    first=client.post("/api/v1/objections/CASE-0001/analyze",headers=H())
    assert first.status_code==200,first.text
    assert first.json()["case"]["status"]=="EN_REVISION"
    assert first.json()["case"]["findings"][0]["status"]=="INSUFFICIENT"
    assert first.json()["case"]["ai_review"] is None
    assert first.json()["case"]["response_reference"] is None


def test_unrecognized_causal_gets_general_evidence_needs(env):
    client,_=env
    c={"objections":[{"objection_ref":"UNKNOWN-1","kind":"GLOSA","code":"ZZ9090",
                      "description":"Código sin catalogar",
                      "account":{"account_ref":"C-ZZ"}}]}
    assert client.post("/api/v1/objections/batch",headers=H(),json=c).status_code==201
    r=client.post("/api/v1/objections/triage",headers=H())
    assert r.status_code==200 and r.json()["categories"]["Revisión general"]==1
