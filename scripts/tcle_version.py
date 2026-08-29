"""
scripts/tcle_version.py — Verifica e troca a versão vigente do TCLE nos lugares que a declaram.

**Por que existe.** A versão do termo é declarada em QUATRO arquivos, em três linguagens, e o
backend recusa (409) qualquer aceite cuja versão divirja da sua. Se `tcleVersion` (Dart) e
`TCLE_CURRENT` (Python) se separarem, **nada no CI reclama**: os testes de backend importam a
constante em vez do literal, e o teste de widget usa a do app. A divergência só aparece em
produção, como um 409 em cima do participante na hora de consentir — depois de ele ter lido o
termo inteiro. `--check` fecha esse furo, e é o que roda no CI (job `contracts`).

**Trocar a versão NÃO é "uma linha em cada arquivo"** — o roadmap dizia isso e estava errado.
Além dos quatro literais, sair de `-rascunho` derruba um teste de widget que guarda de propósito o
estado de rascunho, e há decisões editoriais que um script não deve tomar sozinho. Por isso o modo
de troca **faz o mecânico e imprime o resto** (seção "a fazer à mão"), em vez de fingir que
terminou.

Uso:
    python scripts/tcle_version.py --check          # falha (exit 1) se os sites divergirem
    python scripts/tcle_version.py --show           # imprime a versão vigente e onde ela vive
    python scripts/tcle_version.py 1.0.0            # troca em todos os sites
    python scripts/tcle_version.py 1.0.0 --dry-run  # mostra o diff sem gravar
"""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Cada site: (arquivo, regex com o grupo `v` na versão, para que serve).
# O regex precisa casar UMA vez só — casamento múltiplo ou nenhum é erro, não aviso: significa
# que o arquivo mudou de forma e o script passaria a editar a linha errada em silêncio.
SITES: list[tuple[str, str, str]] = [
    (
        "backend/app/modules/consent/router.py",
        r'^TCLE_CURRENT = "(?P<v>[^"]+)"$',
        "constante do backend — é ela que devolve 409 a aceite com versão divergente",
    ),
    (
        "backend/app/modules/consent/router.py",
        r'tcle_version: str = Field\(\.\.\., examples=\["(?P<v>[^"]+)"\]\)',
        "exemplo do contrato — sai no OpenAPI e na doc da API",
    ),
    (
        "app/lib/core/config.dart",
        r"^const String tcleVersion = '(?P<v>[^']+)';$",
        "constante do app — é a versão que o cliente envia ao consentir",
    ),
    (
        "docs/tcle-rascunho.md",
        r"\*\*Versão deste rascunho:\*\* `(?P<v>[^`]+)`",
        "cabeçalho de status do documento que vai ao CEP",
    ),
]

# O que a troca NÃO faz sozinha. Cada linha é uma decisão ou uma reescrita com julgamento.
A_MAO_AO_SAIR_DO_RASCUNHO = [
    ("app/test/tcle_full_text_test.dart",
     "o teste 'avisa que é rascunho' afirma `tcleVersion.contains('rascunho')` de propósito — "
     "ele DEVE falhar agora. Reescreva-o para o termo aprovado (o aviso de RASCUNHO some da tela "
     "sozinho, porque `_DraftNotice` olha o sufixo); não o apague."),
    ("docs/tcle-rascunho.md",
     "o bloco de status no topo e o '· RASCUNHO' do título ainda dizem que nada foi aprovado. "
     "Reescreva citando o parecer do CEP (número e data), e revise as notas §N4/§N5."),
    ("scripts/docs_to_pdf.py",
     "a tarja do documento `tcle` diz 'RASCUNHO — NÃO APROVADO PELO COMITÊ DE ÉTICA'. "
     "Trocar antes de gerar qualquer PDF para participante."),
    ("app/lib/l10n/app_localizations.dart",
     "conferir se os 7 tópicos de `_consentSummary` ainda correspondem ao texto aprovado — "
     "o resumo não é gerado do .md, ao contrário do texto integral."),
    ("docs/lgpd-nit-checklist.md + ROADMAP.md",
     "itens B2 e G5 (e F2.1/F3.4 do roadmap) passam a citar o parecer, não a pendência."),
]


