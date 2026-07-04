# ADR-042 — Modelos e migração portáveis (Postgres em produção, SQLite em testes)

- **Status:** Aceito
- **Data:** 2026-07-03
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/banco)
- **Contexto de origem:** implementação da 1ª fatia vertical (TCLE)

## Contexto
Os modelos da Etapa 5 usavam tipos exclusivos do PostgreSQL (JSONB, UUID, INET, BYTEA).
Isso impedia rodar testes de banco sem subir um Postgres, tornando o CI mais lento e frágil.
Queremos testes de integração rápidos e determinísticos no CI, sem serviço externo.

## Decisão
1. **Modelos portáveis** (`core/models.py`): tipos genéricos do SQLAlchemy com `.with_variant`
   para preservar o nativo no Postgres — `JSON().with_variant(JSONB,"postgresql")`,
   `String(45).with_variant(INET,"postgresql")`, `Uuid`, `LargeBinary`, `DateTime(timezone=True)`.
   PK UUID com default no lado da aplicação (`uuid4`), portável entre bancos.
2. **Engine preguiçosa** (`core/db.py`): a engine só é criada no 1º uso, para importar a app
   não exigir o driver do banco (testes SQLite não precisam de `psycopg`).
3. **Migração inicial portável**: a migração usa `sa.JSON()`/`sa.String()` genéricos, rodando
   tanto em SQLite (CI) quanto em Postgres.
4. **CI** roda `alembic upgrade` em SQLite + `pytest` (bloqueante), sem serviço de banco.

## Alternativas consideradas
- **Manter tipos Postgres-only e exigir Postgres no CI (serviço docker).** Rejeitado nesta fase:
  mais lento/frágil para ganho pequeno num piloto; reavaliar se surgirem recursos que dependam
  de JSONB/GIN de forma essencial.
- **Monkeypatch de compilação dos tipos PG para SQLite só nos testes.** Rejeitado: frágil e
  esconde divergências entre teste e produção.

## Consequências
- **Positivas:** CI de banco rápido e sem dependência externa; testes de integração reais
  (app → banco) por fatia vertical.
- **Custo/tradeoff:** a migração cria `JSON`/`VARCHAR(45)` (não `JSONB`/`INET`) no banco real.
  Aceitável no piloto. Se, no futuro, forem necessários índices/consultas JSONB ou o tipo INET,
  criar migração de follow-up para promover essas colunas ao tipo nativo (os modelos já pedem
  o nativo no Postgres via variant; `schema_reference.sql` documenta o DDL nativo-alvo).
- **Neutras:** `schema_reference.sql` continua mostrando o DDL Postgres nativo como referência.

## Conformidade
CI verde exige: `alembic upgrade` (SQLite) + `pytest` do backend passando, além de FFT e OpenAPI.
