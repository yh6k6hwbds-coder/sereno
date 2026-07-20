"""
core/pii_crypto.py — Cifra de campo para PII em repouso (AES-256-GCM, AEAD).

A PII (nome/e-mail) é cifrada **na aplicação** antes de tocar o banco e fica separada do
dado de pesquisa (LGPD; decisão inegociável). A chave (KEK) vem da porta de custódia
(`core/keyring.py`) — ambiente/secret hoje, KMS/Vault amanhã, sem mudar este módulo.

Formato do token (bytes crus, coluna binária):
  ``0x01 || len(key_id) || key_id || nonce(12) || ciphertext+tag``
O **id da chave** viaja no token → dá para **rotacionar** a chave (a antiga segue decifrando o
que já existe; a nova cifra o resto). Tokens do formato antigo (``nonce(12) || ct``, sem o
byte de versão) ainda são decifrados com a chave ativa (compatibilidade retroativa).
Um **AAD** liga cada ciphertext ao participante e ao campo (``name``/``email``), impedindo
mover/renomear um valor entre linhas ou campos. Nada aqui é logado.
"""
from __future__ import annotations
import base64
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core import keyring
from app.core.keyring import KeyMissing as PiiKeyMissing   # nome mantido p/ compatibilidade

_NONCE_LEN = 12
_MAGIC = 0x01                      # byte de versão do formato com id de chave


def aad_for(participant_id: uuid.UUID, field: str) -> bytes:
    """Dado associado (AAD): liga o ciphertext ao participante e ao campo."""
    return f"contact_info|{participant_id}|{field}".encode("utf-8")


def encrypt(plaintext: str, *, aad: bytes) -> bytes:
    """Cifra ``plaintext`` (AES-256-GCM) com a chave ATIVA, embutindo o id dela no token."""
    key_id, key = keyring.get_key_provider().active()
    kid_b = key_id.encode("utf-8")
    if not 1 <= len(kid_b) <= 255:
        raise PiiKeyMissing("id de chave inválido (1..255 bytes).")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return bytes([_MAGIC, len(kid_b)]) + kid_b + nonce + ct


def decrypt(token: bytes, *, aad: bytes) -> str:
    """Decifra o token; levanta ``InvalidTag`` se a chave/AAD não conferirem.

    Resolve a chave pelo **id** embutido (rotação). Tokens antigos (sem o byte de versão)
    caem no formato legado e usam a chave ativa."""
    if token and token[0] == _MAGIC:
        kid_len = token[1]
        key_id = token[2:2 + kid_len].decode("utf-8")
        rest = token[2 + kid_len:]
        nonce, ct = rest[:_NONCE_LEN], rest[_NONCE_LEN:]
        key = keyring.get_key_provider().by_id(key_id)
        return AESGCM(key).decrypt(nonce, ct, aad).decode("utf-8")
    # Legado (pré-versionamento): nonce || ct, decifrado com a chave ativa.
    _kid, key = keyring.get_key_provider().active()
    nonce, ct = token[:_NONCE_LEN], token[_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, aad).decode("utf-8")


def generate_key_b64() -> str:
    """Utilitário de ops (dev): gera uma chave base64 nova. NÃO versionar a saída."""
    return base64.b64encode(os.urandom(32)).decode("ascii")
