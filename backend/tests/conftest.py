import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.auth import current_email
from app.models import Tenant, Membership

@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        db.add_all([Tenant(id="ips-a", name="IPS A"), Tenant(id="ips-b", name="IPS B")])
        db.add_all([
            Membership(tenant_id="ips-a", email="admin@example.com", roles=["ADMIN", "AUDITOR", "CONFIGURADOR"]),
            Membership(tenant_id="ips-b", email="other@example.com", roles=["ADMIN", "AUDITOR"]),
            Membership(tenant_id="ips-a", email="reader@example.com", roles=["ANALISTA"]),
        ])
        db.commit()
    def db_override():
        with Session(engine) as db: yield db
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[current_email] = lambda: "admin@example.com"
    with TestClient(app) as client:
        yield client, db_override
    app.dependency_overrides.clear()
    engine.dispose()
