"""
modules/recommender/service.py — camada de aplicação do recomendador POR REGRAS (E1/ADR-068).

Resolve os SINAIS DE SEGURANÇA no servidor (nunca confiando no cliente): evento adverso
recente e contraindicação (triagem inelegível) alimentam os guardrails do motor de regras.
Persiste cada recomendação em `recommendation_log` (entrada→regra→saída + `feature_vector`
para um ML FUTURO). Opera sobre handles NEUTROS e não olha a alocação — logo não vaza o braço.
"""
from __future__ import annotations
import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import (AdverseEvent, Screening, RecommendationLog, PostSessionSurvey,
                             Session as SessionModel)
from app.modules.recommender.recommender import recommend, RecommendationInput, coherence_report, LIBRARY

# Janela do evento adverso: EAs mais antigos que isso não de-escalonam (evita ficar preso
# para sempre num EA remoto). Conservador, mas com validade — refinável por política do estudo.
ADVERSE_WINDOW_DAYS = 14
# Limiar de "não gostou": nota `liked` (0–4) abaixo disso conta como não-tolerado.
LIKED_THRESHOLD = 2


def _recent_adverse_severity(db: Session, participant_id: uuid.UUID) -> Optional[str]:
    """Gravidade do EA mais recente do participante DENTRO da janela (autoritativo no servidor).

    Conservador por segurança: qualquer EA recente pesa; o motor decide se de-escalona
    (só moderate/severe disparam o guardrail). EAs fora da janela não pesam.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=ADVERSE_WINDOW_DAYS)
    return db.scalar(
        select(AdverseEvent.severity)
        .where(AdverseEvent.participant_id == participant_id,
               AdverseEvent.occurred_at >= cutoff)
        .order_by(AdverseEvent.occurred_at.desc())
        .limit(1)
    )


def _last_session_signals(db: Session, participant_id: uuid.UUID) -> tuple[Optional[bool], Optional[int]]:
    """(last_liked, last_intensity) da pós-sessão mais recente do participante.

    Alimenta o guardrail de tolerabilidade: sessão anterior intensa demais e não tolerada
    → de-escalonar. `liked` (0–4) vira booleano por `LIKED_THRESHOLD`. Nada no cliente.
    """
    row = db.execute(
        select(PostSessionSurvey.liked, PostSessionSurvey.intensity)
        .join(SessionModel, PostSessionSurvey.session_id == SessionModel.id)
        .where(SessionModel.participant_id == participant_id)
        .order_by(PostSessionSurvey.answered_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    liked, intensity = row
    return (liked >= LIKED_THRESHOLD if liked is not None else None), intensity


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
    last_liked, last_intensity = _last_session_signals(db, participant_id)
    return RecommendationInput(
        goal=goal,
        sleep_issue=sleep_issue,
        time_of_day=time_of_day,
        recent_adverse_severity=_recent_adverse_severity(db, participant_id),
        contraindicated=_contraindicated(db, participant_id),
        last_liked=last_liked,
        last_intensity=last_intensity,
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


def link_session(db: Session, participant_id: uuid.UUID, rec_id: uuid.UUID,
                 session_id: uuid.UUID) -> bool:
    """Vincula (best-effort) a recomendação à sessão que a seguiu, p/ a coerência.

    Só vincula se a recomendação for do participante e ainda não estiver vinculada — nunca
    falha o fluxo de sessão (um id inválido é simplesmente ignorado). Devolve se vinculou.
    """
    row = db.scalar(
        select(RecommendationLog).where(
            RecommendationLog.id == rec_id,
            RecommendationLog.participant_id == participant_id,
            RecommendationLog.session_id.is_(None),
        )
    )
    if row is None:
        return False
    row.session_id = session_id
    db.flush()
    return True


def coherence(db: Session) -> dict:
    """Relatório de COERÊNCIA (exploratório, CEGO) sobre todo o `recommendation_log`.

    Reúsa `coherence_report` do motor: alinhamento objetivo→banda, taxa de aceitação e, quando
    há vínculo recomendação→sessão, a média de **relaxamento** pós-sessão (aceitas vs recusadas).
    Não há braço envolvido — o relatório é cego.
    """
    rows = db.scalars(select(RecommendationLog)).all()
    # Relaxamento pós-sessão (0–4) por sessão vinculada — para as médias exploratórias.
    linked = [r.session_id for r in rows if r.session_id is not None]
    relax: dict = {}
    if linked:
        relax = {
            sid: rlx for sid, rlx in db.execute(
                select(PostSessionSurvey.session_id, PostSessionSurvey.relaxation)
                .where(PostSessionSurvey.session_id.in_(linked))
            ).all()
        }
    events = []
    for row in rows:
        proto = row.suggested_protocol
        ev = {
            "rec": {
                "action": "recommend" if proto else "no_recommendation",
                "band": LIBRARY.get(proto, {}).get("band") if proto else None,
                "input_snapshot": (row.inputs or {}).get("snapshot", {}),
            },
            "accepted": row.accepted,
        }
        if row.session_id in relax and relax[row.session_id] is not None:
            ev["reported_relaxation"] = relax[row.session_id]
        events.append(ev)
    return coherence_report(events)
