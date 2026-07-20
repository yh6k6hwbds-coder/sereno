"""
modules/staff/router.py — Gestão de staff (admin) + cadastro de MFA (TOTP).

- POST /v1/staff (admin `user:manage`): cria pesquisador/admin (senha argon2id). NÃO há
  auto-registro público. E-mail único (409). Auditado, sem senha/segredo.
- GET /v1/staff (admin): lista o estado operacional (papel, MFA, ativo, último login).
- POST /v1/staff/{id}/deactivate|activate (admin): lifecycle — desativar suspende o acesso
  imediatamente (o RBAC confere `is_active` no banco); admin não desativa a si mesmo.
- POST /v1/staff/me/password: rotação da própria senha (exige a atual) + revoga o token em uso.
- POST /v1/staff/me/mfa/enroll: gera e guarda um segredo TOTP e devolve o `provisioning_uri`;
  o MFA só é ATIVADO após confirmar (evita lockout).
- POST /v1/staff/me/mfa/confirm: valida um código TOTP e ativa o MFA.
Nunca se loga/audita o segredo de MFA nem a senha. problem+json em erros.
"""
from __future__ import annotations
import datetime as dt
import re
import uuid
from typing import Literal
from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require, current_staff_enrolling, current_user
from app.core.token_revocation import get_denylist
from app.core.problem import ProblemException
from app.core.models import StaffUser
from app.core import auth
from app.modules.audit.service import record_event

router = APIRouter(prefix="/staff", tags=["staff"])
_bearer = HTTPBearer(auto_error=False)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StaffCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    role: Literal["researcher", "admin"]
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("e-mail inválido")
        return v


