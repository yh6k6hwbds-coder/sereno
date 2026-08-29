# ADR-098 — Fase F fecha com documento de cobrança por dono, não com mais documentação

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) — escolha explícita da trilha F1/F2 — + arquiteto (Claude)
- **Etapas relacionadas:** ética/consentimento e conformidade (LGPD)
- **Contexto de origem:** **F1** e **F2** do `docs/ROADMAP.md`; a DoD global registra que os itens
  da Fase F "fecham com **decisão registrada**", não com CI verde.
- **Relaciona-se com:** ADR-097 (critério de língua no §4 do TCLE), e todo o pacote LGPD
  (`lgpd-nit-checklist.md`, RIPD, ROPA, retenção, incidentes).

## Contexto

As fases de código A–E estão fechadas e quatro itens da F4 foram construídos. O que impede o piloto
de coletar dado real são onze pendências institucionais, éticas e operacionais — e o projeto já
tinha **seis documentos** descrevendo-as: o checklist LGPD, o RIPD, o ROPA, a política de retenção,
o plano de incidentes e a carta de pendências à orientadora.

O problema não era falta de material. Era que **todo o material descreve**, e nenhum **pede**.
A carta à orientadora lista o que falta e por dono; o checklist marca ⬜ nos itens que dependem do
NIT; o RIPD conclui que dois riscos residuais Altos não são técnicos. Mas nenhum deles chega a
alguém com uma pergunta que essa pessoa possa **responder** — e uma pendência que ninguém consegue
responder em uma sentença tende a ficar aberta. Entre 22 de julho e 29 de agosto, nenhuma das onze
avançou.

Há ainda um desequilíbrio de esforço: o NIT, a orientadora e o CEP recebem hoje um pedido genérico
("definir a base legal") que exige que eles reconstruam o contexto do zero, enquanto o repositório
já contém a análise que reduziria esse trabalho a uma revisão.

## Decisão

1. **Cada dono das pendências recebe um documento próprio, que termina com campos a preencher.**
   A pendência fecha quando a folha volta preenchida — não quando alguém "leu o RIPD".

   | Documento | Dono | Fecha |
   |---|---|---|
   | `solicitacao-nit-base-legal.md` | NIT / assessoria / DPO | F1.1–F1.6 |
   | `formulario-protocolo-clinico.md` | Pesquisadora responsável | F2.2 (e os contatos do TCLE) |
   | `dossie-submissao-cep.md` | CEP | F2.1, F2.3, F2.4, F2.5 |

2. **Cada pendência vira uma pergunta objetiva, com as opções já mapeadas.** Onde a leitura técnica
   aponta uma via mais provável, ela vai marcada como **leitura preliminar** — nunca como
   conclusão. O objetivo é que responder custe uma revisão, não um estudo.

3. **A ressalva de competência é obrigatória em cada um.** O responsável técnico não é profissional
   do direito nem membro do comitê; o mapeamento **sinaliza, não decide** (`CLAUDE.md`). Um
   documento que facilita a resposta sem essa ressalva vira parecer disfarçado.

4. **Cada pergunta declara o que muda no sistema quando respondida.** É a contribuição que só o lado
   técnico pode dar, e é o que transforma uma pendência abstrata em consequência concreta (ex.:
   "aprovar os prazos destrava o item F4.2, hoje bloqueado").

5. **Os três entram no catálogo de `docs_to_pdf.py`**, com tarja de status própria, e saem em PDF
   (para ler e arquivar) e DOCX (para preencher e comentar). Fonte única: o `.md` do repositório.
   Não há segunda redação.

6. **A base legal continua sendo uma pergunta, não uma proposta.** As três opções do §2 da
   solicitação (Art. 11, I · Art. 11, II, "c" · combinação) são as que o próprio ROPA já rascunhou.
   A questão foi reduzida ao que de fato trava a decisão — *a UNINTA se enquadra como órgão de
   pesquisa no Art. 5º, XVIII?* — porque é dela que dependem as outras duas.

## Achado desta rodada (defeito, não decisão)

