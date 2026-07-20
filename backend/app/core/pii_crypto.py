"""
core/pii_crypto.py — Cifra de campo para PII em repouso (AES-256-GCM, AEAD, ENVELOPE).

A PII (nome/e-mail) é cifrada **na aplicação** antes de tocar o banco e fica separada do
dado de pesquisa (LGPD; decisão inegociável).

**Envelope (ADR-088):** cada valor é cifrado com uma **DEK aleatória** (chave de dados, por
registro); a DEK é **embrulhada** pela **KEK** (chave-mestra) via a porta de custódia
(`core/keyring.py`). Num KMS real a KEK nunca sai do HSM: a app só pede wrap/unwrap. A KEK
nunca cifra a PII diretamente — só embrulha DEKs. Rotacionar a KEK re-embrulha DEKs, sem
re-cifrar a PII.

Formatos de token (bytes crus, coluna binária; auto-descritivos pelo 1º byte):
  - ``0x02`` (envelope, atual):
      ``0x02 || len(kid) || kid || len(blob)(2) || wrap_blob || nonce(12) || ct``
  - ``0x01`` (v1, ADR-087): KEK cifrando direto — ainda **decifrado** (compat).
  - sem byte de versão: formato legado ``nonce(12) || ct`` — ainda decifrado com a chave ativa.
O ``wrap_blob`` é OPACO (o keyring o produz/consome). Um **AAD** liga tanto a DEK embrulhada
quanto o ct ao participante e ao campo, impedindo mover/renomear valores. Nada aqui é logado.
"""
from __future__ import annotations
import base64
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core import keyring
from app.core.keyring import KeyMissing as PiiKeyMissing   # nome mantido p/ compatibilidade

_NONCE_LEN = 12
_V_DIRECT = 0x01                   # v1 (ADR-087): KEK cifra a PII direto — decrypt-only
_V_ENVELOPE = 0x02                 # v2 (ADR-088): DEK por registro embrulhada pela KEK
_DEK_LEN = 32


def aad_for(participant_id: uuid.UUID, field: str) -> bytes:
    """Dado associado (AAD): liga o ciphertext ao participante e ao campo."""
    return f"contact_info|{participant_id}|{field}".encode("utf-8")


def encrypt(plaintext: str, *, aad: bytes) -> bytes:
    """Cifra ``plaintext`` por ENVELOPE: DEK aleatória cifra a PII; a KEK embrulha a DEK."""
    provider = keyring.get_key_provider()
    dek = os.urandom(_DEK_LEN)
    key_id, blob = provider.wrap(dek, aad=aad)      # a KEK embrulha a DEK (opaco)
    kid_b = key_id.encode("utf-8")
    if not 1 <= len(kid_b) <= 255:
        raise PiiKeyMissing("id de chave inválido (1..255 bytes).")
    if len(blob) > 0xFFFF:
        raise PiiKeyMissing("wrap blob grande demais (>64KiB).")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return (bytes([_V_ENVELOPE, len(kid_b)]) + kid_b
            + len(blob).to_bytes(2, "big") + blob + nonce + ct)


def decrypt(token: bytes, *, aad: bytes) -> str:
    """Decifra o token; levanta ``InvalidTag`` se a chave/AAD não conferirem.

    Despacha pelo 1º byte: envelope (v2), v1 (KEK direto, compat) ou legado (sem versão)."""
    if token and token[0] == _V_ENVELOPE:
        i = 1
        kid_len = token[i]; i += 1
        key_id = token[i:i + kid_len].decode("utf-8"); i += kid_len
        blob_len = int.from_bytes(token[i:i + 2], "big"); i += 2
        blob = token[i:i + blob_len]; i += blob_len
        nonce, ct = token[i:i + _NONCE_LEN], token[i + _NONCE_LEN:]
        dek = keyring.get_key_provider().unwrap(key_id, blob, aad=aad)
        return AESGCM(dek).decrypt(nonce, ct, aad).decode("utf-8")
    if token and token[0] == _V_DIRECT:
        # v1 (ADR-087): a KEK cifrou a PII direto.
        kid_len = token[1]
        key_id = token[2:2 + kid_len].decode("utf-8")
        rest = token[2 + kid_len:]
        nonce, ct = rest[:_NONCE_LEN], rest[_NONCE_LEN:]
        kek = keyring.get_key_provider().by_id(key_id)
        return AESGCM(kek).decrypt(nonce, ct, aad).decode("utf-8")
    # Legado (pré-versionamento): nonce || ct, decifrado com a chave ativa.
    _kid, kek = keyring.get_key_provider().active()
    nonce, ct = token[:_NONCE_LEN], token[_NONCE_LEN:]
    return AESGCM(kek).decrypt(nonce, ct, aad).decode("utf-8")


def generate_key_b64() -> str:
    """Utilitário de ops (dev): gera uma chave base64 nova. NÃO versionar a saída."""
    return base64.b64encode(os.urandom(32)).decode("ascii")
