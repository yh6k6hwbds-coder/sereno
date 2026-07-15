"""
modules/consent/router.py — Fluxo de consentimento (TCLE). Primeira fatia vertical.

POST /v1/participants/me/consent registra o aceite/recusa do TCLE do participante
autenticado: valida a versão vigente, calcula um hash de conteúdo (rastreabilidade)
e persiste em consent_record. Erros em problem+json.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import uuid
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import ConsentRecord
from app.modules.audit.service import record_event

router = APIRouter(prefix="/participants/me", tags=["consent"])

# Versão vigente do TCLE (em produção: vir de configuração/conteúdo versionado).
TCLE_CURRENT = "1.0.0"


class ConsentIn(BaseModel):
    tcle_version: str = Field(..., examples=["1.0.0"])
    accepted: bool = Field(..., description="True = concorda em participar")


class ConsentOut(BaseModel):
    id: uuid.UUID
    accepted: bool
    accepted_at: dt.datetime
    content_hash: str


@router.get("/consent/_status")
async def status():
    return {"module": "consent", "tcle_version": TCLE_CURRENT}


@router.post("/consent", status_code=201, response_model=ConsentOut)
async def record_consent(
    body: ConsentIn,
    request: Request,
    db: Session = Depends(get_db),
    participant_id: uuid.UUID = Depends(current_participant),
    _user: dict = Depends(require("consent:write")),
):
    # Só se consente a versao vigente do termo.
    if body.tcle_version != TCLE_CURRENT:
        raise ProblemException(
            409, "Versao do TCLE desatualizada",
            f"Versao vigente e {TCLE_CURRENT}; recarregue o termo atual.",
        )

    now = dt.datetime.now(dt.timezone.utc)
    # Hash de conteudo: prova de o que/quando foi consentido (nao e segredo).
    payload = f"{participant_id}|{body.tcle_version}|{body.accepted}|{now.isoformat()}"
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    record = ConsentRecord(
        participant_id=participant_id,
        tcle_version=body.tcle_version,
        accepted=body.accepted,
        accepted_at=now,
        content_hash=content_hash,
        ip_address=client_ip(request),
    )
    db.add(record)
    db.flush()   # obtem o id; o commit ocorre em get_db

    # Auditoria (append-only, sem PII): registra o aceite/recusa na mesma transação.
    record_event(db, action="consent.recorded", resource_type="consent_record",
                 actor_type="participant", actor_id=participant_id, resource_id=record.id,
                 meta={"tcle_version": body.tcle_version, "accepted": body.accepted})

    return ConsentOut(id=record.id, accepted=record.accepted,
                      accepted_at=record.accepted_at, content_hash=record.content_hash)
