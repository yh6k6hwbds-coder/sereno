# ADR-065 — Docker + compose (Postgres/Redis) + segredos

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/infra)
- **Contexto de origem:** Fatia D3 do ROADMAP
- **Relaciona-se com:** ADR-024 (Postgres + migrações), ADR-031 (Redis/worker), ADR-059/060 (segredos/chave selada)

## Contexto
Faltava um ambiente **prod-like** reprodutível: Postgres + Redis + API, com migrações no
deploy e configuração por ambiente/cofre (nunca segredos no repositório).

## Decisão
1. **`backend/Dockerfile`**: `python:3.11-slim`, usuário **não-root**, dependências por wheels
   (camada cacheável). `ENTRYPOINT` = `docker-entrypoint.sh`.
2. **`docker-entrypoint.sh`**: aplica `alembic upgrade head` e então sobe `uvicorn`. Produção usa
   **Alembic** (schema versionado), **nunca** `create_all`.
3. **`docker-compose.yml`**: serviços `db` (postgres:16), `redis` (redis:7) e `backend`, com
   **healthchecks** e `depends_on: condition: service_healthy`. Toda config vem de env; variáveis
   obrigatórias usam `${VAR:?}` (falha explícita se faltarem).
4. **Segredos por ambiente:** `.env.example` documenta as chaves; o `.env` real é **gitignored**.
   A **chave selada** `ARM_CONDITION_MAP` é sinalizada para custódia **separada** (cofre/KMS).
5. **CI opcional com Postgres:** job `backend-postgres` sobe um serviço Postgres e roda
   `alembic upgrade head` no banco **real** — pega problemas de DDL (JSONB/INET/CHECK) que o
   smoke em SQLite não vê.

## Alternativas consideradas
- **`create_all` no start.** Rejeitada: produção precisa de migrações versionadas/reversíveis
  (ADR-024); `create_all` mascara drift de schema.
- **Migração no entrypoint vs. job/initContainer separado.** Escolhido o entrypoint pela
  simplicidade no piloto; em **multi-réplica** convém rodar a migração em **um** runner (job
  dedicado) para evitar corrida — registrado como pendência.
- **Multi-stage build.** Desnecessário: todos os pacotes têm wheels; a imagem já é enxuta.
- **Segredos em arquivo no repo.** Rejeitada: `.env` fica fora do git; produção usa cofre/KMS.

## Consequências
- **Positivas:** `docker compose up --build` sobe o ambiente com migrações automáticas; o job de
  CID valida a migração no Postgres real; base para D4/observabilidade e deploy.
- **Custo/tradeoff (visão do analista):**
  - **Não verificável localmente aqui** (sem Docker na máquina de dev): a config é YAML-válida e o
    caminho Postgres é exercido **no CI** (`backend-postgres`), não localmente.
  - **Migração no entrypoint** roda em toda réplica no start — ok para instância única; multi-
    réplica exige gate (um migrador).
  - **Segredos em env** ficam visíveis ao processo do contêiner; produção real deve puxar do
    **cofre/KMS** (não do `.env`), e a **chave selada** deve ter custódia à parte.
- **Pendências:** secret manager/KMS (em vez de `.env`); job de migração dedicado p/ multi-réplica;
  imagem do worker (RQ) quando a fila assíncrona entrar; TLS/reverse-proxy à frente da API.

## Conformidade
`docker-compose.yml` é YAML válido (serviços db/redis/backend + volume). O job de CI
`backend-postgres` aplica `alembic upgrade head` num **Postgres real** — falha se a migração não
for compatível. (O `docker compose up` completo depende de Docker no ambiente do mantenedor.)
