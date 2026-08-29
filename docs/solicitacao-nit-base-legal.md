# Solicitação ao NIT / assessoria jurídica — decisões de proteção de dados pendentes

> **Para:** Núcleo de Inovação Tecnológica (NIT) · assessoria jurídica · Encarregado de Proteção de
> Dados (quando designado) — UNINTA
> **De:** Augusto André — responsável técnico do projeto Sereno
> **Com conhecimento de:** Dra. Bianca Régia Silva (orientadora, pesquisadora responsável)
> **Assunto:** seis decisões institucionais necessárias para que o estudo-piloto possa coletar dados
> reais. **Nenhuma depende de desenvolvimento** — o sistema está pronto e testado.

> ⚠️ **A decisão nº 1 (base legal) bloqueia o início da coleta.** As demais podem correr em
> paralelo. Enquanto a base legal não estiver definida, o projeto **não trata dado real de
> participante** — é a recomendação técnica registrada no RIPD §10.

## O que esta solicitação pede

Cada decisão abaixo está redigida como **uma pergunta objetiva**, acompanhada de (a) por que ela
precisa ser respondida, (b) o material que o projeto já produziu como insumo, (c) as opções
mapeadas na leitura técnica e (d) **o que muda no sistema e nos documentos quando a resposta
chegar**. A intenção é que responder custe uma revisão, e não um estudo do zero.

O item (c) — as opções — é **mapeamento técnico, não parecer**. O responsável técnico do projeto não
é profissional do direito; a escolha, a fundamentação e a redação final são da assessoria. Onde há
uma leitura mais provável, ela aparece marcada como **leitura preliminar**, para ser confirmada ou
descartada.

**A folha de resposta está na seção 8.** Basta preenchê-la: o restante do projeto se ajusta a partir
dela.

---

## 1. Identificação do tratamento (resumo, para não exigir a leitura dos anexos)

| | |
|---|---|
| **Projeto** | Sereno — estudo-piloto de viabilidade de aplicativo de frequências binaurais como apoio ao relaxamento e ao sono |
| **Natureza** | Piloto randomizado, controlado, duplo-cego, com sham ativo · N≈40 · 4 semanas por participante |
| **Controlador (a confirmar formalmente)** | UNINTA |
| **Titulares** | Participantes adultos, possivelmente estudantes vinculados à própria instituição (ver risco **R-09**) |
| **Dado pessoal comum** | Nome e e-mail de contato (cifrados, separados do dado de pesquisa) |
| **Dado pessoal sensível** | Dado referente à **saúde** — GAD-7 (ansiedade), PSQI (sono), diário de sono, eventos adversos (Art. 5º, II) |
| **Operações mapeadas** | 8 (OP-01 a OP-08), no `registro-operacoes-tratamento.md` |
| **Operadores** | Fly.io (hospedagem + banco, região `gru`/São Paulo), provedor de SMTP (a contratar), GitHub Pages (aplicativo web) |
| **Residência dos dados** | Brasil (São Paulo) — restrição de projeto, já implementada |
| **Medidas do Art. 46** | Implementadas e verificáveis por teste automatizado — inventário no `lgpd-nit-checklist.md`, seção C |

---

## 2. Decisão 1 — Base legal do tratamento de dado sensível de saúde ⛔ *bloqueia a coleta*

> **Pergunta:** qual é a **base legal** do tratamento dos dados de saúde neste estudo, e em que
> formulação ela deve ser registrada no ROPA e no termo de consentimento?

**Por que precisa ser respondida.** Dado de saúde é dado pessoal sensível (Art. 5º, II) e só pode ser
tratado nas hipóteses do **Art. 11**. Hoje as **oito operações** do ROPA estão com a base legal
marcada `[a confirmar]`, e a seção 12 do termo de consentimento traz o mesmo marcador. Sem essa
definição, não há como informar ao participante sob que fundamento seus dados são tratados — e
consentimento informado exige exatamente isso.

**Insumo pronto:** `registro-operacoes-tratamento.md` (base legal proposta por operação);
`relatorio-impacto-protecao-dados.md` §4 e §10; `lgpd-nit-checklist.md` item **A2**.

