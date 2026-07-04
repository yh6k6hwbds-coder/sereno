"""
tests/test_signal_battery.py — Gate inegociável do estímulo (validação por FFT).

Prova que:
  (1) a bateria de validação passa para toda a biblioteca de referência usando
      APENAS numpy/scipy (o caminho crítico não arrasta matplotlib);
  (2) ativo tem o Δf esperado e sham tem Δf = 0;
  (3) a validação REPROVA sinais fora de especificação (guarda contra regressões que
      deixariam o gate passar indevidamente — o furo que este teste protege).
A geração da figura é opcional e não pertence a este gate (ver render_validation_figure).
"""
from __future__ import annotations
import sys

import binaural_instrument as bi


def test_battery_passes_with_numpy_scipy_only():
    # Importar o módulo e rodar a bateria não pode depender de matplotlib.
    assert "matplotlib" not in sys.modules
    assert bi.run_battery(bi.REFERENCE_LIBRARY) is True
    assert "matplotlib" not in sys.modules


def test_active_has_beat_and_sham_has_none():
    for proto in bi.REFERENCE_LIBRARY:
        rep_active = bi.validate_signal(bi.synthesize(proto, sham=False), proto, sham=False)
        rep_sham = bi.validate_signal(bi.synthesize(proto, sham=True), proto, sham=True)
        assert rep_active["passed"], f"{proto.protocol_id} ativo reprovou"
        assert rep_sham["passed"], f"{proto.protocol_id} sham reprovou"


def test_validation_rejects_swapped_channels():
    """Canais L/R trocados devem REPROVAR (atribuição e Δf invertidos)."""
    proto = bi.REFERENCE_LIBRARY[0]              # alpha-10 (Δf = 10)
    sig = bi.synthesize(proto, sham=False)
    swapped = sig[:, ::-1].copy()                # troca L ↔ R
    rep = bi.validate_signal(swapped, proto, sham=False)
    assert rep["passed"] is False


def test_validation_rejects_wrong_beat():
    """Um sham (Δf=0) validado como se fosse ativo (Δf esperado>0) deve REPROVAR."""
    proto = bi.REFERENCE_LIBRARY[0]
    sham_sig = bi.synthesize(proto, sham=True)   # Δf real = 0
    rep = bi.validate_signal(sham_sig, proto, sham=False)  # esperado Δf = 10
    assert rep["passed"] is False
