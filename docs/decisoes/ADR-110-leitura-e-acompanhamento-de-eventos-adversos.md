# ADR-110 — Eventos adversos: a equipe passa a ler o que só sabia escrever

- **Status:** Aceito
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado e do dossiê ao CEP
- **Etapas relacionadas:** 5 (backend), 7 (operação do estudo)
- **Contexto de origem:** pendência do **ADR-051** ("painel de eventos para a equipe"), que nunca
  virou item de roadmap, e a lacuna nº 4 da auditoria operacional de 2026-08-29.
- **Relaciona-se com:** ADR-051 (relato e sinalização), ADR-093 (alerta por e-mail),
  ADR-102 (`GET /referrals`, o mesmo formato de listagem), ADR-096 (a decisão de **não** ter
  painel gráfico de staff).

## Contexto

**Segurança é desfecho primário do piloto.** E era o único dado do estudo que ninguém conseguia
ler: o módulo tinha `POST /v1/adverse-events` e mais nada. O relato entrava no banco e ficava lá,
alcançável só por SQL direto em produção.

Três coisas tornavam isso pior do que um endpoint faltando:

1. **O alerta apontava para o vazio.** O e-mail de evento moderado/grave (ADR-093) dizia, literalmente:
   *"Acesse o painel de pesquisa para os detalhes."* Esse painel nunca existiu — o ADR-096 decidiu,
   **de propósito**, que não haveria console gráfico de staff. A equipe recebia o aviso e não tinha
   para onde ir.
2. **A coluna `outcome` era letra morta.** Está no schema desde o ADR-051 e **nada jamais a
   escrevia**. Um evento adverso entrava e nunca era encerrado — não havia como registrar que a
   cefaleia passou em 24 h, ou que a participante foi encaminhada. Acompanhar EA até a resolução é
   exatamente o que se espera de um desfecho primário, e é o que o CEP cobra no relatório parcial.
3. **O canal continua aberto após a retirada de consentimento** (dossiê §153). Quem relata depois
   de sair merece o mesmo acompanhamento — e ele não existia para ninguém.

## Decisão

**`GET /v1/adverse-events`** (staff, `research:read`), no mesmo formato de `GET /referrals`:
pseudonimizado por `study_code`, do mais recente para o mais antigo, `limit` de 1 a 500.

Dois filtros, e o segundo é o que muda a rotina da equipe:

- `severity=mild|moderate|severe` — recorte por gravidade; valor fora da lista é **422**, não um
  filtro silenciosamente ignorado.
- **`pending=true`** — só moderado/grave **ainda sem desfecho registrado**. É a pergunta que a
  equipe de fato faz ao abrir a lista ("o que ainda está em aberto?"). Sem ela, a triagem seria
  feita a olho numa lista que só cresce, e o evento esquecido no meio é o que dá errado.

A ordenação é por `occurred_at` **e por `id`**: dois relatos no mesmo instante empatariam, e um
empate não resolvido faz a mesma chamada devolver páginas diferentes.

**`POST /v1/adverse-events/{id}/outcome`** (staff, `enroll:write`) — escreve a coluna que
existia e ninguém preenchia. Duas decisões:

- **Sobrescrever é permitido.** Um desfecho evolui ("em acompanhamento" → "resolvido"). Obrigar a
  equipe a abrir um evento novo para corrigir uma frase encheria de duplicatas justamente a tabela
  em que **contar eventos** é o que importa para a segurança do estudo.
- **A trilha de auditoria guarda que houve o registro, não o que ele dizia.** O texto do desfecho é
  dado de saúde, e a trilha é lida por mais gente do que a lista. `meta` leva só a gravidade.

**`requires_attention` é recalculado da gravidade, não guardado.** Era assim que o `POST` já o
derivava; duas fontes para a mesma verdade divergem no dia em que a regra mudar.

**Cegamento.** Nada aqui devolve braço, protocolo ou PII — e há teste que varre a resposta crua
atrás das palavras que denunciariam um vazamento (`arm`, `condition`, `active`, `sham`,
`protocol`). O `session_id` sai porque é a chave de correlação que a equipe precisa, e hoje
nenhum endpoint de staff traduz sessão em protocolo.

**O texto do e-mail de alerta passou a apontar para os endpoints que existem** — a lista com
`?pending=true` e a rota do desfecho, com o id do evento já preenchido.

## Consequências

- A pendência aberta no ADR-051 fecha, e a lacuna nº 4 da auditoria operacional sai da lista.
- O relatório parcial ao CEP passa a ter de onde sair: eventos por gravidade, com desfecho.
- **Continua sem tela.** O ADR-096 decidiu que a operação é por API, e esta ADR não reverte isso —
  mas agora há o que chamar. A lacuna nº 5 (receituário de operação para uma equipe que não
  programa) segue aberta, e esta mudança a torna mais urgente, não menos: já são cinco listagens
  de staff (`/referrals`, `/discontinuations`, `/adverse-events`, `/research/*`, `/staff`).
- Quem quiser o texto do desfecho no futuro tem de decidir se ele entra no export — hoje **não**
  entra, e é assim que deve ficar até alguém decidir o contrário por escrito.

## Alternativas consideradas

**Um `GET /adverse-events/{id}` avulso.** Rejeitado: a equipe não chega ao evento por id — chega
pela pergunta "o que está em aberto?". A lista com `pending` responde isso; o id vem dela.

**Marcar o evento como "resolvido" com um booleano.** Rejeitado: perde o *como*. Segurança é
desfecho primário e o relatório ao CEP descreve condutas, não conta caixinhas marcadas. A coluna
de texto já existia para isso.

**Mandar o texto do relato no e-mail de alerta.** Rejeitado (mantido do ADR-093): é dado sensível
de saúde saindo por um canal que não controlamos. O e-mail avisa; a leitura é autenticada.

**Construir a tela de uma vez.** Fora de escopo aqui, e maior que esta decisão: seria reverter o
ADR-096 para todas as listagens de staff, não só esta. O endpoint é pré-requisito da tela de
qualquer forma.
