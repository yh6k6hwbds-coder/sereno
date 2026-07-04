# ADR-057 — Triagem/elegibilidade e gate do funil de inscrição

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend), 7 (análise/CONSORT)
- **Contexto de origem:** Fatia C2 do ROADMAP (ordena o funil de inscrição)
- **Relaciona-se com:** ADR-045 (alocação oculta), ADR-056 (auditoria), ADR-036 (regras versionadas)

## Contexto
Faltava o **1º passo do funil**: a triagem que decide a elegibilidade e, com o consentimento,
habilita a alocação. Sem isso, era possível alocar um participante não triado/não consentido —
o que comprometeria a integridade do estudo e o registro CONSORT do fluxo de inscrição.

## Decisão
1. **`POST /v1/screening`** (staff `enroll:write`): o servidor calcula a elegibilidade por uma
   **regra determinística e versionada** — elegível ⇔ **todas as inclusões verdadeiras** E
   **nenhuma exclusão presente**. Guarda `criteria` (com `version`), `eligible` e `symptoms`
   opcionais; **audita** a decisão (sem PII, via C1). **Uma triagem por participante** (409 se
   já triado).
2. **Fronteira honesta:** as **chaves concretas** dos critérios (idade, comorbidades, etc.) vêm
   do **protocolo aprovado pelo CEP** — o servidor aplica apenas a meta-regra
   (inclusão-todas / exclusão-nenhuma), sem embutir limiares clínicos que exigiriam base na
   literatura.
3. **Gate na alocação:** `enrollment_blocker` exige **triagem elegível** + **consentimento
   aceito (não revogado)** antes de alocar; caso contrário, **409** com o motivo. Ordena o funil
   `triagem → elegibilidade → consentimento → alocação`.
4. **Sem migração:** a tabela `screening` já existia; a versão da regra vai dentro do JSON
   `criteria` (sem alterar o schema).

## Alternativas consideradas
- **Cliente envia o booleano `eligible` direto.** Rejeitada: sem transparência nem consistência;
  a regra no servidor é auditável e reprodutível (coerente com ADR-036).
- **Embutir limiares clínicos no servidor** (ex.: faixa etária, escores de corte). Rejeitada
  agora: critérios clínicos exigem base na literatura e no protocolo do CEP; o servidor fica com
  a lógica, não com o conteúdo clínico (evita *overreach* e desalinhamento com o CEP).
- **Permitir re-triagem.** Adiada: uma decisão por participante mantém o funil simples e
  auditável; correção de triagem é processo à parte (fora do escopo do piloto).
- **Bloquear via 422 em vez de 409.** Rejeitada: o bloqueio é conflito com o **estado** de
  inscrição (pré-condição não satisfeita), não erro de validação do corpo → 409 é mais preciso.

## Consequências
- **Positivas:** o funil de inscrição fica ordenado e imposto pelo servidor; a decisão de
  elegibilidade é transparente/versionada e auditada; a alocação só ocorre para quem está apto.
  Suíte: 98 → 111 testes.
- **Custo/tradeoff (visão do analista):**
  - **Critérios genéricos:** a lista concreta é responsabilidade do protocolo; `inclusion`/
    `exclusion` vazios tornam o participante **vacuamente elegível** — o front/staff deve enviar
    os critérios reais. Documentado.
  - **Gate acopla** a alocação ao estado de triagem/consentimento (intencional; é o funil).
  - **Consentimento:** o gate exige `accepted=True` e `revoked_at` nulo; a revogação de
    consentimento (fluxo LGPD/D4) deve, portanto, também bloquear novas alocações — coerente.
- **Pendências:** correção/re-triagem auditada; integrar a triagem à captura de contato (C4) e à
  gestão de staff (C3) no fluxo de inscrição da UI; expor a lista de participantes triados na
  área de pesquisa.

## Conformidade
CI verde exige `tests/test_screening.py`: elegível ⇔ inclusões-todas/exclusão-nenhuma; triagem
registrada e **auditada sem PII**; duplicata → 409; **alocação bloqueada** antes da triagem, se
inelegível, ou sem consentimento (409 com motivo) e **liberada após o funil completo**; negações
401/403/404/422. Os testes de alocação/auditoria foram atualizados para semear o funil.
