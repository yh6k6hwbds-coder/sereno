# ADR-051 — Relato de evento adverso com sinalização de atenção

- **Status:** Aceito
- **Data:** 2026-07-04
- **Etapas relacionadas:** 1 (segurança/desfechos), 5 (backend)
- **Contexto de origem:** 11ª fatia (captura de segurança no backend)

## Contexto
Segurança é desfecho primário do piloto. O relato de evento adverso não pode ser apenas
um registro passivo: eventos moderados/graves exigem atenção, e o participante deve sempre
ser orientado a buscar cuidado — coerente com "ferramenta complementar".

## Decisão
1. **`POST /v1/adverse-events`** (participante autenticado, RBAC `ae:write`): tipo, gravidade
   (mild/moderate/severe), conduta e vínculo OPCIONAL a uma sessão do próprio participante
   (IDOR → 404).
2. **Sinalização `requires_attention`** para moderado/grave, acionando um **gancho de
   notificação da equipe** (`notify_team`, hoje log; PROD: alerta real).
3. **Orientação sempre presente** na resposta; para grave, orientação **urgente** (192/CVV 188).
4. Erros em problem+json; validação de faixa/gravidade (422).

## Alternativas consideradas
- **Registrar sem sinalização.** Rejeitada: perderia o valor de segurança em tempo hábil.
- **Acionar a notificação no cliente.** Rejeitada: a decisão de atenção é do servidor
  (fonte única, auditável), não do app.
- **Detalhar condutas clínicas na resposta.** Rejeitada: o app não prescreve; orienta a buscar
  profissional (limite de escopo).

## Consequências
- **Positivas:** captura de segurança íntegra (sem IDOR), com atenção sinalizada e orientação
  de cuidado; pronta para o monitoramento do estudo e para relato ao CEP.
- **Pendências:** integração real de notificação (e-mail/SMS/on-call); painel de eventos para a
  equipe; possível classificação de causalidade/expectativa (a definir com a orientadora).

## Conformidade
CI exige a suíte de eventos adversos passando (sinalização leve/moderado/grave, gancho de
notificação, IDOR, validação, RBAC).
