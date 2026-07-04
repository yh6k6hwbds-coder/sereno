# backend — monólito modular (FastAPI)

Fronteiras por domínio em `app/modules/`. Integridade no banco (FK/CHECK/UNIQUE);
migrações Alembic; argon2id + JWT + MFA + RBAC; auditoria append-only;
problem+json. **Extrair serviço só com necessidade real de carga/equipe.**

- `app/core/` — config, segurança, db, `models.py` (schema físico).
- `app/modules/` — identity, consent, allocation, sessions, instruments, recommender, research, audit.
- `migrations/` — Alembic (+ `schema_reference.sql`, DDL gerado dos modelos).
- `tests/` — pytest (inclui testes de contrato contra o OpenAPI).
