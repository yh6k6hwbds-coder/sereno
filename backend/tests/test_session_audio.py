"""
tests/test_session_audio.py — Entrega de áudio da sessão (A1), ponta a ponta.

Prova o "Pronto (DoD)" da fatia A1:
  (1) participante baixa o áudio da PRÓPRIA sessão (200 + Content-Type de áudio);
  (2) IDOR: baixar áudio de sessão alheia → 404;
  (3) sem vazamento: braços opostos → MESMA forma de resposta/headers; os bytes/ETag
      diferem (opaco), mas nenhum header/metadado revela ativo/sham/beat/condição;
  (4) fidelidade: sha256(corpo) == ETag (bit-a-bit);
  (5) FFT: o WAV SERVIDO tem picos corretos (ativo: L=portadora, R=portadora+Δf;
      sham: ambos na portadora ⇒ Δf = 0);
  (6) Range (bytes=) → 206 com o trecho correto; faixa insatisfazível → 416.
Cobre ainda 401 (sem token) e 409 (protocolo indisponível).
"""
from __future__ import annotations
import io
import hashlib
import uuid
import wave

import numpy as np

from app.core.models import Participant, Allocation, AudioProtocol, Session as SessionModel
from app.core import auth

START = "/v1/sessions"
# Protocolos CURTOS (2 s) para manter a síntese rápida nos testes.
CARRIER, BEAT_ACTIVE, DUR = 200.0, 10.0, 2.0
FORBIDDEN = ("active", "sham", "beat", "arm", "condition", "ativo")


def _seed_short_library(TestSession):
    """alpha ATIVO (Δf=10) e alpha SHAM (Δf=0), curtos, com content_hash opaco distinto."""
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="ax-0001", version="1.0.0", band="alpha",
                            carrier_hz=CARRIER, beat_hz=BEAT_ACTIVE, duration_s=DUR,
                            target_peak_dbfs=-12.0,
                            content_hash=hashlib.sha256(b"alpha-active").hexdigest()))
        s.add(AudioProtocol(protocol_id="ax-0002", version="1.0.0", band="alpha",
                            carrier_hz=CARRIER, beat_hz=0, duration_s=DUR,
                            target_peak_dbfs=-12.0,
                            content_hash=hashlib.sha256(b"alpha-sham").hexdigest()))
        s.commit()


def _seed_participant(TestSession, code, arm):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="testref"))
        s.commit()
        pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _start(client, hdr) -> str:
    r = client.post(START, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def _isolate_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))


