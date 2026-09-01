"""
tests/test_leito_ambiente.py — O leito ambiente do protocolo (G2, ADR-109).

O protocolo, em "Parâmetros comuns aos dois braços", promete **"trilha de fundo ambiental de
baixa intensidade, idêntica em conteúdo, duração e nível, sobre a qual os tons são
superpostos"** — e, no mesmo parágrafo, **recusa** o mascaramento por ruído rosa, com base
metanalítica. As duas frases juntas restringem bastante o que o leito pode ser.

O que se prova aqui, do lado do SERVIDOR (a bateria de FFT da pipeline prova o lado
científico):

  1. **As duas sínteses concordam amostra a amostra.** A pipeline é a fonte de verdade
     validada por FFT no CI; este módulo é o materializador. Elas são código duplicado por
     decisão antiga, e a duplicação só é aceitável enquanto houver um teste que a amarre.
  2. **O leito é diótico** — a mesma coluna nos dois canais, sem diferença interaural.
  3. **O leito não depende do braço** — ativo e sham recebem o mesmo leito, bit a bit. É um
     item de CEGAMENTO: um leito que variasse com ``beat_hz`` seria uma pista audível.
  4. **O arquivo entregue não estoura o teto digital** contra o qual a calibração em
     acoplador é feita — a amplitude dos tons cede a folga que o pico do leito ocupa.
  5. **Sem leito, nada mudou.** Um protocolo anterior a esta mudança gera exatamente as
     mesmas amostras de antes.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys

import numpy as np
import pytest

from app.modules.sessions import audio_render

# Parâmetros do estímulo do estudo (o de 20 min é longo demais para um teste; a fórmula é a
# mesma, e o que se compara aqui é a síntese, não a duração).
CARRIER, BEAT, DUR, PEAK, FS = 250.0, 3.0, 4.0, -12.0, 48000
BED = -30.0


def _pipeline():
    """Importa ``binaural_instrument`` por caminho — a pipeline não é um pacote instalável."""
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    caminho = os.path.join(raiz, "audio-pipeline", "binaural_instrument.py")
    if not os.path.exists(caminho):
        pytest.skip("audio-pipeline não disponível neste ambiente")
    spec = importlib.util.spec_from_file_location("binaural_instrument", caminho)
    mod = importlib.util.module_from_spec(spec)
    # Registrar ANTES de executar: a pipeline usa ``from __future__ import annotations``, e
    # ``@dataclass`` resolve as anotações em string procurando ``sys.modules[cls.__module__]``.
    # Sem esta linha o import por caminho estoura em AttributeError dentro de dataclasses.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _backend(sham: bool, *, bed: float | None = BED, with_bed: bool = True,
             start: int = 0, count: int | None = None):
    n = int(round(DUR * FS))
    return audio_render.synthesize_segment(
        CARRIER, 0.0 if sham else BEAT, DUR, PEAK, sample_rate=FS,
        fade_in_s=0.5, fade_out_s=0.5, bed_level_dbr=bed, with_bed=with_bed,
        start=start, count=n if count is None else count)


def _leito(sham: bool):
    """O leito isolado: mistura − tons, com os tons na MESMA amplitude reduzida.

    Recuperar por subtração (em vez de comparar o leito sintetizado consigo mesmo) é o que
    faz estes itens pegarem um leito que passasse a depender do braço lá na frente.
    ``with_bed=False`` mantém a amplitude que cedeu a folga do leito; ``bed=None`` devolveria
    os tons no teto cheio e a conta traria a diferença de amplitude junto."""
    return _backend(sham) - _backend(sham, with_bed=False)


def _protocolo(pipeline, *, bed: float | None = BED):
    return pipeline.AudioProtocol("t-leito", "1.0.0", "delta", CARRIER, BEAT, duration_s=DUR,
                                  fade_in_s=0.5, fade_out_s=0.5, sample_rate=FS,
                                  bit_depth=16, bed_level_dbr=bed)


# ------------------------------------------------- 1. as duas sínteses concordam
@pytest.mark.parametrize("sham", [False, True])
def test_backend_e_pipeline_geram_o_mesmo_sinal(sham):
    pipeline = _pipeline()
    do_pipeline = pipeline.synthesize_segment(_protocolo(pipeline), sham=sham)
    do_backend = _backend(sham)
    assert do_backend.shape == do_pipeline.shape
    # Zero, não "quase": as duas implementações executam a MESMA sequência de operações.
    assert np.max(np.abs(do_backend - do_pipeline)) == 0.0


def test_o_leito_sai_igual_em_janelas_e_de_uma_vez_so():
    """O servidor materializa 20 min em janelas de 10 s; o resultado não pode depender disso."""
    inteiro = _backend(False)
    n = inteiro.shape[0]
    passo = n // 7 + 1        # janelas propositalmente desalinhadas com qualquer período
    partes = [_backend(False, start=i, count=min(passo, n - i)) for i in range(0, n, passo)]
    assert np.max(np.abs(np.concatenate(partes, axis=0) - inteiro)) == 0.0


# ------------------------------------------------- 2 e 3. diótico e cego
@pytest.mark.parametrize("sham", [False, True])
def test_o_leito_e_diotico(sham):
    """Sem diferença interaural, o leito não gera batimento nem pista de braço."""
    leito = _leito(sham)
    # A subtração recupera o leito a menos de arredondamento de float64.
    assert np.max(np.abs(leito[:, 0] - leito[:, 1])) < 1e-12
    assert np.max(np.abs(leito)) > 0.0          # e existe de fato


def test_o_leito_e_o_mesmo_nos_dois_bracos():
    """'Idêntica em conteúdo, duração e nível' nas duas condições — item de cegamento."""
    leito_ativo, leito_sham = _leito(False), _leito(True)
    assert np.max(np.abs(leito_ativo - leito_sham)) < 1e-12


# ------------------------------------------------- 4. o teto digital continua valendo
def test_a_mistura_nao_estoura_o_teto_digital():
    """O teto é do arquivo ENTREGUE: é contra ele que a calibração em acoplador é feita."""
    teto = 10.0 ** (PEAK / 20.0)
    pico = float(np.max(np.abs(_backend(False))))
    assert pico <= teto                       # não estoura...
    assert pico > teto * 0.9                  # ...e não desperdiça faixa dinâmica


def test_o_leito_fica_abaixo_do_estimulo():
    """'Baixa intensidade': o nível declarado é respeitado, dentro da oscilação dos LFOs."""
    leito = _leito(False)
    tons = _backend(False, with_bed=False)
    dif_db = 20.0 * math.log10(
        float(np.sqrt(np.mean(leito[:, 0] ** 2))) / float(np.sqrt(np.mean(tons[:, 0] ** 2))))
    assert BED - 3.5 <= dif_db <= BED + 3.5


def test_leito_nao_põe_energia_na_banda_do_estimulo():
    """É o que torna verificável a recusa do protocolo ao mascaramento."""
    leito = _leito(False)[:, 0]
    mag = np.abs(np.fft.rfft(leito * np.hanning(len(leito))))
    freqs = np.fft.rfftfreq(len(leito), d=1.0 / FS)
    na_banda = (freqs >= CARRIER - 20.0) & (freqs <= CARRIER + BEAT + 20.0)
    razao = math.sqrt(float(np.sum(mag[na_banda] ** 2)) / float(np.sum(mag ** 2)))
    assert 20.0 * math.log10(max(razao, 1e-12)) <= -60.0


# ------------------------------------------------- 5. sem leito, nada mudou
@pytest.mark.parametrize("sham", [False, True])
def test_protocolo_sem_leito_gera_o_mesmo_de_antes(sham):
    """Fórmula anterior ao G2, escrita à mão: os protocolos de demo não podem ter mudado."""
    n = int(round(DUR * FS))
    amp = 10.0 ** (PEAK / 20.0)
    t = np.arange(n, dtype=np.float64) / FS
    env = audio_render._envelope_slice(n, int(round(0.5 * FS)), int(round(0.5 * FS)), 0, n)
    esperado = np.stack([amp * np.sin(2.0 * np.pi * CARRIER * t) * env,
                         amp * np.sin(2.0 * np.pi * (CARRIER + (0.0 if sham else BEAT)) * t) * env],
                        axis=1)
    assert np.max(np.abs(_backend(sham, bed=None) - esperado)) == 0.0


def test_a_validacao_por_fft_do_servidor_ainda_reconhece_o_estimulo():
    """O leito não pode confundir a conferência que roda antes de servir o arquivo."""
    medido = audio_render.validate_fft(_backend(False), CARRIER, BEAT, sample_rate=FS)
    assert abs(medido["L"] - CARRIER) <= 1.0
    assert abs(medido["R"] - (CARRIER + BEAT)) <= 1.0
