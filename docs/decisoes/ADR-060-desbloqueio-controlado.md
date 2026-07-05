# ADR-060 — Procedimento de desbloqueio (unblinding) controlado

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança), 1 (cegamento)
- **Contexto de origem:** Fatia C5 do ROADMAP
- **Relaciona-se com:** ADR-027 (braço codificado + chave selada), ADR-046 (resolução cega), ADR-056 (auditoria)

## Contexto
O cegamento é inegociável: **nenhum** endpoint expõe a condição (ativo/sham). Mas há situações
legítimas (segurança do participante, encerramento do estudo) em que um **desbloqueio controlado**
é necessário. Faltava esse procedimento — o único caminho autorizado e auditado para a condição.

## Decisão
1. **`POST /v1/allocation/{id}/unblind-request`** (admin `unblind:request`): revela a condição de
   **UM** participante, resolvendo o braço codificado (`resolve_arm`) e traduzindo pela **chave
   selada** (`condition_for_arm` / `ARM_CONDITION_MAP`). Exige **justificativa** (≥ 10 chars).
2. **A condição é revelada APENAS nesta resposta HTTP** ao admin autorizado. É o **único** ponto
   da API onde a condição aparece; todos os demais endpoints continuam cegos.
3. **Auditoria sem a condição:** grava `unblind.performed` com participante, autor, timestamp e a
   **justificativa** — **nunca** a condição em claro (o braço jamais entra na trilha). Marca
   `allocation.unblinded_at`.
4. **Nunca automático, nunca em massa:** exige chamada explícita, por participante (path param),
   com papel admin e justificativa. Se a chave selada não estiver configurada → 409 (não conclui).

## Alternativas consideradas
- **Aprovação por duas pessoas (separação de funções).** Adiada para o endurecimento de produção:
  exigiria uma tabela de pedidos + máquina de estados + segundo aprovador. O DoD desta fatia pede
  **papel + justificativa** (atendido); a dupla-aprovação fica como pendência explícita.
- **Registrar a condição na auditoria.** Rejeitada: violaria o invariante da trilha (sem braço em
  claro). A prestação de contas é **quem/quando/por quê**, não o valor revelado.
- **Desbloqueio em lote.** Rejeitada: por participante apenas; um lote sem justificativa
  individual quebraria o controle.

## Consequências
- **Positivas:** existe um caminho legítimo, auditado e restrito para a condição, sem enfraquecer o
  cegamento dos demais fluxos; `unblinded_at` deixa rastro de que houve desbloqueio. Suíte: 132 →
  139 testes; prova-se que a condição só aparece via este procedimento.
- **Custo/tradeoff (visão do analista):**
  - **Passo único** (sem separação de funções): mitigado por admin-only + justificativa +
    auditoria + por-participante. Produção deve adicionar **segundo aprovador** e talvez janela/
    expiração do pedido. Registrado como pendência.
  - **Custódia da chave selada:** o servidor precisa da `ARM_CONDITION_MAP` no momento do
    desbloqueio (env/cofre); em produção, com custódia formal (KMS) e acesso restrito.
  - **`unblinded_at` visível** em futuras listagens de pesquisa sinaliza o desbloqueio (metadado),
    sem revelar a condição — a análise cega deve **excluir** participantes desbloqueados quando
    apropriado (nota para C7/relatório final).
- **Pendências:** aprovação em duas pessoas; custódia KMS da chave; expiração do pedido; excluir
  desbloqueados da análise cega quando pertinente.

## Conformidade
CI verde exige `tests/test_unblind.py`: o desbloqueio revela a condição correta pela chave selada
(A→active, B→sham) **só** na resposta ao admin; grava `unblind.performed` **sem** a condição na
trilha (com a justificativa); exige admin (403 para pesquisador), token (401), justificativa (422)
e alocação existente (404); a condição não aparece em nenhum outro evento/endpoint.
