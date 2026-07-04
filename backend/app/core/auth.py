"""
core/auth.py — Primitivos de autenticação (isolados e testáveis).

Contém: hashing de senha (argon2id), emissão/validação de JWT (access + refresh) e
verificação de MFA (TOTP). NÃO faz I/O de banco — é lógica pura, para ser testada
sem subir a app. As rotas (modules/identity) orquestram estes primitivos.

Segredos e parâmetros vêm de variáveis de ambiente (JWT_SECRET etc.). Em produção:
segredo forte em cofre, rotação e, idealmente, RS256. Aqui HS256 por simplicidade.
"""
from __future__ import annotations
import datetime as dt
import os
import uuid

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# --- Configuração (env com defaults só para dev/teste) ---
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-trocar-em-producao")
JWT_ALG = "HS256"
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "15"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "7"))
# Token curto emitido após a senha, exigindo o 2º fator antes do acesso pleno.
MFA_TTL_MIN = 5

_ph = PasswordHasher()   # argon2id com parâmetros seguros por padrão


# ------------------------------------------------------------------ Senha
def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    """True se os parâmetros do hash ficaram abaixo do padrão atual (rotação)."""
    return _ph.check_needs_rehash(hashed)


# ------------------------------------------------------------------ JWT
def _encode(claims: dict, ttl: dt.timedelta, token_type: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {**claims, "type": token_type, "iat": now, "nbf": now,
               "exp": now + ttl, "jti": str(uuid.uuid4())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def issue_access(sub: str, role: str, scope: str = "") -> str:
    return _encode({"sub": sub, "role": role, "scope": scope},
                   dt.timedelta(minutes=ACCESS_TTL_MIN), "access")


def issue_refresh(sub: str, role: str) -> str:
    return _encode({"sub": sub, "role": role}, dt.timedelta(days=REFRESH_TTL_DAYS), "refresh")


def issue_mfa_challenge(sub: str, role: str) -> str:
    """Token intermediário: prova que a senha passou; exige TOTP para virar acesso."""
    return _encode({"sub": sub, "role": role}, dt.timedelta(minutes=MFA_TTL_MIN), "mfa")


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """Valida assinatura/exp e, opcionalmente, o tipo do token. Levanta em caso de erro."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG],
                         options={"require": ["exp", "iat", "sub"]})
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"tipo de token inesperado: {payload.get('type')}")
    return payload


# ------------------------------------------------------------------ MFA (TOTP)
def new_mfa_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    # valid_window=1 tolera pequena defasagem de relógio (±30s).
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def provisioning_uri(secret: str, email: str, issuer: str = "Sereno") -> str:
    """URI otpauth:// para configurar o app autenticador (QR code)."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)
