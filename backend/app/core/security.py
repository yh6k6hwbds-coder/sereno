"""
core/security.py — Autenticação (JWT) e autorização (RBAC), checadas no servidor.

`current_user` valida o token de acesso (Bearer) de verdade — não é mais stub.
`current_participant` deriva o participante do token. `require(perm)` impõe RBAC.
Invariante: NENHUMA permissão concede "ver o braço" (ativo/sham).
"""
from __future__ import annotations
import uuid
import jwt
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.problem import ProblemException
from app.core import auth as auth_core
from app.core.db import get_db
from app.core.models import Participant
from app.core.token_revocation import get_denylist

# Matriz mínima de permissões (espelha a Etapa 5).
RBAC: dict[str, set[str]] = {
    "participant": {"consent:write", "session:write", "assessment:write", "diary:write", "ae:write"},
    "researcher": {"research:read", "export:request", "enroll:write"},
    "admin": {"research:read", "export:request", "enroll:write", "user:manage",
              "unblind:request", "audit:read"},
}

_bearer = HTTPBearer(auto_error=False)


async def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Valida o token de acesso e devolve {id, role, scope}. 401 em problem+json se inválido."""
    if cred is None or not cred.credentials:
        raise ProblemException(401, "Não autenticado", "Token de acesso ausente.")
    try:
        payload = auth_core.decode_token(cred.credentials, expected_type="access")
    except jwt.ExpiredSignatureError:
        raise ProblemException(401, "Sessão expirada", "O token de acesso expirou.")
    except jwt.InvalidTokenError:
        raise ProblemException(401, "Token inválido", "Não foi possível validar o token.")
    # Revogação: um token com jti na denylist (ex.: pós-logout) é recusado.
    jti = payload.get("jti")
    if jti and get_denylist().is_revoked(jti):
        raise ProblemException(401, "Sessão encerrada", "Token revogado.")
    return {"id": payload["sub"], "role": payload.get("role"), "scope": payload.get("scope", "")}


async def current_staff_enrolling(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Autentica para o CADASTRO de MFA aceitando token de acesso OU de "enroll".

    Resolve o ovo-galinha do MFA obrigatório: o staff sem 2º fator ativo recebe no login
    apenas um token de tipo "enroll" (sem escopo), que abre SÓ os endpoints de enroll/confirm.
    Todos os demais endpoints continuam exigindo `current_user` (type "access") — logo o
    token de "enroll" não acessa mais nada. Um token de acesso pleno também é aceito aqui
    (permite rotacionar o MFA já autenticado)."""
    if cred is None or not cred.credentials:
        raise ProblemException(401, "Não autenticado", "Token de acesso ausente.")
    try:
        payload = auth_core.decode_token(cred.credentials)   # valida assinatura/exp
    except jwt.ExpiredSignatureError:
        raise ProblemException(401, "Sessão expirada", "O token expirou.")
    except jwt.InvalidTokenError:
        raise ProblemException(401, "Token inválido", "Não foi possível validar o token.")
    if payload.get("type") not in ("access", "enroll"):
        raise ProblemException(401, "Token inválido", "Tipo de token não permitido aqui.")
    jti = payload.get("jti")
    if jti and get_denylist().is_revoked(jti):
        raise ProblemException(401, "Sessão encerrada", "Token revogado.")
    return {"id": payload["sub"], "role": payload.get("role"), "scope": payload.get("scope", "")}


def require(perm: str):
    """Dependência de autorização: exige `perm` para o papel do usuário."""
    async def dep(user: dict = Depends(current_user)) -> dict:
        if perm not in RBAC.get(user.get("role"), set()):
            raise ProblemException(403, "Acesso negado", f"Requer a permissão: {perm}")
        return user
    return dep


async def current_participant(user: dict = Depends(current_user),
                              db: Session = Depends(get_db)) -> uuid.UUID:
    """Deriva o participante autenticado do token (sub) e confere existência."""
    if user.get("role") != "participant":
        raise ProblemException(403, "Acesso negado", "Requer conta de participante.")
    try:
        pid = uuid.UUID(str(user["id"]))
    except (ValueError, TypeError):
        raise ProblemException(401, "Token inválido", "Identificador de participante inválido.")
    if db.scalar(select(Participant.id).where(Participant.id == pid)) is None:
        raise ProblemException(401, "Não autenticado", "Participante não encontrado.")
    return pid
