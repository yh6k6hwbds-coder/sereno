"""
scripts/docs_to_pdf.py — Gera os PDFs dos documentos de `docs/` (para NIT, DPO, CEP e orientadora).

**Fonte única:** os PDFs são *derivados* dos `.md` do repositório. Não existe uma segunda redação
em lugar nenhum — é a mesma regra do TCLE exibido no app (`sync_tcle.py`). Se o documento mudar,
regere; se alguém editar o PDF à mão, o próximo `docs_to_pdf.py` desfaz — e é isso que se quer.

**Motor:** não há pandoc/LaTeX na máquina do mantenedor, então a impressão usa o **navegador**
(Edge ou Chrome em modo headless). É o mesmo motor do app web, e o CSS de impressão fica aqui.

Cada documento tem uma **tarja de status própria** dizendo o que falta *naquele* documento — um
aviso genérico repetido em seis arquivos vira ruído e ninguém lê. Nenhum destes documentos está
aprovado: as tarjas existem para que ninguém os leia como se estivessem.

Uso:
    python scripts/docs_to_pdf.py                      # gera todos
    python scripts/docs_to_pdf.py tcle ripd            # só os indicados
    python scripts/docs_to_pdf.py --list               # lista as chaves
    python scripts/docs_to_pdf.py --html-only          # só o HTML (não precisa de navegador)
    python scripts/docs_to_pdf.py --out-dir "C:/..."   # destino (padrão: ../ do repo)
"""
from __future__ import annotations
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

try:
    import markdown
except ImportError:                                     # noqa: BLE001
    sys.exit("Falta a dependência: pip install markdown")

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATE = time.strftime("%Y-%m-%d")

# Onde procurar o navegador. Edge vem com o Windows; Chrome/Chromium cobrem Linux/macOS.
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google-chrome", "chromium", "chromium-browser", "msedge",
]

# chave -> (arquivo em docs/, nome de saída, título da tarja, texto da tarja, identificação)
DOCUMENTOS: dict[str, tuple[str, str, str, str, str]] = {
    "pendencias": (
        "comunicacao-pendencias-orientadora.md",
        "Sereno_Pendencias",
        "DOCUMENTO DE TRABALHO — SITUAÇÃO EM {date}",
        "Resumo do que falta para o piloto começar, organizado por quem precisa decidir. "
        "Os documentos citados são <strong>rascunhos técnicos</strong>; nenhum foi aprovado.",
        "Sereno · Pendências para o início do piloto · {date}",
    ),
    "tcle": (
        "tcle-rascunho.md",
        "Sereno_TCLE_rascunho",
        "RASCUNHO — NÃO APROVADO PELO COMITÊ DE ÉTICA",
        "Este documento é uma <strong>versão preliminar</strong> do Termo de Consentimento Livre e "
        "Esclarecido, preparada para revisão da orientadora, da assessoria e do CEP. "
        "<strong>Não deve ser apresentado a nenhum participante</strong> antes da aprovação. "
        "Trechos entre colchetes ainda precisam ser preenchidos ou confirmados.",
        "Sereno · Termo de Consentimento, versão 0.1.0-rascunho · não aprovado pelo CEP · {date}",
    ),
    "ripd": (
        "relatorio-impacto-protecao-dados.md",
        "Sereno_RIPD_rascunho",
        "RASCUNHO TÉCNICO — INSUMO PARA O RIPD FORMAL",
        "Este é um <strong>relatório preliminar</strong> de avaliação de riscos, preparado pelo "
        "responsável técnico a partir do que o sistema efetivamente faz. O RIPD formal é elaborado "
        "<strong>sob responsabilidade do controlador (UNINTA) e do Encarregado (DPO)</strong>. Não é "
        "parecer jurídico: a decisão sobre risco residual aceitável e sobre eventual consulta prévia "
        "à ANPD não cabe a este documento.",
        "Sereno · Relatório de Impacto à Proteção de Dados (RIPD) — rascunho técnico · {date}",
    ),
    "ropa": (
        "registro-operacoes-tratamento.md",
        "Sereno_ROPA_rascunho",
        "RASCUNHO TÉCNICO — INSUMO PARA O REGISTRO FORMAL",
        "Inventário das operações de tratamento na estrutura do <strong>Art. 37 da LGPD</strong>, "
        "levantado a partir do que o sistema efetivamente faz. O registro formal deve ser "
        "<strong>mantido e atualizado pelo controlador (UNINTA)</strong>. A base legal de cada "
        "operação está marcada como <strong>[a confirmar]</strong> — é decisão do NIT/assessoria, "
        "não deste documento.",
        "Sereno · Registro das Operações de Tratamento (ROPA) — rascunho técnico · {date}",
    ),
    "retencao": (
        "politica-retencao-descarte.md",
        "Sereno_Retencao_rascunho",
        "RASCUNHO TÉCNICO — PRAZOS AINDA NÃO APROVADOS",
        "Política de retenção e descarte ancorada nos mecanismos já implementados. <strong>Os prazos "
        "são propostas</strong>, não determinações: a aprovação é do <strong>CEP e da assessoria "
        "jurídica</strong>. Enquanto não forem aprovados, o expurgo do conjunto de dados de pesquisa "
        "não pode ser programado.",
        "Sereno · Política de Retenção e Descarte — rascunho técnico · {date}",
    ),
    "incidentes": (
        "plano-resposta-incidentes.md",
        "Sereno_Incidentes_rascunho",
        "RASCUNHO TÉCNICO — AGUARDA APROVAÇÃO E CONTATOS",
        "Plano de resposta a incidentes de segurança, incluindo a notificação à <strong>ANPD "
        "(Art. 48)</strong>. Faltam os <strong>contatos e o responsável de plantão</strong>, e a "
        "confirmação dos prazos com a assessoria — um plano sem quem acionar não funciona no dia do "
        "incidente. Requer aprovação institucional.",
        "Sereno · Plano de Resposta a Incidentes — rascunho técnico · {date}",
    ),
}