**Opções mapeadas na leitura técnica:**

| | Hipótese | O que exige | Consequência prática se adotada |
|---|---|---|---|
| **A** | **Art. 11, I** — consentimento **específico e destacado** do titular, para finalidades específicas | Consentimento livre, informado, específico e destacado das demais cláusulas | Alinha-se diretamente ao TCLE exigido pela Res. CNS 466/2012. A **revogação** do consentimento (já implementada, em autoatendimento) passa a ter efeito sobre a própria base legal, o que torna a decisão 4 do CEP (retenção pós-revogação) mais sensível |
| **B** | **Art. 11, II, "c"** — realização de **estudos por órgão de pesquisa**, garantida, sempre que possível, a anonimização | Que a UNINTA se enquadre na definição de **órgão de pesquisa** do **Art. 5º, XVIII** — esta é a questão que só o NIT/assessoria responde | O TCLE continua obrigatório pela **norma ética** (Res. CNS 466/2012), mas a base legal não cai com a revogação; a retenção do dado já coletado fica mais bem sustentada (ver também **Art. 16, II**) |
| **C** | **Combinação** — "B" como base legal do tratamento de pesquisa, o TCLE como exigência ética e instrumento de transparência, e o **Art. 7º, I** para o dado **de contato**, que não é dado de pesquisa | As duas análises acima | É a leitura que o ROPA hoje **propõe**: Art. 7º, I para a OP-01 (contato) e Art. 11 para as operações de pesquisa |

> **Leitura preliminar (a confirmar).** A opção **C** é a que menos exige do desenho atual, porque é
> a que o ROPA já rascunhou operação a operação. **E a pergunta de fato é uma só:** a UNINTA se
> enquadra como *órgão de pesquisa* no Art. 5º, XVIII? Se sim, a via do Art. 11, II, "c" fica
> disponível; se não, a via provável é o Art. 11, I — e a decisão 4 do CEP (o que acontece com o
> dado já coletado quando alguém revoga o consentimento) passa a ser crítica.

**O que muda quando a resposta chegar:**
- As 8 operações do ROPA saem de `[a confirmar]` para a base definida.
- A seção 12 do TCLE é preenchida — e, como o texto exibido no aplicativo é **gerado** do documento
  que vai ao CEP, o aplicativo passa a exibir a mesma redação (basta rodar `scripts/sync_tcle.py`).
- O RIPD registra a base legal na análise de necessidade e proporcionalidade.
- **A recomendação técnica de não coletar dado real deixa de ter este motivo.**

---

## 3. Decisão 2 — Encarregado (DPO) e canal de atendimento ao titular

> **Pergunta:** quem é o Encarregado pelo tratamento de dados (Art. 41), qual é o **canal público**
> de atendimento ao titular e qual o **prazo de resposta** adotado pela instituição?

**Por que precisa ser respondida.** O participante precisa saber a quem recorrer, e essa informação
tem de constar do próprio termo que ele aceita. Hoje o termo diz `[a preencher]` em dois lugares
(§12 e §15), e o plano de resposta a incidentes está sem os contatos de acionamento — um plano sem
quem chamar não funciona no dia do incidente.

**Insumo pronto:** `registro-operacoes-tratamento.md` §1; `relatorio-impacto-protecao-dados.md` §2;
`plano-resposta-incidentes.md`; `lgpd-nit-checklist.md` itens **G1** e **D4**.

**O que já existe do lado técnico, para calibrar a resposta:** a **retirada do consentimento** é
autoatendimento no aplicativo (o participante sai sozinho, sem falar com ninguém). Já os pedidos de
**acesso** e de **eliminação** (Art. 18) são operados pela equipe, por endpoints próprios e
auditados. O que falta é o **canal público** e o **prazo** — não o mecanismo.

**O que muda quando a resposta chegar:** preenchimento do TCLE §12/§15 (com regeração do texto
exibido no aplicativo), do ROPA §1, do RIPD §2 e da tabela de acionamento do plano de incidentes.

---

## 4. Decisão 3 — Prazos de retenção e descarte

