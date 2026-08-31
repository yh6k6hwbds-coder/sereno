"""
core/protocol.py — Calendário e dose do protocolo aprovado (fonte única).

Números que vêm do PROTOCOLO, não da engenharia: mexer neles é **emenda de protocolo**.
Ficam aqui, e não espalhados por módulo, porque três lugares diferentes precisam do mesmo
número e já haviam divergido uma vez — a régua de adesão morava em ``research`` e o módulo
de sessões a importava de lá, invertendo a dependência.

O protocolo define:

  - **dose**: 20 min/sessão, **5 sessões por semana durante 4 semanas** = 20 sessões;
  - **adesão** (desfecho primário): proporção das 20 sessões concluídas com pelo menos
    **80% da duração** — o resto não conta;
  - **calendário**: T0 (linha de base), **T2 (2ª semana)** — avaliação intermediária de
    segurança e adesão — e T4 (fim das 4 semanas);
  - **descontinuação por adesão**: menos de **50%** das sessões previstas ao final da segunda
    semana descontinua o participante do protocolo, que **permanece na análise por ITT**.

O marco zero de cada participante é a **alocação** (``Allocation.allocated_at``): é quando a
randomização o coloca num braço e a intervenção pode começar. Nem a inscrição (que pode
anteceder em dias) nem a primeira sessão (que pode nunca acontecer — justamente o caso que a
regra de adesão precisa pegar) serviriam de origem.
"""
from __future__ import annotations
import datetime as dt

STUDY_WEEKS = 4
SESSIONS_PER_WEEK = 5
PRESCRIBED_SESSIONS = STUDY_WEEKS * SESSIONS_PER_WEEK      # 20
# Uma sessão só CONTA para a adesão se rodou pelo menos 80% da duração prescrita — é a
# definição do desfecho primário no protocolo, não uma heurística de engenharia.
MIN_COMPLETION_RATIO = 0.8

# T2 — a avaliação intermediária. O protocolo nomeia os momentos T0/T2/T4 pelas semanas
# decorridas, e a regra de adesão que a acompanha é aferida "ao final da segunda semana":
# antes do dia 14 o denominador (10 sessões) ainda não fechou, então a janela ABRE no dia 14.
# O tamanho da janela (7 dias) NÃO está no protocolo — é escolha operacional, e por isso vive
# como constante nomeada e não escondida numa conta. Ver ADR-106.
T2_WEEK = 2
T2_OPENS_DAY = T2_WEEK * 7                  # dia 14 desde a alocação
T2_WINDOW_DAYS = 7
MIN_WEEK2_ADHERENCE_PCT = 50.0


def as_utc(when: dt.datetime) -> dt.datetime:
    """Datas do banco voltam ingênuas em SQLite; trate-as como UTC (é como foram gravadas)."""
    return when if when.tzinfo is not None else when.replace(tzinfo=dt.timezone.utc)


def study_day(allocated_at: dt.datetime, now: dt.datetime | None = None) -> int:
    """Dia de estudo (1-based): o dia da alocação é o dia 1."""
    agora = now or dt.datetime.now(dt.timezone.utc)
    return (as_utc(agora) - as_utc(allocated_at)).days + 1


def study_week(allocated_at: dt.datetime, now: dt.datetime | None = None) -> int:
    """Semana de estudo (1-based). Pode passar de ``STUDY_WEEKS`` (participante em atraso)."""
    return (study_day(allocated_at, now) - 1) // 7 + 1


def prescribed_through_week(week: int) -> int:
    """Sessões previstas até o FIM da semana ``week``, limitado à dose total."""
    return min(max(week, 0) * SESSIONS_PER_WEEK, PRESCRIBED_SESSIONS)


def t2_window(allocated_at: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Janela da avaliação intermediária: abre ao fim da 2ª semana e dura ``T2_WINDOW_DAYS``."""
    inicio = as_utc(allocated_at) + dt.timedelta(days=T2_OPENS_DAY)
    return inicio, inicio + dt.timedelta(days=T2_WINDOW_DAYS)


def week2_deadline(allocated_at: dt.datetime) -> dt.datetime:
    """Instante em que a 2ª semana se fecha — a partir daí a regra de adesão pode ser aferida."""
    return as_utc(allocated_at) + dt.timedelta(days=T2_OPENS_DAY)


def adherence_pct(completed: int, prescribed: int) -> float:
    """Adesão em pontos percentuais. Denominador zero = 0,0 (não há o que aderir ainda)."""
    return round(100.0 * completed / prescribed, 1) if prescribed else 0.0