CSS = """
@page { size: A4; margin: 16mm 15mm 15mm 15mm; }
* { box-sizing: border-box; }
body { font-family: Georgia,"Times New Roman",serif; font-size:10.5pt; line-height:1.5;
       color:#1a2632; margin:0; }

.band { border:2px solid #e4772e; background:#fdf4ec; padding:3mm 4mm; margin:0 0 6mm; }
.band .t { font-family:Arial,sans-serif; font-weight:bold; font-size:10pt; color:#b35a12;
           letter-spacing:.06em; margin-bottom:1.5mm; }
.band p { margin:0; font-size:9.5pt; text-align:left; }

.ident { font-family:Arial,sans-serif; font-size:8pt; color:#8a97a1; text-align:right;
         border-top:1px solid #dfe6ea; padding-top:1.5mm; margin-top:8mm; }

h1 { font-size:16pt; margin:0 0 3mm; line-height:1.25; }
h2 { font-size:12.5pt; margin:7mm 0 2.5mm; padding-bottom:1.5mm; border-bottom:1.5px solid #128394;
     color:#0f5c68; page-break-after:avoid; }
h3 { font-size:11pt; margin:5mm 0 2mm; color:#1b4b5a; page-break-after:avoid; }
p { margin:0 0 2.5mm; text-align:justify; }
ul,ol { margin:0 0 2.5mm; padding-left:6mm; }
li { margin-bottom:1.2mm; }
strong { color:#101a2b; }

/* Citação = destaque do documento. Com "⚠️" na 1ª linha, vira alerta (laranja). */
blockquote { margin:0 0 4mm; padding:2.5mm 4mm; background:#f2f6f8;
             border-left:3px solid #128394; border-top:1px solid #dfe6ea;
             border-right:1px solid #dfe6ea; border-bottom:1px solid #dfe6ea;
             page-break-inside:avoid; }
blockquote p { margin:0 0 1.5mm; text-align:left; }
blockquote p:last-child { margin-bottom:0; }
blockquote.alerta { background:#fdf4ec; border-color:#e0a878; border-left-color:#e4772e; }

/* Largura automática: com 'fixed', a coluna de texto longo fica tão estreita quanto a de
   uma palavra ("Prob.") e a tabela de riscos vira ilegível. */
table { width:100%; border-collapse:collapse; margin:0 0 4mm; font-size:9pt; }
th,td { border:1px solid #cfdbe2; padding:1.8mm 2mm; text-align:left; vertical-align:top;
        word-wrap:break-word; overflow-wrap:break-word; }
th { background:#eef3f5; font-family:Arial,sans-serif; font-size:8.5pt; }
tr { page-break-inside:avoid; }

code { font-family:"Consolas","Courier New",monospace; font-size:8.5pt;
       background:#eef2f4; padding:0 1mm; border-radius:2px; color:#33454f; }
pre { background:#f2f6f8; border:1px solid #dfe6ea; border-left:3px solid #128394;
      padding:3mm; margin:0 0 4mm; font-size:8pt; line-height:1.35;
      white-space:pre-wrap; page-break-inside:avoid; }
pre code { background:none; padding:0; font-size:8pt; }
hr { border:0; border-top:1px solid #cfdbe2; margin:6mm 0; }
"""