> **Pergunta:** os prazos propostos na política de retenção estão aprovados? Em especial: **5 anos
> após o encerramento/publicação** para o conjunto de dados de pesquisa e para a evidência de
> consentimento; **até 30 dias** após o encerramento da coleta para a PII de contato.

**Por que precisa ser respondida.** É o segundo maior risco residual do RIPD (**R-10**, Alto): dado
que deveria ser expurgado permanece. E é também um bloqueio **de código**: o expurgo automático do
conjunto de dados de pesquisa não pode ser construído contra um prazo que ninguém aprovou — seria
programar uma eliminação irreversível sobre um número inventado.

**Insumo pronto:** `politica-retencao-descarte.md` §4 (inventário completo, categoria por categoria,
com o prazo proposto e a forma de descarte de cada uma) e §5 (gatilhos).

**O que muda quando a resposta chegar:** a política sai de rascunho; o item **F4.2** do roadmap
(expurgo do conjunto de dados ao fim do prazo) deixa de estar bloqueado e pode ser construído; o
TCLE §13 recebe o prazo em número; **R-10 deixa de ser residual Alto.**

> Um prazo da política **não** depende desta decisão e já está implementado: o expurgo de
> transitórios de autenticação (códigos de acesso expirados e links de convite da equipe). Falta
> apenas **agendá-lo** — item operacional, assumido pelo responsável técnico.

---

## 5. Decisão 4 — Contratos com operadores e transferência internacional

> **Pergunta:** quais contratos ou cláusulas de tratamento de dados a instituição exige dos
> operadores, e qual o enquadramento de eventual **transferência internacional** (Art. 33)?

**Por que precisa ser respondida.** São três operadores, e dois deles são empresas estrangeiras —
ainda que a **região de hospedagem contratada seja o Brasil** (São Paulo), o que já está
implementado e é restrição de projeto.

| Operador | Papel | O que trafega | Ponto de atenção |
|---|---|---|---|
| **Fly.io** | Hospedagem + PostgreSQL | Todas as tabelas | Empresa estrangeira, região `gru`/BR — analisar Art. 33 |
| **Provedor de SMTP** *(a contratar)* | Entrega do código de acesso e de avisos à equipe | **E-mail do participante** | Único ponto em que a PII sai do ambiente próprio. O provedor ainda não foi escolhido — **a assessoria pode indicar um já contratado pela instituição** |
| **GitHub Pages** | Distribuição do aplicativo web (arquivos estáticos) | Nenhum dado pessoal | Não recebe dado do participante; serve apenas o código do aplicativo |

**Insumo pronto:** `registro-operacoes-tratamento.md` §4; `lgpd-nit-checklist.md` itens **F2** e **F3**.

**O que muda quando a resposta chegar:** o ROPA passa a citar os contratos firmados; e, se a
instituição indicar o provedor de SMTP, o item operacional correspondente (hoje parado por falta de
credencial) destrava de imediato.

---

## 6. Decisão 5 — Adoção formal do RIPD e do ROPA, risco residual e ANPD

> **Pergunta:** o controlador adota o RIPD e o ROPA (com os ajustes que entender necessários)?
> O **risco residual** declarado é aceitável? Há caso de **consulta prévia à ANPD** (Art. 38)?

**Por que precisa ser respondida.** Os dois documentos existem como **rascunho técnico**, escritos a
partir do que o sistema faz — não como peça institucional adotada. O Art. 37 atribui o registro das
operações ao controlador, e a decisão sobre risco residual aceitável não é conclusão que um
documento técnico possa dar.

**Insumo pronto:** `relatorio-impacto-protecao-dados.md` — 14 riscos ao titular avaliados por
probabilidade × impacto, cada mitigação rastreável à decisão de arquitetura que a implementa, e o
risco residual declarado ao fim; a §10 traz a conclusão técnica preliminar.

**O que a análise técnica já conclui, para poupar leitura:** para os riscos de natureza técnica, o
residual é **Baixo a Médio**. **Dois** residuais permanecem **Altos, e nenhum deles é técnico** —
**R-09** (assimetria de poder no consentimento, tratado na decisão do CEP) e **R-10** (retenção,
tratado na decisão 3 acima). Nenhuma linha de código reduz esses dois.