def _sites() -> list[tuple[pathlib.Path, str, str, str]]:
    """Resolve cada site e extrai a versão declarada. Falha se o arquivo mudou de forma."""
    out = []
    for rel, pattern, why in SITES:
        path = ROOT / rel
        if not path.exists():
            raise SystemExit(f"[erro] site inexistente: {rel} — o script está desatualizado.")
        text = path.read_text(encoding="utf-8")
        found = re.findall(pattern, text, flags=re.MULTILINE)
        if len(found) != 1:
            raise SystemExit(
                f"[erro] em {rel} o padrão casou {len(found)}x (esperado 1): {pattern}\n"
                f"        O arquivo mudou de forma. Corrija SITES antes de trocar a versão — "
                f"senão a troca edita a linha errada sem avisar.")
        out.append((path, pattern, found[0], why))
    return out


def cmd_check(quiet: bool = False) -> int:
    sites = _sites()
    versoes = {v for _, _, v, _ in sites}
    if len(versoes) == 1:
        if not quiet:
            print(f"TCLE em versão única: {versoes.pop()} ({len(sites)} sites).")
        return 0
    print("[FALHA] a versão do TCLE diverge entre os sites — o backend recusaria o aceite "
          "do app com 409, e só em produção:", file=sys.stderr)
    for path, _, v, why in sites:
        print(f"  {v:<20} {path.relative_to(ROOT).as_posix()}  ({why})", file=sys.stderr)
    print("\nCorrija com: python scripts/tcle_version.py <versao>", file=sys.stderr)
    return 1


def cmd_show() -> int:
    sites = _sites()
    for path, _, v, why in sites:
        print(f"  {v:<20} {path.relative_to(ROOT).as_posix()}\n      {why}")
    return cmd_check(quiet=True)


def cmd_bump(nova: str, dry_run: bool) -> int:
    if cmd_check(quiet=True) != 0:
        print("\n[abortado] os sites já divergem entre si. Resolva a divergência antes de "
              "trocar a versão — do contrário o estado atual fica impossível de reconstruir.",
              file=sys.stderr)
        return 1

    sites = _sites()
    atual = sites[0][2]
    if atual == nova:
        print(f"Nada a fazer: a versão já é {nova}.")
        return 0

    print(f"{atual}  ->  {nova}\n")
    for path, pattern, v, _ in sites:
        text = path.read_text(encoding="utf-8")
        # Substitui só o trecho da versão dentro do casamento, preservando o resto da linha.
        m = re.search(pattern, text, flags=re.MULTILINE)
        assert m is not None                       # _sites() já garantiu exatamente 1
        ini, fim = m.span("v")
        novo_texto = text[:ini] + nova + text[fim:]
        rel = path.relative_to(ROOT).as_posix()
        linha = text[:ini].count("\n") + 1
        print(f"  {'[dry-run] ' if dry_run else ''}{rel}:{linha}")
        if not dry_run:
            path.write_text(novo_texto, encoding="utf-8")

    saiu_do_rascunho = "rascunho" in atual and "rascunho" not in nova
    print("\nDepois disto, obrigatoriamente:")
    print("  python scripts/sync_tcle.py          # regera o texto exibido no app")
    print("  cd backend && pytest -q              # a constante é importada, não literal")
    print("  cd app && flutter test               # o CI é quem roda, se não houver SDK local")

    if saiu_do_rascunho:
        print("\n" + "=" * 78)
        print("A FAZER À MÃO — o termo deixou de ser rascunho, e isto o script NÃO faz:")
        print("=" * 78)
        for onde, oque in A_MAO_AO_SAIR_DO_RASCUNHO:
            print(f"\n  * {onde}\n      {oque}")
        print("\n  Nenhum destes é mecânico: são decisões editoriais ou um teste que guarda")
        print("  deliberadamente o estado de rascunho. Um script que os 'resolvesse' sozinho")
        print("  apagaria a rede de segurança junto com o aviso.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verifica e troca a versão vigente do TCLE nos arquivos que a declaram.")
    ap.add_argument("versao", nargs="?", help="nova versão (ex.: 1.0.0). Sem ela, use --check/--show.")
    ap.add_argument("--check", action="store_true", help="só verifica se os sites concordam")
    ap.add_argument("--show", action="store_true", help="lista os sites e a versão de cada um")
    ap.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem gravar")
    a = ap.parse_args()

    if a.check:
        return cmd_check()
    if a.show:
        return cmd_show()
    if not a.versao:
        ap.error("informe a nova versão, ou use --check / --show.")
    return cmd_bump(a.versao, a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
