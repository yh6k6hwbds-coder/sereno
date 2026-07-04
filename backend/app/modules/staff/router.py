"""
modules/staff/router.py — Gestão de staff (admin) + cadastro de MFA (TOTP).

- POST /v1/staff (admin `user:manage`): cria pesquisador/admin (senha argon2id). NÃO há
  auto-registro público. E-mail único (409). Auditado, sem senha/segredo.
- POST /v1/staff/me/mfa/enroll: gera e guarda um segredo TOTP e devolve o `provisioning_uri`;
  o MFA só é ATIVADO após confirmar (evita lockout).
- POST /v1/staff/me/mfa/confirm: valida um código TOTP e ativa o MFA.
Nunca se loga/audita o segredo de MFA nem a senha. problem+json em erros.
"""
from __future__ import annotations
import re
import uuid
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require, current_user
from app.core.problem import ProblemException
from app.core.models import StaffUser
from app.core import auth
from app.modules.audit.service import record_event

router = APIRouter(prefix="/staff", tags=["staff"])

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
    return staff


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
async def enroll_mfa(db: Session = Depends(get_db), user: dict = Depends(current_user)):
    staff = _current_staff(db, user)
    secret = auth.new_mfa_secret()
    staff.mfa_secret = secret.encode()      # guardado como bytes; NUNCA logado
    staff.mfa_enabled = False               # só ativa após confirmar
    db.flush()
    return {"provisioning_uri": auth.provisioning_uri(secret, staff.email), "secret": secret}


@router.post("/me/mfa/confirm")
async def confirm_mfa(body: MfaConfirmIn, db: Session = Depends(get_db),
                      user: dict = Depends(current_user)):
    staff = _current_staff(db, user)
    if not staff.mfa_secret or not auth.verify_totp(staff.mfa_secret.decode(), body.code):
        raise ProblemException(401, "Código inválido", "Código TOTP incorreto ou cadastro não iniciado.")
    staff.mfa_enabled = True
    db.flush()
    record_event(db, action="mfa.enabled", resource_type="staff_user",
                 actor_type="staff", actor_id=staff.id, resource_id=staff.id)
    return {"mfa_enabled": True}
