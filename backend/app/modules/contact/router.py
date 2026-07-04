"""
modules/contact/router.py — Captura de contato do participante com PII CIFRADA.

POST /v1/participants/{id}/contact (staff `enroll:write`): grava nome e e-mail CIFRADOS
em repouso (AES-256-GCM, chave via env/KMS — nunca versionada), separados do dado de
pesquisa. A resposta é NEUTRA (nunca ecoa PII). Pré-requisito para a entrega real de OTP
por e-mail. A captura é auditada (SEM PII) pela trilha append-only. Erros em problem+json.
"""
from __future__ import annotations
import re
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.core.problem import ProblemException
from app.core.models import Participant, ContactInfo
from app.core import pii_crypto
from app.modules.audit.service import record_event

router = APIRouter(prefix="/participants", tags=["contact"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("e-mail inválido")
        return v


@router.post("/{participant_id}/contact", status_code=201)
async def store_contact(participant_id: uuid.UUID, body: ContactIn,
                        db: Session = Depends(get_db),
                        user: dict = Depends(require("enroll:write"))):
    if db.scalar(select(Participant.id).where(Participant.id == participant_id)) is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")

    # Cifra ANTES de tocar o banco; AAD liga cada valor ao participante e ao campo.
    enc_name = pii_crypto.encrypt(body.name, aad=pii_crypto.aad_for(participant_id, "name"))
    enc_email = pii_crypto.encrypt(body.email, aad=pii_crypto.aad_for(participant_id, "email"))

    existing = db.scalar(select(ContactInfo).where(ContactInfo.participant_id == participant_id))
    if existing is None:
        db.add(ContactInfo(participant_id=participant_id, enc_name=enc_name, enc_email=enc_email))
    else:
        existing.enc_name = enc_name          # correção de contato: sobrescreve o ciphertext
        existing.enc_email = enc_email
    db.flush()

    # Auditoria (append-only, SEM PII): registra apenas QUE houve captura, para quem.
    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    record_event(db, action="contact.stored", resource_type="contact_info",
                 actor_type="staff", actor_id=actor_id, resource_id=participant_id)

    return {"status": "stored"}          # resposta NEUTRA — nunca ecoa a PII
