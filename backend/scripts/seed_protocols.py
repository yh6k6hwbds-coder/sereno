"""
scripts/seed_protocols.py — Carrega a BIBLIOTECA DO ESTUDO no banco (idempotente).

Sem estas duas linhas o piloto não toca: a tabela ``audio_protocol`` nasce vazia na
migração inicial e ``seed_demo.py`` só insere protocolos de 30 s para a demo local.

Os parâmetros vêm do protocolo aprovado (seção "Protocolo de intervenção"), não da
engenharia:

    braço experimental — 250 Hz na orelha esquerda, 253 Hz na direita (Δf = 3 Hz, delta);
    braço controle     — 250 Hz idêntico nas duas orelhas (Δf = 0), energia equalizada;
    arquivo            — 20 min, 48 kHz, 16 bits, sem perdas, rampas de 30 s / 60 s.

Mudar qualquer valor aqui é EMENDA DE PROTOCOLO (CEP). Os mesmos números estão em
``audio-pipeline/binaural_instrument.py`` (``PILOT_LIBRARY``) e são conferidos pelo
teste ``backend/tests/test_pilot_protocol.py`` — os três precisam contar a mesma história.

Cegamento (por que o ``content_hash`` é ALEATÓRIO): o cliente recebe o ``content_hash``
como identidade opaca do arquivo. Se ele fosse derivado dos parâmetros (ou de um rótulo
como "ativo"/"sham"), qualquer pessoa que conhecesse o protocolo — que é público, está no
projeto submetido ao CEP — poderia recalcular os dois hashes e descobrir qual braço
recebeu. Opaco de verdade só é opaco se não for reconstruível: um valor aleatório de 32
bytes, sorteado uma vez e guardado na linha, resolve isso sem custo.

Uso (dentro do contêiner ou com DATABASE_URL apontado ao banco):
    python scripts/seed_protocols.py            # semeia se faltar; não altera o que existe
    python scripts/seed_protocols.py --check    # só confere; sai != 0 se faltar algo
"""
from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app.core.db import get_engine                               # noqa: E402
from app.core.models import AudioProtocol                        # noqa: E402
from app.modules.sessions import audio_render                    # noqa: E402

# --------------------------------------------------------------------------- protocolo
CARRIER_HZ = 250.0        # tom portador (orelha esquerda)
BEAT_HZ = 3.0             # diferença interaural do braço experimental → 253 Hz na direita
BAND = "delta"
DURATION_S = 1200.0       # 20 minutos por sessão
SAMPLE_RATE = 48000
FADE_IN_S = 30.0
FADE_OUT_S = 60.0
TARGET_PEAK_DBFS = -12.0  # teto DIGITAL; o nível absoluto (60 dB(A)) é calibrado no acoplador
VERSION = "1.0.0"

# Identificadores NEUTROS: não dizem qual é qual, e a ordem não é o braço.
LIBRARY = [
    {"protocol_id": "sr-2026-01", "beat_hz": BEAT_HZ},   # com diferença interaural
    {"protocol_id": "sr-2026-02", "beat_hz": 0.0},       # sem diferença interaural
]


def _row(spec: dict) -> AudioProtocol:
    return AudioProtocol(
        protocol_id=spec["protocol_id"], version=VERSION, band=BAND,
        carrier_hz=CARRIER_HZ, beat_hz=spec["beat_hz"], duration_s=DURATION_S,
        target_peak_dbfs=TARGET_PEAK_DBFS, sample_rate=SAMPLE_RATE,
        fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S,
        content_hash=secrets.token_hex(32),
    )


def _verify_renderable(spec: dict) -> None:
    """Confere por FFT um trecho do estímulo ANTES de semear (não grava o que não valida)."""
    n_win = int(round(4.0 * SAMPLE_RATE))
    n_total = int(round(DURATION_S * SAMPLE_RATE))
    seg = audio_render.synthesize_segment(
        CARRIER_HZ, spec["beat_hz"], DURATION_S, TARGET_PEAK_DBFS,
        sample_rate=SAMPLE_RATE, fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S,
        start=(n_total - n_win) // 2, count=n_win)
    audio_render.validate_fft(seg, CARRIER_HZ, spec["beat_hz"], sample_rate=SAMPLE_RATE)


def main(check_only: bool = False) -> int:
    faltando, existentes = [], []
    with Session(get_engine()) as s:
        for spec in LIBRARY:
            achado = s.scalar(select(AudioProtocol).where(
                AudioProtocol.protocol_id == spec["protocol_id"],
                AudioProtocol.version == VERSION))
            (existentes if achado is not None else faltando).append(spec)

        if check_only:
            for spec in existentes:
                print(f"ok      {spec['protocol_id']} v{VERSION}")
            for spec in faltando:
                print(f"FALTA   {spec['protocol_id']} v{VERSION}")
            return 1 if faltando else 0

        for spec in faltando:
            _verify_renderable(spec)
            s.add(_row(spec))
            print(f"semeado {spec['protocol_id']} v{VERSION} "
                  f"(banda {BAND}, {DURATION_S:.0f}s, {SAMPLE_RATE} Hz)")
        for spec in existentes:
            print(f"ok      {spec['protocol_id']} v{VERSION} — já existia, nada alterado")
        s.commit()

    print(f"\nBiblioteca do estudo: {len(LIBRARY)} protocolo(s); "
          f"{len(faltando)} semeado(s) agora.")
    return 0


if __name__ == "__main__":
    sys.exit(main(check_only="--check" in sys.argv))
