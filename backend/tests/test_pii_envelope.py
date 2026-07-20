"""
tests/test_pii_envelope.py — Envelope encryption da PII (DEK por registro, C11/ADR-088).

Prova o "Pronto (DoD)":
  (1) formato envelope (0x02): a DEK cifra a PII, a KEK só embrulha a DEK;
  (2) DEK **por registro**: cifrar o mesmo texto duas vezes dá DEKs embrulhadas e ct diferentes;
  (3) AAD liga tanto a DEK embrulhada quanto o ct ao participante+campo (trocar de campo falha);
  (4) a KEK **não** cifra a PII diretamente — desembrulhar dá a DEK, não o texto;
  (5) compatibilidade retroativa: tokens v1 (ADR-087, KEK direto) ainda decifram;
  (6) rotação da KEK continua valendo no envelope (KEK aposentada desembrulha DEK antiga).
"""
from __future__ import annotations
import base64
import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core import pii_crypto, keyring
from app.core.keyring import set_key_provider

_KA = base64.b64encode(b"A" * 32).decode()
_KB = base64.b64encode(b"B" * 32).decode()


def _clear(monkeypatch):
    for v in ("PII_ENC_KEY", "PII_ENC_KEY_ID", "PII_ENC_KEYS"):
        monkeypatch.delenv(v, raising=False)
    set_key_provider(None)


def test_envelope_format_and_roundtrip(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    aad = pii_crypto.aad_for(uuid.uuid4(), "email")
    token = pii_crypto.encrypt("fulano@example.com", aad=aad)
    assert token[0] == 0x02                                    # envelope
    assert pii_crypto.decrypt(token, aad=aad) == "fulano@example.com"


def test_dek_is_per_record(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    aad = pii_crypto.aad_for(uuid.uuid4(), "name")
    t1 = pii_crypto.encrypt("Fulano", aad=aad)
    t2 = pii_crypto.encrypt("Fulano", aad=aad)
    # Mesmo texto, mesma KEK: mas DEK aleatória por registro → tokens totalmente distintos.
    assert t1 != t2
    assert pii_crypto.decrypt(t1, aad=aad) == pii_crypto.decrypt(t2, aad=aad) == "Fulano"


def test_aad_binding_still_enforced(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    pid = uuid.uuid4()
    token = pii_crypto.encrypt("Nome", aad=pii_crypto.aad_for(pid, "name"))
    with pytest.raises(InvalidTag):                            # trocar campo name→email falha
        pii_crypto.decrypt(token, aad=pii_crypto.aad_for(pid, "email"))
    with pytest.raises(InvalidTag):                            # mover p/ outra linha falha
        pii_crypto.decrypt(token, aad=pii_crypto.aad_for(uuid.uuid4(), "name"))


def test_kek_does_not_encrypt_pii_directly(monkeypatch):
    """A KEK só embrulha a DEK: desembrulhar o blob dá a DEK (32 bytes), não a PII."""
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    aad = pii_crypto.aad_for(uuid.uuid4(), "email")
    token = pii_crypto.encrypt("segredo@x.com", aad=aad)
    # Reparte o token envelope e desembrulha o blob com a KEK.
    kid_len = token[1]
    i = 2 + kid_len
    blob_len = int.from_bytes(token[i:i + 2], "big"); i += 2
    blob = token[i:i + blob_len]
    kek = base64.b64decode(_KA)
    dek = AESGCM(kek).decrypt(blob[:12], blob[12:], aad)
    assert len(dek) == 32                                      # é a DEK, não o texto
    assert b"segredo" not in dek


def test_v1_direct_kek_token_still_decrypts(monkeypatch):
    """Compat: um token v1 (ADR-087, 0x01 = KEK cifra direto) ainda decifra."""
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    monkeypatch.setenv("PII_ENC_KEY_ID", "env1")
    aad = pii_crypto.aad_for(uuid.uuid4(), "name")
    # Constrói manualmente um token v1: 0x01 || len(kid) || kid || nonce || ct(KEK direto).
    kek = base64.b64decode(_KA)
    kid = b"env1"
    nonce = os.urandom(12)
    ct = AESGCM(kek).encrypt(nonce, b"heranca-v1", aad)
    v1 = bytes([0x01, len(kid)]) + kid + nonce + ct
    assert pii_crypto.decrypt(v1, aad=aad) == "heranca-v1"


def test_rotation_under_envelope(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    monkeypatch.setenv("PII_ENC_KEY_ID", "k1")
    aad = pii_crypto.aad_for(uuid.uuid4(), "email")
    old = pii_crypto.encrypt("antigo@x.com", aad=aad)          # DEK embrulhada por KEK k1
    # Rotaciona a KEK: k2 ativa; k1 aposentada (só desembrulha).
    monkeypatch.setenv("PII_ENC_KEY", _KB)
    monkeypatch.setenv("PII_ENC_KEY_ID", "k2")
    monkeypatch.setenv("PII_ENC_KEYS", f"k1:{_KA}")
    new = pii_crypto.encrypt("novo@x.com", aad=aad)
    assert new[2:2 + new[1]].decode() == "k2"
    assert pii_crypto.decrypt(old, aad=aad) == "antigo@x.com"  # k1 ainda desembrulha a DEK
    assert pii_crypto.decrypt(new, aad=aad) == "novo@x.com"
