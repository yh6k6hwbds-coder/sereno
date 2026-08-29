# ADR-099 — A versão do TCLE passa a ser verificada no CI, e trocá-la vira um comando

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) — "prossiga para as próximas etapas" (trilha F3) — + arquiteto (Claude)
- **Etapas relacionadas:** 3 (consentimento) e operação
- **Contexto de origem:** itens **F3.4** e **F3.10** do `docs/ROADMAP.md`.
- **Relaciona-se com:** ADR-089 (consentimento/retirada), ADR-094/096 (convite de staff),
  ADR-097 (piloto em pt-BR), `scripts/sync_tcle.py` (mesma disciplina de fonte única).

## Contexto

O backend recusa com **409** qualquer aceite cuja versão do termo não seja a vigente — é assim que
uma revisão do texto invalida aceites contra a redação antiga (ADR-089). O cliente envia a versão
**que exibiu**, declarada em Dart; o servidor compara com a sua, declarada em Python.

Duas coisas estavam erradas.

**1. Nada verificava que as duas concordam.** Os testes de backend importam `TCLE_CURRENT` em vez do
literal (correto: um teste que repete o literal não prova nada) e o teste de widget usa
`tcleVersion`. Cada lado é internamente coerente, e por isso **os dois passam mesmo divergindo entre
si**. A divergência só apareceria em produção, do pior jeito possível: um 409 na cara do
participante **depois** de ele ter lido o termo inteiro e tocado em "concordo" — exatamente o
momento em que o sistema tem menos crédito para pedir que ele tente de novo.

**2. O roadmap subestimava a troca.** A linha F3.4 dizia "trocar a versão em **3 lugares** …
**uma linha em cada**". Na verdade são **quatro literais**, em três linguagens:
`TCLE_CURRENT`, o `examples=[...]` do contrato (que sai no OpenAPI), `tcleVersion` no Dart e o
cabeçalho de status do próprio `tcle-rascunho.md`. E sair de `-rascunho` **derruba um teste de
widget** que afirma `tcleVersion.contains('rascunho')` de propósito — a rede de segurança que
impede alguém de ler a tela como termo vigente. Descobrir isso no dia do parecer do CEP, com pressa,
é como se perde uma rede de segurança: apagando o teste que "quebrou".

## Decisão

1. **`scripts/tcle_version.py --check` entra no CI** (job `contracts`, ao lado de
   `sync_tcle.py --check`). Os quatro sites têm de declarar a mesma versão, ou o job falha com a
   tabela de quem diverge. A verificação é cross-language e por isso não cabe na suíte de backend,
   que testa comportamento de API — cabe junto das outras checagens entre artefatos.
2. **Trocar a versão vira um comando:** `python scripts/tcle_version.py 1.0.0`. Há `--dry-run`,
   `--show` e `--check`.
3. **A troca aborta se os sites já divergirem.** Reescrever por cima de um estado inconsistente
   tornaria impossível reconstruir qual versão cada aceite registrado de fato exibiu.
4. **Cada regex tem de casar exatamente uma vez.** Zero ou duas ocorrências é **erro**, não aviso:
   significa que o arquivo mudou de forma, e um script que continuasse editaria a linha errada em
   silêncio — o modo de falha que este ADR existe para eliminar.
5. **O script faz o mecânico e imprime o resto.** Ao sair de `-rascunho`, lista os cinco pontos que
   exigem julgamento (o teste de widget, o cabeçalho do documento, a tarja do gerador de PDF, o
   resumo de 7 tópicos que **não** é gerado do `.md`, e os itens B2/G5 do checklist). Não os toca.
6. **`STAFF_SETUP_URL` ganha receita** (`deploy-fly.md` §3.3). Era o **único** item da F3 sem
   procedimento escrito em lugar nenhum — existia só como uma linha de roadmap e um comentário no
   `.env.example`.
7. **`deploy-fly.md` abre com a ordem de execução dos dez itens da F3**, com o que destrava cada um
   e o que acontece se ficar de fora. Não é um runbook novo — é a sequência que faltava sobre o
   runbook que já existia, para que "operacional" pare de ser uma lista sem ordem.

## Alternativas consideradas

- **Fonte única: gerar `config.dart` a partir do Python.** Rejeitada. É o padrão certo para o
  *texto* do termo (e é o que `sync_tcle.py` faz com o asset), mas para **uma constante** custa um
  passo de codegen no build do app e faz o Flutter passar a depender de Python. A verificação dá a
  mesma garantia com uma fração do acoplamento.
- **Um teste de backend que lê `config.dart`.** Rejeitada: põe leitura de arquivo de outra
  linguagem dentro da suíte de API, que não deveria saber que existe um app Dart.
- **Fazer o script reescrever também o teste de widget.** Rejeitada, e é a tentação central deste
  ADR: o teste existe para **obrigar** um humano a decidir que o termo saiu do rascunho. Um script
  que o "conserta" sozinho transforma a rede de segurança em formalidade.
- **Deixar como está e confiar no comentário** (`router.py` já dizia "mudar TAMBÉM em config.dart").
  Rejeitada: o comentário estava lá e mesmo assim ninguém verificava — é a definição de controle que
  não controla.
- **Escrever um runbook de go-live novo, separado do `deploy-fly.md`.** Rejeitada: 80% seria cópia,
  e dois runbooks divergem. O que faltava era **ordem e dependências**, não comandos.

## Consequências

**Positivas:** a divergência de versão passa a falhar no CI, em vez de na cara do participante; a
troca pós-CEP deixa de ser uma caça a literais; o item F3.10 sai de "existe uma variável" para "há
um procedimento"; a Fase F3 ganha ordem e fica claro que **nenhum dos dez itens autoriza coletar
dado real** — isso é F1.1.

**Negativas / a vigiar:**
- **`SITES` é lista mantida à mão.** Se alguém declarar a versão num quinto lugar, a verificação não
  saberá. O regex-exatamente-uma-vez cobre o caso oposto (o site mudar de forma), não este.
- **Refatorar qualquer um dos quatro arquivos quebra o CI de propósito.** Renomear a constante ou
  reformatar a linha faz o padrão casar zero vezes e o job falhar com a mensagem pedindo que
  `SITES` seja corrigido. É o comportamento desejado, mas é atrito, e quem o encontrar sem contexto
  vai achar que o script está errado — daí a mensagem de erro dizer o que fazer.
- **O script não sabe se o CEP aprovou coisa alguma.** Ele troca o número que mandarem; nada impede
  alguém de rodar `tcle_version.py 1.0.0` sem parecer nenhum. A trava contra isso continua sendo
  humana (e o `-rascunho` no nome, que torna o gesto visível no diff).
- **A ordem de execução da F3 é uma sugestão fundamentada, não uma dependência técnica.** Os itens
  1–8 podem, na prática, ser feitos em quase qualquer ordem; a tabela reflete o que destrava o quê.

## Verificação

- `python scripts/tcle_version.py --check` → verde nos 4 sites (`0.1.0-rascunho`).
- **Divergência simulada** (`config.dart` para `0.2.0-rascunho`): `--check` sai com **1** e imprime
  qual site diverge; a troca **aborta** em vez de gravar por cima. Estado revertido.
- `--dry-run 1.0.0`: lista os 4 sites com arquivo e linha, mais os 5 itens a fazer à mão.
- Suíte de backend: **352 testes verdes**. `sync_tcle.py --check` verde. OpenAPI válido.
- Flutter: validado pelo CI (sem SDK local). **Nada no app foi alterado nesta fatia**, então os
  49 widget tests não foram afetados.
