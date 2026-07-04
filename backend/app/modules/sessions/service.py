"""
modules/sessions/service.py — Resolução INTERNA de áudio (ativo/sham) por braço.

O mapa A/B → ativo/sham é a CHAVE SELADA: fica fora do banco (variável de ambiente /
cofre), nunca em consulta que ligue participante→condição. `resolve_protocol` escolhe
o arquivo concreto a partir da banda (neutra quanto ao braço) + condição. Nada aqui é
exposto por API. Fidelidade: o cliente reproduz o arquivo (content_hash) bit-a-bit.
"""
from __future__ import annotations
import os
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.models import AudioProtocol


def _sealed_map() -> dict[str, str]:
    """Mapa selado A/B → ativo/sham. Em produção: segredo em cofre, custodiado."""
    raw = os.getenv("ARM_CONDITION_MAP", "A:active,B:sham")
    m: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            m[k.strip()] = v.strip()
    return m


def condition_for_arm(arm: str) -> str | None:
    """Traduz o braço codificado (A/B) em condição (active/sham). INTERNO."""
    return _sealed_map().get(arm)


def resolve_protocol(db: DbSession, band: str, condition: str) -> AudioProtocol | None:
    """Escolhe o protocolo concreto: mesma banda; ativo = beat_hz>0, sham = beat_hz==0."""
    q = select(AudioProtocol).where(AudioProtocol.band == band)
    q = q.where(AudioProtocol.beat_hz > 0) if condition == "active" else q.where(AudioProtocol.beat_hz == 0)
    return db.scalars(q).first()
