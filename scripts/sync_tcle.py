"""
scripts/sync_tcle.py — Gera o TCLE exibido no app a partir do rascunho em docs/.

**Fonte única de verdade:** `docs/tcle-rascunho.md` — é o arquivo que vai ao CEP. O app
NÃO tem uma segunda redação do termo: o asset `app/assets/tcle/tcle-pt.txt` é **derivado**
daqui. Sem isso, o texto submetido ao comitê e o texto que o participante lê na tela
divergiriam com o tempo, e ninguém notaria até alguém comparar os dois à mão.

Extrai apenas o bloco entre os marcadores `INÍCIO/FIM DO TEXTO DIRIGIDO AO PARTICIPANTE`
(o cabeçalho de status e as notas para a equipe **não** vão para o app) e converte o
Markdown num formato de uma linha por bloco, com prefixo — mínimo de parser no cliente:

    H|<título de seção>       cabeçalho (## / ###)
    P|<parágrafo>             texto corrido
    B|<item>                  item de lista (- ou 1.)
    !|<destaque>              bloco de citação (>) — os avisos críticos do termo
    -|                        separador visual

Parágrafos quebrados em várias linhas no Markdown são **reunidos** numa linha só: a quebra
do .md é de largura de editor, não do texto — mantê-la produziria quebras erradas na tela
estreita do celular. Ênfase (`**`), código (`` ` ``) e links são removidos: a tela usa o
estilo do tema, não Markdown, e assim o app não ganha dependência de renderizador.

Uso:
    python scripts/sync_tcle.py            # regenera o asset
    python scripts/sync_tcle.py --check    # falha (exit 1) se estiver fora de sincronia
"""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "tcle-rascunho.md"
ASSET = ROOT / "app" / "assets" / "tcle" / "tcle-pt.txt"

BEGIN = "INÍCIO DO TEXTO DIRIGIDO AO PARTICIPANTE"
END = "FIM DO TEXTO DIRIGIDO AO PARTICIPANTE"

HEADER = (
    "# GERADO por scripts/sync_tcle.py a partir de docs/tcle-rascunho.md — NÃO EDITE À MÃO.\n"
    "# Para mudar o texto, edite o .md (que vai ao CEP) e rode o script.\n"
)


def participant_section(md: str) -> str:
    """Bloco dirigido ao participante, entre os marcadores. Falha se sumirem."""
    try:
        start = md.index(BEGIN)
        end = md.index(END)
    except ValueError as e:
        raise SystemExit(
            f"marcadores não encontrados em {DOC.name}: o texto do participante precisa estar "
            f"entre '{BEGIN}' e '{END}'.") from e
    # Corta na QUEBRA anterior ao marcador de fim: `end` aponta para o texto DENTRO do
    # comentário HTML, então fatiar ali deixaria o "<!-- ====" da última linha no asset.
    body = md[start:md.rindex("\n", 0, end)]
    return body[body.index("\n") + 1:]          # descarta o resto da linha do marcador inicial


def strip_inline(text: str) -> str:
    """Remove ênfase/código/links do Markdown, preservando o conteúdo."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)   # links -> só o rótulo
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def to_blocks(section: str) -> list[str]:
    """Markdown -> linhas com prefixo (ver docstring do módulo)."""
    out: list[str] = []
    para: list[str] = []          # linhas do bloco em construção (a reunir num parágrafo)
    kind = "P"                    # prefixo do bloco em construção

    def flush() -> None:
        nonlocal kind
        if para:
            out.append(f"{kind}|{strip_inline(' '.join(para))}")
            para.clear()
        kind = "P"

    in_table = False
    for raw in section.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:                                   # linha em branco fecha o bloco
            flush()
            in_table = False
            continue

        if stripped.startswith("#"):                       # cabeçalho
            flush()
            out.append("H|" + strip_inline(stripped.lstrip("#").strip()))
            continue

        if stripped.startswith("|"):                       # tabela -> um item por linha
            flush()
            cells = [strip_inline(c) for c in stripped.strip("|").split("|")]
            if all(set(c) <= {"-", ":", ""} for c in cells):
                continue                                   # linha separadora do cabeçalho
            if not in_table:                               # cabeçalho da tabela: descartado
                in_table = True                            # (os rótulos viram o "A — B")
                continue
            out.append("B|" + " — ".join(c for c in cells if c))
            continue

        if stripped.startswith(">"):                       # citação = destaque do termo
            content = stripped.lstrip(">").strip()
            if not content:                                # "> " sozinho separa parágrafos
                flush()
                continue
            if kind != "!":                                # entrou na citação: fecha o anterior
                flush()
                kind = "!"
            item = re.match(r"^([-*]|\d+\.)\s+(.*)$", content)
            if item:                                       # lista DENTRO da citação
                flush()
                kind = "!"
                para.append(item.group(2))
                flush()
                kind = "!"                                 # segue na citação
                continue
            para.append(content)
            continue

        if kind == "!":                                    # saiu da citação
            flush()

        m = re.match(r"^([-*]|\d+\.)\s+(.*)$", stripped)   # item de lista
        if m:
            flush()
            kind = "B"
            para.append(m.group(2))
            flush()
            continue

        if line.startswith(("  ", "\t")) and out and out[-1].startswith(("B|", "!|")):
            out[-1] += " " + strip_inline(stripped)        # continuação recuada do item
            continue

        para.append(stripped)                              # texto corrido

    flush()
    return out


def render() -> str:
    blocks = to_blocks(participant_section(DOC.read_text(encoding="utf-8")))
    return HEADER + "\n".join(blocks) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Sincroniza o TCLE do app com o rascunho em docs/.")
    ap.add_argument("--check", action="store_true",
                    help="Não escreve; falha se o asset estiver desatualizado.")
    args = ap.parse_args()

    expected = render()
    current = ASSET.read_text(encoding="utf-8") if ASSET.exists() else None

    if args.check:
        if current == expected:
            print(f"TCLE em sincronia ({ASSET.relative_to(ROOT)}).")
            return 0
        print("TCLE FORA DE SINCRONIA: o texto do app não corresponde a docs/tcle-rascunho.md.\n"
              "Rode: python scripts/sync_tcle.py", file=sys.stderr)
        return 1

    ASSET.parent.mkdir(parents=True, exist_ok=True)
    ASSET.write_text(expected, encoding="utf-8")
    n = expected.count("\n") - HEADER.count("\n")
    print(f"{ASSET.relative_to(ROOT)} atualizado ({n} blocos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
