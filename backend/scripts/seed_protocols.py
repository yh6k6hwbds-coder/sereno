"""
scripts/seed_protocols.py — Carrega a BIBLIOTECA DO ESTUDO no banco (idempotente).

Sem estas duas linhas o piloto não toca: a tabela ``audio_protocol`` nasce vazia na
migração inicial e ``seed_demo.py`` só insere protocolos de 30 s para a demo local.

Os parâmetros vêm do protocolo aprovado (seção "Protocolo de intervenção"), não da
engenharia:

    braço experimental — 250 Hz na orelha esquerda, 253 Hz na direita (Δf = 3 Hz, delta);
    braço controle     — 250 Hz idêntico nas duas orelhas (Δf = 0), energia equalizada;
    arquivo            — 20 min, 48 kHz, 16 bits, sem perdas, rampas de 30 s / 60 s;
    leito ambiente     — trilha de fundo tonal, diótica, 30 dB abaixo do estímulo (ADR-109).

O **nível** do leito é a única coisa aqui que o protocolo não fixa (ele diz apenas "baixa
intensidade"); −30 dBr é escolha da implementação e vai declarada ao CEP — ver ADR-109.

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
    python scripts/seed_protocols.py               # semeia se faltar; não altera o que existe
    python scripts/seed_protocols.py --check       # confere; sai != 0 se faltar ou sobrar
    python scripts/seed_protocols.py --materialize # semeia E já grava os arquivos no cache

``--materialize`` existe por causa do custo do estímulo do estudo: sintetizar e codificar
20 min a 48 kHz leva dezenas de segundos (ADR-103). Sem isso, quem paga a conta é a PRIMEIRA
requisição de áudio depois de cada deploy — ou seja, um participante esperando na tela de
carregamento. Rodar logo após o deploy (ou depois de trocar ``AUDIO_FORMAT``, que invalida o
cache) transfere essa espera para o operador.
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
BED_LEVEL_DBR = -30.0     # leito ambiente, em dB abaixo do RMS nominal do estímulo (ADR-109)
# 1.1.0 = o leito ambiente entrou. Mudar o que o participante OUVE é versão nova, nunca um
# UPDATE na linha auditada: o ``content_hash`` que um cliente já viu não pode passar a apontar
# para outro áudio. Semear versão nova com o piloto EM CURSO seria emenda de protocolo — a
# sessão guarda o ``protocol_uuid`` que resolveu ao iniciar, mas quem começasse depois ouviria
# outra coisa. Antes do piloto, é só a biblioteca nascendo completa.
VERSION = "1.1.0"

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
        fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S, bed_level_dbr=BED_LEVEL_DBR,
        content_hash=secrets.token_hex(32),
    )


def _verify_renderable(spec: dict) -> None:
    """Confere por FFT um trecho do estímulo ANTES de semear (não grava o que não valida)."""
    n_win = int(round(4.0 * SAMPLE_RATE))
    n_total = int(round(DURATION_S * SAMPLE_RATE))
    seg = audio_render.synthesize_segment(
        CARRIER_HZ, spec["beat_hz"], DURATION_S, TARGET_PEAK_DBFS,
        sample_rate=SAMPLE_RATE, fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S,
        bed_level_dbr=BED_LEVEL_DBR,
        start=(n_total - n_win) // 2, count=n_win)
    audio_render.validate_fft(seg, CARRIER_HZ, spec["beat_hz"], sample_rate=SAMPLE_RATE)


def _materialize() -> None:
    """Grava no cache o arquivo de cada protocolo da biblioteca (idempotente)."""
    from app.modules.sessions.service import materialize_audio    # noqa: E402
    with Session(get_engine()) as s:
        for spec in LIBRARY:
            proto = s.scalar(select(AudioProtocol).where(
                AudioProtocol.protocol_id == spec["protocol_id"],
                AudioProtocol.version == VERSION))
            if proto is None:
                print(f"FALTA   {spec['protocol_id']} v{VERSION} — semeie antes")
                continue
            r = materialize_audio(proto)
            print(f"pronto  {spec['protocol_id']} v{VERSION} — "
                  f"{r.size / 1e6:.1f} MB em {r.fmt}")


def _stale(s: Session) -> list[AudioProtocol]:
    """Linhas da MESMA banda em versão diferente da corrente.

    Semear uma versão nova (o leito ambiente, ADR-109) não apaga a antiga: as duas passam a
    disputar a mesma banda e condição em ``resolve_protocol``, que desempata pela mais nova.
    O desempate impede o pior — servir o estímulo velho —, mas conviver com duas versões é
    erro operacional, e erro operacional silencioso em estudo cego é o que não pode existir.
    Quem lista é o ``--check``; **apagar é decisão humana**, porque uma linha antiga pode ter
    sessões apontando para ela."""
    return list(s.scalars(select(AudioProtocol).where(
        AudioProtocol.band == BAND, AudioProtocol.version != VERSION)))


def main(check_only: bool = False, materialize: bool = False) -> int:
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
            velhas = _stale(s)
            for row in velhas:
                print(f"ANTIGA  {row.protocol_id} v{row.version} — banda {BAND}; a corrente "
                      f"é v{VERSION}. Confira se ainda há sessões apontando para ela antes "
                      f"de remover.")
            return 1 if (faltando or velhas) else 0

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
    if materialize:
        _materialize()
    return 0


if __name__ == "__main__":
    sys.exit(main(check_only="--check" in sys.argv,
                  materialize="--materialize" in sys.argv))
