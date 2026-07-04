"""
instruments_scoring.py
======================
Núcleo de referência dos instrumentos digitais e das métricas do piloto de
neuromodulação não invasiva.

Implementa a PONTUAÇÃO (algoritmos públicos) do GAD-7, PSQI e SUS, as métricas
de adesão e a exportação pseudonimizada. Trabalha sobre VETORES DE RESPOSTA
codificados — NÃO reproduz o texto dos itens. O enunciado oficial e validado
em português brasileiro deve ser licenciado/obtido das fontes apropriadas
(ex.: PSQI é protegido; usar a versão validada PT-BR). Isto é código de
pontuação, não os questionários.

Cada função de escore é VERSIONADA: o resultado carrega a versão do algoritmo,
para que análises permaneçam reprodutíveis se a lógica for corrigida.

Aviso: ferramenta complementar de pesquisa; não substitui avaliação
profissional. Faixas e pontos de corte seguem a literatura das fontes
primárias e devem ser confirmados na versão validada utilizada.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import csv, io

SCORING_VERSIONS = {"gad7": "1.0.0", "psqi": "1.0.0", "sus": "1.0.0", "adherence": "1.0.0"}


# ----------------------------------------------------------------------------
# GAD-7  (7 itens, 0-3; total 0-21)  — Spitzer et al., 2006
# ----------------------------------------------------------------------------
def score_gad7(responses: list[int]) -> dict:
    if len(responses) != 7 or any(r not in (0, 1, 2, 3) for r in responses):
        raise ValueError("GAD-7 requer 7 respostas inteiras de 0 a 3")
    total = sum(responses)
    if total <= 4:   sev = "mínima"
    elif total <= 9: sev = "leve"
    elif total <= 14: sev = "moderada"
    else:            sev = "grave"
    return {"instrument": "GAD-7", "version": SCORING_VERSIONS["gad7"],
            "total": total, "severity": sev, "positive_screen": total >= 10}


# ----------------------------------------------------------------------------
# SUS  (10 itens, 1-5; escore 0-100)  — Brooke, 1996
# ----------------------------------------------------------------------------
def score_sus(responses: list[int]) -> dict:
    if len(responses) != 10 or any(r not in (1, 2, 3, 4, 5) for r in responses):
        raise ValueError("SUS requer 10 respostas inteiras de 1 a 5")
    s = 0
    for i, r in enumerate(responses):
        item = i + 1
        s += (r - 1) if item % 2 == 1 else (5 - r)   # ímpares: r-1; pares: 5-r
    score = s * 2.5
    if score >= 80.3:  band = "excelente"
    elif score >= 68:  band = "acima da média"
    elif score >= 51:  band = "abaixo da média"
    else:              band = "baixo"
    return {"instrument": "SUS", "version": SCORING_VERSIONS["sus"],
            "score": score, "band": band, "note": "SUS não é porcentagem; média de referência ~68"}


# ----------------------------------------------------------------------------
# PSQI  (7 componentes 0-3; global 0-21)  — Buysse et al., 1989
# Recomenda-se a versão validada PT-BR (Bertolazi et al., 2011).
# ----------------------------------------------------------------------------
@dataclass
class PSQIInput:
    subjective_quality: int          # 0=muito boa ... 3=muito ruim
    latency_min: int                 # minutos para adormecer
    cannot_sleep_30min_freq: int     # 0-3 (frequência)
    hours_slept: float               # horas de sono efetivo
    hours_in_bed: float              # horas na cama (deitar -> levantar)
    disturbance_items: list[int]     # 9 itens 0-3 (despertares, etc.)
    medication_freq: int             # 0-3
    stay_awake_freq: int             # 0-3 (dificuldade de ficar acordado)
    enthusiasm_problem: int          # 0-3 (manter entusiasmo)

def _recode(value: int, cuts: list[tuple]) -> int:
    for lo, hi, out in cuts:
        if lo <= value <= hi:
            return out
    return 3

def score_psqi(x: PSQIInput) -> dict:
    # C1 — qualidade subjetiva
    c1 = x.subjective_quality
    # C2 — latência
    lat = _recode(x.latency_min, [(0, 15, 0), (16, 30, 1), (31, 60, 2)])   # >60 -> 3
    c2 = _recode(lat + x.cannot_sleep_30min_freq, [(0, 0, 0), (1, 2, 1), (3, 4, 2)])  # 5-6 -> 3
    # C3 — duração
    h = x.hours_slept
    c3 = 0 if h > 7 else 1 if h >= 6 else 2 if h >= 5 else 3
    # C4 — eficiência habitual
    eff = (x.hours_slept / x.hours_in_bed) * 100 if x.hours_in_bed else 0
    c4 = 0 if eff >= 85 else 1 if eff >= 75 else 2 if eff >= 65 else 3
    # C5 — distúrbios
    if len(x.disturbance_items) != 9:
        raise ValueError("PSQI: disturbance_items deve ter 9 itens 0-3")
    c5 = _recode(sum(x.disturbance_items), [(0, 0, 0), (1, 9, 1), (10, 18, 2)])  # 19-27 -> 3
    # C6 — uso de medicação
    c6 = x.medication_freq
    # C7 — disfunção diurna
    c7 = _recode(x.stay_awake_freq + x.enthusiasm_problem, [(0, 0, 0), (1, 2, 1), (3, 4, 2)])
    comps = {"C1_qualidade": c1, "C2_latencia": c2, "C3_duracao": c3, "C4_eficiencia": c4,
             "C5_disturbios": c5, "C6_medicacao": c6, "C7_disfuncao_diurna": c7}
    glob = sum(comps.values())
    return {"instrument": "PSQI", "version": SCORING_VERSIONS["psqi"],
            "components": comps, "global": glob,
            "interpretation": "sono ruim" if glob > 5 else "sono bom",
            "efficiency_pct": round(eff, 1)}


# ----------------------------------------------------------------------------
# Adesão  (a partir dos registros de sessão)
# ----------------------------------------------------------------------------
@dataclass
class SessionRecord:
    completed: bool
    duration_s: float
    week: int   # 1..4

def adherence_metrics(sessions: list[SessionRecord], prescribed: int = 20,
                      weeks: int = 4) -> dict:
    started = len(sessions)
    completed = sum(1 for s in sessions if s.completed)
    per_week = {w: sum(1 for s in sessions if s.week == w and s.completed) for w in range(1, weeks + 1)}
    mean_dur = round(sum(s.duration_s for s in sessions if s.completed) / completed, 1) if completed else 0.0
    return {"version": SCORING_VERSIONS["adherence"],
            "sessions_started": started, "sessions_completed": completed,
            "completion_rate_pct": round(100 * completed / started, 1) if started else 0.0,
            "adherence_rate_pct": round(100 * completed / prescribed, 1),
            "sessions_per_week": per_week,
            "mean_effective_minutes": round(mean_dur / 60, 1)}


# ----------------------------------------------------------------------------
# Exportação pseudonimizada (rótulos de braço CODIFICADOS; sem PII)
# ----------------------------------------------------------------------------
@dataclass
class ParticipantExport:
    code: str                 # pseudônimo (ex.: P001) — nunca nome/e-mail
    arm_coded: str            # "Grupo A"/"Grupo B" — chave real fica fora do export
    gad7_base: int; gad7_fu: int
    psqi_base: int; psqi_fu: int
    sus_fu: int
    adherence_pct: float
    adverse_events: int
    blinding_guess: str       # braço que o participante acha que recebeu

def build_export_csv(rows: list[ParticipantExport]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["codigo", "grupo_codificado", "gad7_basal", "gad7_seguimento",
                "delta_gad7", "psqi_basal", "psqi_seguimento", "delta_psqi",
                "sus", "adesao_pct", "eventos_adversos", "cegamento_adivinhado",
                "versao_escore_gad7", "versao_escore_psqi", "versao_escore_sus"])
    for r in rows:
        w.writerow([r.code, r.arm_coded, r.gad7_base, r.gad7_fu, r.gad7_fu - r.gad7_base,
                    r.psqi_base, r.psqi_fu, r.psqi_fu - r.psqi_base, r.sus_fu,
                    r.adherence_pct, r.adverse_events, r.blinding_guess,
                    SCORING_VERSIONS["gad7"], SCORING_VERSIONS["psqi"], SCORING_VERSIONS["sus"]])
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Validação executável (dados sintéticos com valores calculados à mão)
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 68)
    print("VALIDAÇÃO DA PONTUAÇÃO — instrumentos e métricas")
    print("=" * 68)

    g = score_gad7([2, 3, 1, 2, 0, 1, 3])          # soma esperada = 12
    assert g["total"] == 12 and g["severity"] == "moderada" and g["positive_screen"]
    print(f"\nGAD-7  respostas [2,3,1,2,0,1,3] -> total={g['total']} "
          f"({g['severity']}, rastreio+={g['positive_screen']})  [esperado 12/moderada]")

    s = score_sus([4, 1, 4, 2, 5, 1, 4, 2, 5, 1])  # esperado 87.5
    assert s["score"] == 87.5
    print(f"SUS    respostas [4,1,4,2,5,1,4,2,5,1] -> escore={s['score']} "
          f"({s['band']})  [esperado 87.5]")

    p = score_psqi(PSQIInput(subjective_quality=1, latency_min=20, cannot_sleep_30min_freq=1,
                             hours_slept=6.0, hours_in_bed=7.5,
                             disturbance_items=[1, 0, 1, 0, 1, 0, 0, 1, 0],
                             medication_freq=0, stay_awake_freq=1, enthusiasm_problem=1))
    assert p["components"] == {"C1_qualidade": 1, "C2_latencia": 1, "C3_duracao": 1,
                               "C4_eficiencia": 1, "C5_disturbios": 1, "C6_medicacao": 0,
                               "C7_disfuncao_diurna": 1}
    assert p["global"] == 6
    print(f"PSQI   exemplo sintético -> componentes={list(p['components'].values())} "
          f"global={p['global']} ({p['interpretation']}, efic.={p['efficiency_pct']}%)  "
          f"[esperado [1,1,1,1,1,0,1]/6]")

    sess = ([SessionRecord(True, 1180, w) for w in [1, 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4]]
            + [SessionRecord(False, 300, 1), SessionRecord(False, 240, 3)])
    a = adherence_metrics(sess)
    assert a["sessions_completed"] == 14 and a["adherence_rate_pct"] == 70.0
    print(f"Adesão 14/20 concluídas -> conclusão={a['completion_rate_pct']}% "
          f"adesão={a['adherence_rate_pct']}% média={a['mean_effective_minutes']} min/sessão "
          f"semana={a['sessions_per_week']}")

    export = build_export_csv([
        ParticipantExport("P001", "Grupo A", 14, 8, 10, 4, 87, 70.0, 0, "Grupo A"),
        ParticipantExport("P002", "Grupo B", 12, 11, 9, 6, 62, 55.0, 1, "Grupo A"),
        ParticipantExport("P003", "Grupo A", 16, 9, 12, 5, 79, 85.0, 0, "não sei"),
    ])
    print("\nExportação pseudonimizada (amostra, sem PII; grupo codificado):")
    print(export)

    print("=" * 68)
    print("TODOS OS ESCORES CONFEREM COM OS VALORES CALCULADOS À MÃO ✓")
    print("=" * 68)
