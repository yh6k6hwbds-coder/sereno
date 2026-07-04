# ADR-056 — Log de auditoria append-only (transversal)

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Fatia C1 do ROADMAP (integridade científica / exigência do CEP)
- **Relaciona-se com:** ADR-030 (auditoria append-only), ADR-026/027 (PII e braço protegidos)

## Contexto
O CEP e a integridade do estudo exigem uma trilha de **ações sensíveis** (consentimento,
alocação e — quando existirem — pedido de exportação e desbloqueio) que seja **imutável**,
**sem PII em claro** e **sem o braço** (ativo/sham). A tabela `audit_log` já existia; faltava
o serviço que a alimenta, a garantia de append-only e uma leitura controlada.

## Decisão
1. **Serviço transversal `audit.service`** com duas operações: `record_event(...)` (grava na
   **mesma transação** da ação — atomicidade: se a ação falha, o evento rola atrás junto) e
   `list_events(...)` (leitura paginada). Nenhum módulo escreve em `audit_log` por conta própria.
2. **Append-only garantido em duas camadas:**
   - **ORM (aplicação):** um listener `before_flush` recusa qualquer `UPDATE`/`DELETE` de
     linha de `AuditLog` em **qualquer** sessão (`AuditAppendOnlyError`). Vale nos testes/SQLite.
   - **Banco (produção):** `REVOKE UPDATE, DELETE ON audit_log` do papel da aplicação (GRANT só
     de `INSERT`/`SELECT`). É a garantia forte; o guard do ORM é defesa em profundidade.
3. **Sem PII, sem braço:** o chamador passa só identificadores **pseudonimizados** (UUID) e
   metadados neutros. Em particular, o evento de **alocação registra apenas o bloco** — nunca
   `arm_coded`. Consentimento registra `tcle_version` e `accepted` (não o IP, que é PII).
4. **Leitura restrita:** `GET /v1/research/audit` exige a permissão **`audit:read`**, concedida
   **só a admin** (nova entrada no RBAC). Paginação **keyset por cursor** em `(occurred_at, id)`,
   mais recentes primeiro; cursor opaco (base64), portável entre Postgres e SQLite.
5. **Escopo honesto desta fatia:** apenas as ações sensíveis **já implementadas** emitem eventos
   (consentimento, alocação). Pedido de **exportação** (C6) e **desbloqueio** (C5) ganham o hook
   `record_event` quando esses fluxos forem construídos — registrado aqui para não dar a falsa
   impressão de cobertura total.

## Alternativas consideradas
- **Confiar só no GRANT do Postgres.** Rejeitada como única linha: os testes rodam em SQLite
  (sem GRANT) e um bug de serviço passaria despercebido; o guard do ORM fecha essa lacuna e
  documenta a intenção no código.
- **Triggers no banco para bloquear UPDATE/DELETE.** Adiada: portabilidade Postgres/SQLite e
  complexidade de migração; o par GRANT + guard ORM cobre o piloto com menos superfície.
- **Tabela append-only por hash-chain (à prova de adulteração forense).** Fora do escopo do
  piloto; anotado como possível endurecimento futuro (não exigido pelo CEP agora).
- **Paginação por offset.** Rejeitada: a convenção do projeto é cursor (keyset é estável sob
  inserções concorrentes, comuns numa trilha que só cresce).

## Consequências
- **Positivas:** ações sensíveis viram evidência imutável; cegamento preservado (o braço nunca
  entra na trilha, provado por teste); leitura só para admin; base pronta para C5/C6 plugarem
  seus eventos. Suíte: 70 → 78 testes.
- **Custo/tradeoff (visão do analista):**
  - O guard do ORM é **global** (todas as sessões). É barato, mas qualquer fluxo legítimo que
    precisasse *corrigir* um evento (não deveria existir) falharia por design — é o objetivo.
  - `list_events` compara `occurred_at` do cursor com o valor persistido; em SQLite o timestamp
    é armazenado sem tz (naïve). O round-trip é consistente (encode a partir do valor lido), mas
    ao migrar para Postgres convém revalidar o cursor com timestamptz.
  - Cobertura de ações é **parcial** por ora (só consent/allocation) — ver escopo acima.
- **Pendências:** aplicar o `REVOKE UPDATE, DELETE` na migração de produção (D3/Docker); plugar
  `record_event` em exportação (C6) e desbloqueio (C5); considerar retenção/expurgo alinhado à
  LGPD (D4) **sem** violar o append-only (expurgo por política, auditado).

## Conformidade
CI verde exige `tests/test_audit.py`: consentimento e alocação gravam evento; o evento de
alocação **não contém o braço**; `UPDATE`/`DELETE` em `audit_log` levantam `AuditAppendOnlyError`;
`GET /research/audit` responde 200 para admin, **403** para pesquisador/participante e **401** sem
token; a resposta não vaza braço/condição; paginação keyset devolve páginas sem sobreposição.
