# ADR-045 — Randomização em blocos e alocação oculta

- **Status:** Aceito
- **Data:** 2026-07-03
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 1, 2, 5 (decisões inegociáveis de cegamento)
- **Contexto de origem:** 5ª fatia vertical (o coração metodológico)

## Contexto
A randomização e a ocultação da alocação são o núcleo da validade interna do ensaio e o
ponto mais escrutinado pelo CEP. Precisam ser reprodutíveis (auditáveis) e à prova de
vazamento do braço — por construção, não por disciplina.

## Decisão
1. **Randomização em blocos determinística** a partir de uma **semente** (segredo
   custodiado em cofre, fora do dado operacional). A mesma semente recria a mesma
   sequência (reprodutibilidade auditável); blocos de tamanho par garantem 1:1.
2. **Três camadas de ocultação**:
   - `arm_coded` (A/B) — o que o participante recebe, **codificado**, no banco operacional.
   - **Handle neutro** — o cliente nunca recebe A/B; a resolução handle→áudio é do servidor.
   - **Chave A/B → ativo/sham** — mantida **selada**, fora deste serviço; nenhuma permissão a expõe.
3. **O serviço de alocação não sabe qual braço é ativo/sham** — só distribui A/B. Assim o
   vazamento é impossível por construção.
4. **Resposta neutra, inclusive para o staff**: `POST /v1/allocation` devolve apenas
   `{status, block}` — nunca o braço (ocultação da alocação também de quem inscreve).
5. **`resolve_arm` é interno** (resolução do áudio da sessão) e **jamais** exposto por API.
6. **`sequence_seed_ref`** (hash não reversível da semente) é gravado para auditar QUAL
   semente foi usada, sem armazenar a semente; no data lock, o hash da semente custodiada deve bater.

## Alternativas consideradas
- **Randomização simples (moeda) sem blocos.** Rejeitada: pode desbalancear em N pequeno.
- **Guardar a semente no banco.** Rejeitada: a semente é o segredo; guarda-se só a referência (hash).
- **Retornar o braço ao staff na inscrição.** Rejeitada: quebraria a ocultação da alocação.
- **Minimização adaptativa.** Adiada: mais complexa; desnecessária para um piloto de viabilidade.

## Consequências
- **Positivas:** validade interna protegida; reprodutibilidade auditável; vazamento do braço
  impossível por construção (testado: nenhum endpoint expõe A/B).
- **Custo/tradeoff (concorrência):** a ordinalidade vem de COUNT(*); inscrições simultâneas
  podem colidir de índice. No piloto, **serializar a inscrição**; versão robusta usa contador
  com bloqueio (SELECT ... FOR UPDATE) ou sequência dedicada. Registrado como limitação.
- **Pendências:** custódia formal da semente e da chave A/B→condição (quem, como, registro) no
  protocolo/CEP; a camada de resolução handle→áudio será implementada na fatia de sessão.

## Conformidade
CI verde exige a suíte de alocação passando, incluindo os testes de **não-vazamento do braço**
(endpoint e /research) e de **reprodutibilidade** da sequência.
