# ADR-073 — Telas de captura de desfechos (B2–B6) com componentes reutilizáveis

- **Status:** Aceito (código; validação via CI `app`)
- **Data:** 2026-07-05
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 3 (UX/cliente), 4 (instrumentos)
- **Contexto de origem:** Fatias B2–B6 do ROADMAP
- **Relaciona-se com:** ADR-008/044 (GAD-7/instrumentos versionados), ADR-051 (evento adverso), ADR-055 (fundação do cliente)

## Contexto
Faltavam as telas de coleta: linha de base (B2), pós-sessão (B3), diário (B4), seguimento (B5)
e evento adverso (B6). Todas são formulários que enviam **itens brutos** à API (o escore é
calculado e versionado **no servidor**). Escrevê-las sem SDK Flutter local e com o CI Flutter
**bloqueante** pede minimizar a superfície não testável.

## Decisão
1. **Componentes reutilizáveis** (`lib/shared/`): `LikertQuestion` (uma pergunta em escala),
   `LikertGroup` (GAD-7 = 7×0–3; SUS = 10×1–5) e `PsqiSection` (itens do PSQI). Cada componente
   notifica o pai com os valores e se está **completo** (habilita o envio).
2. **`OutcomesRepository`** concentra os 5 `POST` autenticados (baseline, survey, diary,
   followup, adverse-events) — a lógica de rede fica **fora das telas** e é testada com `MockClient`.
3. **Enunciados PRÓPRIOS e curtos** — nunca o texto verbatim dos instrumentos validados
   (decisão inegociável). O cliente **não** exibe o escore de forma alarmante (só confirma o registro).
4. **Simplificações do piloto** (registradas): `hours_slept`/`hours_in_bed` do PSQI são números
   diretos (não time-pickers deitar→levantar); o `blinding_guess` (B5) captura só o palpite —
   a UI nunca sugere o braço.

## Alternativas consideradas
- **Uma tela monolítica por instrumento (sem componentes).** Rejeitada: duplicaria GAD-7/PSQI
  entre B2 e B5 e aumentaria a superfície de código não testável.
- **Calcular escore no cliente para feedback imediato.** Rejeitada: o escore é versionado no
  servidor (fonte única); o cliente só envia itens brutos.
- **Time-pickers para o PSQI.** Adiada: números diretos reduzem risco de UI não verificável;
  refinar depois.

## Consequências
- **Positivas:** 5 telas com pouco código próprio cada (compõem os componentes); a lógica de
  rede é coberta por testes (MockClient) — de-riscando B3–B6, que reusam o repositório testado.
- **Custo/tradeoff (visão do analista):**
  - **Telas não rodadas localmente** (sem SDK Flutter): a renderização/validação é gate do job
    `app` do CI (agora bloqueante). Um erro de UI aparece como CI vermelho — sinal para ajustar.
  - **Validação no cliente é de completude** (todos os itens respondidos); as faixas/regras finais
    são do servidor (422). O cliente evita enviar incompleto.
  - **PSQI simplificado** (números diretos) pode diferir levemente do fluxo clínico ideal; aceitável
    no piloto, a refinar.
- **Pendências:** time-pickers do PSQI; acessibilidade (leitor de tela nos chips); i18n; empacotar
  as fontes; migrar a injeção para Riverpod (ADR-055).

## Conformidade
Testes em `app/test/`: `outcomes_repository_test.dart` prova que cada método posta no endpoint
certo, autenticado, com o corpo esperado (baseline/survey/diary/followup/adverse); um widget test
do `LikertQuestion`. As telas são validadas pelo job `app` do CI (`flutter analyze` + `flutter
test`), agora **bloqueante** — não rodado localmente (sem SDK Flutter na máquina de dev).
