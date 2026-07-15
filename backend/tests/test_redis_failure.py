"""
tests/test_redis_failure.py — Política de falha do backend Redis (ADR-079).

Quando o Redis (rate limit / denylist) está indisponível, o sistema degrada conforme
``SECURITY_FAIL_OPEN`` em vez de estourar 500:

  - **fail-open** (padrão): rate limit deixa passar; denylist trata como NÃO revogado
    (disponibilidade em 1º lugar; token de acesso tem TTL curto);
  - **fail-closed** (``SECURITY_FAIL_OPEN=0``): rate limit bloqueia; denylist trata como
    revogado (defesa em 1º lugar);
  - ``revoke()`` é best-effort: um Redis caído **não** propaga exceção (logout não dá 500).
"""
from __future__ import annotations
import pytest

from app.core.rate_limit import RedisRateLimiter
from app.core.token_revocation import RedisDenylist


class _BoomRedis:
    """Cliente Redis que sempre falha (simula indisponibilidade)."""
    def incr(self, *a, **k): raise ConnectionError("redis down")
    def expire(self, *a, **k): raise ConnectionError("redis down")
    def exists(self, *a, **k): raise ConnectionError("redis down")
    def set(self, *a, **k): raise ConnectionError("redis down")


def test_rate_limit_fail_open_by_default(monkeypatch):
    monkeypatch.delenv("SECURITY_FAIL_OPEN", raising=False)
    limiter = RedisRateLimiter(_BoomRedis())
    # deixa passar (True) mesmo com o backend fora
    assert limiter.hit("k", limit=1, window_s=60) is True


def test_rate_limit_fail_closed_when_configured(monkeypatch):
    monkeypatch.setenv("SECURITY_FAIL_OPEN", "0")
    limiter = RedisRateLimiter(_BoomRedis())
    # bloqueia (False → o enforce levanta 429)
    assert limiter.hit("k", limit=1, window_s=60) is False


def test_denylist_fail_open_treats_token_as_valid(monkeypatch):
    monkeypatch.delenv("SECURITY_FAIL_OPEN", raising=False)
    dl = RedisDenylist(_BoomRedis())
    # NÃO revogado → a requisição autenticada segue
    assert dl.is_revoked("some-jti") is False


def test_denylist_fail_closed_treats_token_as_revoked(monkeypatch):
    monkeypatch.setenv("SECURITY_FAIL_OPEN", "0")
    dl = RedisDenylist(_BoomRedis())
    # revogado → a requisição autenticada é recusada (401)
    assert dl.is_revoked("some-jti") is True


def test_revoke_is_best_effort_and_never_raises():
    dl = RedisDenylist(_BoomRedis())
    # não deve propagar exceção mesmo com o Redis fora (logout não vira 500)
    dl.revoke("some-jti", 60)


def test_fail_open_logs_warning(monkeypatch, caplog):
    monkeypatch.delenv("SECURITY_FAIL_OPEN", raising=False)
    limiter = RedisRateLimiter(_BoomRedis())
    with caplog.at_level("WARNING", logger="sereno.security"):
        limiter.hit("k", limit=1, window_s=60)
    assert any("unavailable" in r.message for r in caplog.records)
