"""
modules/screening/router.py — Triagem/elegibilidade (staff). Passo 1 do funil de inscrição.

POST /v1/screening (staff `enroll:write`): calcula a elegibilidade por regra determinística
e versionada, grava critérios + decisão e audita (sem PII). Uma triagem por participante
(409 se já triado). É pré-condição, junto ao consentimento, para a alocação. problem+json.
"""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.core.problem import ProblemException
from app.core.models import Participant, Screening
from app.modules.audit.service import record_event
from app.modules.screening.service import evaluate_eligibility, latest_screening, CRITERIA_VERSION

router = APIRouter(prefix="/screening", tags=["screening"])


class ScreeningIn(BaseModel):
    participant_id: uuid.UUID
    inclusion: dict[str, bool] = Field(default_factory=dict)
    exclusion: dict[str, bool] = Field(default_factory=dict)
    symptoms: dict | None = None


@router.post("", status_code=201)
async def record_screening(body: ScreeningIn, db: Session = Depends(get_db),
                           user: dict = Depends(require("enroll:write"))):
    if db.scalar(select(Participant.id).where(Participant.id == body.participant_id)) is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")
    if latest_screening(db, body.participant_id) is not None:
        raise ProblemException(409, "Já triado", "Este participante já possui triagem registrada.")

    eligible = evaluate_eligibility(body.inclusion, body.exclusion)
    db.add(Screening(
        participant_id=body.participant_id, eligible=eligible,
        criteria={"version": CRITERIA_VERSION, "inclusion": body.inclusion, "exclusion": body.exclusion},
        symptoms=body.symptoms,
    ))
    db.flush()

    # Auditoria (append-only, sem PII): registra a decisão de elegibilidade.
    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    record_event(db, action="screening.recorded", resource_type="screening",
                 actor_type="staff", actor_id=actor_id, resource_id=body.participant_id,
                 meta={"eligible": eligible})

    return {"status": "screened", "eligible": eligible}
