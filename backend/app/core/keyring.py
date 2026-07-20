"""
core/keyring.py — Custódia e resolução de chaves de cifra de PII (porta `KeyProvider`).

Abstrai **de onde vem** a chave que cifra a PII (`pii_crypto`), separando custódia de uso.
Mesmo padrão das outras portas do projeto (`EmailSender`, `AudioStorage`, `WearableSink`):

  - `EnvKeyProvider` (**padrão**): a chave (KEK) vem do ambiente/secret (`PII_ENC_KEY`),
    custódia atual do piloto. Lê o ambiente **a cada chamada** — permite rotação sem
    reiniciar o processo.
  - Um `KmsKeyProvider` (futuro) implementa a MESMA porta buscando/desembrulhando a chave
    num **KMS/Vault** (a KEK nunca sai do HSM; a app pede wrap/unwrap ou busca a chave no
    boot). Encaixa aqui **sem tocar no `pii_crypto`** — é a "custódia evolui para KMS"
    prometida no ADR‑059, agora com seam real.

**Rotação:** cada ciphertext carrega o **id da chave** que o cifrou (ver `pii_crypto`). A chave
ativa (`PII_ENC_KEY` + `PII_ENC_KEY_ID`) cifra o novo; chaves **aposentadas** (`PII_ENC_KEYS`,
`id:base64,...`) seguem disponíveis só para **decifrar** o que já existe. Assim dá para trocar a
chave sem re‑cifrar tudo de uma vez. Nada aqui é logado; chave ausente/ inválida falha explícito."""
from __future__ import annotations
import base64
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_KEY_ID = "env1"
_ACTIVE_ENV = "PII_ENC_KEY"
_ACTIVE_ID_ENV = "PII_ENC_KEY_ID"
_RETIRED_ENV = "PII_ENC_KEYS"      # "id:base64,id:base64" — aposentadas (decrypt-only na rotação)


class KeyMissing(RuntimeError):
    """Chave ausente/ inválida/ desconhecida — falha explícita, sem fallback inseguro."""


def _decode(raw: str, label: str) -> bytes:
    try:
        key = base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise KeyMissing(f"{label} não é base64 válido.") from e
    if len(key) != 32:
        raise KeyMissing(f"{label} deve ter 32 bytes (AES-256).")
    return key


class KeyProvider(Protocol):
    def active(self) -> tuple[str, bytes]: ...   # (key_id, KEK de 32 bytes) — v1/legado
    def by_id(self, key_id: str) -> bytes: ...    # resolve a KEK p/ decifrar v1/legado
    # Envelope (ADR-088): a KEK **embrulha/desembrulha** a DEK; o blob é OPACO ao chamador.
    # Num KMS real é aqui que a app chama wrap/unwrap — a KEK nunca sai do HSM.
    def wrap(self, dek: bytes, *, aad: bytes) -> tuple[str, bytes]: ...     # -> (key_id, blob)
    def unwrap(self, key_id: str, blob: bytes, *, aad: bytes) -> bytes: ...  # -> dek


class EnvKeyProvider:
    """Chaves via ambiente/secret. Lê o ambiente a cada chamada (rotação sem reiniciar).

    O envelope é feito **localmente** (AES-GCM com a KEK do ambiente). Um KmsKeyProvider
    faria o mesmo chamando o KMS — a KEK nunca exposta à aplicação."""

    def active(self) -> tuple[str, bytes]:
        raw = os.getenv(_ACTIVE_ENV)
        if not raw:
            raise KeyMissing(f"{_ACTIVE_ENV} não configurada (base64 de 32 bytes).")
        kid = (os.getenv(_ACTIVE_ID_ENV) or DEFAULT_KEY_ID).strip() or DEFAULT_KEY_ID
        return kid, _decode(raw, _ACTIVE_ENV)

    def by_id(self, key_id: str) -> bytes:
        active_id, active_key = self.active()
        if key_id == active_id:
            return active_key
        for pair in (os.getenv(_RETIRED_ENV) or "").split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            kid, b64 = pair.split(":", 1)
            if kid.strip() == key_id:
                return _decode(b64.strip(), f"{_RETIRED_ENV}[{key_id}]")
        raise KeyMissing(
            f"chave de id '{key_id}' indisponível (rotação: verifique {_RETIRED_ENV}).")

    def wrap(self, dek: bytes, *, aad: bytes) -> tuple[str, bytes]:
        """Embrulha a DEK com a KEK ativa. Blob = ``nonce(12) || dek_cifrada+tag`` (opaco)."""
        key_id, kek = self.active()
        nonce = os.urandom(12)
        return key_id, nonce + AESGCM(kek).encrypt(nonce, dek, aad)

    def unwrap(self, key_id: str, blob: bytes, *, aad: bytes) -> bytes:
        """Desembrulha a DEK com a KEK de ``key_id`` (rotação: pode ser uma aposentada)."""
        kek = self.by_id(key_id)
        nonce, wrapped = blob[:12], blob[12:]
        return AESGCM(kek).decrypt(nonce, wrapped, aad)


_provider: KeyProvider | None = None


def get_key_provider() -> KeyProvider:
    global _provider
    if _provider is None:
        _provider = EnvKeyProvider()
    return _provider


def set_key_provider(provider: KeyProvider | None) -> None:
    """Injeta um provedor (teste / adaptador KMS) ou força reconstrução (None)."""
    global _provider
    _provider = provider
