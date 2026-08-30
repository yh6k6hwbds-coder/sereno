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
from app.modules.instruments.instruments_scoring import score_phq9
from app.modules.safety import service as safety
from app.modules.screening.service import evaluate_eligibility, latest_screening, CRITERIA_VERSION

router = APIRouter(prefix="/screening", tags=["screening"])


class ScreeningIn(BaseModel):
    participant_id: uuid.UUID
    inclusion: dict[str, bool] = Field(default_factory=dict)
    exclusion: dict[str, bool] = Field(default_factory=dict)
    symptoms: dict | None = None
    # Segurança na triagem (G5): PHQ-9 (item 9) e GAD-7. Não são desfecho — são o gatilho do
    # critério de exclusão (d) e do fluxo de encaminhamento.
    phq9_items: list[int] | None = Field(default=None, min_length=9, max_length=9)
    gad7_total: int | None = Field(default=None, ge=0, le=21)


@router.post("", status_code=201)
async def record_screening(body: ScreeningIn, db: Session = Depends(get_db),
                           user: dict = Depends(require("enroll:write"))):
    if db.scalar(select(Participant.id).where(Participant.id == body.participant_id)) is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")
    if latest_screening(db, body.participant_id) is not None:
        raise ProblemException(409, "Já triado", "Este participante já possui triagem registrada.")

    eligible = evaluate_eligibility(body.inclusion, body.exclusion)

    # Segurança ANTES da elegibilidade: o protocolo manda não incluir quem aciona o gatilho,
    # por mais que os critérios marcados digam o contrário. Quem decide aqui é a regra, não
    # quem preencheu o formulário.
    phq9 = None
    if body.phq9_items is not None:
        if any(r not in (0, 1, 2, 3) for r in body.phq9_items):
            raise ProblemException(422, "PHQ-9 inválido", "Respostas do PHQ-9 devem ser 0 a 3.")
        phq9 = score_phq9(list(body.phq9_items))
    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    _, ficha = safety.record_assessment(
        db, body.participant_id, moment="triagem", phq9=phq9, gad7_total=body.gad7_total,
        actor_type="staff", actor_id=actor_id)
    if ficha is not None:
        eligible = False

    criterios = {"version": CRITERIA_VERSION, "inclusion": body.inclusion,
                 "exclusion": body.exclusion}
    if ficha is not None:
        criterios["safety_exclusion"] = list(ficha.reasons or [])
    db.add(Screening(
        participant_id=body.participant_id, eligible=eligible,
        criteria=criterios,
        symptoms=body.symptoms,
    ))
    db.flush()

    # Auditoria (append-only, sem PII): registra a decisão de elegibilidade.
    record_event(db, action="screening.recorded", resource_type="screening",
                 actor_type="staff", actor_id=actor_id, resource_id=body.participant_id,
                 meta={"eligible": eligible, "risk_detected": ficha is not None})

    return {"status": "screened", "eligible": eligible,
            "risk_detected": ficha is not None,
            "referral_id": str(ficha.id) if ficha is not None else None}
