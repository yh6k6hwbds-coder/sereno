"""
core/token_revocation.py — Denylist de tokens por ``jti`` (revogação), atrás de uma porta.

Permite invalidar um JWT **antes** de expirar (logout, incidente de segurança). Como os
tokens já carregam ``jti`` (ver ``core/auth``), basta guardar os revogados até expirarem.
Em memória para dev/teste; em produção defina ``REDIS_URL`` (SET jti EX ttl) para valer
entre workers.
"""
from __future__ import annotations
import os
import time
from typing import Protocol


class TokenDenylist(Protocol):
    def revoke(self, jti: str, ttl_s: int) -> None: ...
    def is_revoked(self, jti: str) -> bool: ...
    def reset(self) -> None: ...


class InMemoryDenylist:
    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}   # jti -> instante de expiração (monotonic)

    def revoke(self, jti: str, ttl_s: int) -> None:
        self._revoked[jti] = time.monotonic() + max(ttl_s, 1)

    def is_revoked(self, jti: str) -> bool:
        exp = self._revoked.get(jti)
        if exp is None:
            return False
        if exp < time.monotonic():
            self._revoked.pop(jti, None)   # expirou: limpeza preguiçosa
            return False
        return True

    def reset(self) -> None:
        self._revoked.clear()


class RedisDenylist:
    _PREFIX = "revoked_jti:"

    def __init__(self, client) -> None:
        self._r = client

    def revoke(self, jti: str, ttl_s: int) -> None:
        self._r.set(self._PREFIX + jti, "1", ex=max(ttl_s, 1))

    def is_revoked(self, jti: str) -> bool:
        return bool(self._r.exists(self._PREFIX + jti))

    def reset(self) -> None:
        pass


_denylist: TokenDenylist | None = None


def get_denylist() -> TokenDenylist:
    """Singleton: Redis se ``REDIS_URL`` estiver definido; senão, em memória."""
    global _denylist
    if _denylist is None:
        url = os.getenv("REDIS_URL")
        if url:
            import redis
            _denylist = RedisDenylist(redis.Redis.from_url(url))
        else:
            _denylist = InMemoryDenylist()
    return _denylist


def set_denylist(denylist: TokenDenylist | None) -> None:
    """Injeta uma denylist (ou ``None`` para reconstruir do ambiente na próxima chamada).

    Uso em testes: forçar ``InMemoryDenylist`` garante isolamento mesmo quando
    ``REDIS_URL`` está definido (o ``reset()`` do Redis é no-op deliberado em prod)."""
    global _denylist
    _denylist = denylist
