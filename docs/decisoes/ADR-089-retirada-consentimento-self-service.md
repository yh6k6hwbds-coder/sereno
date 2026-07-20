# ADR-089 — Retirada de consentimento self-service pelo titular (LGPD Art. 8 §5)

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/LGPD), 1 (consentimento/TCLE)
- **Contexto de origem:** item **B3** do `docs/lgpd-nit-checklist.md` — "revogação do consentimento
  pelo titular"; a única via era a **eliminação por admin** (ADR-066), faltava um caminho
  **self-service**.
- **Relaciona-se com:** consentimento/TCLE (`consent/`), ADR-066 (direitos do titular: acesso/
  eliminação por admin), inegociável #6 (LGPD; auditoria append-only), ADR-056/086 (auditoria).

## Contexto
O TCLE é registrado em `consent_record` (aceite/recusa, versão, IP, hash). A LGPD (Art. 8 §5)
garante ao titular **revogar o consentimento a qualquer momento**, e de forma tão fácil quanto foi
consentir. Até aqui a única forma de "revogar" era a **eliminação operada por admin** (ADR-066),
que remove PII — o titular não tinha um botão próprio para **retirar** o consentimento. O modelo já
antecipava isso: `consent_record.revoked_at` existia, sem fluxo que o usasse.

## Decisão
1. **`POST /v1/participants/me/consent/withdraw`** (participante autenticado, `consent:write`):
   carimba `revoked_at = now` nos consentimentos **ativos** (aceitos e não revogados) do próprio
   titular e muda `participant.status` para `withdrawn`. Auditado (`consent.withdrawn`, sem PII —
   só o nº de registros revogados).
2. **Enforcement:** a retirada **encerra a participação** — `POST /v1/sessions` passa a recusar
   (403) participante `withdrawn`. Sem isso a revogação seria simbólica. O relato de **evento
   adverso permanece aberto** (segurança acima de tudo) — a guarda é só no início de sessão.
3. **Retirada ≠ eliminação (separação de direitos):** retirar o consentimento **não apaga** o dado
   de pesquisa já coletado. A **eliminação** (Art. 18) é direito distinto, operado pela rota de
   admin (ADR-066) e mediado pelo canal do Encarregado (item D4, institucional); o dado de pesquisa
   já coletado é **retido pseudonimizado** (exceção de pesquisa, ADR-066) e a auditoria nunca é
   apagada. Essa separação é a conduta correta para pesquisa com CEP (retenção do já coletado).
4. **Idempotência por estado:** retirar de novo → **409** (já `withdrawn`). Sem consentimento
   prévio aceito, ainda encerra a participação (revoga 0 registros) — o titular pode optar por sair.
5. **Sem migração:** usa colunas existentes (`consent_record.revoked_at`, `participant.status`).

## Alternativas consideradas
- **Retirada que também elimina a PII.** Rejeitada como padrão: conflar revogação com eliminação
  destrói dado que o protocolo/CEP pode exigir reter (já coletado) e mistura dois direitos
  distintos. A eliminação segue disponível como ação própria (ADR-066).
- **Só marcar `status=withdrawn` sem carimbar `revoked_at`.** Rejeitada: perderia a trilha de
  *qual* consentimento foi revogado e quando; `revoked_at` é a evidência que o modelo previu.
- **Não bloquear sessões.** Rejeitada: revogação sem efeito não é revogação. Guarda no início de
  sessão (a intervenção experimental) é o enforcement mínimo credível.
- **Permitir re-consentir (desfazer) self-service.** Adiada: no piloto a retirada é terminal; um
  fluxo de re-adesão exigiria decisão de protocolo/CEP.

## Consequências
- **Positivas:** o titular exerce a revogação **por conta própria** (fecha B3), com efeito real
  (sessões bloqueadas) e trilha auditável; reduz a dependência do canal manual para este direito.
  Suíte 273 → 281 (+8). Sem migração.
- **Custo/tradeoff:** a guarda de participação hoje cobre o **início de sessão**; outros autorrelatos
  (diário/instrumentos) não são bloqueados — aceitável (baixo risco; o evento adverso deve mesmo
  permanecer aberto). Refinar as guardas por endpoint fica como evolução se o CEP pedir.
- **Pendências:** **D4** (canal do Encarregado + prazo de resposta) segue institucional; texto do
  TCLE deve descrever retirada e retenção do já coletado (assessoria/CEP); re-adesão self-service se
  o protocolo permitir.

## Conformidade
CI verde exige `tests/test_consent_withdraw.py`: retirar marca `revoked_at` + `withdrawn` (200);
**bloqueia novas sessões** (403); retirar de novo → 409; auditado sem PII (só nº revogado);
**retém** o registro de pesquisa (não elimina); sem consentimento prévio ainda encerra; staff não
usa a rota do titular (403); sem token (401). `test_consent.py`/`test_sessions.py` seguem verdes.
Auditoria append-only preservada; sem PII em log (inegociável #6).
