"""
modules/allocation/router.py — Alocação randômica (ação de staff na inscrição).

POST /v1/allocation aloca um participante e devolve APENAS uma confirmação neutra
(status + bloco) — nunca o braço. A ocultação da alocação vale inclusive para o staff
que inscreve. Nenhum endpoint deste módulo expõe A/B. Erros em problem+json.
"""
from __future__ import annotations
import datetime as dt
import os
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.core.problem import ProblemException
from app.core.models import Participant, Allocation
from app.modules.allocation.service import allocate_participant, is_allocated, resolve_arm
from app.modules.sessions.service import condition_for_arm
from app.modules.audit.service import record_event
from app.modules.screening.service import enrollment_blocker

router = APIRouter(prefix="/allocation", tags=["allocation"])

# Semente e tamanho de bloco vêm do ambiente (semente = segredo custodiado em cofre).
SEED = os.getenv("ALLOCATION_SEED", "dev-seed-trocar-em-producao")
BLOCK_SIZE = int(os.getenv("ALLOCATION_BLOCK_SIZE", "4"))


class AllocateIn(BaseModel):
    participant_id: uuid.UUID


class UnblindIn(BaseModel):
    justification: str = Field(min_length=10, max_length=500)


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


@router.post("/{participant_id}/unblind-request")
async def unblind_request(participant_id: uuid.UUID, body: UnblindIn,
                          db: Session = Depends(get_db),
                          user: dict = Depends(require("unblind:request"))):
    """Desbloqueio CONTROLADO de UM participante: revela a condição (ativo/sham) usando a
    chave selada, exigindo admin + justificativa e registrando o evento em auditoria.

    A condição é revelada APENAS nesta resposta ao admin; a trilha NÃO guarda a condição em
    claro. É o ÚNICO caminho da API para a condição — nenhum outro endpoint a expõe."""
    arm = resolve_arm(db, participant_id)
    if arm is None:
        raise ProblemException(404, "Participante não alocado",
                               "Não há alocação para desbloquear.")
    condition = condition_for_arm(arm)          # usa a chave selada (ARM_CONDITION_MAP)
    if condition is None:
        raise ProblemException(409, "Desbloqueio indisponível",
                               "Chave de condição não configurada; procedimento não pode concluir.")
    alloc = db.scalar(select(Allocation).where(Allocation.participant_id == participant_id))
    alloc.unblinded_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    # Auditoria: quem/quando/POR QUÊ — SEM a condição em claro (o braço nunca entra na trilha).
    record_event(db, action="unblind.performed", resource_type="allocation",
                 actor_type="staff", actor_id=actor_id, resource_id=participant_id,
                 meta={"justification": body.justification})

    return {"participant_id": participant_id, "condition": condition,
            "unblinded_at": alloc.unblinded_at, "justification": body.justification}
