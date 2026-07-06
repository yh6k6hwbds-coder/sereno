# ADR-076 — Deploy do backend na Fly.io (região São Paulo) e residência de dados

- Status: Aceito
- Data: 2026-07-06
- Contexto: MVP do piloto feature-completo; o app cliente (web/Pages e APK) só é
  utilizável quando existe um backend acessível por HTTPS. Até aqui o backend só
  rodava em Docker local (`localhost:8000`), então o app publicado não conectava.

## Decisão

Hospedar o backend (FastAPI) + PostgreSQL gerenciado na **Fly.io, região `gru`
(São Paulo/Brasil)**, a partir do `Dockerfile` já existente. Config em `fly.toml`.

- **Sem Redis gerenciado no piloto.** `rate_limit.py` e `token_revocation.py` já
  caem para implementação em memória quando `REDIS_URL` não está definido. Com **1
  instância** (`min_machines_running = 1`) isso é suficiente e correto. Se um dia
  houver múltiplas réplicas, provisionar Redis e definir `REDIS_URL` (o código já
  suporta) para que limite/denylist sejam compartilhados.
- **Normalização de `DATABASE_URL`.** Provedores gerenciados injetam
  `postgres://…`, esquema que o SQLAlchemy 2.0 recusa e que não seleciona o driver
  psycopg v3. Adicionado `normalize_database_url()` em `app/core/db.py`, reusado em
  `migrations/env.py`. Coberto por `tests/test_db_url.py`.
- **CORS** restrito à origem do app no GitHub Pages (`CORS_ORIGINS` no `fly.toml`),
  nunca `*` — dados sensíveis.
- **Injeção da URL da API no cliente.** O CI (`release.yml`) passa
  `--dart-define=API_BASE_URL=<fly>/v1` nos builds web e APK; default aponta para o
  `app` do `fly.toml`, sobrescrevível pela variável `API_BASE_URL` do repositório.

## Residência de dados (decisão inegociável #6) — atende, com ressalva

A escolha da região `gru` **honra** a exigência de residência no Brasil. Enquanto o
deploy usar **apenas dados sintéticos** (o `seed_demo`), não há PII real em jogo.

**Antes de qualquer participante real:** confirmar com o orientador/NIT que Fly.io
(São Paulo) satisfaz os requisitos institucionais e da LGPD (contrato/operador de
tratamento, DPA, criptografia em repouso do Postgres gerenciado). Isto **não é
aconselhamento jurídico** — sinalizar, não decidir. Alternativas com contrato
brasileiro (nuvem nacional / região BR de AWS/GCP) podem ser exigidas.

## Pendências que este deploy NÃO resolve

- **Entrega real do OTP por e-mail.** Enquanto `EMAIL_DEV_CONSOLE=1`, o código sai
  no `fly logs` (serve só para teste). Produção exige SMTP (secrets
  `SMTP_HOST/USER/PASSWORD`) e a remoção de `EMAIL_DEV_CONSOLE`.
- **Custódia da chave selada A/B→condição** (`ARM_CONDITION_MAP`): idealmente fora
  do provedor de app (cofre/KMS), não como env comum. Aceitável no teste; revisar
  para o piloto real.
- **Backups/retenção do Postgres** e rotação de segredos: definir antes do piloto.
