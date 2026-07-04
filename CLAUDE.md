# CLAUDE.md — Sereno (plataforma de neuromodulação não invasiva)

> Este arquivo é o briefing permanente do projeto. O Claude Code deve lê-lo no
> início de cada sessão e respeitá-lo. Se algo aqui conflitar com um pedido,
> **pare e pergunte** antes de prosseguir.

## O que é

App (Flutter) + backend (Python/FastAPI) que reproduz sessões de áudio com
**frequências binaurais** para relaxamento e sono, **instrumentando um estudo-piloto
de iniciação científica** (randomizado, controlado, duplo-cego, 4 semanas, N≈40).
Nome provisório: **Sereno**.

Instituição: Centro Universitário INTA (UNINTA), Sobral–CE. Orientação: Dra. Bianca Régia Silva.

## ESCOPO TRAVADO (não expandir sem decisão explícita)

- O alvo é o **MVP do piloto de 4 semanas** — **não** a plataforma internacional
  maximalista da visão original. Escalabilidade é *preparada*, não *construída* agora.
- Ao surgir ideia de ampliar escopo (wearables, nuvem, ML, EEG, multi-idioma,
  monetização): **registrar no roadmap e perguntar**, não implementar.
- Princípio-guia: **simplicidade suficiente > complexidade prematura**.

## DECISÕES INEGOCIÁVEIS (quebrar o CI se forem violadas)

Estas decisões vêm das Etapas 1–7 (ver `docs/`). Não as reverta sem atualizar o ADR
e avisar o mantenedor.

1. **Cegamento**: duplo-cego com **sham ativo (Δf = 0)**; a UI da sessão é **idêntica**
   nos dois braços; a **visualização ambiente NÃO é reativa ao áudio** (reagir vazaria o braço).
2. **Alocação oculta**: o cliente recebe apenas um **handle neutro** de protocolo; o mapa
   handle→arquivo (ativo/sham) vive só no servidor; **braço codificado (A/B)**; a chave
   A/B→condição fica **selada** e só abre no *data lock*. **Nenhuma permissão de RBAC revela o braço.**
3. **Áudio é instrumento**: síntese **determinística offline**, validada por **FFT em CI**,
   empacotada como biblioteca **sem perdas** (WAV/FLAC); o cliente **reproduz bit-a-bit**
   (sem reamostragem/DSP/normalização/downmix). **Fones com fio** recomendados; Bluetooth avisado/registrado.
4. **Instrumentos**: **GAD-7** (autorrelato) no lugar da HAM-A; **PSQI** e **SUS**; escores
   **determinísticos e versionados** (`score_version`). Usar versões validadas em PT-BR
   (PSQI = Bertolazi 2011); **não** reproduzir o texto verbatim dos instrumentos no código.
5. **Recomendador**: **por regras transparentes e versionadas** (não ML). Seleciona **apenas**
   dentro da biblioteca validada (faixas seguras); registra `entrada→regra→saída`; guarda
   `feature_vector` para ML futuro — **ML nunca decide ao vivo** sem validação.
6. **Segurança/LGPD**: argon2id + JWT (access/refresh) + **MFA** para staff; **RBAC no servidor**;
   TLS + cripto em repouso; **PII cifrada e separada**; dataset de pesquisa **pseudonimizado**;
   **auditoria append-only**; erros em **problem+json (RFC 9457)**; residência de dados no Brasil.

## POSTURA CIENTÍFICA (obrigatória em qualquer texto ou copy)

- Frequências binaurais = intervenção **experimental**; evidência **limitada e heterogênea**.
- O app é **ferramenta complementar** — **não** substitui avaliação/tratamento profissional.
  Esse aviso é persistente na interface.
- **Diferenciar sempre** evidência / hipótese / opinião. **Sem overclaim** (nem de eficácia, nem de "IA").
- Piloto é de **viabilidade** — não dimensionado para eficácia; ansiedade e sono são **exploratórios**.

## Stack

- **Cliente**: Flutter / Dart (iOS + Android), offline-first.
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic, PostgreSQL, Redis + worker (RQ/Dramatiq).
- **Contrato**: `shared-contracts/openapi.yaml` é a **fonte de verdade** da API.
- **Pipeline de áudio**: Python (numpy/scipy) — síntese + validação FFT (offline/CI).

## Mapa do repositório

- `docs/` — fonte de verdade em Markdown (etapas 1–7) + `docs/decisoes/` (ADRs) + `docs/anexos-docx/` (Word p/ CEP).
- `app/` — cliente Flutter (`lib/core`, `lib/features/<domínio>`, `lib/shared`, `lib/services`).
- `backend/` — monólito **modular** (`app/modules/<domínio>`, `app/core`, `migrations`, `tests`).
- `audio-pipeline/` — síntese e validação do estímulo (Etapa 2).
- `shared-contracts/` — `openapi.yaml` (gerar tipos do cliente a partir daqui).
- `.github/workflows/` — CI.

## Comandos (preencher conforme implementar)

```bash
# Backend
cd backend && uvicorn app.main:app --reload         # rodar API
cd backend && pytest -q                              # testes
cd backend && ruff check . && ruff format .          # lint/format
cd backend && alembic upgrade head                   # migrações

# Áudio (validação obrigatória em CI)
cd audio-pipeline && python -m pytest tests/         # bateria FFT

# App
cd app && flutter run                                # rodar
cd app && flutter test                               # testes
```

## Convenções

- REST com recursos no plural e **versão no caminho** (`/v1`); toda entrada validada com pydantic;
  criações **idempotentes** (cabeçalho `Idempotency-Key`); paginação por cursor.
- Integridade **no banco** (FK/CHECK/UNIQUE); toda mudança de schema via **migração Alembic**.
- **Todo módulo novo** vem com testes; **CI bloqueia merge** com falha (inclui FFT e escores).
- **Nunca** commitar segredos; **nunca** logar PII; **nunca** expor o braço em resposta de API.
- Manter histórico de autoria limpo (git com autores reais) — relevante para PI.

## Como trabalhar comigo (fatias verticais)

- Entregar **um fluxo de ponta a ponta por vez** (ex.: TCLE → tela → API → banco → teste),
  não "todo o front, depois todo o back".
- **Contrato primeiro**: alterou a API? Atualize `openapi.yaml` **antes** do código.
- Cada fatia termina com: código + testes passando + doc/ADR atualizado quando a decisão for relevante.

## Guardrails para o Claude Code

- Não reverter nenhuma **decisão inegociável** sem atualizar o ADR e avisar.
- Não introduzir dependência experimental em caminho crítico; preferir libs maduras.
- Não implementar ML de decisão, EEG, wearables ou multi-idioma "de brinde" — está fora do MVP.
- Isto **não é aconselhamento jurídico/médico**: LGPD, SaMD/ANVISA e PI exigem NIT + assessoria; sinalizar, não decidir.
- Na dúvida sobre escopo ou método, **pergunte** — os *gates* de aprovação são do mantenedor.

## Definição de "pronto" (por fatia)

Código limpo e modular · testes passando · sem PII em logs · sem segredo no repo ·
contrato OpenAPI atualizado · decisão relevante registrada em ADR · nada que quebre as decisões inegociáveis.