---

## 7. Decisão 6 — Enquadramento como dispositivo médico (SaMD / ANVISA)

> **Pergunta:** confirma-se que o aplicativo, apresentado como **ferramenta complementar
> experimental**, sem alegação diagnóstica ou terapêutica, **não** se enquadra como dispositivo
> médico sujeito a regulação sanitária?

**Por que precisa ser respondida.** A postura é deliberada e está travada no projeto: nenhuma tela,
texto ou material afirma eficácia; o aplicativo declara ao participante que **não é tratamento** e
que a evidência sobre frequências binaurais é limitada e inconsistente; o recomendador funciona
**por regras**, e nenhum modelo estatístico decide nada ao vivo. Isso reduz o risco de
enquadramento — mas "reduz" não é "afasta", e a confirmação não é técnica.

**Insumo pronto:** `lgpd-nit-checklist.md` item **G6**; postura científica registrada no `CLAUDE.md`;
seção 8 do TCLE (destaque "isto não é tratamento", com os contatos de emergência).

---

## 8. Folha de resposta

Preencher e devolver — o restante do projeto se ajusta a partir desta folha. Uma resposta parcial já
é útil: **a decisão 1, sozinha, destrava a coleta.**

| # | Decisão | Resposta | Quem decidiu | Data |
|---|---|---|---|---|
| 1 | **Base legal** do dado sensível de saúde (opção A / B / C / outra) ⛔ | | | |
| 1b | A UNINTA se enquadra como *órgão de pesquisa* (Art. 5º, XVIII)? | | | |
| 2 | **Encarregado (DPO)**: nome, canal público e prazo de resposta | | | |
| 3 | **Prazos de retenção**: aprova os propostos? Se não, quais? | | | |
| 4 | **Operadores**: contratos exigidos, enquadramento do Art. 33, provedor de SMTP indicado | | | |
| 5 | **RIPD/ROPA**: adotados? Risco residual aceito? Consulta prévia à ANPD? | | | |
| 6 | **SaMD/ANVISA**: confirmado o não enquadramento? | | | |

**Prazo desejado de retorno:** `[a combinar]` — a coleta não pode ser agendada antes da decisão 1.

---

## 9. Anexos (todos em PDF, gerados dos documentos do projeto)

| Documento | O que é | Serve a qual decisão |
|---|---|---|
| `Sereno_TCLE_rascunho` | Termo de Consentimento, 16 seções, versão preliminar | 1, 2, 3 |
| `Sereno_RIPD_rascunho` | Relatório de Impacto — 14 riscos, mitigações e residual | 1, 3, 5 |
| `Sereno_ROPA_rascunho` | Registro das Operações de Tratamento (Art. 37) — 8 operações | 1, 4, 5 |
| `Sereno_Retencao_rascunho` | Política de retenção e descarte — inventário e prazos propostos | 3 |
| `Sereno_Incidentes_rascunho` | Plano de resposta a incidentes, com notificação à ANPD (Art. 48) | 2, 5 |
| `lgpd-nit-checklist` | Mapeamento item a item: o que já está implementado e o que falta | todas |

---

> **Ressalva de competência.** Este documento e os anexos foram preparados pelo responsável técnico
> do projeto, que **não é profissional do direito nem membro do comitê de ética**. Eles descrevem o
> que o sistema efetivamente faz e **sinalizam** o que a legislação costuma exigir, com as opções
> mapeadas para reduzir o trabalho de quem decide. **Não são parecer jurídico e nada aqui foi
> aprovado.** O termo de consentimento está marcado como rascunho dentro do próprio aplicativo,
> justamente para que não seja confundido com documento em vigor.

Augusto André
*Responsável técnico — projeto Sereno*

---

*Sereno — estudo-piloto de viabilidade. O aplicativo é ferramenta complementar experimental; não
substitui avaliação ou tratamento profissional. Frequências binaurais têm evidência científica
limitada e inconsistente — por isso estão sendo estudadas.*
