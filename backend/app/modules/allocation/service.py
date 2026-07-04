"""
modules/allocation/service.py — Alocação (persistência) e resolução INTERNA do braço.

`allocate_participant` grava o braço CODIFICADO (A/B) a partir da sequência determinística.
`resolve_arm` é usado apenas no servidor (resolução handle→áudio nas sessões) e NUNCA é
exposto por API. Nota de concorrência: a ordinalidade vem de COUNT(*); em inscrições
simultâneas há risco de colisão de índice — no piloto, serializar a inscrição; numa versão
robusta, usar um contador com bloqueio (SELECT ... FOR UPDATE) ou sequência dedicada.
"""
from __future__ import annotations
import uuid
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.models import Allocation
from app.modules.allocation.randomization import arm_for_index, block_of, seed_ref


def is_allocated(db: Session, participant_id: uuid.UUID) -> bool:
    return db.scalar(select(Allocation.id).where(Allocation.participant_id == participant_id)) is not None


def allocate_participant(db: Session, participant_id: uuid.UUID, *, seed: str, block_size: int) -> Allocation:
    index = db.scalar(select(func.count()).select_from(Allocation))   # ordinal (0-based)
    alloc = Allocation(
        participant_id=participant_id,
        arm_coded=arm_for_index(index, block_size, seed),
        block=block_of(index, block_size),
        sequence_seed_ref=seed_ref(seed),
    )
    db.add(alloc)
    db.flush()
    return alloc


def resolve_arm(db: Session, participant_id: uuid.UUID) -> str | None:
    """INTERNO — jamais exposto por API. Só para resolver o áudio da sessão (ativo/sham)."""
    return db.scalar(select(Allocation.arm_coded).where(Allocation.participant_id == participant_id))
