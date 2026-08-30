"""
tests/test_audio_format.py — Formato de entrega do estímulo (G1/ADR-103).

O protocolo aprovado pede 20 min a 48 kHz/16 bits: **230 MB por arquivo** em PCM cru. Nesse
formato o piloto não roda (participante em 4G, servidor lendo o corpo inteiro por requisição).
A saída é FLAC — mas só vale se ele for, de fato, **sem perdas**: a decisão inegociável #3 diz
que o cliente reproduz o estímulo bit-a-bit.

Este arquivo guarda as quatro promessas da fatia:
  (1) FLAC e WAV decodificam para o MESMO PCM, amostra a amostra (é o que autoriza a troca);
  (2) o FLAC de fato encolhe o estímulo do estudo (senão a fatia não teria motivo);
  (3) a validação por FFT olha o ARQUIVO GRAVADO, não a síntese — com um codificador no
      caminho, validar o sinal em memória deixaria de falar sobre o que o participante ouve;
  (4) sem codificador, a materialização FALHA em vez de cair em silêncio para 230 MB de WAV.
"""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from app.core.config import InsecureConfigError, audio_format
from app.modules.sessions import audio_render

# Estímulo do estudo, em versão curta o bastante para o teste ser rápido.
KW = dict(carrier_hz=250.0, beat_hz=3.0, duration_s=3.0, target_peak_dbfs=-12.0,
          sample_rate=48000, fade_in_s=0.5, fade_out_s=1.0)


def _pcm(path: str) -> np.ndarray:
    dados, _ = sf.read(path, dtype="int16", always_2d=True)
    return dados


# ------------------------------------------------------------------ (1) sem perdas
def test_flac_decodifica_para_o_mesmo_pcm_do_wav(tmp_path):
    """A troca de formato não pode mudar UMA amostra — é o que sustenta o inegociável #3."""
    wav = audio_render.render_protocol_to_file(str(tmp_path / "a.wav"), fmt="wav", **KW)
    flac = audio_render.render_protocol_to_file(str(tmp_path / "a.flac"), fmt="flac", **KW)
    assert np.array_equal(_pcm(wav.path), _pcm(flac.path))
    assert wav.sample_rate == flac.sample_rate == 48000
    assert wav.sha256 != flac.sha256          # contêineres diferentes, conteúdo idêntico


def test_sham_tambem_sobrevive_a_codificacao(tmp_path):
    """O braço de controle (Δf = 0) passa pelo mesmo codificador e continua idêntico.

    Importa porque um codificador que tratasse canais correlacionados de forma especial
    poderia degradar SÓ um dos braços — e um artefato assimétrico é vazamento de braço."""
    kw = {**KW, "beat_hz": 0.0}
    wav = audio_render.render_protocol_to_file(str(tmp_path / "s.wav"), fmt="wav", **kw)
    flac = audio_render.render_protocol_to_file(str(tmp_path / "s.flac"), fmt="flac", **kw)
    esquerda, direita = _pcm(flac.path)[:, 0], _pcm(flac.path)[:, 1]
    assert np.array_equal(_pcm(wav.path), _pcm(flac.path))
    assert np.array_equal(esquerda, direita)   # sham: sem pista interaural, nem após o FLAC


# ------------------------------------------------------------------ (2) tamanho
def test_flac_encolhe_o_estimulo_do_estudo(tmp_path):
    """O motivo da fatia: 230 MB por sessão inviabilizam o piloto em rede móvel.

    O estímulo é um par de senoides — material em que a predição linear do FLAC vai muito
    bem. Exigimos folgadamente menos da metade; na prática fica perto de 15%."""
    wav = audio_render.render_protocol_to_file(str(tmp_path / "b.wav"), fmt="wav", **KW)
    flac = audio_render.render_protocol_to_file(str(tmp_path / "b.flac"), fmt="flac", **KW)
    assert flac.size < wav.size / 2


# ------------------------------------------------------------------ (3) validação do artefato
def test_validacao_le_o_arquivo_gravado_e_nao_so_a_sintese(tmp_path, monkeypatch):
    """Um codificador que alterasse o sinal tem de ser pego ANTES de o arquivo ser publicado."""
    original = audio_render.read_pcm_window

    def janela_adulterada(path, fmt, start, count):
        sinal = original(path, fmt, start, count)
        sinal[:, 1] = sinal[:, 0]        # simula um codificador que colapsou os canais
        return sinal

    monkeypatch.setattr(audio_render, "read_pcm_window", janela_adulterada)
    destino = tmp_path / "c.flac"
    with pytest.raises(ValueError, match="FFT"):
        audio_render.render_protocol_to_file(str(destino), fmt="flac", **KW)
    assert not destino.exists()                    # nada é publicado...
    assert not (destino.parent / (destino.name + ".tmp")).exists()   # ...nem sobra lixo


def test_arquivo_parcial_nunca_e_publicado(tmp_path, monkeypatch):
    """Falha no meio da escrita não pode deixar um artefato servível pela metade."""
    def explode(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(audio_render, "_to_pcm16", explode)
    destino = tmp_path / "d.flac"
    with pytest.raises(OSError):
        audio_render.render_protocol_to_file(str(destino), fmt="flac", **KW)
    assert not destino.exists()
    assert not (destino.parent / (destino.name + ".tmp")).exists()


# ------------------------------------------------------------------ (4) falha visível
def test_sem_codificador_a_materializacao_falha_alto(tmp_path, monkeypatch):
    """Cair em silêncio para WAV serviria 230 MB a quem está em 4G: a falha é do operador."""
    def sem_soundfile():
        raise audio_render.EncoderUnavailable("sem libsndfile")

    monkeypatch.setattr(audio_render, "_soundfile", sem_soundfile)
    with pytest.raises(audio_render.EncoderUnavailable):
        audio_render.render_protocol_to_file(str(tmp_path / "e.flac"), fmt="flac", **KW)
    # ...e o WAV continua funcionando sem o codificador (saída de emergência do operador).
    assert audio_render.render_protocol_to_file(str(tmp_path / "e.wav"), fmt="wav", **KW).size > 0


def test_formato_desconhecido_e_recusado(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        audio_render.render_protocol_to_file(str(tmp_path / "f.ogg"), fmt="ogg", **KW)
    monkeypatch.setenv("AUDIO_FORMAT", "mp3")
    with pytest.raises(InsecureConfigError):
        audio_format()


# ------------------------------------------------------------------ leitura em janelas
def test_corpo_e_lido_em_janelas_do_disco(tmp_path):
    """O handle entrega faixas exatas sem carregar o arquivo — é o que sustenta o Range."""
    r = audio_render.render_protocol_to_file(str(tmp_path / "g.flac"), fmt="flac", **KW)
    inteiro = open(r.path, "rb").read()
    assert r.size == len(inteiro)
    assert r.read_all() == inteiro
    assert b"".join(r.chunks(10, 199, chunk_size=7)) == inteiro[10:200]
    assert b"".join(r.chunks(r.size - 1)) == inteiro[-1:]
    assert b"".join(r.chunks(r.size)) == b""        # faixa vazia não estoura
