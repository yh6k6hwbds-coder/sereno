# Dossiê de submissão ao CEP — o que já existe, o que falta e as 5 perguntas ao comitê

> **Natureza:** documento de trabalho do responsável técnico, para a pesquisadora responsável montar
> a submissão pela Plataforma Brasil. **Não substitui os modelos e exigências do CEP local.**
> **Base normativa:** Res. CNS nº 466/2012 e nº 510/2016 · LGPD (Lei nº 13.709/2018).

## Relação com o roteiro de julho

O `Roteiro_Submissao_CEP.docx` (v1.0, julho de 2026) continua válido no que descreve a **estrutura
do protocolo** (§4), o **plano de análise** (§6), o **monitoramento de segurança** (§7) e o
**cronograma com critérios de progressão** (§9) — nada disso mudou.

**Duas seções daquele roteiro estão superadas** e este dossiê as substitui:

- **§5, "esqueleto do TCLE"** — era um rascunho de parágrafos. Existe agora um **termo completo, de
  16 seções**, redigido na estrutura da resolução: `tcle-rascunho.md`. O esqueleto não deve mais ser
  usado.
- **§8, "Confidencialidade e LGPD"** — era uma lista de intenções ("recomendados"). As medidas estão
  **implementadas e verificáveis**, e há cinco documentos de conformidade escritos a partir do que o
  sistema faz. A seção 4 deste dossiê traz o que dizer ao comitê.

---

## 1. Situação da submissão em uma tabela

| Documento exigido na submissão | Existe? | Onde / o que falta |
|---|---|---|
| **Folha de rosto** (Plataforma Brasil) | ⬜ | Gerada no sistema e assinada pela instituição |
| **Projeto detalhado (protocolo)** | 🟡 | Estrutura no roteiro de julho §4. **Faltam os campos do `formulario-protocolo-clinico.md`** — critérios de elegibilidade, sessões por semana, tempo total |
| **TCLE** | 🟡 | **`tcle-rascunho.md` — 16 seções, completo**, salvo os campos em branco listados na seção 3 |
| **Instrumentos de coleta** | ✅ | PSQI, GAD-7 e SUS, com pontuação automática **versionada**; telas do aplicativo disponíveis para anexar. **Verificar o licenciamento do PSQI** |
| **Cronograma e orçamento** | ⬜ | Fases no roteiro de julho §9; custeio a definir |
| **Anuência da instituição / coparticipante** | ⬜ | Institucional |
| **Currículos (Lattes)** | ⬜ | Conforme exigência do CEP |
| **Declarações do pesquisador** | ⬜ | Sigilo, uso e destino dos dados, LGPD — o conteúdo pode citar as medidas da seção 4 |
| **Registro no ReBEC** | ⬜ | Boa prática recomendada no roteiro de julho; exigida por muitos periódicos |

---

## 2. As cinco perguntas ao comitê

Além de aprovar o mérito e o termo, há **cinco questões** que só o CEP resolve. Estão aqui juntas
para que possam ser levadas na mesma consulta.

### Pergunta 1 — Aprovação do texto do termo

O termo foi redigido cobrindo os elementos exigidos pela Res. CNS nº 466/2012: justificativa,
objetivos, procedimentos, desconfortos e riscos, benefícios, acompanhamento e assistência,
voluntariedade, sigilo e proteção de dados, ressarcimento, indenização, e contatos do pesquisador e
do próprio comitê. Ele é submetido para **aprovação de conteúdo e de linguagem**.

> O RIPD recomenda, antes da submissão, **testar a compreensão do texto com 2 ou 3 pessoas do perfil
> dos participantes**. Consentimento que não é compreendido não é informado. Esse teste ainda não
> foi feito.

### Pergunta 2 — O aceite no aplicativo substitui a assinatura?

**O que o sistema faz hoje.** O participante lê o **texto integral do termo na própria tela**, antes
de qualquer confirmação — não apenas um resumo — e o aceite grava: versão do termo aceita, data e
hora, a decisão (aceite ou recusa), um **resumo criptográfico do conteúdo exibido** e o endereço IP.
Se o texto do termo mudar, a versão muda, e o servidor **recusa** aceites contra a redação antiga.
O participante pode **retirar o consentimento sozinho** pelo aplicativo, sem falar com ninguém.

**A pergunta:** esse registro basta como consentimento, ou o estudo exige também uma via assinada?
E, se a via digital bastar, **como a via do participante deve ser entregue** a ele?

