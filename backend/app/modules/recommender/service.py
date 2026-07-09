"""
modules/recommender/service.py — camada de aplicação do recomendador POR REGRAS (E1/ADR-068).

Resolve os SINAIS DE SEGURANÇA no servidor (nunca confiando no cliente): evento adverso
recente e contraindicação (triagem inelegível) alimentam os guardrails do motor de regras.
Persiste cada recomendação em `recommendation_log` (entrada→regra→saída + `feature_vector`
para um ML FUTURO). Opera sobre handles NEUTROS e não olha a alocação — logo não vaza o braço.
"""
from __future__ import annotations
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AdverseEvent, Screening, RecommendationLog
from app.modules.recommender.recommender import recommend, RecommendationInput, coherence_report, LIBRARY


def _recent_adverse_severity(db: Session, participant_id: uuid.UUID) -> Optional[str]:
    """Gravidade do evento adverso mais recente do participante (autoritativo no servidor).

    Conservador por segurança: qualquer EA recente pesa; o motor decide se de-escalona
    (só moderate/severe disparam o guardrail). Janela temporal fica como refinamento futuro.
    """
    return db.scalar(
        select(AdverseEvent.severity)
        .where(AdverseEvent.participant_id == participant_id)
        .order_by(AdverseEvent.occurred_at.desc())
        .limit(1)
    )


def _contraindicated(db: Session, participant_id: uuid.UUID) -> bool:
    """Contraindicação = triagem mais recente existente e INELEGÍVEL (rede de segurança)."""
    eligible = db.scalar(
        select(Screening.eligible)
        .where(Screening.participant_id == participant_id)
        .order_by(Screening.screened_at.desc())
        .limit(1)
    )
    return eligible is False


def build_input(db: Session, participant_id: uuid.UUID, *, goal: str,
                sleep_issue: Optional[str], time_of_day: str) -> RecommendationInput:
    """Monta a entrada do motor: contexto autorrelatado + sinais de segurança do servidor."""
    return RecommendationInput(
        goal=goal,
        sleep_issue=sleep_issue,
        time_of_day=time_of_day,
        recent_adverse_severity=_recent_adverse_severity(db, participant_id),
        contraindicated=_contraindicated(db, participant_id),
    )


def create_recommendation(db: Session, participant_id: uuid.UUID, *, goal: str,
                          sleep_issue: Optional[str] = None,
                          time_of_day: str = "evening") -> tuple[RecommendationLog, dict]:
    """Avalia as regras e registra a recomendação. Devolve (linha_do_log, saída_do_motor)."""
    inp = build_input(db, participant_id, goal=goal, sleep_issue=sleep_issue, time_of_day=time_of_day)
    rec = recommend(inp)
    row = RecommendationLog(
        participant_id=participant_id,
        session_id=None,                                   # recomendação é pré-sessão
        inputs={"snapshot": rec["input_snapshot"], "feature_vector": rec["feature_vector"]},
        rule_id=rec["rule_id"],
        rule_version=rec["ruleset_version"],
        suggested_protocol=rec["suggested_protocol"],      # None em no_recommendation (guardrail)
        accepted=None,
    )
    db.add(row)
    db.flush()
    return row, rec


def get_owned_recommendation(db: Session, participant_id: uuid.UUID,
                             rec_id: uuid.UUID) -> Optional[RecommendationLog]:
    """Recupera uma recomendação SOMENTE se pertencer ao participante (rede anti-IDOR)."""
    return db.scalar(
        select(RecommendationLog).where(
            RecommendationLog.id == rec_id,
            RecommendationLog.participant_id == participant_id,
        )
    )


def coherence(db: Session) -> dict:
    """Relatório de COERÊNCIA (exploratório, CEGO) sobre todo o `recommendation_log`.

    Reúsa `coherence_report` do motor: alinhamento objetivo→banda e taxa de aceitação.
    As médias de relaxamento dependem de um vínculo recomendação→sessão ainda não modelado,
    logo saem como null (pendência honesta). Não há braço envolvido — o relatório é cego.
    """
    events = []
    for row in db.scalars(select(RecommendationLog)).all():
        proto = row.suggested_protocol
        events.append({
            "rec": {
                "action": "recommend" if proto else "no_recommendation",
                "band": LIBRARY.get(proto, {}).get("band") if proto else None,
                "input_snapshot": (row.inputs or {}).get("snapshot", {}),
            },
            "accepted": row.accepted,
        })
    return coherence_report(events)
