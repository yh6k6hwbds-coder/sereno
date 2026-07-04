# audio-pipeline (o estímulo é um instrumento)

Síntese **determinística offline** do áudio binaural e do **sham (Δf=0)**, validada
por **FFT** (`binaural_instrument.py`). Saída: biblioteca **sem perdas** (WAV/FLAC)
versionada + hash. O cliente **reproduz bit-a-bit** — nunca sintetiza nem processa.
A bateria de FFT roda no CI e **bloqueia** áudio fora de especificação.
