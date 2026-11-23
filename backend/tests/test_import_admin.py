"""Production-path tests for import ownership, administrative deletion and reset."""
from sqlalchemy import select, func
from app.main import app
from app.auth import current_email
from app.models import AuditEvent, RuleVersion, ObjectionCase, ImportBatch


def headers(tenant="ips-a"):
    return {"X-Tenant-Id": tenant}


def objections(prefix):
    return [
        {"objection_ref": prefix+"-001", "kind": "GLOSA", "code": "FA0101",
         "description": "Días facturados por verificar",
         "amount": "167000", "account": {"account_ref": "C-101", "payer": "EPS Alfa"}},
        {"objection_ref": prefix+"-002", "kind": "DEVOLUCION", "code": "DE1601",
         "description": "Pagador por verificar",
         "amount": "120000", "account": {"account_ref": "C-102", "payer": "EPS Beta"}}
    ]


def upload(client, prefix="REG", tenant="ips-a", name="glosas.csv"):
    return client.post("/api/v1/objections/batch", headers=headers(tenant), json={
        "objections": objections(prefix), "file_name": name, "source_type": "CSV"})


def test_batch_history_survives_reimport_and_delete(env):
    client, db_factory = env
    first = upload(client, name="uploads/enero.csv")
    assert first.status_code == 201, first.text
    assert first.json()["inserted"] == 2
    batch_id = first.json()["batch_id"]
    assert batch_id
    batches = client.get("/api/v1/objections/batches", headers=headers()).json()
    assert len(batches) == 1 and batches[0]["file_name"] == "enero.csv"
    assert batches[0]["inserted_count"] == 2
    repeated = upload(client, name="enero.csv")
    assert repeated.status_code == 201
    assert repeated.json()["inserted"] == 0 and repeated.json()["batch_id"] is None
    assert len(client.get("/api/v1/objections/batches", headers=headers()).json()) == 1
    assert client.get("/api/v1/objections", headers=headers()).json()["total"] == 2

    deleted = client.delete("/api/v1/objections/batches/"+batch_id, headers=headers())
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 2
    assert client.get("/api/v1/objections", headers=headers()).json()["total"] == 0
    assert client.get("/api/v1/objections/batches", headers=headers()).json() == []
    with next(db_factory()) as db:
        log = db.scalar(select(AuditEvent).where(AuditEvent.action == "OBJECTION_BATCH_DELETED"))
        assert log is not None and log.details["removed_cases"] == 2


def test_delete_is_tenant_scoped_and_restricted(env):
    client, _ = env
    first = upload(client)
    batch_id = first.json()["batch_id"]
    app.dependency_overrides[current_email] = lambda: "other@example.com"
    assert client.delete("/api/v1/objections/batches/"+batch_id,
                         headers=headers("ips-b")).status_code == 404
    assert client.post("/api/v1/objections/reset", headers=headers("ips-b"),
                       json={"confirmation": "ELIMINAR TODO"}).status_code == 200
    app.dependency_overrides[current_email] = lambda: "reader@example.com"
    assert client.get("/api/v1/objections/batches", headers=headers()).status_code == 403
    assert client.delete("/api/v1/objections/batches/"+batch_id, headers=headers()).status_code == 403
    assert client.post("/api/v1/objections/reset", headers=headers(),
                       json={"confirmation": "ELIMINAR TODO"}).status_code == 403
    app.dependency_overrides[current_email] = lambda: "admin@example.com"
    assert client.get("/api/v1/objections", headers=headers()).json()["total"] == 2


def test_reset_requires_exact_confirmation_and_preserves_other_ips(env):
    client, db_factory = env
    upload(client, prefix="A")
    app.dependency_overrides[current_email] = lambda: "other@example.com"
    upload(client, prefix="B", tenant="ips-b")
    app.dependency_overrides[current_email] = lambda: "admin@example.com"
    invalid = client.post("/api/v1/objections/reset", headers=headers(),
                          json={"confirmation": "BORRAR"})
    assert invalid.status_code == 422
    assert client.get("/api/v1/objections", headers=headers()).json()["total"] == 2
    reset = client.post("/api/v1/objections/reset", headers=headers(),
                        json={"confirmation": "ELIMINAR TODO"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["deleted_cases"] == 2
    assert reset.json()["deleted_batches"] == 1
    cleared = client.get("/api/v1/objections", headers=headers()).json()
    assert cleared["total"] == 0 and cleared["progress"] == 0
    app.dependency_overrides[current_email] = lambda: "other@example.com"
    assert client.get("/api/v1/objections", headers=headers("ips-b")).json()["total"] == 2
    with next(db_factory()) as db:
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "OBJECTION_DATA_RESET"))
        assert audit is not None
        assert db.scalar(select(func.count()).select_from(ObjectionCase)) == 2


def test_manual_case_not_removed_by_unrelated_batch(env):
    client, _ = env
    original = upload(client)
    manual = client.post("/api/v1/objections/batch", headers=headers(), json={
        "objections": [{
            "objection_ref": "MANUAL-1", "kind": "GLOSA",
            "description": "Objeción manual", "account": {"account_ref": "M-1"}
        }]
    })
    assert manual.status_code == 201
    assert manual.json()["batch_id"] is None
    assert client.delete("/api/v1/objections/batches/"+original.json()["batch_id"],
                         headers=headers()).status_code == 200
    entries = client.get("/api/v1/objections", headers=headers()).json()["items"]
    assert [x["objection_ref"] for x in entries] == ["MANUAL-1"]
    assert client.delete("/api/v1/objections/MANUAL-1", headers=headers()).status_code == 200
    assert client.get("/api/v1/objections", headers=headers()).json()["total"] == 0
