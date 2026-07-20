"""
modules/wearables/sink.py — Porta de ENTRADA de vestíveis (E2/ADR-084), desacoplada.

Seam de ingestão de FC/sono de wearables: o cliente empurra leituras **já normalizadas**
(vindas do HealthKit/Google Fit no próprio device) e um **adaptador desacoplado** (`WearableSink`)
decide o que fazer com elas. Mesma forma das outras portas do projeto (`EmailSender`,
`AudioStorage`): implementações Null (padrão, seguro) / Memory (teste) / — no futuro — persistência
ou provedor real.

**Inegociáveis preservados:**
  - o adaptador padrão é o **Null** (descarta; NÃO persiste) — "preparada, não construída"
    (CLAUDE.md); persistir dado de saúde exige cifra/separação como a PII (inegociável #6),
    fica para a fatia de persistência;
  - o sink é um **beco sem saída** quanto à decisão: nada aqui alimenta o recomendador ao vivo,
    que segue **por regras** (inegociável #5). Leituras de vestível não são feature de decisão.
"""
from __future__ import annotations
import datetime as dt
import os
import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Reading:
    """Leitura canônica de vestível (já normalizada no device). Sem PII direta."""
    kind: str            # "heart_rate" | "sleep"
    taken_at: dt.datetime
    value: float
    unit: str            # ex.: "bpm", "min"
    source: str          # rótulo do provedor (ex.: "healthkit", "googlefit", "manual")


class WearableSink(Protocol):
    def ingest(self, participant_id: uuid.UUID, readings: list[Reading]) -> int: ...
    def reset(self) -> None: ...


class NullWearableSink:
    """Padrão seguro: aceita e **descarta** (não persiste). Devolve quantas recebeu."""
    def ingest(self, participant_id: uuid.UUID, readings: list[Reading]) -> int:
        return len(readings)

    def reset(self) -> None:
        pass


class MemoryWearableSink:
    """Guarda em memória — para testes e para provar o seam ponta a ponta."""
    def __init__(self) -> None:
        self._by_participant: dict[uuid.UUID, list[Reading]] = {}

    def ingest(self, participant_id: uuid.UUID, readings: list[Reading]) -> int:
        self._by_participant.setdefault(participant_id, []).extend(readings)
        return len(readings)

    def readings_for(self, participant_id: uuid.UUID) -> list[Reading]:
        return list(self._by_participant.get(participant_id, []))

    def reset(self) -> None:
        self._by_participant.clear()


_sink: WearableSink | None = None


def get_wearable_sink() -> WearableSink:
    """Sink atual. Reconstrói do ambiente (`WEARABLE_SINK`) — padrão `null` (descarta)."""
    global _sink
    if _sink is None:
        mode = os.getenv("WEARABLE_SINK", "null").strip().lower()
        _sink = MemoryWearableSink() if mode == "memory" else NullWearableSink()
    return _sink


def set_wearable_sink(sink: WearableSink | None) -> None:
    """Injeta um sink (teste) ou passa None p/ reconstruir do ambiente na próxima chamada."""
    global _sink
    _sink = sink
