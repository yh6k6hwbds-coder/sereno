# ADR-116 — A adesão passa a ser medida pelo áudio, e o encerramento deixa de regredir

- **Status:** Aceito
- **Data:** 2026-09-13
- **Decisores:** Arquiteto (Claude), mantenedor (aval para implementar)
- **Etapas relacionadas:** 2 (player/instrumento), 5 (backend), 4 (instrumentos e métricas)
- **Contexto de origem:** **primeira execução da etapa (ii)** — o app rodando de ponta a ponta em
  aparelho real, com o mantenedor percorrendo o fluxo inteiro.
- **Relaciona-se com:** ADR-107 (registro por sessão), ADR-101 (ganho travado), ADR-103 (entrega do
  áudio), F2.7 (liberação em três etapas).

## Contexto

Na primeira sessão completa em aparelho real — 20 minutos de áudio, ouvidos até o fim, com o
encerramento automático disparado pelo próprio player — o registro chegou ao servidor assim:

```
started: 01:13:58   ended: 01:34:21   tempo de parede: 1223 s
effective_seconds: 0     completed: FALSE
gain_mean: null          gain_peak: null
paused_seconds: 0        interruptions: 0     relaxation_0_10: 10
```

Tudo o que o cronômetro produziria veio zerado, enquanto o áudio tocou inteiro. Dois defeitos
distintos, que se somaram.

### Defeito 1 — o tempo efetivo vinha de um cronômetro da tela

`session_player_screen.dart` acumulava o tempo num `Timer.periodic` de um segundo. O Android
**suspende a isolate do Dart** quando o app vai para segundo plano; o áudio não para, porque quem
toca é o player nativo. O cronômetro congela e o som segue.

Numa sessão de relaxamento de 20 minutos, **bloquear a tela é o comportamento esperado** do
participante — provavelmente o mais comum. Ou seja: em uso real, `effective_seconds` seria zero
quase sempre, `completed` seria sempre falso, e a **adesão — desfecho primário — mediria zero o
estudo inteiro**. Junto iam `gain_mean`/`gain_peak`, que o ADR-107 criou exatamente para registrar
o volume aplicado.

Nenhum teste pegaria isso: é ciclo de vida do Android, não lógica Dart. A bateria de widget tests
avançava o relógio do Flutter com `pump`, que faz o `Timer` disparar — exatamente o que o aparelho
real não faz.

### Defeito 2 — o encerramento sobrescrevia sem critério

`complete` é chamado **duas vezes de propósito** (ADR-107): o encerramento vai antes de perguntar o
item de relaxamento, para que a adesão não dependa de o participante responder, e a resposta vem
num segundo envio com o registro completo. O comentário do cliente dizia que o servidor trata o
segundo envio "como complemento — nunca como apagamento".

**O servidor não fazia isso.** Ele reatribuía todos os campos a cada chamada; só
`relaxation_0_10` era preenchido com cuidado. Como a fila de telemetria também reenvia, um envio
atrasado — ou de um app reaberto, que perdeu os contadores — chegava com tempo menor e rebaixava o
que já estava gravado, em silêncio.

## Decisão

**1. O tempo efetivo é a posição do áudio.** `AudioPlayerPort` ganha `position`, e a tela deriva
dela o tempo ouvido. O `Timer` fica apenas para o relógio na tela; se não rodar, nada se perde —
no próximo tique ele relê a posição. A duração das pausas é o relógio de parede desde o *play*
menos o que soou, o que também sobrevive ao segundo plano.

**2. O ganho é registrado como o valor travado**, e não integrado tique a tique. O app não oferece
controle de volume (ADR-101/G3): médio e máximo coincidem com o ganho aplicado por construção.
Continua nulo — não zero — quando não houve áudio ouvido.

**3. O encerramento é monotônico nos campos de adesão.** Um envio com `effective_seconds` menor que
o gravado é aceito (200) mas não substitui tempo, interrupções, pausa nem volume; só complementa
`relaxation_0_10`. A resposta reflete o estado **gravado**, não o corpo enviado.

**4. O relógio de parede da tela é injetável**, porque a duração das pausas depende dele e o `pump`
do widget test move o relógio do Flutter, não o do sistema.

## Alternativa descartada

**Recusar o segundo `complete` com 409**, como fazem `/recommendations/{id}/accept` e o
descegamento. Foi a primeira proposta e **estava errada**: o cliente depende do segundo envio para
entregar o item de relaxamento. Um 409 fecharia a porta que o ADR-107 abriu de propósito. O
problema nunca foi a repetição — foi a regressão.

## Consequências

- A adesão passa a medir o que o participante realmente ouviu, inclusive com a tela bloqueada.
- Um reenvio de fila deixa de poder apagar dado bom. O caminho normal (segundo envio com o mesmo
  tempo ou maior) segue funcionando.
- **Dado já coletado não é recuperável:** as sessões registradas antes desta correção têm tempo
  efetivo irreal. São dados de demonstração — nenhum participante foi incluído —, mas se houvesse
  piloto em curso, a série teria de ser descartada.
- Dois testes novos guardam os dois defeitos: um widget test que não deixa **nenhum** tique
  acontecer e ainda assim exige a adesão inteira, e um teste de backend que reenvia um registro
  pobre e verifica que nada regrediu.

## Nota de método

Os três defeitos desta noite — a permissão de rede ausente (correção anterior), a medição da adesão
e a sobrescrita do registro — estavam no sistema desde sempre e passaram por 510 testes verdes.
Todos apareceram na **primeira** execução da etapa (ii) do F2.7. É o argumento empírico para fazer
essa etapa a sério, com mais gente e mais sessões, antes de qualquer participante.

Registrado também um incômodo menor achado no caminho: rodar a suíte do backend **localmente** dá
dez falhas falsas em `test_staff_onboarding.py`, porque o `EMAIL_DEV_CONSOLE=1` do `.env` desvia a
entrega para o console e o `MemoryEmailSender` injetado pelo teste nunca recebe nada. No CI não há
`.env` e a suíte passa. Não corrigido aqui; fica anotado para não custar outra caçada.
