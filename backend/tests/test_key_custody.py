"""
tests/test_key_custody.py — Custódia/rotação de chave de PII (porta KeyProvider, C11/ADR-087).

Prova o "Pronto (DoD)":
  (1) round-trip com a chave ativa (id embutido no token);
  (2) ROTAÇÃO: troca-se a chave ativa mantendo a antiga aposentada — o dado velho ainda
      decifra (via id) e o novo passa a usar a chave nova;
  (3) id de chave desconhecido → falha explícita (KeyMissing), não silêncio;
  (4) o KmsKeyProvider é um drop-in: injeta-se um provedor alternativo e a cifra/decifra
      passam por ele (é o seam onde o KMS/Vault encaixa);
  (5) compatibilidade retroativa: token no formato legado (sem byte de versão) ainda decifra;
  (6) sem chave configurada → KeyMissing.
"""
from __future__ import annotations
import base64
import os
import uuid

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core import pii_crypto, keyring
from app.core.keyring import KeyMissing, set_key_provider

_AAD = pii_crypto.aad_for(uuid.uuid4(), "email")
_KA = base64.b64encode(b"A" * 32).decode()
_KB = base64.b64encode(b"B" * 32).decode()


def _clear(monkeypatch):
    for v in ("PII_ENC_KEY", "PII_ENC_KEY_ID", "PII_ENC_KEYS"):
        monkeypatch.delenv(v, raising=False)
    set_key_provider(None)


def test_roundtrip_embeds_active_key_id(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    monkeypatch.setenv("PII_ENC_KEY_ID", "k1")
    token = pii_crypto.encrypt("segredo", aad=_AAD)
    assert token[0] == 0x02                                   # byte de versão (envelope, ADR-088)
    kid_len = token[1]
    assert token[2:2 + kid_len].decode() == "k1"             # id da chave viaja no token
    assert pii_crypto.decrypt(token, aad=_AAD) == "segredo"


def test_rotation_old_decrypts_new_encrypts(monkeypatch):
    _clear(monkeypatch)
    # Estado inicial: chave A é a ativa (id k1).
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    monkeypatch.setenv("PII_ENC_KEY_ID", "k1")
    token_old = pii_crypto.encrypt("antigo", aad=_AAD)

    # Rotaciona: B vira ativa (id k2); A fica aposentada (só decifra).
    monkeypatch.setenv("PII_ENC_KEY", _KB)
    monkeypatch.setenv("PII_ENC_KEY_ID", "k2")
    monkeypatch.setenv("PII_ENC_KEYS", f"k1:{_KA}")
    token_new = pii_crypto.encrypt("novo", aad=_AAD)

    assert token_new[2:2 + token_new[1]].decode() == "k2"    # novo usa a chave nova
    assert pii_crypto.decrypt(token_old, aad=_AAD) == "antigo"   # velho ainda decifra
    assert pii_crypto.decrypt(token_new, aad=_AAD) == "novo"


def test_unknown_key_id_fails_explicitly(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    monkeypatch.setenv("PII_ENC_KEY_ID", "k1")
    token = pii_crypto.encrypt("x", aad=_AAD)
    # A chave que cifrou (k1) some do ambiente (nem ativa nem aposentada).
    monkeypatch.setenv("PII_ENC_KEY_ID", "k2")               # ativa agora é k2 (mesma KEK)
    with pytest.raises(KeyMissing):
        pii_crypto.decrypt(token, aad=_AAD)


class _FakeKmsProvider:
    """Simula um KmsKeyProvider: a KEK viria do KMS/Vault e o wrap/unwrap seria uma chamada
    à API do KMS. Aqui embrulha localmente, mas prova que a cifra passa pela porta."""
    def __init__(self):
        self._kek = b"K" * 32
        self.wraps = 0
        self.unwraps = 0
    def active(self):
        return "kms-1", self._kek
    def by_id(self, key_id):
        if key_id != "kms-1":
            raise KeyMissing(key_id)
        return self._kek
    def wrap(self, dek, *, aad):
        self.wraps += 1
        n = os.urandom(12)
        return "kms-1", n + AESGCM(self._kek).encrypt(n, dek, aad)
    def unwrap(self, key_id, blob, *, aad):
        self.unwraps += 1
        if key_id != "kms-1":
            raise KeyMissing(key_id)
        return AESGCM(self._kek).decrypt(blob[:12], blob[12:], aad)


def test_kms_provider_is_a_drop_in_seam(monkeypatch):
    _clear(monkeypatch)
    fake = _FakeKmsProvider()
    set_key_provider(fake)                                   # injeta o adaptador "KMS"
    token = pii_crypto.encrypt("via-kms", aad=_AAD)
    assert token[2:2 + token[1]].decode() == "kms-1"
    assert pii_crypto.decrypt(token, aad=_AAD) == "via-kms"
    # A cifra/decifra passou pelo wrap/unwrap do provedor (é o seam do KMS).
    assert fake.wraps == 1 and fake.unwraps == 1


def test_legacy_format_still_decrypts(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PII_ENC_KEY", _KA)
    # Constrói um token no formato ANTIGO (nonce || ct, sem byte de versão) com a chave ativa.
    # 1º byte do nonce forçado a != 0x01 para não colidir com o byte de versão do formato novo
    # (a desambiguação por conteúdo é inerente; ver ADR-087 — não há dado legado em produção).
    key = base64.b64decode(_KA)
    nonce = b"\x00" + os.urandom(11)
    legacy = nonce + AESGCM(key).encrypt(nonce, b"heranca", _AAD)
    assert pii_crypto.decrypt(legacy, aad=_AAD) == "heranca"


def test_missing_key_raises(monkeypatch):
    _clear(monkeypatch)                                      # sem PII_ENC_KEY
    with pytest.raises(KeyMissing):
        pii_crypto.encrypt("x", aad=_AAD)
