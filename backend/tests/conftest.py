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
    """Isola o estado dos singletons de rate limit / denylist / e-mail entre testes.

    Rate limit e denylist são forçados para as implementações **em memória**: se
    ``REDIS_URL`` estiver no ambiente (ex.: rodando dentro do container prod-like), o
    singleton seria o backend Redis, cujo ``reset()`` é no-op deliberado — o estado
    vazaria entre testes. Injetar in-memory garante suíte hermética em qualquer ambiente."""
    from app.core.rate_limit import set_rate_limiter, InMemoryRateLimiter
    from app.core.token_revocation import set_denylist, InMemoryDenylist
    from app.core.email import set_email_sender, set_email_delivery
    from app.core.keyring import set_key_provider
    from app.modules.research.export_service import get_job_store
    from app.modules.wearables.sink import set_wearable_sink
    set_rate_limiter(InMemoryRateLimiter())
    set_denylist(InMemoryDenylist())
    get_job_store().reset()
    set_email_sender(None)     # próxima chamada reconstrói a partir do ambiente
    set_email_delivery(None)   # idem — e drena o pool de um BackgroundDelivery anterior
    set_wearable_sink(None)    # próxima chamada reconstrói a partir do ambiente
    set_key_provider(None)     # idem — provedor de chave de PII (env por padrão)
    yield
    set_rate_limiter(None)     # próxima chamada reconstrói a partir do ambiente
    set_denylist(None)
    set_email_sender(None)
    set_email_delivery(None)
    set_wearable_sink(None)
    set_key_provider(None)


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
