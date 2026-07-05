"""
core/rate_limit.py — Limite de taxa por chave (IP), atrás de uma porta.

Protege endpoints sensíveis (solicitar OTP, login) contra abuso/força-bruta. A
implementação **em memória** serve a testes e a um único processo; em **produção** com
múltiplos workers, defina ``REDIS_URL`` para usar Redis (INCR + EXPIRE) — só assim o limite
vale entre processos. Janela fixa (simples e suficiente para o piloto).
"""
from __future__ import annotations
import os
import time
from typing import Protocol

from fastapi import Request

from app.core.problem import ProblemException


class RateLimiter(Protocol):
    def hit(self, key: str, *, limit: int, window_s: int) -> bool: ...
    def reset(self) -> None: ...


class InMemoryRateLimiter:
    """Janela fixa por chave. Não compartilha estado entre processos (dev/teste)."""
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, int]] = {}   # key -> (início_janela, contagem)

    def hit(self, key: str, *, limit: int, window_s: int) -> bool:
        now = time.monotonic()
        start, count = self._buckets.get(key, (now, 0))
        if now - start >= window_s:
            start, count = now, 0
        count += 1
        self._buckets[key] = (start, count)
        return count <= limit

    def reset(self) -> None:
        self._buckets.clear()


class RedisRateLimiter:
    """Janela fixa distribuída (INCR + EXPIRE). Para produção multi-worker."""
    def __init__(self, client) -> None:
        self._r = client

    def hit(self, key: str, *, limit: int, window_s: int) -> bool:
        n = int(self._r.incr(key))
        if n == 1:
            self._r.expire(key, window_s)
        return n <= limit

    def reset(self) -> None:
        pass  # não se limpa o Redis inteiro em produção (no-op deliberado)


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Singleton: Redis se ``REDIS_URL`` estiver definido; senão, em memória."""
    global _limiter
    if _limiter is None:
        url = os.getenv("REDIS_URL")
        if url:
            import redis  # import tardio: só quando há Redis configurado
            _limiter = RedisRateLimiter(redis.Redis.from_url(url))
        else:
            _limiter = InMemoryRateLimiter()
    return _limiter


def set_rate_limiter(limiter: RateLimiter | None) -> None:
    """Injeta um limiter (ou ``None`` para reconstruir do ambiente na próxima chamada).

    Uso em testes: forçar ``InMemoryRateLimiter`` garante isolamento mesmo quando
    ``REDIS_URL`` está definido (o ``reset()`` do Redis é no-op deliberado em prod)."""
    global _limiter
    _limiter = limiter


def enforce(request: Request, *, bucket: str, default_limit: int, window_s: int = 60) -> None:
    """Consome uma unidade de taxa para (bucket, IP); levanta 429 problem+json se estourar.

    Os limites são configuráveis por ambiente: ``<BUCKET>_RATE_LIMIT`` e
    ``<BUCKET>_RATE_WINDOW_S`` (ex.: ``LOGIN_RATE_LIMIT``)."""
    ip = request.client.host if request and request.client else "unknown"
    limit = int(os.getenv(f"{bucket.upper()}_RATE_LIMIT", str(default_limit)))
    window = int(os.getenv(f"{bucket.upper()}_RATE_WINDOW_S", str(window_s)))
    if not get_rate_limiter().hit(f"{bucket}:{ip}", limit=limit, window_s=window):
        raise ProblemException(429, "Muitas tentativas",
                               "Limite de tentativas excedido. Aguarde e tente novamente.")
