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


# --- Triagem (G8) -----------------------------------------------------------
# Desde o G8 as chaves da triagem são as do protocolo e o conjunto é FECHADO: mandar só
# "idade_18: True" agora é 422. Escores que caem na faixa sintomática de inclusão (GAD-7 5–14
# e/ou PSQI > 5) sem acionar o gatilho de segurança (GAD-7 >= 15).
GAD7_ELEGIVEL, PSQI_ELEGIVEL = 8, 9


def screening_criteria(*, inclusao_ok: bool = True, exclusao: dict | None = None) -> dict:
    """Conjunto COMPLETO de critérios declaráveis (os derivados ficam com o servidor)."""
    from app.modules.screening.service import DECLARED_INCLUSION, DECLARED_EXCLUSION
    exclusao = exclusao or {}
    return {
        "inclusion": {k: bool(inclusao_ok) for k in DECLARED_INCLUSION},
        "exclusion": {k: bool(exclusao.get(k, False)) for k in DECLARED_EXCLUSION},
    }


def screening_body(participant_id, *, inclusao_ok: bool = True, exclusao: dict | None = None,
                   **extra) -> dict:
    """Corpo de POST /v1/screening que passa na faixa sintomática, salvo se ``extra`` mudar."""
    corpo = {"participant_id": str(participant_id), "gad7_total": GAD7_ELEGIVEL,
             "psqi_global": PSQI_ELEGIVEL,
             **screening_criteria(inclusao_ok=inclusao_ok, exclusao=exclusao)}
    corpo.update(extra)
    return corpo
