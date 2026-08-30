"""
tests/helpers.py — Corpos de requisição compartilhados.

Iniciar sessão exige, desde G4/ADR-101, a EVIDÊNCIA da verificação dicótica de fones e o
ganho travado da reprodução (G3). Repetir o dicionário em cada teste esconderia a regra;
aqui ele fica num lugar só, com o significado escrito.
"""
from __future__ import annotations

# Verificação APROVADA: duas rodadas, nenhum erro (o mínimo que o servidor aceita).
CHECK_OK = {"version": "1.0.0", "rounds": 2, "errors": 0, "attempts": 1, "ears": "LR"}
# Verificação REPROVADA: o participante errou uma rodada — a sessão não pode começar.
CHECK_FALHOU = {"version": "1.0.0", "rounds": 2, "errors": 1, "ears": "RL"}

GANHO = 0.8      # ganho digital travado do cliente (<= AUDIO_MAX_GAIN)


def start_body(handle: str = "delta", **extra) -> dict:
    """Corpo de POST /v1/sessions com a verificação aprovada."""
    return {"protocol_handle": handle, "headphone_check": CHECK_OK, "audio_gain": GANHO, **extra}