class MfaConfirmIn(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class PasswordRotateIn(BaseModel):
    current_password: str = Field(min_length=8, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


def _current_staff(db: Session, user: dict) -> StaffUser:
    """Carrega o StaffUser autenticado; 403 se não for staff, 401 se não existir."""
    if user.get("role") not in ("researcher", "admin"):
        raise ProblemException(403, "Acesso negado", "Requer conta de staff.")
    try:
        staff = db.get(StaffUser, uuid.UUID(str(user["id"])))
    except (ValueError, TypeError):
        raise ProblemException(401, "Token inválido", "Identificador de staff inválido.")
    if staff is None:
        raise ProblemException(401, "Não autenticado", "Usuário de staff não encontrado.")
    if not staff.is_active:
        # Vale também para o token de "enroll": conta suspensa não cadastra MFA (ADR-081).
        raise ProblemException(401, "Acesso suspenso", "Esta conta de staff está desativada.")
    return staff


def _actor_id(user: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        return None


def _set_active(db: Session, staff_id: str, admin: dict, *, active: bool) -> dict:
    """Núcleo comum de activate/deactivate: 404 inexistente, 409 se já está no estado."""
    try:
        target = db.get(StaffUser, uuid.UUID(str(staff_id)))
    except (ValueError, TypeError):
        target = None
    if target is None:
        raise ProblemException(404, "Staff não encontrado", "Não existe staff com este identificador.")
    actor = _actor_id(admin)
    if not active and actor is not None and target.id == actor:
        # Lockout: um admin que se desativa perde o próprio caminho de volta.
        raise ProblemException(409, "Operação inválida", "Um admin não pode desativar a si mesmo.")
    if target.is_active == active:
        raise ProblemException(409, "Estado inalterado",
                               "A conta já está " + ("ativa." if active else "desativada."))
    target.is_active = active
    db.flush()
    # Auditoria SEM PII: só quem, sobre quem e o novo estado (o e-mail não entra no log).
    record_event(db, action="staff.activated" if active else "staff.deactivated",
                 resource_type="staff_user", actor_type="staff", actor_id=actor,
                 resource_id=target.id, meta={"role": target.role})
    return {"id": target.id, "is_active": target.is_active}


@router.get("")
async def list_staff(db: Session = Depends(get_db),
                     _admin: dict = Depends(require("user:manage"))):
    """Estado operacional do time — sem senha e sem segredo de MFA no corpo."""
    rows = db.scalars(select(StaffUser).order_by(StaffUser.created_at)).all()
    return {"items": [{"id": u.id, "email": u.email, "role": u.role,
                       "mfa_enabled": u.mfa_enabled, "is_active": u.is_active,
                       "last_login_at": u.last_login_at, "created_at": u.created_at}
                      for u in rows]}


@router.post("/{staff_id}/deactivate")
async def deactivate_staff(staff_id: str, db: Session = Depends(get_db),
                           admin: dict = Depends(require("user:manage"))):
    return _set_active(db, staff_id, admin, active=False)


@router.post("/{staff_id}/activate")
async def activate_staff(staff_id: str, db: Session = Depends(get_db),
                         admin: dict = Depends(require("user:manage"))):
    return _set_active(db, staff_id, admin, active=True)


@router.post("/me/password")
async def rotate_password(body: PasswordRotateIn, db: Session = Depends(get_db),
                          cred: HTTPAuthorizationCredentials = Depends(_bearer),
                          user: dict = Depends(current_user)):
    """Troca a própria senha. Exige a atual (posse do token não basta) e revoga o
    token usado na chamada — trocar senha encerra a sessão em curso (ADR-081)."""
    staff = _current_staff(db, user)
    if not auth.verify_password(staff.password_hash, body.current_password):
        raise ProblemException(401, "Credenciais inválidas", "A senha atual está incorreta.")
    if body.new_password == body.current_password:
        raise ProblemException(422, "Senha inválida", "A nova senha deve ser diferente da atual.")
    staff.password_hash = auth.hash_password(body.new_password)
    db.flush()
    # Auditoria SEM segredo: registra o fato, nunca a senha (nem hash).
    record_event(db, action="staff.password_rotated", resource_type="staff_user",
                 actor_type="staff", actor_id=staff.id, resource_id=staff.id)
    if cred is not None:
        payload = auth.decode_token(cred.credentials, expected_type="access")
        jti, exp = payload.get("jti"), payload.get("exp")
        if jti and exp:
            now = int(dt.datetime.now(dt.timezone.utc).timestamp())
            get_denylist().revoke(jti, max(int(exp) - now, 1))
    return {"status": "password_rotated"}


@router.post("", status_code=201)
async def create_staff(body: StaffCreateIn, db: Session = Depends(get_db),
                       admin: dict = Depends(require("user:manage"))):
    if db.scalar(select(StaffUser.id).where(StaffUser.email == body.email)) is not None:
        raise ProblemException(409, "E-mail já cadastrado", "Já existe staff com este e-mail.")
    staff = StaffUser(email=body.email, password_hash=auth.hash_password(body.password),
                      role=body.role, mfa_enabled=False)
    db.add(staff)
    db.flush()

    actor_id = None
    try:
        actor_id = uuid.UUID(str(admin["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    # Auditoria SEM PII/segredo: só o papel criado (o e-mail não entra no log).
    record_event(db, action="staff.created", resource_type="staff_user",
                 actor_type="staff", actor_id=actor_id, resource_id=staff.id,
                 meta={"role": staff.role})

    return {"id": staff.id, "email": staff.email, "role": staff.role}


@router.post("/me/mfa/enroll")
async def enroll_mfa(db: Session = Depends(get_db), user: dict = Depends(current_staff_enrolling)):
    staff = _current_staff(db, user)
    secret = auth.new_mfa_secret()
    staff.mfa_secret = secret.encode()      # guardado como bytes; NUNCA logado
    staff.mfa_enabled = False               # só ativa após confirmar
    db.flush()
    return {"provisioning_uri": auth.provisioning_uri(secret, staff.email), "secret": secret}


@router.post("/me/mfa/confirm")
async def confirm_mfa(body: MfaConfirmIn, db: Session = Depends(get_db),
                      user: dict = Depends(current_staff_enrolling)):
    staff = _current_staff(db, user)
    if not staff.mfa_secret or not auth.verify_totp(staff.mfa_secret.decode(), body.code):
        raise ProblemException(401, "Código inválido", "Código TOTP incorreto ou cadastro não iniciado.")
    staff.mfa_enabled = True
    db.flush()
    record_event(db, action="mfa.enabled", resource_type="staff_user",
                 actor_type="staff", actor_id=staff.id, resource_id=staff.id)
    return {"mfa_enabled": True}
