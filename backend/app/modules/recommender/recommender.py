"""
recommender.py — Motor de recomendação POR REGRAS (transparente e versionado).
==============================================================================
Seleciona um protocolo APENAS dentro da biblioteca de áudio já validada (Etapa 2),
sempre em faixas seguras. Não é "IA que aprende": é um conjunto de regras
auditáveis. Registra tudo (entrada → regra → saída) para análise exploratória de
coerência (desfecho secundário da Etapa 1) e para instrumentar um ML FUTURO — sem
tomar decisões por ML agora e sem overclaim de eficácia.

Segurança do cegamento: o recomendador opera sobre HANDLES/bandas neutros e é
IDÊNTICO nos dois braços; a resolução handle → arquivo (ativo/sham) ocorre na
camada de ocultação (Etapa 5). Logo, personalizar não vaza a alocação.

Postura de evidência: a associação banda↔estado (alfa→relaxamento; teta→indução
do sono; delta→sono profundo) é CONVENÇÃO da literatura, não eficácia comprovada.
Ferramenta complementar; não substitui cuidado profissional.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

RULESET_VERSION = "1.0.0"

# Biblioteca validada (subconjunto de exemplo — Etapa 2). Handles NEUTROS.
LIBRARY = {
    "alpha-10": {"band": "alpha", "purpose": "relaxamento / ansiedade"},
    "theta-6":  {"band": "theta", "purpose": "indução do sono (adormecer)"},
    "delta-2":  {"band": "delta", "purpose": "sono profundo (manutenção)"},
}
GENTLE_DEFAULT = "alpha-10"     # protocolo mais brando, para de-escalonar
DISCLAIMER = ("Ferramenta complementar; não substitui avaliação ou tratamento "
              "profissional. Estímulo experimental.")
EVIDENCE_NOTE = ("Associação convencional banda↔estado; eficácia não comprovada. "
                 "Seleção restrita a protocolos experimentais validados.")


@dataclass
class RecommendationInput:
    goal: str                                   # "sleep" | "anxiety"
    sleep_issue: Optional[str] = None           # "onset" | "maintenance" | None
    time_of_day: str = "evening"                # "day" | "evening" | "night"
    recent_adverse_severity: Optional[str] = None   # None | "mild" | "moderate" | "severe"
    last_liked: Optional[bool] = None
    last_intensity: Optional[int] = None        # 0–4 (percepção de intensidade)
    contraindicated: bool = False               # rede de segurança (excluídos na triagem)

    def feature_vector(self) -> dict:
        """Vetor de atributos registrado para um ML FUTURO (não usado na decisão)."""
        return {
            "goal": self.goal, "sleep_issue": self.sleep_issue, "time_of_day": self.time_of_day,
            "recent_adverse_severity": self.recent_adverse_severity,
            "last_liked": self.last_liked, "last_intensity": self.last_intensity,
        }


@dataclass
class Rule:
    rule_id: str
    predicate: Callable[[RecommendationInput], bool]
    protocol: Optional[str]
    rationale: str
    is_guardrail: bool = False
    flag_review: bool = False
    action: str = "recommend"                   # "recommend" | "no_recommendation"


def _low_tolerability(i: RecommendationInput) -> bool:
    return (i.last_intensity is not None and i.last_intensity >= 4) and (i.last_liked is False)


# ---- Catálogo de regras (ordem = prioridade). Guardrails primeiro. ----
RULES: list[Rule] = [
    Rule("G1-contraindication", lambda i: i.contraindicated, None,
         "Contraindicação sinalizada: não recomendar sessão; orientar profissional.",
         is_guardrail=True, action="no_recommendation"),
    Rule("G2-safety-deescalate",
         lambda i: i.recent_adverse_severity in ("moderate", "severe") or _low_tolerability(i),
         GENTLE_DEFAULT,
         "Evento adverso relevante ou baixa tolerabilidade: de-escalonar para o protocolo mais brando e sinalizar revisão.",
         is_guardrail=True, flag_review=True),
    Rule("R1-anxiety", lambda i: i.goal == "anxiety", "alpha-10",
         "Objetivo ansiedade → banda alfa (relaxamento)."),
    Rule("R2-sleep-onset", lambda i: i.goal == "sleep" and i.sleep_issue == "onset", "theta-6",
         "Objetivo sono, dificuldade de adormecer → banda teta (indução)."),
    Rule("R3-sleep-maintenance",
         lambda i: i.goal == "sleep" and i.sleep_issue in ("maintenance", None) and i.time_of_day in ("evening", "night"),
         "delta-2", "Objetivo sono, manutenção/noite → banda delta (sono profundo)."),
    Rule("R4-sleep-default", lambda i: i.goal == "sleep", "theta-6",
         "Objetivo sono (padrão) → banda teta."),
]
_DEFAULT = Rule("D0-default", lambda i: True, GENTLE_DEFAULT,
                "Sem regra específica aplicável → protocolo brando padrão.")


def recommend(i: RecommendationInput) -> dict:
    """Avalia as regras em ordem e devolve a recomendação COM registro completo."""
    fired = next((r for r in RULES if r.predicate(i)), _DEFAULT)

    # Garantia de segurança: nunca sair da biblioteca validada.
    protocol = fired.protocol
    if fired.action == "recommend":
        assert protocol in LIBRARY, "Recomendação fora da biblioteca validada é proibida."

    return {
        "action": fired.action,
        "suggested_protocol": protocol if fired.action == "recommend" else None,
        "band": LIBRARY.get(protocol, {}).get("band") if protocol else None,
        "rule_id": fired.rule_id,
        "ruleset_version": RULESET_VERSION,
        "is_guardrail": fired.is_guardrail,
        "flag_review": fired.flag_review,
        "rationale": fired.rationale,
        "evidence_note": EVIDENCE_NOTE,
        "disclaimer": DISCLAIMER,
        "input_snapshot": asdict(i),
        "feature_vector": i.feature_vector(),      # para ML futuro (auditoria)
    }


# ---- Métrica de coerência (desfecho exploratório da Etapa 1) ----
# Mapa convencional objetivo→banda usado para checar alinhamento da recomendação.
_GOAL_BAND = {"anxiety": {"alpha"}, "sleep": {"theta", "delta"}}

def coherence_report(events: list[dict]) -> dict:
    """events: [{"rec": <saída de recommend>, "accepted": bool, "reported_relaxation": int}]"""
    recs = [e for e in events if e["rec"]["action"] == "recommend"]
    if not recs:
        return {"n": 0}
    aligned = sum(1 for e in recs if e["rec"]["band"] in _GOAL_BAND.get(e["rec"]["input_snapshot"]["goal"], set()))
    accepted = [e for e in recs if e.get("accepted")]
    rel_acc = [e["reported_relaxation"] for e in accepted if e.get("reported_relaxation") is not None]
    rel_rej = [e["reported_relaxation"] for e in recs if not e.get("accepted") and e.get("reported_relaxation") is not None]
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    return {
        "n": len(recs),
        "goal_alignment_rate": round(100.0 * aligned / len(recs), 1),
        "acceptance_rate": round(100.0 * len(accepted) / len(recs), 1),
        "mean_relaxation_accepted": mean(rel_acc),
        "mean_relaxation_rejected": mean(rel_rej),
    }


# ---------------------------------------------------------------- Testes
if __name__ == "__main__":
    ok = True
    def expect(name, got, want):
        global ok; good = got == want; ok &= good
        print(f"   {'✓' if good else '✗'} {name:44s} obtido={got}  esperado={want}")

    print("=" * 70); print("VALIDAÇÃO DO RECOMENDADOR — regras transparentes e seguras"); print("=" * 70)

    print("\nRegras principais")
    expect("ansiedade → alpha-10 (R1)",
           (lambda r: (r["suggested_protocol"], r["rule_id"]))(recommend(RecommendationInput(goal="anxiety"))),
           ("alpha-10", "R1-anxiety"))
    expect("sono/adormecer → theta-6 (R2)",
           recommend(RecommendationInput(goal="sleep", sleep_issue="onset"))["suggested_protocol"], "theta-6")
    expect("sono/manutenção/noite → delta-2 (R3)",
           recommend(RecommendationInput(goal="sleep", sleep_issue="maintenance", time_of_day="night"))["suggested_protocol"], "delta-2")
    expect("sono padrão → theta-6 (R4)",
           recommend(RecommendationInput(goal="sleep", time_of_day="day"))["suggested_protocol"], "theta-6")

    print("\nGuardrails de segurança")
    r_ae = recommend(RecommendationInput(goal="anxiety", recent_adverse_severity="moderate"))
    expect("evento adverso moderado → de-escalona + revisão",
           (r_ae["suggested_protocol"], r_ae["rule_id"], r_ae["flag_review"]),
           ("alpha-10", "G2-safety-deescalate", True))
    r_tol = recommend(RecommendationInput(goal="sleep", sleep_issue="onset", last_liked=False, last_intensity=4))
    expect("baixa tolerabilidade → de-escalona (não vai para teta)",
           r_tol["rule_id"], "G2-safety-deescalate")
    r_ci = recommend(RecommendationInput(goal="anxiety", contraindicated=True))
    expect("contraindicação → sem recomendação",
           (r_ci["action"], r_ci["suggested_protocol"]), ("no_recommendation", None))

    print("\nInvariantes e registro")
    all_recs = [recommend(RecommendationInput(goal=g, sleep_issue=s, time_of_day=t))
                for g in ("sleep", "anxiety") for s in (None, "onset", "maintenance") for t in ("day", "evening", "night")]
    expect("toda recomendação fica na biblioteca validada",
           all(r["suggested_protocol"] in LIBRARY for r in all_recs if r["action"] == "recommend"), True)
    expect("todo log tem versão do conjunto de regras",
           all(r["ruleset_version"] == RULESET_VERSION for r in all_recs), True)
    expect("todo log carrega snapshot + feature_vector (ML futuro)",
           all(("input_snapshot" in r and "feature_vector" in r) for r in all_recs), True)
    expect("toda saída traz aviso e nota de evidência",
           all((r["disclaimer"] and r["evidence_note"]) for r in all_recs), True)

    print("\nCoerência (exemplo exploratório)")
    events = [
        {"rec": recommend(RecommendationInput(goal="anxiety")), "accepted": True, "reported_relaxation": 3},
        {"rec": recommend(RecommendationInput(goal="sleep", sleep_issue="onset")), "accepted": True, "reported_relaxation": 4},
        {"rec": recommend(RecommendationInput(goal="sleep", sleep_issue="maintenance", time_of_day="night")), "accepted": False, "reported_relaxation": 1},
    ]
    cr = coherence_report(events)
    print("   relatório:", cr)
    expect("alinhamento objetivo→banda = 100%", cr["goal_alignment_rate"], 100.0)

    print("\n" + "=" * 70)
    print("RESULTADO:", "TODOS OS TESTES APROVADOS ✓" if ok else "HÁ FALHAS ✗")
    print("=" * 70)
