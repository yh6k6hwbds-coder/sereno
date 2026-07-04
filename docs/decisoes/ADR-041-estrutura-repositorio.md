# ADR-041 — Estrutura do repositório e fronteiras de módulo

- **Status:** Aceito
- **Data:** 2026-07-03
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 1 (arquitetura), 3 (cliente), 5 (backend/segurança)
- **Substitui/atualiza:** — (primeiro ADR pós-planejamento; consolida ADR-001..040)

> Este ADR também é o **modelo** para os próximos. Copie a estrutura de seções
> (Contexto → Decisão → Alternativas → Consequências → Conformidade) ao criar `ADR-042`, etc.

## Contexto

Concluído o planejamento (Etapas 1–7), é preciso um layout de repositório único
que: (a) seja legível por ferramentas de código (Claude Code lê Markdown, não `.docx`);
(b) espelhe o **monólito modular** decidido na Etapa 5 (ADR-001) e o cliente Flutter
por features (Etapa 3); (c) preserve as **decisões inegociáveis** (cegamento, fidelidade
do estímulo, ocultação de alocação) contra erosão silenciosa em sessões futuras; e
(d) mantenha histórico auditável (relevante para o CEP e para eventual proteção de PI).

Restrição de fundo (transversal a todo o projeto): **escopo travado no MVP do piloto de
4 semanas** — a estrutura deve permitir crescer, não induzir a construir a plataforma
maximalista agora.

## Decisão

Adotar um monorepo com quatro domínios de topo e a documentação como fonte de verdade:

- `docs/` — Markdown como fonte de verdade; `.docx` apenas como anexo (CEP/relatório) em
  `docs/anexos-docx/`; ADRs em `docs/decisoes/`.
- `app/` — Flutter, organizado **por feature** (`lib/features/<domínio>`), com `core`,
  `shared` (design system "Sereno") e `services`.
- `backend/` — FastAPI como **monólito modular**, com fronteiras explícitas em
  `app/modules/<domínio>` (identity, consent, allocation, sessions, instruments,
  recommender, research, audit) e infraestrutura em `app/core`.
- `audio-pipeline/` — síntese offline + validação FFT (o estímulo é instrumento).
- `shared-contracts/openapi.yaml` — **fonte de verdade da API**; tipos do cliente são
  gerados a partir dele.
- `CLAUDE.md` na raiz — briefing permanente lido pelo Claude Code a cada sessão.
- `.github/workflows/ci.yml` — CI que **materializa** as decisões inegociáveis: a bateria
  de **FFT** e a **validação do contrato OpenAPI** rodam e bloqueiam merge.

Regra de fronteira: **nenhum módulo expõe o braço (ativo/sham)**; o mapa handle→condição
vive só no servidor e a chave A/B fica selada (ADR-007, 015, 027).

## Alternativas consideradas

1. **Pasta única de `.docx` (proposta inicial do mantenedor).** Rejeitada como fonte de
   verdade: `.docx` não é diffável nem versionável de forma útil, e o Claude Code o
   reprocessa a cada sessão. Mantido apenas como anexo para humanos/CEP.
2. **Repositórios separados para app, backend e áudio (polyrepo).** Rejeitado nesta fase:
   overhead de coordenação sem ganho real para um time de um desenvolvedor; o monorepo
   mantém contrato, schema e docs sincronizados. Reavaliar se/quando houver múltiplos times.
3. **Estrutura por camada técnica no backend (controllers/services/models globais).**
   Rejeitada: dilui as fronteiras de domínio e facilita acoplamento; a organização por
   **módulo de domínio** contém melhor as mudanças e reflete os ADRs.
4. **Misturar neste repo o app de educação médica (monitorias).** Rejeitado: é outro
   produto, com outro escopo — merece repositório e `CLAUDE.md` próprios. Misturar repetiria
   o erro de escopo que o projeto evita por princípio.

## Consequências

**Positivas**
- Contexto legível e estável para o Claude Code; decisões inegociáveis viram *trava de CI*,
  não recomendação.
- Mudanças ficam contidas por módulo; contrato e schema centralizados evitam divergência
  front/back.
- Histórico auditável (autoria limpa) — apoia CEP e PI.

**Negativas / custos**
- Exige disciplina de manter Markdown e `.docx` coerentes (mitigado: `.docx` é derivado,
  não co-fonte).
- Monorepo pode crescer; se surgirem times independentes, migrar módulos para serviços
  (previsto em ADR-001).

**Neutras**
- Gera tipos do cliente a partir do OpenAPI (passo extra no fluxo, com ganho de consistência).

## Conformidade (como verificar)

- CI verde exige: bateria FFT aprovada, OpenAPI válido, testes do backend e `flutter analyze`.
- Revisão de PR checa: nenhum segredo no repo, nenhum PII em log, nenhuma resposta de API
  que exponha o braço, contrato atualizado antes do código.
- Qualquer violação de decisão inegociável deve vir acompanhada de **novo ADR** e aviso ao
  mantenedor (regra do `CLAUDE.md`).
