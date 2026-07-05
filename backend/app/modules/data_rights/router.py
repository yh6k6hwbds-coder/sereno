"""
modules/data_rights/router.py — Direitos do titular (LGPD): acesso e eliminação (admin).

GET  /v1/participants/{id}/data  — exporta os dados do titular (PII do próprio; sem o braço).
POST /v1/participants/{id}/erase — remove a PII direta e marca 'withdrawn' (retém pesquisa
pseudonimizada; auditoria append-only intacta). Ambos auditados. problem+json.
"""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.core.problem import ProblemException
from app.core.models import Participant
from app.modules.audit.service import record_event
from app.modules.data_rights.service import erase_personal_data, export_subject_data

router = APIRouter(prefix="/participants", tags=["data-rights"])


def _actor(user: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        return None


def _require_participant(db: Session, participant_id: uuid.UUID) -> None:
    if db.scalar(select(Participant.id).where(Participant.id == participant_id)) is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")


@router.get("/{participant_id}/data")
async def export_data(participant_id: uuid.UUID, db: Session = Depends(get_db),
                      user: dict = Depends(require("user:manage"))):
    _require_participant(db, participant_id)
    data = export_subject_data(db, participant_id)
    # Auditoria SEM PII: registra que houve acesso, para quem (não o conteúdo).
    record_event(db, action="participant.data_exported", resource_type="participant",
                 actor_type="staff", actor_id=_actor(user), resource_id=participant_id)
    return jsonable_encoder(data)


@router.post("/{participant_id}/erase")
async def erase(participant_id: uuid.UUID, db: Session = Depends(get_db),
                user: dict = Depends(require("user:manage"))):
    _require_participant(db, participant_id)
    removed = erase_personal_data(db, participant_id)
    record_event(db, action="participant.erased", resource_type="participant",
                 actor_type="staff", actor_id=_actor(user), resource_id=participant_id,
                 meta={"removed": removed})
    return {"status": "erased", "removed": removed}
