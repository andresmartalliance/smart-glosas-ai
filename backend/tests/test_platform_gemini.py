"""Security of host signed context; Gemini never accepts ungrounded final drafts."""
import base64
import hashlib
import hmac
import json
import time
from app.main import app
from app.gemini import prepare_context, generate_review
from app.auth import current_email

SECRET = "unit-test-platform-shared-secret-with-32-characters-minimum"

def token(tenant="ips-a", exp=None):
    enc=lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    header=enc({"alg":"HS256","typ":"JWT"})
    claims=enc({"iss":"smart-platform","aud":"smart-glosas-ai","sub":"admin@example.com",
               "tenant_id":tenant,"tenant_name":"IPS A","roles":["ADMIN","AUDITOR"],
               "exp":exp if exp is not None else int(time.time())+600})
    data=header+"."+claims
    sig=base64.urlsafe_b64encode(hmac.new(SECRET.encode(),data.encode(),hashlib.sha256).digest()).rstrip(b"=").decode()
    return data+"."+sig

def test_platform_requires_correct_signed_tenant(env,monkeypatch):
    client,_=env
    monkeypatch.setenv("SMART_AUTH_MODE","platform")
    monkeypatch.setenv("SMART_PLATFORM_JWT_SECRET",SECRET)
    app.dependency_overrides.pop(current_email,None)
    headers={"Authorization":"Bearer "+token(),"X-Tenant-Id":"ips-a"}
    assert client.get("/api/v1/session",headers=headers).status_code==200
    assert client.get("/api/v1/rules",headers=headers).status_code==200
    assert client.get("/api/v1/rules",headers={**headers,"X-Tenant-Id":"ips-b"}).status_code==403
    assert client.get("/api/v1/session",headers={**headers,"Authorization":"Bearer bad"}).status_code==401
    assert client.get("/api/v1/session",headers={**headers,"Authorization":"Bearer "+token(exp=int(time.time())-30)}).status_code==401

def test_ai_requires_key_and_redacts_identity(env,monkeypatch):
    client,_=env
    row=client.post("/api/v1/analyses/prevent",headers={"X-Tenant-Id":"ips-a"},
        json={"accounts":[{"account_ref":"C11","facts":{},"evidence":[]}]}).json()["analyses"][0]
    assert client.post("/api/v1/analyses/"+row["id"]+"/ai-review",headers={"X-Tenant-Id":"ips-a"}).status_code==503
    context=prepare_context({"phase":"RESPOND","account_ref":"10001234567",
        "objection_description":"Paciente 1234567890, contacto example@hospital.co","findings":[]})
    data=json.dumps(context)
    assert "10001234567" not in data and "1234567890" not in data and "example@hospital.co" not in data

def test_ai_keeps_drafts_human_reviewed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY","unit-test-secret")
    class Reply:
        def raise_for_status(self):pass
        def json(self):
            return {"candidates":[{"content":{"parts":[{"text":json.dumps({
                "resumen":"Revision necesaria","accion_sugerida":"CONTROVERTIR",
                "propuesta_borrador":"Borrador de prueba","informacion_faltante":[],"advertencias":[]})}]}}]}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):return Reply()
    monkeypatch.setattr("app.gemini.httpx.Client",Client)
    no_sources=generate_review({"phase":"RESPOND","findings":[]})
    assert no_sources["draft"] is None and no_sources["requires_human_review"]
    sourced=generate_review({"phase":"RESPOND","findings":[{"status":"REVIEW","source_ref":"Referencia verificable"}]})
    assert sourced["draft"]=="Borrador de prueba"
