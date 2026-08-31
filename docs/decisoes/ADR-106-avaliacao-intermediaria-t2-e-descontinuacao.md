# ADR-106 — A avaliação intermediária (T2) vira um momento, e a descontinuação vira um registro

- **Status:** Aceito
- **Data:** 2026-08-31
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 4 (instrumentos), 5 (backend), 3 (UX), 7 (análise)
- **Contexto de origem:** item **G6** do `docs/ROADMAP.md`, aberto pelo ADR-102.
- **Relaciona-se com:** ADR-102 (PHQ-9 de segurança, retirada por segurança), ADR-100 (dose e
  régua de adesão), ADR-089 (retirada de consentimento), ADR-051 (relato de evento adverso).

## Contexto

O protocolo diz três coisas que o sistema não cumpria:

- **"A coleta ocorrerá em três momentos: linha de base (T0), segunda semana (T2, avaliação
  intermediária de segurança e adesão) e ao término das quatro semanas (T4)."** O ADR-102
  entregou o instrumento (PHQ-9 de segurança) e a tela, alcançáveis pela Home a qualquer
  momento. O que faltava era o **momento**: nada convidava o participante na 2ª semana, e
  "coleta em T2" era um parágrafo do protocolo sem contrapartida no software.
- **"Critérios de descontinuação. Solicitação do participante em qualquer momento; ocorrência de
  evento adverso que contraindique a continuidade, a critério da pesquisadora responsável;
  adesão inferior a 50% das sessões previstas ao final da segunda semana."** Nenhum dos três
  tinha onde ser registrado.
- **"…situação em que o participante permanece na análise por intenção de tratar, mas é
  registrado como descontinuação de protocolo."** Isto é o que separa descontinuar de retirar: o
  sistema só distinguia `active`, `withdrawn` (consentimento), `removed` (segurança) e
  `completed`.

Três perguntas o protocolo **não** responde, e que o software precisa responder para funcionar:

1. **Qual é o marco zero de cada participante?** A inscrição pode anteceder o começo em dias, e a
   primeira sessão pode nunca acontecer — justamente o caso que a regra de adesão existe para
   pegar. A **alocação** é o instante em que a randomização coloca a pessoa num braço e a
   intervenção pode começar.
2. **Quando exatamente a janela do T2 abre?** O protocolo nomeia os momentos T0/T2/T4 pelas
   semanas decorridas, e a regra de adesão que acompanha o T2 é aferida "ao final da segunda
   semana". Antes do dia 14 o denominador (10 sessões) ainda não fechou.
3. **Quanto tempo a janela fica aberta?** Sobre isso o protocolo é silente.

## Decisão

1. **O calendário do estudo vira código, num lugar só:** `backend/app/core/protocol.py`. Dose (20
   sessões = 5 × 4 semanas), régua de adesão (80% da duração), T2, o corte de 50% e as funções de
   dia/semana. Antes, `PRESCRIBED_SESSIONS` e `MIN_COMPLETION_RATIO` moravam em
   `research/export_service.py` e o módulo de **sessões importava de pesquisa** — dependência
   invertida, e o tipo de arranjo em que dois números iguais divergem com o tempo.
2. **Marco zero = `Allocation.allocated_at`**; dia 1 é o dia da alocação.
3. **A janela do T2 abre no dia 14 e dura 7 dias.** A abertura vem do protocolo (T2 = 2 semanas,
   e a adesão é aferida ao final da segunda); os **7 dias são escolha operacional** e por isso
   vivem como `T2_WINDOW_DAYS`, uma constante nomeada e não uma conta escondida. Passada a
   janela, o convite continua — com outra redação (`late`) — porque uma resposta atrasada ainda
   serve à segurança.
4. **T2 respondida = uma avaliação com `moment = "intermediaria"` a partir da abertura da
   janela.** Um PHQ-9 respondido espontaneamente na 1ª semana é bem-vindo e continua registrado,
   mas não é a avaliação da 2ª semana: contá-lo faria o convite sumir antes da hora.
5. **`GET /v1/participants/me/status`** devolve semana, adesão, estado do T2 e a descontinuação,
   se houver. É o que permite ao aplicativo convidar **na hora certa** em vez de deixar a tela
   sempre disponível e torcer. Não revela braço, condição nem escore. Novo escopo de RBAC:
   `progress:read` (participante).
6. **Novo status `discontinued` + tabela `protocol_discontinuation`** (uma por participante, sem
   texto livre, com a contagem que motivou a decisão automática e `kept_in_itt`). Sessão passa a
   403; **os dados já coletados permanecem**, e o participante permanece no denominador da
   análise — é o que ITT quer dizer.
7. **A regra de adesão da 2ª semana é do servidor; os outros dois motivos são de gente.**
   `POST /v1/participants/{id}/discontinue` aceita apenas `solicitacao_participante` e
   `evento_adverso`.
