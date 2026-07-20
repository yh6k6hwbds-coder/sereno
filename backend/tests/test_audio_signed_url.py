"""
tests/test_audio_signed_url.py — Entrega de áudio por URL ASSINADA (E3/ADR-082).

Prova o "Pronto (DoD)":
  (1) modo padrão (inline) inalterado — coberto por test_session_audio; aqui garantimos
      que ligar AUDIO_DELIVERY=signed-url faz o endpoint da sessão responder 302 para
      /audio/{content_hash} com exp+sig;
  (2) a URL assinada entrega o MESMO WAV bit-a-bit (ETag == sha256 do corpo) e suporta Range;
  (3) sem vazamento de braço: o Location e a resposta assinada são NEUTROS (nenhum termo de
      condição); braços opostos produzem a mesma FORMA de resposta;
  (4) capability: assinatura adulterada, ausente ou expirada → 403 (genérico, sem oráculo);
      hash desconhecido (bem assinado é impossível sem a chave) → 404 via helper interno;
  (5) a chave do objeto é o content_hash OPACO — o mesmo já devolvido no start da sessão.
"""
from __future__ import annotations
import hashlib
import time

from app.core.models import Participant, Allocation, AudioProtocol
from app.core import auth
from app.modules.sessions import storage

START = "/v1/sessions"
CARRIER, BEAT_ACTIVE, DUR = 200.0, 10.0, 2.0
FORBIDDEN = ("active", "sham", "beat", "arm", "condition", "ativo")
ACTIVE_HASH = hashlib.sha256(b"alpha-active").hexdigest()
SHAM_HASH = hashlib.sha256(b"alpha-sham").hexdigest()


def _seed_short_library(TestSession):
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="ax-0001", version="1.0.0", band="alpha",
                            carrier_hz=CARRIER, beat_hz=BEAT_ACTIVE, duration_s=DUR,
                            target_peak_dbfs=-12.0, content_hash=ACTIVE_HASH))
        s.add(AudioProtocol(protocol_id="ax-0002", version="1.0.0", band="alpha",
                            carrier_hz=CARRIER, beat_hz=0, duration_s=DUR,
                            target_peak_dbfs=-12.0, content_hash=SHAM_HASH))
        s.commit()


def _seed_participant(TestSession, code, arm):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="testref"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _start(client, hdr) -> str:
    r = client.post(START, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def _signed_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("AUDIO_DELIVERY", "signed-url")


def test_session_audio_redirects_to_signed_url(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-SIGN", "A")
    sid = _start(client, hdr)

    # httpx segue redirects por padrão; queremos inspecionar o 302 em si.
    r = client.get(f"{START}/{sid}/audio", headers=hdr, follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith(f"/v1/audio/{ACTIVE_HASH}?")     # chave = content_hash OPACO
    assert "exp=" in loc and "sig=" in loc
    # Location NEUTRO: nada nomeia a condição.
    assert not any(tok in loc.lower() for tok in FORBIDDEN)


def test_signed_url_delivers_same_bytes_and_fidelity(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-SIGN2", "A")
    sid = _start(client, hdr)

    # Seguindo o redirect (sem Authorization no destino: a assinatura é a capability).
    loc = client.get(f"{START}/{sid}/audio", headers=hdr, follow_redirects=False).headers["location"]
    r = client.get(loc)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.headers["accept-ranges"] == "bytes"
    body = r.content
    assert body[:4] == b"RIFF" and len(body) > 44
    assert r.headers["etag"].strip('"') == hashlib.sha256(body).hexdigest()   # bit-a-bit


def test_signed_url_supports_range(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-SIGN-RANGE", "A")
    loc = client.get(f"{START}/{_start(client, hdr)}/audio", headers=hdr,
                     follow_redirects=False).headers["location"]
    full = client.get(loc).content
    r = client.get(loc, headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-99/{len(full)}"
    assert r.content == full[:100]


def test_signed_url_no_leak_same_shape_opposite_arms(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pa, hdr_a = _seed_participant(TestSession, "P-SG-A", "A")   # ativo
    _pb, hdr_b = _seed_participant(TestSession, "P-SG-B", "B")   # sham
    la = client.get(f"{START}/{_start(client, hdr_a)}/audio", headers=hdr_a, follow_redirects=False).headers["location"]
    lb = client.get(f"{START}/{_start(client, hdr_b)}/audio", headers=hdr_b, follow_redirects=False).headers["location"]
    ra, rb = client.get(la), client.get(lb)
    assert ra.status_code == rb.status_code == 200

    def shape(resp):
        return {k.lower() for k in resp.headers.keys()}
    assert shape(ra) == shape(rb)
    assert ra.headers["content-type"] == rb.headers["content-type"] == "audio/wav"
    for resp in (ra, rb):
        blob = " ".join(f"{k}:{v}" for k, v in resp.headers.items()).lower()
        assert not any(tok in blob for tok in FORBIDDEN)
    # Bytes diferem (arquivos opacos distintos), mas a forma é idêntica.
    assert ra.content != rb.content


def test_tampered_signature_403(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-TAMPER", "A")
    loc = client.get(f"{START}/{_start(client, hdr)}/audio", headers=hdr,
                     follow_redirects=False).headers["location"]
    # Adultera o último caractere hex da assinatura.
    bad = loc[:-1] + ("0" if loc[-1] != "0" else "1")
    assert client.get(bad).status_code == 403


def test_missing_signature_403(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    # Sem exp/sig: não é uma URL assinada válida.
    assert client.get(f"/v1/audio/{ACTIVE_HASH}").status_code == 403


def test_expired_signature_403(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    # Assinatura BEM formada mas já expirada (TTL negativo) — validade é conferida.
    past = storage.build_signed_path(ACTIVE_HASH, ttl_s=-10)
    assert client.get(past).status_code == 403


def test_valid_signature_unknown_hash_404(api, monkeypatch, tmp_path):
    _signed_mode(monkeypatch, tmp_path)
    client, TestSession = api
    _seed_short_library(TestSession)
    # Hash bem assinado (com a MESMA chave do servidor) mas ausente da biblioteca → 404.
    ghost = hashlib.sha256(b"nao-existe").hexdigest()
    path = storage.build_signed_path(ghost, ttl_s=300)
    assert client.get(path).status_code == 404


def test_inline_mode_is_default_no_redirect(api, monkeypatch, tmp_path):
    # Sem AUDIO_DELIVERY: comportamento A1 (200 inline), nenhum 302.
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))
    client, TestSession = api
    _seed_short_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-INLINE", "A")
    r = client.get(f"{START}/{_start(client, hdr)}/audio", headers=hdr, follow_redirects=False)
    assert r.status_code == 200 and "location" not in {k.lower() for k in r.headers}


def test_sign_verify_roundtrip_and_key_isolation(monkeypatch):
    # Unidade: a assinatura só valida com a MESMA chave; trocar a chave invalida.
    monkeypatch.setenv("AUDIO_URL_SIGNING_KEY", "chave-1")
    exp = int(time.time()) + 300
    from app.modules.sessions.storage import _sign          # helper interno
    sig = _sign(ACTIVE_HASH, exp)
    assert storage.verify_signed(ACTIVE_HASH, exp, sig) is True
    # Assinatura de OUTRO hash não vale para este (a mensagem cobre content_hash|exp).
    assert storage.verify_signed(SHAM_HASH, exp, sig) is False
    monkeypatch.setenv("AUDIO_URL_SIGNING_KEY", "chave-2")
    assert storage.verify_signed(ACTIVE_HASH, exp, sig) is False    # outra chave não valida
