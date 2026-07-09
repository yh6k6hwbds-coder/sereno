"""
modules/recommender/router.py — Recomendador POR REGRAS ao vivo (E1/ADR-068).

POST /v1/recommendations (participante, `recommend:read`): devolve uma sugestão de protocolo
NEUTRO dentro da biblioteca validada, por regras transparentes e versionadas. Os sinais de
segurança (evento adverso recente, contraindicação) são resolvidos NO SERVIDOR. Cada chamada
é registrada em `recommendation_log` (auditoria + `feature_vector` para um ML FUTURO). ML nunca
decide ao vivo. Não vaza o braço: os handles são idênticos nos dois braços. Erros em problem+json.
"""
from __future__ import annotations
import uuid
from typing import Optional, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require, current_participant
from app.modules.recommender.service import create_recommendation

router = APIRouter(prefix="/recommendations", tags=["recommender"])


class RecommendationRequest(BaseModel):
    goal: Literal["sleep", "anxiety"]
    sleep_issue: Optional[Literal["onset", "maintenance"]] = None
    time_of_day: Literal["day", "evening", "night"] = "evening"


@router.post("", status_code=201)
async def get_recommendation(
    body: RecommendationRequest,
    db: Session = Depends(get_db),
    participant_id: uuid.UUID = Depends(current_participant),
    _user: dict = Depends(require("recommend:read")),
):
    row, rec = create_recommendation(
        db, participant_id, goal=body.goal,
        sleep_issue=body.sleep_issue, time_of_day=body.time_of_day,
    )
    # Resposta ao participante: apenas o necessário e NEUTRO. `input_snapshot`/`feature_vector`
    # ficam só no log (auditoria/ML futuro) e nada aqui revela ativo/sham.
    return {
        "id": str(row.id),
        "action": rec["action"],
        "suggested_protocol": rec["suggested_protocol"],
        "band": rec["band"],
        "rule_id": rec["rule_id"],
        "ruleset_version": rec["ruleset_version"],
        "flag_review": rec["flag_review"],
        "rationale": rec["rationale"],
        "evidence_note": rec["evidence_note"],
        "disclaimer": rec["disclaimer"],
    }
