# Etapa 2 — O player como instrumento científico
Fonte: `anexos-docx/Etapa2_Player_Instrumento.docx` · código: `../audio-pipeline/binaural_instrument.py`.
- **Estímulo do protocolo aprovado (ADR-100):** 250 Hz na orelha esquerda e 253 Hz na direita
  (**Δf = 3 Hz**, faixa delta); controle = 250 Hz nas duas orelhas (Δf = 0), energia equalizada;
  20 min por sessão, 48 kHz, 16 bits, rampas de 30 s (entrada) e 60 s (saída).
- Síntese determinística offline; **sham Δf=0**; **validação por FFT** (executada).
- Reprodução **bit-a-bit**, sem perdas, sem DSP; fones com fio; teto de volume.
- Ocultação de alocação por handle neutro; cegamento no app.
