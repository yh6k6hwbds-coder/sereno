"""
modules/allocation/router.py — Alocação randômica (ação de staff na inscrição).

POST /v1/allocation aloca um participante e devolve APENAS uma confirmação neutra
(status + bloco) — nunca o braço. A ocultação da alocação vale inclusive para o staff
que inscreve. Nenhum endpoint deste módulo expõe A/B. Erros em problem+json.
"""
from __future__ import annotations
import os
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.core.problem import ProblemException
from app.core.models import Participant
from app.modules.allocation.service import allocate_participant, is_allocated
from app.modules.audit.service import record_event
from app.modules.screening.service import enrollment_blocker

router = APIRouter(prefix="/allocation", tags=["allocation"])

# Semente e tamanho de bloco vêm do ambiente (semente = segredo custodiado em cofre).
SEED = os.getenv("ALLOCATION_SEED", "dev-seed-trocar-em-producao")
BLOCK_SIZE = int(os.getenv("ALLOCATION_BLOCK_SIZE", "4"))


class AllocateIn(BaseModel):
    participant_id: uuid.UUID


@router.get("/_status")
async def status():
    return {"module": "allocation", "status": "stub"}


@router.post("", status_code=201)
async def allocate(body: AllocateIn, db: Session = Depends(get_db),
                   user: dict = Depends(require("enroll:write"))):
    if db.scalar(select(Participant.id).where(Participant.id == body.participant_id)) is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")
    # Funil de inscrição: só aloca quem foi triado (elegível) e consentiu (C2).
    blocker = enrollment_blocker(db, body.participant_id)
    if blocker is not None:
        raise ProblemException(409, "Inscrição incompleta", blocker)
    if is_allocated(db, body.participant_id):
        raise ProblemException(409, "Participante já alocado", "Este participante já possui alocação.")
    alloc = allocate_participant(db, body.participant_id, seed=SEED, block_size=BLOCK_SIZE)

    # Auditoria (append-only): registra que houve alocação — NUNCA o braço (arm_coded),
    # que permanece oculto inclusive na trilha. Apenas metadado neutro (bloco).
    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    record_event(db, action="allocation.created", resource_type="allocation",
                 actor_type="staff", actor_id=actor_id, resource_id=alloc.id,
                 meta={"block": alloc.block})

    # Confirmação NEUTRA — sem o braço (ocultação da alocação, inclusive para o staff).
    return {"status": "allocated", "block": alloc.block}