Hoje o termo diz `[a confirmar com o CEP]` nesses dois pontos (§11 e §16).

### Pergunta 3 — Eliminação do dado de pesquisa já coletado, a pedido do titular

**O que o sistema faz hoje.** Ao pedido de eliminação, o dado de **identificação** (nome, e-mail) é
apagado e a participação é encerrada. O dado **de pesquisa já coletado** é **mantido de forma
pseudonimizada** — prática padrão em pesquisa, e amparada na exceção de conservação para estudos.

**A pergunta:** o participante pode pedir também a eliminação do dado de pesquisa já coletado?
Em que condições — a qualquer momento, ou até um marco (por exemplo, o fechamento da base para
análise)? A resposta depende também da base legal que o NIT definir: se o tratamento se apoiar em
**consentimento**, a revogação pesa mais sobre o dado já coletado do que se apoiar na hipótese de
**estudos por órgão de pesquisa**.

### Pergunta 4 — Prazo de guarda dos dados

**Proposta:** 5 anos após o encerramento ou a publicação, para o conjunto de dados de pesquisa e
para a evidência de consentimento; a identificação de contato eliminada em até 30 dias após o
encerramento da coleta. O inventário completo, categoria por categoria, está na política de
retenção.

**A pergunta:** os prazos estão aprovados? Esta decisão é compartilhada com a assessoria jurídica e
está na mesma solicitação enviada ao NIT.

### Pergunta 5 — Salvaguardas de recrutamento (assimetria de poder) ⚠️

**Este é o maior risco residual da avaliação de impacto, e nenhuma medida técnica o reduz.**

Os participantes são, possivelmente, estudantes vinculados à mesma instituição que conduz a
pesquisa. Se o convite partir de alguém que avalia academicamente o candidato, aceitar — ou não
desistir — deixa de ser escolha inteiramente livre.

O termo já afirma, **em destaque**, que recusar ou desistir não afeta notas, vínculo ou atendimento,
e o aplicativo permite sair sem falar com ninguém. Isso é necessário e **não é suficiente**: o resto
é procedimento de convite.

**Proposta a submeter ao comitê:**
1. O convite é feito por pessoa **sem vínculo de avaliação** com o candidato.
2. A desistência **não precisa passar pelo pesquisador** — já garantido no aplicativo.
3. A lista de quem foi convidado e recusou **não chega** a quem avalia o candidato.

**A pergunta:** essas salvaguardas são suficientes? O comitê exige outras?

---

## 3. Campos do termo ainda em branco, por dono

Nenhum é do responsável técnico. A submissão só fecha quando os três donos responderem.

| Onde no termo | O que falta | De quem é |
|---|---|---|
| Cabeçalho, §15 | Título oficial, titulação e contatos da equipe | Pesquisadora responsável — `formulario-protocolo-clinico.md` |
| §4 | Critérios de inclusão e exclusão, idade mínima | Protocolo — idem |
| §5 | Sessões por semana, tempo total de participação | Protocolo — idem |
| §8 | Serviço de saúde de referência para encaminhamento | Pesquisadora responsável — idem |
| §10, §14 | Operacionalização da assistência, indenização e ressarcimento | Instituição — idem |
| §12 | **Base legal** do tratamento de dado de saúde | NIT / assessoria — `solicitacao-nit-base-legal.md` |
| §12, §15 | Encarregado (DPO) e canal de atendimento ao titular | NIT / UNINTA — idem |
| §13 | Prazo de guarda | Assessoria + CEP — pergunta 4 |
| §11, §16 | Via digital / entrega da via ao participante | CEP — pergunta 2 |
| §13 | Eliminação do dado de pesquisa a pedido | CEP — pergunta 3 |
| §15 | Nome, endereço, telefone, e-mail e horário do **próprio CEP** | O comitê |

---

## 4. O que dizer ao comitê sobre proteção de dados

Substitui a §8 do roteiro de julho. Cada afirmação abaixo corresponde a mecanismo implementado e
coberto por teste automatizado; o detalhamento item a item está no `lgpd-nit-checklist.md`.

- **Pseudonimização.** A pesquisa opera sobre um **código de estudo**, não sobre nomes. A exportação
  para análise sai **sem identificação** e com o grupo apenas **codificado** — a chave que liga o
  código ao grupo real fica fora da base.
- **Separação e cifra da identificação.** Nome e e-mail são cifrados individualmente e guardados
  apartados do dado de pesquisa. Sem a chave, não são legíveis nem por quem tenha o banco.
