# ADR-111 — O registro por sessão passa a ser legível (e o cegamento decide o que sai)

- **Status:** Aceito
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 5 (backend), 7 (operação do estudo)
- **Contexto de origem:** item **H2** do `docs/ROADMAP.md`, aberto pelo ADR-110.
- **Relaciona-se com:** ADR-107 (as colunas que o protocolo manda registrar), ADR-110 (a mesma
  forma, para eventos adversos), ADR-075 (descegamento com dois admins), ADR-096 (operação por API).

## Contexto

O ADR-107 releu "Registro e monitoramento" do protocolo contra o schema e achou **três dos seis
itens sem coluna**. As colunas entraram — duração das interrupções, volume médio e máximo,
relaxamento 0–10 — e **nenhuma delas era legível**. Ficavam no banco e saíam, no máximo,
agregadas no relatório de análise.

"Manter registro" é obrigação de manter dado **recuperável por quem responde pelo estudo**. Dado
que só o `psql` alcança não está mantido nesse sentido: não dá para conferir uma sessão específica
quando o CEP pergunta, nem para ver quem começou e não terminou.

E havia uma dívida menor, mas mais constrangedora: **o contrato prometia `GET /sessions`**
("listar sessões do participante") e a rota não existia. O módulo tinha o `POST`, o `complete`, o
áudio e o questionário. Um cliente escrito a partir do contrato receberia 405.

## Decisão

**Duas leituras, porque são duas perguntas diferentes** — e, sobretudo, porque o que cada uma
pode mostrar é diferente.

**`GET /v1/sessions`** (participante) — o próprio histórico. O filtro por `participant_id` vem do
**token**, nunca de parâmetro: não há como pedir as sessões alheias, e o IDOR é impossível por
omissão, não por checagem.

**O histórico do participante não repete identificador do áudio** (`content_hash`, handle).
No início da sessão o cliente precisa deles para buscar o arquivo; num histórico, seriam dois
identificadores **estáveis** que dois participantes poderiam comparar entre si — e dois valores
diferentes revelariam, sem mais nada, que estão em braços diferentes. O histórico responde "o que
eu já fiz", não "o que eu ouvi".

**`GET /v1/sessions/registry`** (equipe, `research:read`) — o registro do protocolo,
pseudonimizado por `study_code`, com as seis colunas do ADR-107 mais adesão e verificação de fones.
Filtro opcional por `study_code`; código inexistente devolve **lista vazia, não 404** — "este
participante tem sessões?" tem "nenhuma" como resposta legítima.

**Nada do protocolo de áudio sai daqui:** nem `protocol_uuid`, nem `protocol_hash`, nem a banda.
Não é excesso de zelo. **Só existem dois protocolos, um por braço.** Qualquer identificador estável
do áudio particiona os participantes em dois grupos; quem lê não saberia qual grupo é o ativo, mas
**saber quem está com quem já quebra o cegamento da análise**. Descegar tem rito próprio e exige
dois admins distintos (ADR-075) — não pode acontecer de lado, por uma listagem operacional. Há
teste que varre a resposta crua atrás dessas palavras, e outro que confirma que os dois braços
saem com exatamente as mesmas chaves.

**Sessões abertas aparecem**, com os campos do fim nulos. É o que permite ver quem começou e não
terminou — justamente o caso que interessa acompanhar, e que uma listagem só de sessões concluídas
esconderia.

**Fica sob `/sessions/registry`, não em `/research`.** É o registro operacional da sessão, não a
análise: `/research` produz relatório cego e agregados: aqui se olha uma sessão de uma pessoa.

## Consequências

- O H2 fecha e a deriva do contrato some: `GET /sessions` existe e faz o que a página dizia.
- A equipe consegue responder "o que aconteceu na sessão de 12/03 da P-014?" sem abrir o banco.
- O cegamento fica **testado** em mais um ponto, com um item que não existia: nenhuma listagem
  operacional pode agrupar participantes por áudio.
- `paused_seconds`, `gain_mean`, `gain_peak` e `relaxation_0_10` saem **anuláveis**, porque são:
  um cliente antigo (ou um reenvio da fila offline) encerra a sessão sem eles, e a ausência é
  informação — o ADR-107 decidiu assim e a leitura não pode fingir o contrário.

## Achado registrado, não corrigido aqui

**`GET /v1/research/participants` é um stub que devolve `{"items": [], "next_cursor": null}`** com
um `TODO` no corpo. Não é uma rota faltando: é uma rota que **responde errado em silêncio** — quem
a chamar conclui que não há participantes. Está fora do escopo do H2 (é a listagem de
participantes, não de sessões) e virou o item **H6** do roadmap, para ser corrigida ou removida.
Escolher entre as duas coisas é decisão, não digitação: se a listagem cega de participantes for
mesmo necessária, precisa de braço codificado e paginação; se não for, a rota deve sair do
contrato.

## Alternativas consideradas

**Uma rota só, mudando o conteúdo conforme o papel.** Rejeitada: a diferença entre as duas não é
de permissão, é de **conteúdo** — uma esconde o áudio do participante, a outra esconde o áudio da
equipe, e por razões diferentes. Uma rota que devolve formas distintas conforme quem chama é onde
esse tipo de regra se perde numa refatoração.

**Expor `protocol_hash` para a equipe "porque é opaco".** Rejeitada: opaco não é o mesmo que
inútil. Ele é **estável por braço**, e estabilidade é tudo de que o agrupamento precisa.

**Devolver só sessões concluídas.** Rejeitada: quem começou e não terminou é exatamente o caso que
a equipe precisa ver — é o sinal precoce de abandono que alimenta a regra da 2ª semana (ADR-106).
