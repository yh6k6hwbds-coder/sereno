"""
modules/screening/router.py — Triagem/elegibilidade (staff). Passo 1 do funil de inscrição.

POST /v1/screening (staff `enroll:write`): recebe as respostas dos critérios do protocolo,
CALCULA os critérios derivados (faixa sintomática e gatilho de risco) a partir dos escores,
aplica a regra determinística, grava critérios + decisão e audita (sem PII). Uma triagem por
participante (409 se já triado). É pré-condição, junto ao consentimento, para a alocação.

GET /v1/screening/criteria: o catálogo em vigor — as chaves que o formulário precisa
responder e quais o servidor calcula sozinho. problem+json.
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
from app.modules.screening import service as screening

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
    # G8: a faixa sintomática de inclusão é "GAD-7 entre 5 e 14 E/OU PSQI > 5" — sem o PSQI,
    # quem tem só sono ruim não teria como entrar pela regra.
    psqi_global: int | None = Field(default=None, ge=0, le=21)


@router.get("/criteria")
async def list_criteria(_user: dict = Depends(require("enroll:write"))):
    """Critérios de elegibilidade em vigor (chaves, rótulos e quais são derivados)."""
    return screening.criteria_catalog()


@router.post("", status_code=201)
async def record_screening(body: ScreeningIn, db: Session = Depends(get_db),
                           user: dict = Depends(require("enroll:write"))):
    if db.scalar(select(Participant.id).where(Participant.id == body.participant_id)) is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")
    if screening.latest_screening(db, body.participant_id) is not None:
        raise ProblemException(409, "Já triado", "Este participante já possui triagem registrada.")
    try:
        screening.validate_declared(body.inclusion, body.exclusion)
    except screening.CriteriaError as e:
        raise ProblemException(422, "Critérios de triagem incompletos", str(e)) from None

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

    # Critérios DERIVADOS: calculados dos escores, nunca declarados (ver service).
    inclusion = dict(body.inclusion)
    inclusion["sintomas_elegiveis"] = screening.symptoms_eligible(body.gad7_total, body.psqi_global)
    exclusion = dict(body.exclusion)
    exclusion["d_gad7_grave_ou_risco"] = ficha is not None

    eligible = screening.evaluate_eligibility(inclusion, exclusion)

    criterios = {"version": screening.CRITERIA_VERSION, "inclusion": inclusion,
                 "exclusion": exclusion,
                 "scores": {"gad7_total": body.gad7_total, "psqi_global": body.psqi_global}}
    if ficha is not None:
        criterios["safety_exclusion"] = list(ficha.reasons or [])
    db.add(Screening(
        participant_id=body.participant_id, eligible=eligible,
        criteria=criterios,
        symptoms=body.symptoms,
    ))
    db.flush()

    # Auditoria (append-only, sem PII): registra a decisão de elegibilidade e QUAIS critérios
    # a barraram — sem isso, "inelegível" não se explica a quem lê a trilha depois.
    nao_atendidos = sorted([k for k, v in inclusion.items() if not v]
                           + [k for k, v in exclusion.items() if v])
    record_event(db, action="screening.recorded", resource_type="screening",
                 actor_type="staff", actor_id=actor_id, resource_id=body.participant_id,
                 meta={"eligible": eligible, "risk_detected": ficha is not None,
                       "criteria_version": screening.CRITERIA_VERSION,
                       "unmet": nao_atendidos})

    return {"status": "screened", "eligible": eligible,
            "risk_detected": ficha is not None,
            "unmet_criteria": nao_atendidos,
            "referral_id": str(ficha.id) if ficha is not None else None}
