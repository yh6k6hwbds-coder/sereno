"""
modules/allocation/randomization.py — Randomização em blocos permutados (lógica pura).

Determinística a partir de uma SEMENTE (segredo custodiado, fora do dado operacional):
a mesma semente recria a mesma sequência — reprodutibilidade auditável, essencial para
o CEP e para a análise. Não faz I/O e não conhece qual braço é ativo/sham — só distribui A/B.

**Tamanho de bloco VARIÁVEL (G7).** O protocolo especifica blocos permutados de 4 e 6. Com
bloco de tamanho fixo e conhecido, quem acompanha as alocações anteriores deduz a última
posição de cada bloco: num bloco de 4 em que já saíram A, B, A, a próxima é necessariamente
B. Isso é previsão de alocação — não quebra o cegamento do participante, mas quebra a
*ocultação* de quem inscreve, que é justamente o que a randomização em blocos deveria
proteger. Sorteando o tamanho de cada bloco na mesma sequência determinística, a fronteira
do bloco deixa de ser conhecida e a dedução deixa de funcionar, sem perder reprodutibilidade:
o sorteio do tamanho sai da mesma semente.
"""
from __future__ import annotations
import hashlib
import random
from typing import Iterable, Iterator


def _rng(seed: str) -> random.Random:
    # random.Random com semente string é determinístico entre plataformas (Python 3.2+).
    return random.Random(seed)


def normalize_block_sizes(block_sizes: Iterable[int] | int) -> tuple[int, ...]:
    """Valida e ordena os tamanhos de bloco permitidos. Aceita um int (bloco fixo)."""
    if isinstance(block_sizes, int):
        block_sizes = (block_sizes,)
    sizes = tuple(sorted({int(b) for b in block_sizes}))
    if not sizes:
        raise ValueError("block_sizes não pode ser vazio.")
    if any(b <= 0 or b % 2 != 0 for b in sizes):
        raise ValueError("Cada tamanho de bloco deve ser um inteiro par positivo.")
    return sizes


def _blocks(seed: str, sizes: tuple[int, ...]) -> Iterator[list[str]]:
    """Blocos sucessivos: tamanho sorteado entre ``sizes``, conteúdo permutado 1:1."""
    rng = _rng(seed)
    while True:
        # Com um único tamanho permitido, NÃO consome sorteio: uma sequência gerada antes
        # do G7 (bloco fixo) continua idêntica sob a mesma semente. Importa porque a semente
        # é custodiada e o hash dela é conferido no data lock.
        size = sizes[0] if len(sizes) == 1 else sizes[rng.randrange(len(sizes))]
        block = ["A"] * (size // 2) + ["B"] * (size // 2)
        rng.shuffle(block)
        yield block


def generate_sequence(n: int, block_sizes: Iterable[int] | int, seed: str) -> list[str]:
    """Sequência de 'A'/'B' balanceada dentro de cada bloco, reprodutível pela semente."""
    sizes = normalize_block_sizes(block_sizes)
    if n < 0:
        raise ValueError("n não pode ser negativo.")
    seq: list[str] = []
    for block in _blocks(seed, sizes):
        if len(seq) >= n:
            break
        seq.extend(block)
    return seq[:n]


def assign(index: int, block_sizes: Iterable[int] | int, seed: str) -> tuple[str, int]:
    """Braço (A/B) e número do bloco (1-based) do i-ésimo participante (0-based).

    Devolve os dois juntos porque, com bloco variável, o número do bloco deixou de ser
    aritmética (``index // block_size``) e passou a exigir percorrer a mesma sequência —
    calculá-los em duas passagens seria gerar a sequência duas vezes."""
    if index < 0:
        raise ValueError("index não pode ser negativo.")
    sizes = normalize_block_sizes(block_sizes)
    consumidos = 0
    for numero, block in enumerate(_blocks(seed, sizes), start=1):
        if index < consumidos + len(block):
            return block[index - consumidos], numero
        consumidos += len(block)
    raise AssertionError("inalcançável: _blocks é infinito")   # pragma: no cover


def arm_for_index(index: int, block_sizes: Iterable[int] | int, seed: str) -> str:
    """Braço (A/B) para o i-ésimo participante (0-based) na sequência determinística."""
    return assign(index, block_sizes, seed)[0]


def block_of(index: int, block_sizes: Iterable[int] | int, seed: str) -> int:
    """Número do bloco (1-based) do i-ésimo participante."""
    return assign(index, block_sizes, seed)[1]


def seed_ref(seed: str) -> str:
    """Referência não reversível da semente (para auditar QUAL semente foi usada,
    sem armazenar a própria semente). No data lock, hash da semente custodiada deve bater."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
