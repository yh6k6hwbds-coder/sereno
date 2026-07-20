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

from sqlalchemy import select, update

from app.core.client_ip import client_ip
from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import ConsentRecord, Participant
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


@router.post("/consent/withdraw")
async def withdraw_consent(
    db: Session = Depends(get_db),
    participant_id: uuid.UUID = Depends(current_participant),
    _user: dict = Depends(require("consent:write")),
):
    """O próprio titular retira o consentimento (LGPD, Art. 8 §5).

    Marca o consentimento ativo como revogado (`revoked_at`) e o participante como
    `withdrawn` — o que **encerra a participação** (o início de sessão passa a recusar).
    NÃO elimina dados: a eliminação (Art. 18) é direito separado (canal do Encarregado /
    rota de admin) e o dado de pesquisa já coletado é retido pseudonimizado (ADR-066).
    Auditado, sem PII. Retirar de novo → 409."""
    p = db.get(Participant, participant_id)
    if p is None:                                    # rede: current_participant já garante
        raise ProblemException(401, "Não autenticado", "Participante não encontrado.")
    if p.status == "withdrawn":
        raise ProblemException(409, "Consentimento já retirado",
                               "Você já retirou o consentimento anteriormente.")

    now = dt.datetime.now(dt.timezone.utc)
    # Carimba revoked_at nos consentimentos ATIVOS (aceitos e ainda não revogados).
    revoked = db.execute(
        update(ConsentRecord)
        .where(ConsentRecord.participant_id == participant_id,
               ConsentRecord.accepted.is_(True),
               ConsentRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount
    p.status = "withdrawn"
    db.flush()

    # Auditoria SEM PII: só o fato e quantos registros foram revogados.
    record_event(db, action="consent.withdrawn", resource_type="participant",
                 actor_type="participant", actor_id=participant_id, resource_id=participant_id,
                 meta={"revoked_consents": int(revoked or 0)})

    return {"status": "withdrawn", "revoked_consents": int(revoked or 0),
            "withdrawn_at": now.isoformat()}
