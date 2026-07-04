# ADR-046 — Sessão e resolução cega do áudio (ativo/sham)

- **Status:** Aceito
- **Data:** 2026-07-03
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 2 (player-instrumento), 5 (backend), 6 (recomendador)
- **Contexto de origem:** 6ª fatia vertical (a que fecha o ciclo do participante)

## Contexto
A sessão é onde a alocação oculta "fecha o ciclo": o participante usa o app sem jamais
saber seu braço, mas recebe o áudio correto (ativo/sham). Precisa entregar o arquivo certo
sem vazar a condição e registrar telemetria de adesão.

## Decisão
1. **Fluxo em duas etapas**: `POST /v1/sessions` (iniciar) e `POST /v1/sessions/{id}/complete`
   (encerrar, com duração efetiva e interrupções).
2. **Resolução INTERNA do braço→condição**: o servidor chama `resolve_arm` (A/B) e traduz
   para active/sham por uma **chave selada** (`ARM_CONDITION_MAP`) que vive **fora do banco**
   (variável de ambiente / cofre). Nenhuma consulta liga participante→condição.
3. **Handle neutro + hash opaco**: a resposta traz apenas `session_id`, `protocol_handle`
   (a **banda** — idêntica nos dois braços) e `content_hash` (opaco). Nunca braço, condição,
   `beat_hz` ou banda-específica-de-condição. A banda NÃO revela o braço (ativo e sham
   compartilham a banda; diferem no `beat_hz`).
4. **Fidelidade (inegociável)**: verificação de fones é pré-condição no servidor (422 se
   ausente); o cliente **reproduz o arquivo bit-a-bit** (referenciado pelo `content_hash`),
   sem sintetizar/processar.
5. **Proteção contra IDOR**: encerrar exige que a sessão seja do participante autenticado (404 caso contrário).

## Alternativas consideradas
- **Devolver ao cliente a banda/beat ou um handle que codifique a condição.** Rejeitada:
  vazaria o braço. O handle é a banda (neutra); a condição fica no servidor.
- **Guardar o mapa A/B→condição no banco.** Rejeitada: a chave é selada e custodiada fora do
  dado operacional; guardá-la no banco a exporia a quem tem acesso de leitura.
- **Sintetizar o áudio no cliente.** Rejeitada (Etapa 2): quebra a fidelidade e a validação por FFT.

## Consequências
- **Positivas:** cegamento preservado ponta a ponta (testado: braços opostos → respostas de
  mesma forma; servidor resolve áudios diferentes internamente); telemetria de adesão registrada.
- **Custo/tradeoff (visão do analista):** `session.protocol_uuid` aponta para um protocolo cujo
  `beat_hz` revela a condição. Isso NÃO vaza por API (nenhum endpoint expõe), mas exige
  **controle de acesso ao banco** e views de pesquisa que não juntem participante→`beat_hz`
  até o desbloqueio. Registrado como pendência de governança de dados.
- **Pendências:** custódia formal da chave `ARM_CONDITION_MAP`; a biblioteca de áudio real
  (multi-banda) e a seleção via recomendador (Etapa 6) integram-se nesta rota depois.

## Conformidade
CI verde exige a suíte de sessão passando, incluindo o teste de **não-vazamento do braço**
(respostas indistinguíveis) e a **resolução interna correta** (A→ativo, B→sham).