Ao mapear onde cada campo do protocolo entra no sistema, apareceu um erro silencioso:
`adherence_metrics(prescribed=20, weeks=4)`, em
`backend/app/modules/instruments/instruments_scoring.py`, calcula a **taxa de adesão** contra 20
sessões prescritas. Esse número veio da suposição "5×/semana × 4 semanas" do
`Roteiro_Submissao_CEP.docx` de julho — **não de protocolo aprovado**.

A adesão é **desfecho primário** do piloto e critério de progressão para um ensaio definitivo. Se a
frequência real for outra, o percentual sai proporcionalmente errado e **não se denuncia**, porque
continua parecendo plausível. Não foi corrigido aqui de propósito: o valor certo é resposta do
protocolo (pergunta 9 do formulário), e trocar um número inventado por outro não seria conserto.
Registrado no F2.2 do roadmap, na pergunta 9 do formulário e na carta à orientadora.

## Alternativas consideradas

- **Continuar cobrando pela carta de pendências.** Rejeitada: é o que existe desde julho, e nada
  avançou. A carta é boa como panorama para uma pessoa; não serve como pedido a três donos com
  competências distintas.
- **Um documento único de cobrança, para todos.** Rejeitada: obrigaria cada dono a filtrar o que é
  seu, e as competências não se misturam — a base legal não é do CEP, e a via digital não é do NIT.
  Documento que exige triagem antes da leitura não é respondido.
- **Propor a base legal como recomendação técnica, para acelerar.** Rejeitada, e é a alternativa
  mais tentadora: seria opinião jurídica emitida por quem não pode dá-la, sobre dado sensível de
  saúde. O mapeamento das opções vai até onde pode ir — e para aí.
- **Corrigir `prescribed` para o valor mais provável (20 continua, ou 5×4).** Rejeitada: ver acima.
- **Esperar as respostas antes de mexer nos documentos existentes.** Rejeitada: o roadmap, o
  checklist (`.md` **e** `.html`) e a carta precisam apontar para os três novos agora, senão
  passam a contar histórias diferentes — é a regra que a própria DoD impõe.

## Consequências

**Positivas:** as onze pendências passam a ter, cada uma, um destinatário e um formato de resposta;
o esforço de quem decide cai de "reconstruir o contexto" para "revisar e assinalar"; o achado do
`prescribed=20` foi encontrado justamente porque o formulário exigia dizer o que cada campo muda no
sistema.

**Negativas / a vigiar:**
- **Nada disso destrava sozinho.** São documentos para enviar; se não forem enviados, o efeito é
  zero, e o repositório terá nove documentos em vez de seis. **O envio é do mantenedor.**
- **Sete documentos passam a ter de contar a mesma história.** Ao chegar qualquer resposta,
  atualizar o documento correspondente, o checklist (`.md` e `.html`), o roadmap e o TCLE. O
  `.html` do checklist é escrito à mão — não é gerado do `.md`, e diverge se ninguém o acompanhar.
- **As opções de base legal envelhecem.** Foram mapeadas contra a redação vigente da LGPD; se a
  assessoria trouxer enquadramento diverso, o §2 da solicitação é insumo descartável, e tudo bem.
- **O formulário do protocolo presume que o protocolo existe.** Se os critérios de elegibilidade
  ainda não estiverem definidos, ele deixa de ser transcrição e vira o pedido de uma decisão de
  pesquisa — mais lento do que a folha sugere.

## Verificação

Não há verificação por CI: itens da Fase F não fecham com teste verde. O que foi verificado nesta
rodada:

- `scripts/sync_tcle.py --check` continua verde (o corpo do TCLE não foi tocado).
- `scripts/docs_to_pdf.py --list` reconhece as três novas chaves; PDF e DOCX gerados para os três
  (7, 4 e 5 páginas), mais a carta de pendências regerada com o trecho novo.
- Roadmap (F1, F2, F2.2), `docs/README.md`, `lgpd-nit-checklist.md`, `lgpd-nit-checklist.html` e
  `comunicacao-pendencias-orientadora.md` atualizados para apontar aos três — a consistência entre
  documentos é a única "suíte" que a Fase F tem.

**A verificação real é externa:** cada folha de resposta que voltar preenchida.