8. **A regra roda em três lugares, porque um só não basta:** ao carregar o andamento, ao iniciar
   sessão (é quando alguém com adesão insuficiente voltaria a se expor) e numa **varredura**
   (`POST /v1/discontinuations/evaluate`). A varredura é a que importa: a avaliação preguiçosa
   nunca alcança quem parou de abrir o aplicativo — que é exatamente o caso que a regra existe
   para pegar.
9. **A descontinuação nunca rebaixa um status mais forte.** Quem já saiu por segurança
   (`removed`), retirou o consentimento (`withdrawn`) ou concluiu não vira `discontinued` — a
   mesma precaução que o ADR-102 tomou com o `erase`.
10. **Na Home:** cartão de convite quando o T2 é devido; quando descontinuado, um aviso que
    explica que os registros continuam no estudo e **o CTA de sessão some** — oferecer um botão
    que o servidor recusaria com 403 é pior do que não oferecer. O andamento é acessório: sem
    rede, a Home continua inteira e o convite apenas não aparece.
11. **`GET /v1/discontinuations`** e um bloco `descontinuacoes` no `/research/analysis`, por
    motivo, para o fluxo de participantes do CONSORT e o relatório parcial ao CEP.

## Alternativas consideradas

- **Contar o calendário a partir da inscrição ou da 1ª sessão.** Rejeitadas: a inscrição pode
  anteceder o início em dias; a 1ª sessão pode não existir, e é o caso que a regra precisa pegar.
- **Abrir o T2 no dia 8 ("durante a 2ª semana").** Rejeitada: a regra de adesão que acompanha o
  T2 só pode ser aferida com a 2ª semana fechada, e ter a avaliação e a regra em momentos
  diferentes criaria dois calendários para o mesmo T2.
- **Fechar o convite ao fim da janela.** Rejeitada: é uma avaliação de **segurança**; recusá-la
  por atraso seria trocar cuidado por burocracia.
- **Só marcar a descontinuação, sem parar a sessão.** Rejeitada: "descontinuação de protocolo"
  significa sair da intervenção. Continuar dosando quem o protocolo descontinuou é registrar uma
  coisa e fazer outra.
- **Reaproveitar `withdrawn`.** Rejeitada: apagaria a distinção que o protocolo faz questão de
  manter — quem descontinua **permanece na análise**, quem retira o consentimento não.
- **Só a varredura, sem a avaliação preguiçosa.** Rejeitada: dependeria de alguém lembrar de
  rodá-la para que a exposição parasse.
- **Só a avaliação preguiçosa, sem varredura.** Rejeitada: não alcança quem sumiu.
- **Agendador embutido (cron no backend).** Rejeitada por ora: não há agendador em produção (o
  expurgo do OTP tem o mesmo problema, item F3.1). O endpoint é o que um agendador chamaria.

## Consequências

- **Positivas:** o T2 existe como momento e chega ao participante; os três critérios de
  descontinuação têm registro; o ITT fica explícito no dado, não só na cabeça de quem analisa; o
  relatório ao CEP ganha o fluxo de participantes sem ninguém compilar à mão; a dose e a régua de
  adesão passam a ter uma fonte só.
- **Custo:** +1 migração (`c9d0e1f2a3b4`, uma tabela e um valor de status); +1 escopo de RBAC;
  +4 endpoints; a Home deixou de ser `StatelessWidget`. +20 testes de backend, +5 de widget.
- **Detalhe de implementação que merece registro:** ao recusar a sessão de quem acabou de ser
  descontinuado, o router **faz commit antes de levantar a exceção**. Exceção causa rollback da
  requisição inteira (`get_db`): sem o commit, a descontinuação recém-decidida sumiria e seria
  redecidida — e reavisada à equipe — a cada nova tentativa.
- **⚠️ A varredura precisa de alguém que a chame.** Enquanto não houver agendador (F3.1), a
  regra da 2ª semana só alcança quem sumiu se a equipe rodar
  `POST /v1/discontinuations/evaluate`. Entrou no roadmap como item de operação.
- **⚠️ O aviso à equipe depende de `TEAM_NOTIFY_EMAIL`** (F3.7), como o do encaminhamento.
- **⚠️ A janela de 7 dias não está no protocolo.** É decisão operacional desta implementação e
  deve ser confirmada — ou corrigida — quando o CEP responder o formulário do protocolo.
- **A descontinuação por evento adverso continua sendo juízo humano.** O sistema registra e para
  a exposição; quem decide que um evento contraindica a continuidade é a pesquisadora
  responsável, como o protocolo determina.

## Conformidade

CI verde exige `backend/tests/test_progress_t2.py` (calendário a partir da alocação, janela que
não abre antes do dia 14, convite que fecha ao responder, avaliação anterior à janela que não
conta, corte em 50% com a fronteira exata, sessão parcial que não salva a adesão, sessão
atrasada que não reescreve a 2ª semana, exposição que para de fato, ITT preservado, não
rebaixamento de `removed`, idempotência, varredura, lista pseudonimizada e ausência de braço) e
`app/test/home_t2_test.dart` (convite só quando devido, texto de atraso, estado descontinuado
sem CTA, Home inteira sem rede); migração `c9d0e1f2a3b4`; OpenAPI válido.
