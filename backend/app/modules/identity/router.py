"""
modules/identity/router.py — Autenticação de staff (pesquisador/admin).

Fluxo: POST /auth/token (senha argon2) -> se MFA habilitado, exige TOTP em
/auth/mfa/verify; senão emite JWT (access + refresh). /auth/refresh renova o acesso.
Sem enumeração de usuário (falhas retornam 401 genérico). Erros em problem+json.
Autenticação de PARTICIPANTE é uma fatia à parte (fluxo mais simples).
"""
from __future__ import annotations
import uuid
import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.problem import ProblemException
from app.core.models import StaffUser
from app.core import auth
from app.core.security import RBAC

router = APIRouter(prefix="/auth", tags=["identity"])


class LoginIn(BaseModel):
    email: str
    password: str


class MfaIn(BaseModel):
    mfa_token: str
    code: str = Field(pattern=r"^[0-9]{6}$")


class RefreshIn(BaseModel):
    refresh_token: str


def _tokens(sub: str, role: str) -> dict:
    scope = " ".join(sorted(RBAC.get(role, set())))
    return {
        "access_token": auth.issue_access(sub, role, scope),
        "refresh_token": auth.issue_refresh(sub, role),
        "token_type": "bearer",
        "expires_in": auth.ACCESS_TTL_MIN * 60,
        "mfa_required": False,
    }


@router.post("/token")
async def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalars(select(StaffUser).where(StaffUser.email == body.email)).first()
    if user is None or not auth.verify_password(user.password_hash, body.password):
        raise ProblemException(401, "Credenciais inválidas", "E-mail ou senha incorretos.")
    if user.mfa_enabled:
        # Ainda não dá acesso: emite desafio; exige o 2º fator.
        return {"mfa_required": True, "token_type": "bearer",
                "mfa_token": auth.issue_mfa_challenge(str(user.id), user.role)}
    return _tokens(str(user.id), user.role)


@router.post("/mfa/verify")
async def mfa_verify(body: MfaIn, db: Session = Depends(get_db)):
    try:
        payload = auth.decode_token(body.mfa_token, expected_type="mfa")
    except jwt.InvalidTokenError:
        raise ProblemException(401, "Desafio MFA inválido", "Token de MFA inválido ou expirado.")
    user = db.get(StaffUser, uuid.UUID(payload["sub"]))
    if user is None or not user.mfa_secret or not auth.verify_totp(user.mfa_secret.decode(), body.code):
        raise ProblemException(401, "Código inválido", "Código de verificação incorreto.")
    return _tokens(str(user.id), user.role)


@router.post("/refresh")
async def refresh(body: RefreshIn):
    try:
        payload = auth.decode_token(body.refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError:
        raise ProblemException(401, "Sessão inválida", "Token de renovação inválido ou expirado.")
    return _tokens(payload["sub"], payload["role"])
