import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.auth import login_limiter


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with test_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.main.SessionLocal", test_sessions)
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr("app.main.prune_expired_evidence", lambda: None)
    monkeypatch.setattr("app.config.settings.auth_mode", "demo")
    monkeypatch.setattr("app.config.settings.demo_access_password", "test-passphrase-012345")
    monkeypatch.setattr("app.config.settings.allowed_origins", "http://testserver")
    login_limiter.attempts.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
