"""
core/pii_crypto.py — Cifra de campo para PII em repouso (AES-256-GCM, AEAD).

A PII (nome/e-mail) é cifrada **na aplicação** antes de tocar o banco e fica separada do
dado de pesquisa (LGPD; decisão inegociável). A chave vem do ambiente/cofre
(``PII_ENC_KEY`` = base64 de 32 bytes) e **nunca** é versionada; se ausente/ inválida, a
operação falha explicitamente (jamais cifrar com chave fraca). Em produção a custódia
evolui para envelope/KMS (ver ADR-059).

Formato do token: ``nonce(12) || ciphertext+tag`` (bytes crus, guardados em coluna binária).
Um **AAD** liga cada ciphertext ao participante e ao campo (``name``/``email``), impedindo
mover/renomear um valor entre linhas ou campos.
"""
from __future__ import annotations
import base64
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12
_KEY_ENV = "PII_ENC_KEY"


class PiiKeyMissing(RuntimeError):
    """``PII_ENC_KEY`` ausente ou inválida — falha explícita, sem fallback inseguro."""


def _key() -> bytes:
    raw = os.getenv(_KEY_ENV)
    if not raw:
        raise PiiKeyMissing(f"{_KEY_ENV} não configurada (base64 de 32 bytes).")
    try:
        key = base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise PiiKeyMissing(f"{_KEY_ENV} não é base64 válido.") from e
    if len(key) != 32:
        raise PiiKeyMissing(f"{_KEY_ENV} deve ter 32 bytes (AES-256).")
    return key


def aad_for(participant_id: uuid.UUID, field: str) -> bytes:
    """Dado associado (AAD): liga o ciphertext ao participante e ao campo."""
    return f"contact_info|{participant_id}|{field}".encode("utf-8")


def encrypt(plaintext: str, *, aad: bytes) -> bytes:
    """Cifra ``plaintext`` (AES-256-GCM) devolvendo ``nonce || ciphertext+tag``."""
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return nonce + ct


def decrypt(token: bytes, *, aad: bytes) -> str:
    """Decifra o token; levanta ``InvalidTag`` se a chave/AAD não conferirem."""
    nonce, ct = token[:_NONCE_LEN], token[_NONCE_LEN:]
    pt = AESGCM(_key()).decrypt(nonce, ct, aad)
    return pt.decode("utf-8")


def generate_key_b64() -> str:
    """Utilitário de ops (dev): gera uma chave base64 nova. NÃO versionar a saída."""
    return base64.b64encode(os.urandom(32)).decode("ascii")