def test_download_own_audio_200_and_fidelity(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-AUDIO", "A")
    sid = _start(client, hdr)

    r = client.get(f"{START}/{sid}/audio", headers=hdr)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["cache-control"] == "private, no-store"
    body = r.content
    assert body[:4] == b"RIFF" and len(body) > 44          # WAV válido, com conteúdo
    # (4) fidelidade bit-a-bit: ETag == sha256(corpo)
    assert r.headers["etag"].strip('"') == hashlib.sha256(body).hexdigest()


def test_idor_other_participant_404(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pa, hdr_a = _seed_participant(TestSession, "P-OWNER", "A")
    _pb, hdr_b = _seed_participant(TestSession, "P-INTRUDER", "B")
    sid = _start(client, hdr_a)
    r = client.get(f"{START}/{sid}/audio", headers=hdr_b)     # B tenta o áudio de A
    assert r.status_code == 404


def test_no_token_401(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-NOAUTH", "A")
    sid = _start(client, hdr)
    r = client.get(f"{START}/{sid}/audio")                    # sem Authorization
    assert r.status_code == 401


def test_protocol_unavailable_409(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-GONE", "A")
    sid = _start(client, hdr)
    # Simula protocolo ausente da biblioteca: aponta a sessão para um UUID inexistente.
    with TestSession() as s:
        rec = s.get(SessionModel, uuid.UUID(sid))
        rec.protocol_uuid = uuid.uuid4()
        s.commit()
    r = client.get(f"{START}/{sid}/audio", headers=hdr)
    assert r.status_code == 409


def test_no_leak_same_shape_opposite_arms(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pa, hdr_a = _seed_participant(TestSession, "P-ARM-A", "A")   # A → ativo
    _pb, hdr_b = _seed_participant(TestSession, "P-ARM-B", "B")   # B → sham
    ra = client.get(f"{START}/{_start(client, hdr_a)}/audio", headers=hdr_a)
    rb = client.get(f"{START}/{_start(client, hdr_b)}/audio", headers=hdr_b)
    assert ra.status_code == rb.status_code == 200

    # (i) MESMA forma: mesmo conjunto de headers e mesmo Content-Type.
    def shape(resp):
        return {k.lower() for k in resp.headers.keys()}
    assert shape(ra) == shape(rb)
    assert ra.headers["content-type"] == rb.headers["content-type"] == "audio/wav"

    # (ii) Nenhum header revela o braço.
    for resp in (ra, rb):
        blob = " ".join(f"{k}:{v}" for k, v in resp.headers.items()).lower()
        assert not any(tok in blob for tok in FORBIDDEN)

    # (iii) Bytes/ETag diferem (arquivos distintos, opacos), mas nada nomeia a condição.
    assert ra.content != rb.content
    assert ra.headers["etag"] != rb.headers["etag"]


def _decode_channel_peaks(wav_bytes: bytes) -> tuple[float, float, int]:
    """Decodifica o WAV servido e devolve (pico_L_Hz, pico_R_Hz, taxa)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        fs = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype="<i2").reshape(-1, 2).astype(np.float64)
    window = np.hanning(data.shape[0])
    freqs = np.fft.rfftfreq(data.shape[0], d=1.0 / fs)
    peak_l = float(freqs[int(np.argmax(np.abs(np.fft.rfft(data[:, 0] * window))))])
    peak_r = float(freqs[int(np.argmax(np.abs(np.fft.rfft(data[:, 1] * window))))])
    return peak_l, peak_r, fs


def test_served_wav_fft_active_vs_sham(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pa, hdr_a = _seed_participant(TestSession, "P-FFT-A", "A")   # ativo
    _pb, hdr_b = _seed_participant(TestSession, "P-FFT-B", "B")   # sham
    body_a = client.get(f"{START}/{_start(client, hdr_a)}/audio", headers=hdr_a).content
    body_b = client.get(f"{START}/{_start(client, hdr_b)}/audio", headers=hdr_b).content

    l_a, r_a, _ = _decode_channel_peaks(body_a)
    l_b, r_b, _ = _decode_channel_peaks(body_b)
    # Ativo: L na portadora, R na portadora+Δf (Δf medido ≈ BEAT_ACTIVE).
    assert abs(l_a - CARRIER) <= 1.0 and abs(r_a - (CARRIER + BEAT_ACTIVE)) <= 1.0
    assert abs((r_a - l_a) - BEAT_ACTIVE) <= 1.0
    # Sham: ambos na portadora ⇒ Δf ≈ 0.
    assert abs(l_b - CARRIER) <= 1.0 and abs(r_b - CARRIER) <= 1.0
    assert abs(r_b - l_b) <= 1.0


def test_range_request_206(api, monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-RANGE", "A")
    sid = _start(client, hdr)
    full = client.get(f"{START}/{sid}/audio", headers=hdr).content
    total = len(full)

    # Primeiros 100 bytes.
    r = client.get(f"{START}/{sid}/audio", headers={**hdr, "Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-99/{total}"
    assert r.content == full[:100]

    # Trecho no meio (retomada).
    r2 = client.get(f"{START}/{sid}/audio", headers={**hdr, "Range": f"bytes=100-{total - 1}"})
    assert r2.status_code == 206
    assert r2.content == full[100:]

    # Faixa insatisfazível → 416.
    r3 = client.get(f"{START}/{sid}/audio", headers={**hdr, "Range": f"bytes={total + 10}-{total + 20}"})
    assert r3.status_code == 416
