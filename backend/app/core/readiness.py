"""
core/readiness.py — Sonda de prontidão real (D5/ADR-090).

``/ready`` responde à pergunta "esta réplica pode receber tráfego?". Antes era um
``{"status": "ready"}` fixo — mentia durante uma queda de banco e o roteador da Fly
mandava requisições para uma réplica que só sabia dar 500. Aqui a resposta passa a
depender de sondas reais:

  - **banco** (obrigatório): ``SELECT 1``. Sem banco não há nada útil a servir → **não pronto**.
  - **Redis** (opcional, só quando ``REDIS_URL`` está definido): ``PING``. O peso dele segue
    a postura já decidida em ADR-079 — com ``SECURITY_FAIL_OPEN`` (padrão) uma queda do
    Redis **não** derruba login/OTP, então também **não** pode tirar a réplica de serviço:
    reporta-se ``degraded`` e segue pronta. Com ``SECURITY_FAIL_OPEN=0`` (fail-closed) a
    defesa é prioridade e a réplica se declara **não pronta**, coerente com o que ela faria
    de fato (429/401 em tudo).

A resposta é **agregada e sem PII**: só o nome da dependência e um estado curto — nada de
URL, host, credencial ou texto de exceção (que costuma trazer DSN). ``/health`` continua
sendo *liveness* puro (o processo está de pé), sem tocar em dependência.

**Sonda tem de ser LIMITADA no tempo.** Banco inalcançável na rede (pacote descartado, não
recusado) não devolve erro: pendura. Uma sonda pendurada é pior que uma que falha — o
orquestrador estoura o próprio timeout e a requisição ainda segura um worker. Por isso o
``connect_timeout`` da engine (ver ``core/db``) é curto e a sonda usa a **sessão da própria
requisição**, a mesma que os endpoints usam — sondar uma engine à parte diria "pronto" sobre
uma conexão que ninguém usa.
"""
from __future__ import annotations
import logging
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import security_fail_open

logger = logging.getLogger("sereno.infra")


def _probe_db(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — qualquer falha é "não pronto"
        # Só o TIPO da exceção: a mensagem costuma carregar a DSN (credencial).
        logger.warning("readiness: db unavailable",
                       extra={"extra_fields": {"error": type(exc).__name__}})
        return False


def _probe_redis() -> bool:
    from app.core.token_revocation import get_denylist
    client = getattr(get_denylist(), "_r", None)
    if client is None:      # denylist em memória (dev/teste): nada a sondar
        return True
    try:
        client.ping()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("readiness: redis unavailable",
                       extra={"extra_fields": {"error": type(exc).__name__}})
        return False


def probe(db: Session) -> tuple[bool, dict]:
    """Devolve ``(pronto, corpo)``. O corpo é agregado e seguro para expor."""
    db_ok = _probe_db(db)
    checks: dict[str, str] = {"db": "ok" if db_ok else "down"}

    ready = db_ok
    if os.getenv("REDIS_URL"):
        redis_ok = _probe_redis()
        checks["redis"] = "ok" if redis_ok else "down"
        if not redis_ok and not security_fail_open():
            ready = False       # fail-closed: sem Redis a app recusaria tudo (ADR-079)
    else:
        checks["redis"] = "disabled"

    if ready:
        status = "ready" if all(v != "down" for v in checks.values()) else "degraded"
    else:
        status = "not_ready"
    return ready, {"status": status, "checks": checks}
