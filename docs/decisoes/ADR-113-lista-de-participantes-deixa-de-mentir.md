# ADR-113 — A lista de participantes deixa de responder errado em silêncio

- **Status:** Aceito
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend), 7 (operação do estudo)
- **Contexto de origem:** item **H6** do `docs/ROADMAP.md`, aberto pelo achado do ADR-111.
- **Relaciona-se com:** ADR-111 e ADR-110 (as outras leituras da Fase H), ADR-075 (chave selada
  A/B→condição), ADR-106 (adesão e dose em `core/protocol.py`).

## Contexto

`GET /v1/research/participants` existia, estava no contrato, respondia **200** — e devolvia:

```python
    # TODO (fatia vertical): listar com braço CODIFICADO (A/B) e paginação por cursor.
    return {"items": [], "next_cursor": None}
```

**Isso é pior que uma rota faltando.** Uma rota ausente dá 404 e quem chama percebe na hora. Esta
respondia com sucesso e uma lista vazia: quem a consultasse concluiria que **não há participantes
no estudo**, e nada indicaria o contrário. O `TODO` estava no código-fonte, onde a equipe que
opera o estudo não olha.

O achado saiu do ADR-111, ao mapear o que a equipe consegue ler. Registrei ali como decisão
pendente — implementar ou remover do contrato —, porque as duas são defensáveis quando não se sabe
se a listagem é necessária.

## Decisão

**Implementar, exatamente na forma que o contrato já prometia.** Não era uma escolha em aberto: o
`ResearchParticipant` do `openapi.yaml` já especificava `study_code`, `arm_coded` (A/B),
`adherence_pct` e `adverse_events`, e o `TODO` no corpo dizia "braço codificado e paginação por
cursor". A intenção estava documentada em dois lugares; faltava o código. Remover a rota seria
descartar capacidade que o roadmap e o contrato já tinham decidido querer.

**Novo `modules/research/participants_service.py`**, separado do router como os outros serviços de
pesquisa — a consulta tem regra (adesão, contagens, paginação) e regra com teste não vive em
handler.

**As contagens saem por subconsulta, não por `join`.** Juntar sessões **e** eventos adversos na
mesma linha multiplicaria uma pela outra: quem tivesse 20 sessões e 2 eventos apareceria com 40 de
cada, e a adesão sairia multiplicada por um fator inteiro. É o tipo de defeito que sobrevive a uma
revisão distraída porque **o número continua parecendo plausível** — 40 sessões não gritam. Há
teste que fixa 3 e 2, e falharia com 6 e 6.

**Paginação keyset em `(enrolled_at, id)`**, igual à da trilha de auditoria. O desempate por `id`
não é preciosismo: dois participantes inscritos no mesmo instante (um mutirão de triagem é
exatamente isso) fariam a página repetir uma linha e pular outra. Há teste com cinco inscrições no
mesmo `enrolled_at` que percorre todas as páginas e exige o conjunto completo, sem repetição.

**O braço sai codificado e nunca traduzido.** A/B não dizem qual é o ativo, e é assim que a área
de pesquisa já enxerga o estudo (o relatório de análise reporta por braço codificado). O mapa
A/B→condição segue selado até o *data lock*, com dois admins (ADR-075).

**Quem ainda não foi randomizado aparece com `arm_coded: null`.** Inscrito e não alocado é estado
real do estudo — é a fila de espera da randomização. Esconder essas linhas faria a lista mentir de
outro jeito.

## Consequências

- A Fase H fica com as quatro leituras que a equipe precisa: eventos adversos (ADR-110), registro
  por sessão (ADR-111), participantes (esta) e as que já existiam (`/referrals`,
  `/discontinuations`).
- O H4 (receituário de operação) ganha o que faltava para ser escrito: agora há uma lista de
  participantes de verdade para o receituário mandar consultar.
- Um `TODO` que respondia 200 saiu do sistema. Vale a varredura: qualquer outro *stub* que devolva
  sucesso com corpo vazio tem o mesmo defeito, e não aparece em teste nenhum — testes tendem a
  afirmar o formato da resposta, e o formato estava certo.

## Nota sobre a varredura de cegamento nos testes

O teste que varre a resposta crua atrás de vazamento **deixa `active` de fora, de propósito**:
aqui a palavra é o `status` do participante (inscrito e ativo), não a condição do braço. Varrer
por ela reprovaria a resposta correta — e um item que grita no caso certo deixa de ser lido quando
grita no caso errado. A varredura fica com `sham`, `condition`, `protocol`, `content_hash` e
`beat_hz`, que não têm outro significado neste contexto.

## Alternativas consideradas

**Remover a rota do contrato.** Era a outra metade da decisão registrada no ADR-111. Rejeitada: a
listagem é necessária para operar o estudo — sem ela não há como responder "quem está inscrito, em
que pé está cada um" sem abrir o banco, que é exatamente o problema que a Fase H fecha.

**Reaproveitar `/research/analysis`.** Rejeitada: o relatório é agregado por braço e existe para a
análise. Aqui se olha **pessoa a pessoa**, que é operação, não análise.

**Paginar por `offset`.** Rejeitada pelo motivo de sempre num estudo que ganha participantes
enquanto se lê a lista: `offset` pula e repete linhas quando o conjunto muda entre páginas. O
keyset já era o padrão da casa.
