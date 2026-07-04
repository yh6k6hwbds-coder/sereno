"""
modules/research/analysis_service.py — Relatório de análise do piloto (cego, reprodutível).

Agrega os dados reusando a exportação cega (casos completos, por braço CODIFICADO A/B) e roda o
plano de análise (``analysis_plan``): viabilidade/adesão/retenção, usabilidade (SUS), índice de
Bang (cegamento), testes exploratórios (GAD-7/PSQI) e o semáforo de progressão.

Enquadramento: piloto de VIABILIDADE — exploratório/gerador de hipóteses. Nada aqui decide
eficácia nem desfecho **ao vivo**; a saída é um relatório para humanos decidirem. Nunca aparece
a condição (ativo/sham) — só o braço codificado.
"""
from __future__ import annotations
import math
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import Allocation, FollowupAssessment, AdverseEvent
from app.modules.research import analysis_plan as ap
from app.modules.research.export_service import gather_export_rows

ADHERENCE_TARGET_PCT = 70.0   # participante "aderente" se adesão ≥ alvo


def _json_safe(obj):
    """Substitui floats não-finitos (nan/inf) por None — ex.: p-valor indefinido em dados
    degenerados (braço com escores idênticos). Mantém o relatório JSON-compliant e honesto."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _bang_for_arm(rows, arm_label: str) -> dict | None:
    """Índice de Bang de UM braço, a partir do palpite vs braço codificado ('A'/'B')."""
    if not rows:
        return None
    correct = sum(1 for r in rows if r.blinding_guess == arm_label)
    dont = sum(1 for r in rows if r.blinding_guess == "nao_sei")
    incorrect = len(rows) - correct - dont
    return ap.bang_blinding_index(correct, incorrect, dont)


def _within(rows_arm, base_attr: str, fu_attr: str) -> dict | None:
    if len(rows_arm) < 3:
        return None
    return ap.within_arm_change([getattr(r, base_attr) for r in rows_arm],
                                [getattr(r, fu_attr) for r in rows_arm])


def build_report(db: Session) -> dict:
    n_allocated = int(db.scalar(select(func.count()).select_from(Allocation)) or 0)
    n_followup = int(db.scalar(
        select(func.count(func.distinct(FollowupAssessment.participant_id)))) or 0)
    n_severe = int(db.scalar(select(func.count()).select_from(AdverseEvent)
                             .where(AdverseEvent.severity == "severe")) or 0)

    rows = gather_export_rows(db)                 # casos completos, cegos (A/B)
    arm_a = [r for r in rows if r.arm_coded == "Grupo A"]
    arm_b = [r for r in rows if r.arm_coded == "Grupo B"]

    # Viabilidade / adesão / retenção (IC95% Wilson)
    n_adherent = sum(1 for r in rows if r.adherence_pct >= ADHERENCE_TARGET_PCT)
    adherence = ap.rate_with_ci(n_adherent, n_allocated)
    retention = ap.rate_with_ci(n_followup, n_allocated)
    sus = ap.describe([r.sus_fu for r in rows]) if rows else None

    # Cegamento (índice de Bang por braço codificado)
    bang = {"grupo_a": _bang_for_arm(arm_a, "A"), "grupo_b": _bang_for_arm(arm_b, "B")}
    present = [b for b in bang.values() if b]
    blinding_ok = all(abs(b["bang_bi"]) < 0.2 for b in present) if present else True

    # Exploratórios (só com n suficiente; gerador de hipóteses)
    def between(base_attr: str, fu_attr: str) -> dict | None:
        da = [getattr(r, fu_attr) - getattr(r, base_attr) for r in arm_a]
        dbb = [getattr(r, fu_attr) - getattr(r, base_attr) for r in arm_b]
        if len(da) < 3 or len(dbb) < 3:
            return None
        return ap.between_arms(da, dbb)

    exploratory = {
        "gad7_intra": {"grupo_a": _within(arm_a, "gad7_base", "gad7_fu"),
                       "grupo_b": _within(arm_b, "gad7_base", "gad7_fu")},
        "psqi_intra": {"grupo_a": _within(arm_a, "psqi_base", "psqi_fu"),
                       "grupo_b": _within(arm_b, "psqi_base", "psqi_fu")},
        "gad7_entre_bracos": between("gad7_base", "gad7_fu"),
        "psqi_entre_bracos": between("psqi_base", "psqi_fu"),
    }

    progression = ap.progression_semaphore(
        adherence.get("rate_pct"), retention.get("rate_pct"), n_severe, blinding_ok)

    return _json_safe({
        "framing": ("Piloto de VIABILIDADE. Desfechos primários descritivos (viabilidade, adesão, "
                    "usabilidade, segurança). Ansiedade/sono são EXPLORATÓRIOS. Não demonstra "
                    "eficácia; ferramenta complementar."),
        "enrollment": {"allocated": n_allocated, "complete_cases": len(rows),
                       "arm_a_n": len(arm_a), "arm_b_n": len(arm_b)},
        "feasibility": {"adherence": adherence, "retention": retention,
                        "usability_sus": sus, "adherence_target_pct": ADHERENCE_TARGET_PCT},
        "blinding": {"bang_index": bang, "maintained": blinding_ok},
        "exploratory": exploratory,
        "progression": progression,
    })
