# ADR-104 — Blocos permutados de tamanho variável (4 e 6)

- **Status:** Aceito
- **Data:** 2026-08-31
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 5 (backend), 7 (análise)
- **Contexto de origem:** item **G7** do `docs/ROADMAP.md`.
- **Relaciona-se com:** ADR-045 (randomização e alocação oculta), ADR-100 (parâmetros do
  protocolo aprovado).

## Contexto

O ADR-045 implementou randomização em blocos permutados com **tamanho fixo**, configurável por
`ALLOCATION_BLOCK_SIZE` (padrão 4). O protocolo aprovado especifica outra coisa: blocos
permutados de tamanho **variável, 4 e 6**.

A diferença não é decorativa. Com bloco de tamanho conhecido, quem acompanha as alocações
anteriores **deduz** as últimas posições de cada bloco: num bloco de 4 em que já saíram A, B, A,
a próxima é necessariamente B. Isso não quebra o cegamento do participante — ele nunca vê o
braço — mas quebra a **ocultação da alocação** para quem inscreve, que é precisamente o que a
randomização em blocos existe para proteger. Um recrutador que consiga prever a próxima
alocação pode, mesmo sem má-fé, escolher quem convida naquele dia.

Havia ainda um detalhe de implementação atrapalhando: `block_of(index, block_size)` era
aritmética pura (`index // block_size`). Com tamanho variável, o número do bloco passa a exigir
percorrer a mesma sequência determinística.

## Decisão

1. **`generate_sequence`, `arm_for_index` e `block_of` passam a receber uma LISTA de tamanhos
   permitidos** (`block_sizes`), não um número. O tamanho de cada bloco é sorteado **na mesma
   sequência determinística**, a partir da mesma semente: a reprodutibilidade — que o CEP e o
   *data lock* exigem — fica intacta, e a fronteira do bloco deixa de ser conhecida.
2. **`assign(index, block_sizes, seed) -> (braço, bloco)`** é a função nova, e é o que o serviço
   de alocação usa. Calcular braço e bloco em duas chamadas geraria a sequência duas vezes.
3. **Com um único tamanho permitido, nenhum sorteio é consumido.** `generate_sequence(n, (4,), seed)`
   produz exatamente a mesma sequência que a versão pré-G7 produzia com bloco fixo 4. Importa
   porque a semente é custodiada e o hash dela é conferido no fechamento do banco: uma semente já
   usada não pode passar a significar outra sequência por causa de uma refatoração.
4. **A configuração vira `ALLOCATION_BLOCK_SIZES`** (`"4,6"` por padrão), em `core/config.py`, ao
   lado das demais invariantes do estudo — é parâmetro de protocolo, não constante de router.
5. **A variável antiga (`ALLOCATION_BLOCK_SIZE`) é recusada em voz alta.** Se estiver definida, a
   leitura da config levanta `InsecureConfigError`.

## Alternativas consideradas

- **Continuar com bloco fixo e documentar o desvio.** Rejeitada: é um parâmetro do protocolo
  aprovado, e o desvio precisaria ir ao CEP como emenda — sem ganho nenhum em troca.
- **Sortear o tamanho com um gerador separado.** Rejeitada: duas fontes de aleatoriedade
  significam duas coisas a custodiar e a conferir no *data lock*. A mesma semente basta.
- **Ignorar `ALLOCATION_BLOCK_SIZE` em silêncio.** Rejeitada: um ambiente que a define teria a
  randomização trocada sem ninguém perceber. A sequência de alocação é auditada; mudá-la
  caladamente é o pior desfecho possível.
- **Guardar o tamanho do bloco na tabela `allocation`.** Rejeitada: seria dado derivável da
  semente, e mais uma coluna por onde a previsão poderia vazar para quem lê o banco.

## Consequências

- **Positivas:** a alocação passa a corresponder ao protocolo; a última posição de cada bloco
  deixa de ser previsível; a reprodutibilidade e a auditabilidade permanecem exatamente como
  estavam (mesma semente → mesma sequência).
- **Custo:** a assinatura de `block_of` mudou (agora precisa da semente); `Allocation.block`
  passa a numerar blocos de tamanhos diferentes — quem ler a coluna não deve inferir a posição
  dentro do bloco a partir dela. +6 testes.
- **Sem migração:** nada muda no schema.
- **⚠️ Balanceamento 1:1 só é garantido nas fronteiras de bloco**, como já era. Com blocos de 4 e
  6, a diferença máxima entre braços a qualquer momento é 3 (metade do maior bloco), contra 2
  antes. É a contrapartida esperada de blocos maiores e está dentro do que o protocolo pede.

## Conformidade

CI verde exige `backend/tests/test_allocation.py` (reprodutibilidade, balanceamento por bloco
fechado, o tamanho variando de fato, a sequência de tamanho único preservada, `assign` de acordo
com `generate_sequence`, validação dos tamanhos) e `backend/tests/test_config_guard.py`
(padrão `(4, 6)`, parsing, recusa de valor inválido e da variável antiga).
