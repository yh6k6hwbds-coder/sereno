"""
tests/conftest.py — Infraestrutura compartilhada dos testes.

Fornece a fixture `api`: sobe a app com SQLite em memória (schema via metadata),
sobrescreve `get_db` para usar a sessão de teste, e devolve (client, SessionMaker).
Auth é exercida de verdade (tokens reais), não por override.
"""
from __future__ import annotations
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.models import Base
from app.core import db as db_module
from app.main import app


@pytest.fixture(autouse=True)
def _reset_throttles():
    """Isola o estado dos singletons de rate limit / denylist entre testes."""
    from app.core.rate_limit import get_rate_limiter
    from app.core.token_revocation import get_denylist
    get_rate_limiter().reset()
    get_denylist().reset()
    yield


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        s = TestSession()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback(); raise
        finally:
            s.close()

    app.dependency_overrides[db_module.get_db] = override_get_db
    yield TestClient(app), TestSession
    app.dependency_overrides.clear()
