"""
core/logging.py — Logs estruturados (JSON) SEM PII nem o braço.

Regra: nunca logar corpo de requisição (pode conter PII, OTP, senha), nem a condição
(ativo/sham). O log de requisição registra apenas método, caminho, status e latência —
o caminho pode conter identificadores PSEUDÔNIMOS (UUID), nunca PII em claro.
"""
from __future__ import annotations
import datetime as dt
import json
import logging
import os
import sys

request_logger = logging.getLogger("sereno.request")


class JsonFormatter(logging.Formatter):
    """Formata cada registro como uma linha JSON (amigável a coletores de log)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str | None = None) -> None:
    """Instala um handler JSON na raiz (idempotente). Nível via LOG_LEVEL (padrão INFO)."""
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