- **Cegamento.** Nem o participante nem a equipe conhecem o grupo durante o estudo. Nenhuma
  permissão do sistema revela o grupo, e os dois braços são indistinguíveis do lado do aplicativo —
  mesma interface, mesma duração, mesma visualização.
- **Controle de acesso.** Acesso por papel, definido no servidor, com **segundo fator obrigatório**
  para toda a equipe. Cada pessoa define a própria senha por link de uso único: nem o administrador
  conhece a senha de outra pessoa, o que torna confiável o registro de quem fez o quê.
- **Trilha de auditoria inalterável.** As ações sensíveis — consentimento, sorteio, exportação,
  eliminação, quebra de cegamento — são registradas de forma que **não podem ser apagadas nem
  alteradas**, garantia imposta pelo próprio banco de dados, não apenas pelo programa.
- **Quebra de cegamento controlada.** O procedimento de desbloqueio exige **duas pessoas** e fica
  registrado.
- **Eventos adversos.** O canal de relato permanece aberto **mesmo depois de o participante retirar
  o consentimento** — segurança acima da conveniência do estudo — e a equipe é avisada
  automaticamente se um aviso de evento adverso deixar de ser entregue.
- **Direitos do titular.** Acesso aos próprios dados, eliminação da identificação, e retirada de
  consentimento em **autoatendimento**.
- **Residência dos dados.** Servidor e banco no Brasil (São Paulo).
- **Registros sem identificação.** Os registros de funcionamento e as métricas não contêm dado
  pessoal nem o grupo do participante.
- **Documentos de conformidade.** Avaliação de impacto (RIPD) com 14 riscos ao participante,
  registro das operações de tratamento, política de retenção e plano de resposta a incidentes —
  todos em versão preliminar, submetidos à adoção institucional.

> **O que é honesto declarar como ainda não resolvido:** a base legal do tratamento não está
> definida (pendência com o NIT), os prazos de retenção não estão aprovados, o Encarregado não foi
> designado, e não houve teste de intrusão independente. A recomendação técnica registrada é
> **não iniciar coleta com dados reais** antes disso.

---

## 5. Checklist antes de submeter

- [ ] Campos do `formulario-protocolo-clinico.md` preenchidos e transcritos para o termo.
- [ ] Termo revisado e aprovado pela pesquisadora responsável.
- [ ] **Teste de compreensão** do termo com 2–3 pessoas do perfil dos participantes.
- [ ] Termo adaptado ao **modelo do CEP local**, se houver modelo próprio.
- [ ] Desfechos, versões de pontuação e regras de análise **congelados** antes da coleta.
- [ ] Instrumentos em versões validadas em PT-BR; **licenciamento do PSQI verificado**.
- [ ] As cinco perguntas da seção 2 levadas ao comitê **na mesma consulta**.
- [ ] Documentos da Plataforma Brasil completos (folha de rosto, anuências, declarações, Lattes).
- [ ] Registro no ReBEC providenciado.
- [ ] Coerência entre protocolo, termo e este dossiê conferida — os três precisam contar a mesma
      história.

---

## 6. Quando o parecer chegar

1. **Termo aprovado:** transcrevo o texto final, regenero o texto exibido no aplicativo a partir do
   mesmo documento (há verificação automática que falha se os dois divergirem) e troco a versão do
   termo de `0.1.0-rascunho` para **`1.0.0`** — no servidor, no aplicativo e no resumo exibido.
   O sufixo "rascunho" existe hoje exatamente para que nenhum aceite anterior à aprovação possa ser
   lido como consentimento a um termo aprovado; ele sai junto com o aviso de rascunho na tela.
2. **Respostas às perguntas 2, 3 e 4:** ajusto as seções 11, 13 e 16 do termo e alinho a política de
   retenção, o registro das operações e a avaliação de impacto — os quatro documentos precisam
   contar a mesma história.
3. **Salvaguardas da pergunta 5:** entram no procedimento de recrutamento e na avaliação de impacto,
   que hoje classifica esse risco como **residual Alto**.
4. **Se houver exigências:** cada uma vira um item rastreável, com o documento correspondente
   atualizado.

Augusto André
*Responsável técnico — projeto Sereno*

---

*Sereno — estudo-piloto de viabilidade. O aplicativo é ferramenta complementar experimental; não
substitui avaliação ou tratamento profissional. Frequências binaurais têm evidência científica
limitada e inconsistente — por isso estão sendo estudadas.*
