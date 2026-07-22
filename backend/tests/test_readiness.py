"""
tests/test_readiness.py — Sonda de prontidão real (D5/ADR-090).

Prova o "Pronto (DoD)":
  - /health é liveness PURO: responde 200 mesmo com o banco fora (senão o orquestrador
    reiniciaria o processo em loop tentando consertar uma dependência externa);
  - /ready sonda o banco de verdade: banco fora → 503 (o roteador para de mandar tráfego);
  - Redis segue a postura do ADR-079: fail-open (padrão) → degraded mas PRONTO;
    fail-closed → não pronto (é o que a app faria de fato: recusar tudo);
  - a resposta não vaza URL/credencial/host — só nome da dependência e estado curto.
"""
from __future__ import annotations
import pytest

from app.core import readiness

HEALTH, READY = "/health", "/ready"


class _DeadRedis:
    def ping(self):
        raise ConnectionError("redis down")


class _LiveRedis:
    def ping(self):
        return True


class _FakeDenylist:
    """Denylist com cliente Redis injetado — a sonda o alcança por `_r`, como em produção."""
    def __init__(self, client):
        self._r = client

    def revoke(self, jti, ttl_s): pass
    def is_revoked(self, jti): return False
    def reset(self): pass


@pytest.fixture
def _db_down(monkeypatch):
    monkeypatch.setattr(readiness, "_probe_db", lambda db: False)


def test_ready_ok_when_db_reachable(api):
    client, _ = api
    r = client.get(READY)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"] == "ok"


def test_ready_503_when_db_down(api, _db_down):
    client, _ = api
    r = client.get(READY)
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"
    assert r.json()["checks"]["db"] == "down"


def test_health_stays_200_when_db_down(api, _db_down):
    # Liveness ≠ readiness: o processo está vivo; reiniciá-lo não conserta o banco.
    client, _ = api
    assert client.get(HEALTH).status_code == 200


def test_redis_absent_is_not_a_failure(api, monkeypatch):
    # Sem REDIS_URL (dev/piloto de um processo só) não há o que sondar.
    monkeypatch.delenv("REDIS_URL", raising=False)
    client, _ = api
    r = client.get(READY)
    assert r.status_code == 200 and r.json()["checks"]["redis"] == "disabled"


def test_redis_down_is_degraded_but_ready_when_fail_open(api, monkeypatch):
    # ADR-079: com fail-open, Redis fora NÃO derruba login/OTP — logo não pode tirar a
    # réplica de serviço. Reporta o estado real sem parar de atender.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECURITY_FAIL_OPEN", "1")
    from app.core.token_revocation import set_denylist
    set_denylist(_FakeDenylist(_DeadRedis()))
    client, _ = api
    r = client.get(READY)
    assert r.status_code == 200
    assert r.json()["status"] == "degraded" and r.json()["checks"]["redis"] == "down"


def test_redis_down_is_not_ready_when_fail_closed(api, monkeypatch):
    # Fail-closed: sem Redis a app recusaria tudo (429/401) — declarar-se pronta seria mentir.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECURITY_FAIL_OPEN", "0")
    from app.core.token_revocation import set_denylist
    set_denylist(_FakeDenylist(_DeadRedis()))
    client, _ = api
    r = client.get(READY)
    assert r.status_code == 503 and r.json()["status"] == "not_ready"


def test_redis_up_is_ready(api, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from app.core.token_revocation import set_denylist
    set_denylist(_FakeDenylist(_LiveRedis()))
    client, _ = api
    r = client.get(READY)
    assert r.status_code == 200 and r.json()["checks"]["redis"] == "ok"


def test_ready_body_leaks_no_connection_details(api, monkeypatch):
    # A mensagem de erro do driver costuma trazer a DSN (usuário:senha@host) — nada disso
    # pode sair no corpo, que é público-ish (sonda de infra, sem auth).
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://sereno:s3nha@db.interno:5432/sereno")
    monkeypatch.setattr(readiness, "_probe_db", lambda db: False)
    client, _ = api
    body = client.get(READY).text.lower()
    for token in ("s3nha", "db.interno", "sereno:", "5432", "postgres"):
        assert token not in body
