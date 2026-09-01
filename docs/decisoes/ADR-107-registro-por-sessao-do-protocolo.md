# ADR-107 — O registro por sessão que o protocolo lista

- **Status:** Aceito
- **Data:** 2026-08-31
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 2 (player/instrumento), 4 (instrumentos), 5 (backend), 3 (UX)
- **Contexto de origem:** item **G10** do `docs/ROADMAP.md`, aberto pelo ADR-101.
- **Relaciona-se com:** ADR-101 (verificação dicótica e teto de volume), ADR-108 (dose auditiva,
  que consome o volume registrado aqui), ADR-100 (parâmetros do estímulo).

## Contexto

O protocolo, em **"Registro e monitoramento"**, é explícito sobre o que a plataforma guarda de
cada sessão:

> "A plataforma registrará, para cada sessão: horário de início e término, tempo efetivo de
> reprodução, **interrupções e sua duração**, **volume médio e máximo**, resultado da verificação
> de fones e **resposta a um item único de percepção de relaxamento em escala numérica de 0 a
> 10**. Um botão de interrupção imediata permanecerá visível durante toda a sessão."

O roadmap tratava o G10 como quase-fechado ("falta o volume médio/máximo quando houver algo que
varie"). Relendo o parágrafo contra o schema, **três dos seis itens não tinham onde ser
guardados**:

| item do protocolo | antes deste ADR |
|---|---|
| horário de início e término | ✅ `started_at` / `ended_at` |
| tempo efetivo de reprodução | ✅ `effective_seconds` |
| interrupções **e sua duração** | 🟡 só a **contagem** (`interruptions`) |
| **volume médio e máximo** | ❌ só o ganho **declarado ao iniciar** (`audio_gain`) |
| resultado da verificação de fones | ✅ `headphones_ok` + `headphone_check` (ADR-101) |
| **item único de relaxamento, 0 a 10** | ❌ existia um `relaxation` **de 0 a 4**, dentro do
  questionário pós-sessão, que é **opcional** |
| botão de interrupção sempre visível | ✅ já era assim no player |

O terceiro caso era o mais sério: o `PostSessionSurvey` tem um campo `relaxation`, mas em escala
de **0 a 4** e dentro de um questionário que o participante pode pular. O protocolo pede um item
**de 0 a 10**, para **cada** sessão. Chamar um do outro seria dizer ao CEP que se coleta uma coisa
e coletar outra.

## Decisão

**Quatro colunas novas em `session`** (migração `d0e1f2a3b4c5`), todas anuláveis:

- **`paused_seconds`** — tempo total em pausa. A contagem sozinha não distingue quem pausou 5 s
  de quem pausou meia hora, e é a duração que descreve a interrupção.
- **`gain_mean` / `gain_peak`** — volume médio e máximo **efetivamente aplicados**. O ganho é
  travado (G3/ADR-101), então hoje os dois coincidem com `audio_gain`. Registrá-los assim mesmo é
  o que transforma "é constante por construção" em **fato auditável sessão a sessão** — e é o
  insumo de que a dose auditiva (ADR-108) precisa.
- **`relaxation_0_10`** — o item único do protocolo. Fica na **sessão**, não no questionário
  pós-sessão: amarrá-lo ao questionário opcional faria a coleta desaparecer junto com ele.

**Anuláveis, e não com default zero.** A ausência é informação: `paused_seconds = 0` afirmaria que
ninguém pausou, e `relaxation_0_10 = 0` afirmaria o relaxamento mínimo. Sessões anteriores à
mudança não têm o dado e não podem ganhar um valor inventado — a mesma postura do ADR-101.

**O cliente mede, não presume.** O player integra o ganho aplicado **no tempo ouvido** (não no
relógio de parede) e acumula o máximo; a pausa é contada no mesmo tique de 1 s que já contava o
tempo efetivo. Se algum dia o ganho variar (uma rampa aplicada no cliente, um *ducking* do
sistema), a medida acompanha sem que ninguém precise lembrar de mudá-la.

**O item de relaxamento é perguntado DEPOIS de a adesão já ter sido enviada.** O encerramento
segue para o servidor assim que a sessão termina; a pergunta 0–10 aparece no diálogo de conclusão
e dispara um **segundo envio**, complementar. Responder não pode ser condição para a sessão contar
— adesão é desfecho **primário**, e perdê-la porque alguém fechou o app antes de escolher um
número seria trocar o desfecho principal por um secundário.

**O teto de volume passa a valer também no encerramento.** `gain_peak` acima de `AUDIO_MAX_GAIN`,
ou `gain_mean > gain_peak`, é **422**. Antes, o teto só era conferido ao **iniciar**: um cliente
que declarasse 0,8 e subisse o ganho no meio da sessão passava.

**Todos os campos novos são opcionais no contrato.** A fila de telemetria é **persistente em
disco**: um arquivo gravado pela versão anterior volta sem eles e precisa continuar sendo enviável.
E um segundo envio **sem** o item de relaxamento não apaga o que já foi respondido — o servidor só
preenche.

## Consequências

- O relatório ao CEP passa a poder afirmar, item a item, que o parágrafo "Registro e
  monitoramento" está cumprido — antes, três dos seis itens eram promessa.
- **A equipe ainda não tem como LER esse registro.** Não existe `GET` de sessões; o dado está no
  banco e sai pelo export agregado. É a mesma lacuna do painel de eventos adversos (lacuna
  operacional #4) e continua fora de qualquer lista de roadmap.
- O questionário pós-sessão (0–4) **continua existindo** e não foi mexido: ele é o instrumento de
  UX/tolerabilidade da Etapa 4, com outra finalidade. O que mudou é que o item do **protocolo**
  deixou de depender dele.
- `gain_mean` e `gain_peak` serão idênticos em todas as sessões do piloto. Isso é o esperado, e é
  exatamente o que se quer poder demonstrar.
- **Não** houve mudança no estímulo, no cegamento ou na régua de adesão.

## Alternativas consideradas

- **Mudar a escala do `relaxation` do questionário de 0–4 para 0–10.** Recusada: quebraria a
  comparabilidade das respostas já coletadas e continuaria deixando o item dentro de um
  questionário opcional, que é a metade errada do problema.
- **Não registrar volume por ser constante.** Recusada: o protocolo lista o item, e "é constante"
  é uma afirmação sobre o software que só o registro pode sustentar diante de uma auditoria.
- **Perguntar o relaxamento antes de enviar a telemetria** (um envio só). Recusada pelo risco de
  perder a medida de adesão se o participante fechar o app na pergunta.
- **Guardar cada interrupção como um evento** (início/fim de cada pausa). Recusada por ora:
  o protocolo pede "interrupções e sua duração", que a contagem mais o total já respondem, e uma
  tabela de eventos por sessão é complexidade que o piloto não usaria.
