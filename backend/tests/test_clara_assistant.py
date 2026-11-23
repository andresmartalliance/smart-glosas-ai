"""Clara's contextual assistant is tenant-scoped and never sends documents."""
from app.main import app
from app.auth import current_email
from app.models import AuditEvent, ObjectionCase
from sqlalchemy import select
import app.clara_assistant as assistant

def H(tenant="ips-a"):
    return {"X-Tenant-Id":tenant}

def test_clara_assistant_read_only_and_context_aware(env, monkeypatch):
    client, db_factory = env
    monkeypatch.setenv("GEMINI_API_KEY", "unexposed-test-key")
    seen=[]
    def stub(context):
        seen.append(context)
        return {"answer":"Consulta de orientación, no se enviaron respuestas.","agent":"Clara","model":"stub","read_only":True}
    monkeypatch.setattr(assistant,"ask_gemini",stub)
    response=client.post("/api/v1/clara/assist",headers=H(),json={
        "question":"¿Cómo debo priorizar las glosas pendientes?",
        "screen":"historial"
    })
    assert response.status_code==200,response.text
    assert response.json()["read_only"] is True
    assert seen[0]["screen"]=="historial"
    assert seen[0]["objection_counts"]["POR_ANALIZAR"]==0
    assert "email" not in str(seen[0]).lower()
    with next(db_factory()) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action=="CLARA_ASSIST_CONSULTED")) is not None

def test_clara_does_not_expose_other_tenants_cases(env,monkeypatch):
    client, db_factory=env
    monkeypatch.setenv("GEMINI_API_KEY","stub")
    with next(db_factory()) as db:
        db.add(ObjectionCase(tenant_id="ips-b",objection_ref="G-B",account_ref="B-1",
                            kind="GLOSA",description="Objecion ajena",source={},
                            created_by="other@example.com",updated_by="other@example.com"))
        db.commit()
    app.dependency_overrides[current_email]=lambda:"admin@example.com"
    result=client.post("/api/v1/clara/assist",headers=H("ips-a"),json={
        "question":"¿Cuál es su estado?","screen":"respond","objection_ref":"G-B"
    })
    assert result.status_code==404

def test_clara_rejects_potential_patient_identifiers(env,monkeypatch):
    client,_=env
    monkeypatch.setenv("GEMINI_API_KEY","stub")
    result=client.post("/api/v1/clara/assist",headers=H(),json={
        "question":"Revisa la cédula 1234567890 de esta persona",
        "screen":"prevent"
    })
    assert result.status_code==422
    assert client.post("/api/v1/clara/assist",json={
        "question":"Cómo responder una glosa", "screen":"respond"
    }).status_code==400

def test_clara_without_gemini_returns_config_error(env,monkeypatch):
    client,_=env
    monkeypatch.delenv("GEMINI_API_KEY",raising=False)
    response=client.post("/api/v1/clara/assist",headers=H(),json={
        "question":"¿Qué normas aplicar?","screen":"reglas"
    })
    assert response.status_code==503
