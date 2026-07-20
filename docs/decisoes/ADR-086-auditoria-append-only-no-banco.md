# ADR-086 — Auditoria append-only reforçada NO BANCO (trigger), não só no ORM

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança/LGPD)
- **Contexto de origem:** item **C8** do `docs/lgpd-nit-checklist.md` — a auditoria append-only
  estava garantida **só no ORM** (contornável por SQL cru); o `REVOKE` no banco era intenção
  documentada, não aplicada.
- **Relaciona-se com:** ADR-056 (auditoria append-only — decisão original), inegociável #6
  (auditoria append-only), ADR-066 (o `erase` de LGPD nunca apaga a auditoria).

## Contexto
O ADR-056 estabeleceu a trilha append-only e a garantiu com um **guard no ORM**
(`before_flush` recusa UPDATE/DELETE de `AuditLog`). Isso protege o caminho normal, mas um
`UPDATE`/`DELETE` por **SQL cru** — fora da sessão ORM — o contornaria. O docstring do módulo
prometia um `REVOKE UPDATE, DELETE` no Postgres, mas **nenhuma migração o aplicava**; e, mesmo
aplicado, o `REVOKE` **não basta**: no Postgres o **dono da tabela ignora** as checagens de
privilégio, então o usuário da aplicação (tipicamente o dono) continuaria podendo alterar linhas.
Para uma trilha de auditoria com valor probatório (LGPD/CEP), a invariante precisa valer **no
próprio banco**, independentemente de dono/privilégio.

## Decisão
1. **Trigger no banco** que aborta qualquer `UPDATE`/`DELETE` em `audit_log`, aplicado por
   migração (`d4e5f6a7b8c9`) e centralizado em `core/audit_ddl.py` (fonte única da DDL):
   - **PostgreSQL:** função `audit_log_append_only_guard()` + trigger `BEFORE UPDATE OR DELETE`
     que faz `RAISE EXCEPTION`; vale mesmo para o **dono** da tabela. Acompanha um
     `REVOKE UPDATE, DELETE ... FROM PUBLIC` como camada extra (não como defesa principal).
   - **SQLite** (testes/CI-espelho): dois triggers `BEFORE UPDATE`/`BEFORE DELETE` com
     `RAISE(ABORT)`, para a invariante ser **exercida na suíte**.
2. **Duas camadas explícitas:** o guard no ORM (ADR-056) continua — dá erro Python claro no
   caminho normal; o trigger é a **defesa em profundidade** contra SQL cru. Documentado como
   tal em `modules/audit/service.py`.
3. **Instalação também no schema de teste:** um listener `after_create` em `AuditLog.__table__`
   instala o trigger quando o schema é montado por `create_all` (testes), espelhando o que a
   migração faz em produção — sem duplicar a DDL.
4. **Honestidade do checklist:** o item C8 do checklist LGPD sai de "🟡 (só ORM; REVOKE é
   intenção)" para **✅** (enforcement no banco, testado).

## Alternativas consideradas
- **Só `REVOKE UPDATE, DELETE`.** Rejeitada como defesa principal: o dono da tabela ignora
  privilégios no Postgres — o `REVOKE` sozinho não impede a aplicação de alterar a auditoria.
  Mantido apenas como camada extra.
- **Só o guard no ORM (status quo).** Insuficiente: não cobre SQL cru / acesso direto ao banco.
- **Row-Level Security / tabela em outro schema com role separada.** Mais robusto ainda, porém
  exige separação de papéis no deploy (a app não ser dona da tabela) — desproporcional ao piloto;
  o trigger entrega a invariante sem depender disso. Registrado como evolução possível.

## Consequências
- **Positivas:** a auditoria passa a ser append-only **no banco**, valendo contra SQL cru e contra
  o próprio dono da tabela; a invariante é **testada** no SQLite da suíte (antes só o caminho ORM
  era coberto). Fecha C8. Suíte 257 → 261 (+4).
- **Custo/tradeoff:** um trigger a manter; a DDL é dialect-aware (Postgres/SQLite; outros dialetos
  caem no no-op e mantêm só o guard do ORM). Migração idempotente (`IF NOT EXISTS` / `DROP IF
  EXISTS`), com downgrade.
- **Pendências:** se algum dia a app deixar de ser dona da tabela, revisitar para RLS/role
  dedicada (defesa ainda mais forte). Retenção/expurgo da auditoria seguem no escopo do ADR-066.

## Conformidade
CI verde exige `tests/test_audit_append_only_db.py`: INSERT segue permitido; `UPDATE`/`DELETE`
**crus** (fora do ORM) são recusados pelo banco e a linha permanece intacta; UPDATE em massa sem
`WHERE` também é barrado. A migração aplica em SQLite limpo e o ciclo downgrade→upgrade é idempotente.
O guard do ORM (ADR-056) segue coberto por `test_audit.py`. Sem PII/braço na auditoria.
