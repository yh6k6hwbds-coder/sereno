# ADR-075 — Desbloqueio (unblinding) em duas pessoas

- **Status:** Aceito
- **Data:** 2026-07-05
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança) e 7 (integridade científica)
- **Contexto de origem:** Pendência da fatia C5 ("aprovação por duas pessoas") — endurecimento p/ dado real/CEP
- **Relaciona-se com:** ADR-060 (desbloqueio controlado, 1 passo), ADR-027/014/015 (braço codificado + chave selada **[inegociável]**), ADR-056 (auditoria append-only)

## Contexto
O desbloqueio (ADR-060) revelava a condição (ativo/sham) em **um único passo**: um admin com
`unblind:request` + justificativa recebia o braço na hora. Para um ECR duplo-cego, o cegamento é o
ativo mais sensível — um único operador conseguindo revelar sozinho é um risco de integridade
(quebra acidental/indevida do cego) que o CEP e a análise não deveriam tolerar. A boa prática é
**controle por duas pessoas** (dual control): quem pede não é quem libera.

## Decisão
Divide o procedimento em **dois passos**, ambos exigindo admin (`unblind:request`):
1. **`POST /allocation/{id}/unblind-request`** — abre um **pedido** justificado. Grava
   `unblind_requested_by`/`_at`/`_justification` na `allocation` e audita `unblind.requested`
   **sem** a condição. **NÃO revela.** 409 se já houver pedido pendente ou já desbloqueado.
2. **`POST /allocation/{id}/unblind-approve`** — um **segundo admin DISTINTO** aprova. Só aqui a
   condição é revelada (via chave selada `ARM_CONDITION_MAP`), grava-se `unblinded_at` e audita-se
   `unblind.performed` (quem aprovou/quando) **sem** a condição. 409 se: não há pedido pendente; o
   aprovador é o **mesmo** solicitante (regra das duas pessoas); ou já desbloqueado.

A condição continua sendo o **único** dado sensível e aparece **só** na resposta da aprovação —
nenhum outro endpoint, nem a trilha de auditoria, a expõe (invariante preservada de ADR-060).

Migração `a1b2c3d4e5f6`: adiciona 3 colunas nullable à `allocation` (aplicada e verificada no
Postgres real). Sem tabela nova — o estado corrente cabe na alocação; o histórico fica na auditoria.

## Alternativas consideradas
- **Tabela `unblind_request` dedicada (com status/histórico).** Rejeitada por ora: o histórico já
  vive na auditoria append-only (`requested`/`performed`); campos na `allocation` bastam p/ o estado
  atual. Simplicidade suficiente > complexidade prematura.
- **Permissão separada `unblind:approve` para o aprovador.** Adiada: a separação hoje é por
  **identidade** (aprovador ≠ solicitante), não por papel. Distinguir papéis (ex.: um "custodiante"
  que só aprova) é política a registrar depois, se o CEP exigir.
- **Aprovação por N pessoas / quórum.** Fora de escopo do piloto; duas pessoas é o mínimo eficaz.
- **Permitir cancelar o pedido pendente.** Adiado: sem endpoint de cancelamento (baixa frequência
  no piloto); um pedido pendente bloqueia novos (409) até ser aprovado.

## Consequências
- **Positivas:** nenhum operador único revela o braço; o cegamento ganha dual control auditável;
  o pedido e a aprovação ficam separados na trilha (quem pediu / quem liberou). Suíte: 149 → 154.
- **Custo/tradeoff (visão do analista):**
  - Um pedido pendente **bloqueia** novos pedidos (409) e não há cancelamento — aceitável no piloto
    (desbloqueio é evento raro e justificado), mas é um ponto de fricção a revisitar se necessário.
  - A regra "duas pessoas" é por `actor_id` do token; tokens **cunhados fora do login** (uso em
    testes) continuam válidos — a garantia real está no fluxo de emissão (login com MFA, ADR-074).
  - `refresh`/tokens de acesso não expiram o pedido; a janela de aprovação é operacional, não técnica.
- **Pendências:** cancelar/expirar pedido; papel `unblind:approve` dedicado; notificar o 2º
  aprovador (integra com D1/e-mail); política de "quem pode ser custodiante".

## Conformidade
CI verde exige `tests/test_unblind.py`: o **pedido** não revela e audita `unblind.requested` sem a
condição; a **aprovação** por um 2º admin distinto revela e audita `unblind.performed` sem a
condição; o **mesmo** admin não aprova o próprio pedido (409); aprovar sem pedido → 409; re-pedir/
aprovar já desbloqueado → 409; não-admin → 403; sem token → 401; não alocado → 404; sem
justificativa → 422; a condição só aparece na resposta da aprovação.
