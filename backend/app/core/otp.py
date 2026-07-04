"""
core/otp.py — Código de uso único (OTP) para login de participante.

Segurança: o código NUNCA é gravado em claro (guarda-se sha256(código+pepper)); tem
expiração curta, uso único e limite de tentativas. OTP de 6 dígitos é de baixa entropia
por natureza — a defesa é expiração + limite + uso único + pepper (segredo em cofre).
Entrega por e-mail (ao contato cifrado) é integração à parte (PROD); em DEV é abstraída.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import os
import secrets

OTP_TTL_MIN = 5
OTP_MAX_ATTEMPTS = 5
_PEPPER = os.getenv("OTP_PEPPER", "dev-otp-pepper-trocar")


def generate_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256((code + _PEPPER).encode("utf-8")).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    return secrets.compare_digest(hash_code(code), code_hash)


def expiry() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=OTP_TTL_MIN)


def as_utc(d: dt.datetime) -> dt.datetime:
    """Normaliza para aware-UTC (SQLite devolve naive; Postgres devolve aware)."""
    return d if d.tzinfo is not None else d.replace(tzinfo=dt.timezone.utc)
