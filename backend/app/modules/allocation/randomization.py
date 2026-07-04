"""
modules/allocation/randomization.py — Randomização em blocos (lógica pura).

Determinística a partir de uma SEMENTE (segredo custodiado, fora do dado operacional):
a mesma semente recria a mesma sequência — reprodutibilidade auditável, essencial para
o CEP e para a análise. Blocos de tamanho par garantem balanceamento 1:1 ao longo do
recrutamento. Não faz I/O e não conhece qual braço é ativo/sham — só distribui A/B.
"""
from __future__ import annotations
import hashlib
import random


def _rng(seed: str) -> random.Random:
    # random.Random com semente string é determinístico entre plataformas (Python 3.2+).
    return random.Random(seed)


def generate_sequence(n: int, block_size: int, seed: str) -> list[str]:
    """Sequência de 'A'/'B' balanceada dentro de cada bloco, reprodutível pela semente."""
    if block_size <= 0 or block_size % 2 != 0:
        raise ValueError("block_size deve ser um inteiro par positivo.")
    if n < 0:
        raise ValueError("n não pode ser negativo.")
    rng = _rng(seed)
    seq: list[str] = []
    while len(seq) < n:
        block = ["A"] * (block_size // 2) + ["B"] * (block_size // 2)
        rng.shuffle(block)
        seq.extend(block)
    return seq[:n]


def arm_for_index(index: int, block_size: int, seed: str) -> str:
    """Braço (A/B) para o i-ésimo participante (0-based) na sequência determinística."""
    if index < 0:
        raise ValueError("index não pode ser negativo.")
    return generate_sequence(index + 1, block_size, seed)[index]


def block_of(index: int, block_size: int) -> int:
    """Número do bloco (1-based) do i-ésimo participante."""
    return index // block_size + 1


def seed_ref(seed: str) -> str:
    """Referência não reversível da semente (para auditar QUAL semente foi usada,
    sem armazenar a própria semente). No data lock, hash da semente custodiada deve bater."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