def find_browser() -> str | None:
    for cand in BROWSERS:
        if os.path.sep in cand or ":" in cand:
            if pathlib.Path(cand).exists():
                return cand
        elif shutil.which(cand):
            return shutil.which(cand)
    return None


def to_html(src: pathlib.Path, band_t: str, band_p: str, ident: str) -> str:
    md = src.read_text(encoding="utf-8")

    # Marcadores do bloco do participante (só no TCLE) viram régua visível — o revisor precisa
    # enxergar onde começa e termina o texto que o participante lê.
    md = re.sub(r"<!--\s*=+\s*INÍCIO DO TEXTO DIRIGIDO AO PARTICIPANTE\s*=+\s*-->",
                "\n---\n\n**↓ A partir daqui é o texto que o participante lê ↓**\n", md)
    md = re.sub(r"<!--\s*=+\s*FIM DO TEXTO DIRIGIDO AO PARTICIPANTE\s*=+\s*-->",
                "\n**↑ Fim do texto dirigido ao participante ↑**\n\n---\n", md)

    body = markdown.markdown(md, extensions=["tables", "sane_lists", "fenced_code"])
    # Citação que começa com ⚠️ é alerta: pinta de laranja (o marcador em si sai do texto).
    body = re.sub(r"<blockquote>\s*<p>⚠️\s*", '<blockquote class="alerta"><p>', body)

    band = f'<div class="band"><div class="t">{band_t}</div><p>{band_p}</p></div>'
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<title>{src.stem}</title><style>{CSS}</style></head><body>'
            f'{band}{body}<div class="ident">{ident}</div></body></html>')


def to_pdf(browser: str, html: pathlib.Path, pdf: pathlib.Path, timeout_s: int = 60) -> bool:
    """Imprime via navegador headless. Ele RETORNA ANTES de terminar de escrever o arquivo —
    daí a espera ativa (esperar um tempo fixo curto dá 'arquivo não existe' em documento grande)."""
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", html.as_uri()],
            capture_output=True, timeout=timeout_s, check=False)
        deadline = time.time() + timeout_s
        size = -1
        while time.time() < deadline:
            if pdf.exists():
                cur = pdf.stat().st_size
                if cur > 0 and cur == size:          # tamanho estável = escrita concluída
                    return True
                size = cur
            time.sleep(0.5)
    return pdf.exists()


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera os PDFs dos documentos de docs/.")
    ap.add_argument("docs", nargs="*", help="chaves a gerar (padrão: todas)")
    ap.add_argument("--list", action="store_true", help="lista as chaves disponíveis")
    ap.add_argument("--html-only", action="store_true", help="não imprime; só gera o HTML")
    ap.add_argument("--out-dir", default=str(ROOT.parent),
                    help="destino dos arquivos (padrão: pasta acima do repositório)")
    args = ap.parse_args()

    if args.list:
        for k, (src, out, *_ ) in DOCUMENTOS.items():
            print(f"  {k:12} {src:45} -> {out}_{DATE}.pdf")
        return 0

    chaves = args.docs or list(DOCUMENTOS)
    if desconhecidas := [k for k in chaves if k not in DOCUMENTOS]:
        sys.exit(f"chave(s) desconhecida(s): {', '.join(desconhecidas)} "
                 f"(use --list para ver as válidas)")

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    browser = None if args.html_only else find_browser()
    if browser is None and not args.html_only:
        sys.exit("Navegador não encontrado (Edge/Chrome). Use --html-only e imprima manualmente.")

    falhas = 0
    for k in chaves:
        src_name, out_name, band_t, band_p, ident = DOCUMENTOS[k]
        src = DOCS / src_name
        if not src.exists():
            print(f"  [ERRO] {k}: {src_name} não encontrado")
            falhas += 1
            continue

        html_text = to_html(src, band_t.format(date=DATE), band_p, ident.format(date=DATE))
        if args.html_only:
            dest = out_dir / f"{out_name}_{DATE}.html"
            dest.write_text(html_text, encoding="utf-8")
            print(f"  [ok] {k:12} -> {dest.name}")
            continue

        with tempfile.TemporaryDirectory() as tmp:
            html = pathlib.Path(tmp) / f"{k}.html"
            html.write_text(html_text, encoding="utf-8")
            pdf = pathlib.Path(tmp) / f"{k}.pdf"
            if to_pdf(browser, html, pdf):
                dest = out_dir / f"{out_name}_{DATE}.pdf"
                shutil.copy(pdf, dest)
                print(f"  [ok] {k:12} -> {dest.name}  ({pdf.stat().st_size // 1024} KB)")
            else:
                print(f"  [ERRO] {k}: o navegador não produziu o PDF")
                falhas += 1

    print(f"\n{len(chaves) - falhas}/{len(chaves)} gerado(s) em {out_dir}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
