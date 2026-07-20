"""
modules/research/features_service.py — Consolidação OFFLINE de features p/ ML (E4/ADR-083).

Achata o ``recommendation_log`` (a espinha: entrada→regra→saída + ``feature_vector``) unindo,
quando houver, a telemetria da sessão vinculada e a pós-sessão, num **dataset de pesquisa**
para modelagem FUTURA. Inegociáveis preservados:

  - **Sempre OFFLINE** (inegociável #5): consolida o que já foi registrado; **nada aqui decide**
    nem alimenta o recomendador ao vivo. O motor continua por regras.
  - **SEM PII** (inegociável #6): só o ``study_code`` pseudônimo; nenhum nome/e-mail/timestamp
    em claro (usa-se um índice ordinal por participante, não a hora de parede).
  - **SEM a condição** (inegociável #2): jamais ativo/sham nem a chave selada — apenas o braço
    **CODIFICADO A/B** (que a análise cega usa; o mapa A/B→condição só abre no *data lock*). O
    ``protocolo_sugerido`` é o **handle neutro** de banda (ex.: ``alpha-10``), não revela braço.

Uma linha por recomendação — inclusive as ``no_recommendation`` dos guardrails (evento de
segurança) e as ainda **não vinculadas** a uma sessão (telemetria em branco). Não persiste em
banco (sem migração); em produção a consolidação vira um job offline (RQ) + storage.
"""
from __future__ import annotations
import csv
import io
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import (Allocation, Participant, RecommendationLog,
                             Session as SessionModel, PostSessionSurvey)


def _arm_label(arm_coded: str | None) -> str:
    """Rótulo CODIFICADO (nunca a condição). Sem alocação → marcador explícito."""
    if arm_coded == "A":
        return "Grupo A"
    if arm_coded == "B":
        return "Grupo B"
    return "nao_alocado"


def _yn(v: bool | None) -> str:
    """bool → 'sim'/'nao'; None → '' (ausência é informativa, não é 0)."""
    return "" if v is None else ("sim" if v else "nao")


def _s(v) -> str:
    return "" if v is None else str(v)


@dataclass
class FeatureRow:
    codigo: str
    grupo_codificado: str
    rec_index: int                 # ordinal por participante (temporal, sem hora de parede)
    # feature_vector (entrada da regra) — o que o ML FUTURO estudaria:
    objetivo: str
    problema_sono: str
    hora_do_dia: str
    severidade_ea_recente: str
    gostou_anterior: str
    intensidade_anterior: str
    # regra disparada → saída (handle NEUTRO; nunca ativo/sham):
    regra: str
    versao_regras: str
    protocolo_sugerido: str
    acao: str
    aceita: str
    # telemetria da sessão vinculada (em branco se não houver):
    sessao_completa: str
    segundos_efetivos: str
    interrupcoes: str
    # pós-sessão (em branco se não houver):
    sentimento: str
    relaxamento: str
    dormiu_melhor: str
    gostou: str
    intensidade: str
    repetiria: str


_COLUMNS = ["codigo", "grupo_codificado", "rec_index", "objetivo", "problema_sono",
            "hora_do_dia", "severidade_ea_recente", "gostou_anterior", "intensidade_anterior",
            "regra", "versao_regras", "protocolo_sugerido", "acao", "aceita",
            "sessao_completa", "segundos_efetivos", "interrupcoes",
            "sentimento", "relaxamento", "dormiu_melhor", "gostou", "intensidade", "repetiria"]


def gather_feature_rows(db: Session) -> list[FeatureRow]:
    """Uma linha por recomendação, pseudonimizada e CEGA (braço codificado)."""
    logs = db.scalars(select(RecommendationLog).order_by(
        RecommendationLog.participant_id, RecommendationLog.created_at, RecommendationLog.id)).all()

    # Braço codificado por participante (uma consulta; None se não alocado).
    arm_by_pid = {a.participant_id: a.arm_coded for a in db.scalars(select(Allocation)).all()}

    # Pós-sessão por sessão vinculada (uma consulta) — para juntar sem N+1.
    linked_sids = [l.session_id for l in logs if l.session_id is not None]
    surveys: dict = {}
    sessions: dict = {}
    if linked_sids:
        surveys = {s.session_id: s for s in db.scalars(
            select(PostSessionSurvey).where(PostSessionSurvey.session_id.in_(linked_sids))).all()}
        sessions = {s.id: s for s in db.scalars(
            select(SessionModel).where(SessionModel.id.in_(linked_sids))).all()}

    codes: dict = {}
    counters: dict = {}
    rows: list[FeatureRow] = []
    for log in logs:
        pid = log.participant_id
        if pid not in codes:
            p = db.get(Participant, pid)
            codes[pid] = p.study_code if p else _s(pid)
        counters[pid] = counters.get(pid, 0) + 1

        fv = (log.inputs or {}).get("feature_vector", {}) or {}
        sess = sessions.get(log.session_id)
        surv = surveys.get(log.session_id)
        rows.append(FeatureRow(
            codigo=codes[pid],
            grupo_codificado=_arm_label(arm_by_pid.get(pid)),
            rec_index=counters[pid],
            objetivo=_s(fv.get("goal")),
            problema_sono=_s(fv.get("sleep_issue")),
            hora_do_dia=_s(fv.get("time_of_day")),
            severidade_ea_recente=_s(fv.get("recent_adverse_severity")),
            gostou_anterior=_yn(fv.get("last_liked")),
            intensidade_anterior=_s(fv.get("last_intensity")),
            regra=log.rule_id,
            versao_regras=log.rule_version,
            protocolo_sugerido=_s(log.suggested_protocol),
            acao="recommend" if log.suggested_protocol else "no_recommendation",
            aceita=_yn(log.accepted),
            sessao_completa=_yn(sess.completed) if sess else "",
            segundos_efetivos=_s(sess.effective_seconds) if sess else "",
            interrupcoes=_s(sess.interruptions) if sess else "",
            sentimento=_s(surv.feeling) if surv else "",
            relaxamento=_s(surv.relaxation) if surv else "",
            dormiu_melhor=_s(surv.slept_better) if surv else "",
            gostou=_s(surv.liked) if surv else "",
            intensidade=_s(surv.intensity) if surv else "",
            repetiria=_yn(surv.would_repeat) if surv else "",
        ))
    return rows


def build_features_csv(rows: list[FeatureRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_COLUMNS)
    for r in rows:
        w.writerow([getattr(r, c) for c in _COLUMNS])
    return buf.getvalue()


def build_features_csv_from_db(db: Session) -> str:
    return build_features_csv(gather_feature_rows(db))
