# Sereno — plataforma de neuromodulação não invasiva (MVP de pesquisa)

App (Flutter) + backend (Python/FastAPI) que instrumenta um **estudo-piloto de
iniciação científica** com frequências binaurais (relaxamento e sono).
**Ferramenta complementar; não substitui cuidado profissional.**

> **Leia primeiro o [`CLAUDE.md`](./CLAUDE.md)** — escopo travado, decisões
> inegociáveis e convenções. Ele governa todo o desenvolvimento.

## Estrutura

| Pasta | O quê |
|---|---|
| `docs/` | Fonte de verdade (Markdown, etapas 1–7) + ADRs + Word para o CEP |
| `app/` | Cliente Flutter/Dart (offline-first) |
| `backend/` | Monólito modular Python/FastAPI + PostgreSQL |
| `audio-pipeline/` | Síntese do estímulo + validação por FFT (Etapa 2) |
| `shared-contracts/` | `openapi.yaml` — fonte de verdade da API |
| `.github/workflows/` | CI (testes, lint, validação de sinal) |

## Estado atual

Planejamento (Etapas 1–7) concluído; código de referência **validado** já incluído
(síntese/FFT, escores, schema, OpenAPI, segurança, recomendador, análise).
Próximo passo: implementação por **fatias verticais** (ver `CLAUDE.md`).

## Aviso

Piloto de **viabilidade**, não dimensionado para eficácia. Evidência de frequências
binaurais é limitada e heterogênea. LGPD/SaMD/PI exigem NIT e assessoria jurídica.

## Planejamento e execução (handoff para o Claude Code)
- `docs/ROADMAP.md` — backlog de fatias verticais (dependências, critério de pronto, inegociáveis).
- `docs/PROMPTS_CLAUDE_CODE.md` — prompts prontos para executar cada fatia no Claude Code (VS Code).
- Método por fatia: contrato → código → teste (com caminhos de negação) → CI verde → ADR → commit.
