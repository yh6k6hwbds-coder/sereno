"""
tests/test_pilot_protocol.py — O estímulo do PROTOCOLO APROVADO (não o de desenvolvimento).

Guarda os números que vêm do projeto de pesquisa, não da engenharia:

    braço experimental — 250 Hz na orelha esquerda, 253 Hz na direita (Δf = 3 Hz, delta);
    braço controle     — 250 Hz idêntico nas duas orelhas (Δf = 0), energia equalizada;
    arquivo            — 20 min, 48 kHz, 16 bits, sem perdas, rampas de 30 s / 60 s.

Mudar qualquer um destes valores é EMENDA DE PROTOCOLO (CEP), não refatoração: por isso
o teste falha na cara de quem editar a biblioteca sem passar pelo comitê.
"""
from __future__ import annotations

import numpy as np

import binaural_instrument as bi


def _pilot():
    assert len(bi.PILOT_LIBRARY) == 1, "o piloto usa UM protocolo fixo (sem personalização)"
    return bi.PILOT_LIBRARY[0]


def test_parametros_do_protocolo_aprovado():
    p = _pilot()
    assert (p.carrier_hz, p.beat_hz, p.band) == (250.0, 3.0, "delta")
    assert p.expected_channels_hz(sham=False) == (250.0, 253.0)
    assert p.expected_channels_hz(sham=True) == (250.0, 250.0)
    assert p.duration_s == 1200.0                      # 20 minutos por sessão
    assert (p.sample_rate, p.bit_depth) == (48000, 16)  # sem perdas
    assert (p.fade_in_s, p.fade_out_s) == (30.0, 60.0)  # rampas assimétricas


def test_dose_total_do_estudo():
    """20 sessões de 20 min = 400 min ≈ 6 h 40 — a exposição declarada ao CEP."""
    p = _pilot()
    total_s = 20 * p.duration_s
    assert total_s == 24000.0
    assert round(total_s / 3600, 2) == 6.67


def test_bateria_fft_aprova_ativo_e_sham():
    p = _pilot()
    for sham in (False, True):
        rep = bi.validate_protocol(p, sham=sham)
        assert rep["passed"], [c for c in rep["checks"] if not c["ok"]]


def test_energia_equalizada_entre_bracos():
    """Sem isto o braço ativo poderia soar diferente do controle e o cegamento cairia."""
    assert bi.validate_arm_energy_match(_pilot())["ok"]


def test_sham_nao_tem_pista_interaural():
    """No controle os dois canais são o MESMO sinal, amostra a amostra."""
    seg = bi.synthesize_segment(_pilot(), sham=True, start_s=600.0, duration_s=1.0)
    assert np.array_equal(seg[:, 0], seg[:, 1])

    ativo = bi.synthesize_segment(_pilot(), sham=False, start_s=600.0, duration_s=1.0)
    assert not np.array_equal(ativo[:, 0], ativo[:, 1])
    # o canal esquerdo é idêntico nos dois braços: a diferença é SÓ o canal direito
    assert np.array_equal(seg[:, 0], ativo[:, 0])


def test_trecho_e_bit_a_bit_igual_ao_sinal_inteiro():
    """Validar por trechos não pode mudar o sinal — é a mesma fórmula, só que fatiada.

    Provado num protocolo curto (o de 20 min não cabe inteiro na memória: ~920 MB)."""
    curto = bi.AudioProtocol("t-3", "1.0.0", "delta", 250.0, 3.0, duration_s=8.0,
                             fade_in_s=1.0, fade_out_s=3.0, sample_rate=48000)
    inteiro = bi.synthesize(curto, sham=False)
    fs = curto.sample_rate
    for start_s, dur_s in ((0.0, 1.5), (3.0, 2.0), (6.5, 1.5)):
        trecho = bi.synthesize_segment(curto, sham=False, start_s=start_s, duration_s=dur_s)
        ini = int(round(start_s * fs))
        assert np.array_equal(trecho, inteiro[ini:ini + trecho.shape[0]])


def test_rampas_assimetricas_tem_a_duracao_pedida():
    """A rampa de entrada dura 30 s e a de saída 60 s — e o meio fica em regime permanente."""
    p = _pilot()
    amp = 10.0 ** (p.target_peak_dbfs / 20.0)

    # ~metade da rampa de entrada (15 s) → envelope ≈ 0,5 (raised-cosine)
    meio_fade_in = bi.synthesize_segment(p, sham=False, start_s=15.0, duration_s=0.05)
    assert 0.3 * amp < np.max(np.abs(meio_fade_in)) < 0.7 * amp

    # logo após o fim da rampa de entrada → amplitude plena
    apos = bi.synthesize_segment(p, sham=False, start_s=31.0, duration_s=0.05)
    assert np.max(np.abs(apos)) > 0.99 * amp

    # ~metade da rampa de saída (30 s antes do fim) → envelope ≈ 0,5
    meio_fade_out = bi.synthesize_segment(p, sham=False, start_s=1170.0, duration_s=0.05)
    assert 0.3 * amp < np.max(np.abs(meio_fade_out)) < 0.7 * amp

    # ainda em regime permanente 61 s antes do fim (a rampa de saída só começa em 1140 s)
    antes = bi.synthesize_segment(p, sham=False, start_s=1138.0, duration_s=0.05)
    assert np.max(np.abs(antes)) > 0.99 * amp
