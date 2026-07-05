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


def _actor_id(user: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        return None


@router.post("/{participant_id}/unblind-request")
async def unblind_request(participant_id: uuid.UUID, body: UnblindIn,
                          db: Session = Depends(get_db),
                          user: dict = Depends(require("unblind:request"))):
    """Passo 1 do desbloqueio em DUAS PESSOAS: um admin abre um pedido justificado.

    NÃO revela a condição — apenas registra a pendência (quem/quando/por quê) e audita o
    pedido SEM a condição. A revelação só ocorre em `unblind-approve`, exigida a um SEGUNDO
    admin distinto. Impede reveal por uma única pessoa (integridade do cegamento)."""
    alloc = db.scalar(select(Allocation).where(Allocation.participant_id == participant_id))
    if alloc is None:
        raise ProblemException(404, "Participante não alocado",
                               "Não há alocação para desbloquear.")
    if alloc.unblinded_at is not None:
        raise ProblemException(409, "Já desbloqueado", "Esta alocação já foi revelada.")
    if alloc.unblind_requested_at is not None:
        raise ProblemException(409, "Pedido já pendente",
                               "Já existe um pedido de desbloqueio aguardando aprovação.")
    alloc.unblind_requested_by = _actor_id(user)
    alloc.unblind_requested_at = dt.datetime.now(dt.timezone.utc)
    alloc.unblind_justification = body.justification
    db.flush()

    # Auditoria do PEDIDO — sem a condição (o braço nunca entra na trilha).
    record_event(db, action="unblind.requested", resource_type="allocation",
                 actor_type="staff", actor_id=alloc.unblind_requested_by,
                 resource_id=participant_id, meta={"justification": body.justification})

    return {"participant_id": participant_id, "status": "pending_approval",
            "requested_at": alloc.unblind_requested_at}


@router.post("/{participant_id}/unblind-approve")
async def unblind_approve(participant_id: uuid.UUID, db: Session = Depends(get_db),
                          user: dict = Depends(require("unblind:request"))):
    """Passo 2 do desbloqueio em duas pessoas: um SEGUNDO admin DISTINTO aprova e revela.

    A condição (ativo/sham) é revelada APENAS nesta resposta, via chave selada; a trilha
    NÃO guarda a condição. Regra das duas pessoas: o aprovador não pode ser o solicitante.
    É o ÚNICO caminho da API para a condição — nenhum outro endpoint a expõe."""
    alloc = db.scalar(select(Allocation).where(Allocation.participant_id == participant_id))
    if alloc is None:
        raise ProblemException(404, "Participante não alocado",
                               "Não há alocação para desbloquear.")
    if alloc.unblinded_at is not None:
        raise ProblemException(409, "Já desbloqueado", "Esta alocação já foi revelada.")
    if alloc.unblind_requested_at is None:
        raise ProblemException(409, "Sem pedido pendente",
                               "É preciso um pedido de desbloqueio antes de aprovar.")
    approver = _actor_id(user)
    if approver is not None and approver == alloc.unblind_requested_by:
        raise ProblemException(409, "Requer segundo aprovador",
                               "A aprovação exige um admin distinto de quem solicitou.")
    condition = condition_for_arm(resolve_arm(db, participant_id))   # chave selada (ARM_CONDITION_MAP)
    if condition is None:
        raise ProblemException(409, "Desbloqueio indisponível",
                               "Chave de condição não configurada; procedimento não pode concluir.")
    alloc.unblinded_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    # Auditoria da APROVAÇÃO — quem aprovou/quando/por quê — SEM a condição em claro.
    record_event(db, action="unblind.performed", resource_type="allocation",
                 actor_type="staff", actor_id=approver, resource_id=participant_id,
                 meta={"justification": alloc.unblind_justification})

    return {"participant_id": participant_id, "condition": condition,
            "unblinded_at": alloc.unblinded_at, "justification": alloc.unblind_justification}
