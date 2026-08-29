# Formulário do protocolo clínico — o que falta para fechar o termo de consentimento

> **Para:** Dra. Bianca Régia Silva — pesquisadora responsável / orientadora
> **De:** Augusto André — responsável técnico do projeto Sereno
> **Assunto:** 14 informações que **só existem no protocolo de pesquisa** e sem as quais o termo de
> consentimento não pode ser submetido ao CEP.

## Por que este formulário existe

O termo de consentimento está redigido por inteiro — 16 seções, na estrutura da Resolução CNS
nº 466/2012 — **exceto** pelos campos abaixo. Eles não estão em nenhum documento do projeto porque
não são decisões de engenharia: vêm do desenho da pesquisa. Enquanto estiverem em branco, o termo
não fecha, e sem termo fechado não há submissão ao comitê de ética.

**Como usar:** preencher a coluna "Resposta". Onde a resposta já estiver decidida no projeto de
pesquisa, basta indicar onde ("conforme item X do projeto") — eu transcrevo. Não é preciso redigir
em linguagem de termo: **eu adapto para a linguagem acessível exigida pela resolução** e devolvo
para revisão.

**Três campos têm efeito direto sobre o sistema**, não apenas sobre o texto — estão marcados com
⚙️ e detalhados na seção 4. O restante é redação.

---

## 1. Identificação do estudo e da equipe

Vai para o cabeçalho e para a seção 15 do termo (contatos).

| # | Campo | Formato esperado | Resposta |
|---|---|---|---|
| 1 | **Título oficial do estudo**, como aprovado/registrado no projeto | Texto | |
| 2 | **Pesquisadora responsável** — titulação e vínculo completos | Ex.: "Dra. …, docente do curso de …, UNINTA" | |
| 3 | **Demais pesquisadores** da equipe | Nomes e papéis | |
| 4 | **Contato da pesquisadora responsável** para o participante | Telefone, e-mail, endereço institucional e **horário de atendimento** | |
| 5 | **Contato da equipe de pesquisa** (se diferente do anterior) | Idem | |

---

## 2. Critérios de elegibilidade (seção 4 do termo) ⚙️

Hoje o termo diz, literalmente, `[a confirmar com o protocolo — critérios de inclusão e exclusão]`.

| # | Campo | Formato esperado | Resposta |
|---|---|---|---|
| 6 | **Idade mínima** | Número. O termo já pressupõe participantes adultos | |
| 7 | ⚙️ **Critérios de inclusão** — lista fechada | Uma linha por critério, redigida como condição verificável ("apresenta sintomas leves a moderados de ansiedade", "possui smartphone com fones estéreo") | |
| 8 | ⚙️ **Critérios de exclusão** — lista fechada | Idem. O roteiro de submissão de julho sugeria: epilepsia ou crises não controladas, ideação suicida ativa, uso conflitante de outra intervenção. **Confirmar se são esses e se são todos** | |

> **Já incluí um critério por conta própria, e ele precisa da sua avaliação:** "**compreender
> português**". O aplicativo e o termo existem **apenas em português** desde a decisão de agosto —
> antes o aplicativo também se apresentava em inglês, o que criava a possibilidade de alguém aceitar
> um termo que não teve como ler. Não é preferência de interface: é a condição para que o
> consentimento seja informado. A redação vai ao CEP para confirmação.

---

## 3. Dose e duração da intervenção (seção 5 do termo) ⚙️

O termo já afirma: sessões de **aproximadamente 20 minutos**, com **fones de ouvido**, ao longo de
**4 semanas**, com aproximadamente **40 participantes**. Falta o resto.

| # | Campo | Formato esperado | Resposta |
|---|---|---|---|
| 9 | ⚙️ **Número de sessões por semana** | Número. O roteiro de julho registrava "5×/semana" — **confirmar** | |
| 10 | ⚙️ **Número total de sessões prescritas** no estudo inteiro | Número. Decorre do item 9, mas precisa ser explícito (ver seção 4 abaixo) | |
| 11 | **Tempo total estimado de participação**, incluindo questionários | Ex.: "cerca de X horas ao longo de 4 semanas" — é o que o participante lê para decidir | |

---

## 4. ⚙️ O que muda no sistema conforme estas respostas

Três dos campos acima não são só texto do termo. Registro aqui porque a diferença é fácil de passar
despercebida — e uma delas produziria um **número errado no relatório final** sem nenhum aviso.

**Campos 9 e 10 — o denominador da adesão.** A taxa de adesão é calculada hoje contra
**20 sessões prescritas em 4 semanas**, valor que está fixado como padrão no código de pontuação
(`backend/app/modules/instruments/instruments_scoring.py`, função `adherence_metrics`). Esse número
veio da suposição "5 sessões por semana × 4 semanas" registrada no roteiro de julho — **não de um
protocolo aprovado**. Se o protocolo disser outra coisa, a adesão sai proporcionalmente errada, e
como o relatório apresenta um percentual plausível, o erro não se denuncia sozinho. **A adesão é um
dos desfechos primários do piloto**, e um dos critérios de progressão para um ensaio definitivo.
Corrigir é trivial (um parâmetro), desde que eu saiba o número correto.

**Campos 7 e 8 — a triagem.** O sistema **não precisa de alteração** para receber os critérios: ele
registra a lista de itens que a equipe informar e aplica uma regra fixa e versionada — elegível se
todas as inclusões forem verdadeiras e nenhuma exclusão estiver presente. O que falta é a **lista
canônica de itens**, para que toda triagem use exatamente os mesmos e a elegibilidade seja
comparável entre participantes. Sem essa lista, cada triagem pode ser registrada com nomes
diferentes para o mesmo critério, e o dado deixa de ser analisável.

---

## 5. Rede de apoio e assistência (seções 8, 10 e 14 do termo)

| # | Campo | Formato esperado | Resposta |
|---|---|---|---|
| 12 | **Serviço de saúde de referência** para encaminhar um participante em sofrimento | Nome, endereço e forma de acesso. O termo já traz **CVV 188**, **SAMU 192** e **190**; falta a referência local/institucional | |
| 13 | **Como a instituição operacionaliza** a assistência integral e gratuita por eventuais danos, e a garantia de indenização (Res. CNS 466/2012) | Descrição do procedimento — a quem o participante recorre, na prática | |
| 14 | **Ressarcimento de despesas** — há alguma despesa prevista (deslocamento para etapa presencial, uso de dados móveis)? Como o participante solicita? | Descrição. Se não houver etapa presencial e nenhuma despesa prevista, basta dizer isso | |

---

## 6. O que **não** está neste formulário, e por quê

Para não misturar quem decide o quê, estes campos do termo estão em branco mas **não são seus**:

| Campo em branco no termo | De quem é | Onde está sendo tratado |
|---|---|---|
| **Base legal** do tratamento de dados de saúde (§12) | NIT / assessoria jurídica | `solicitacao-nit-base-legal.md`, decisão 1 — **bloqueia a coleta** |
| **Encarregado (DPO)** e canal ao titular (§12, §15) | NIT / UNINTA | idem, decisão 2 |
| **Prazo de guarda** dos dados (§13) | Assessoria + CEP | idem, decisão 3 |
| Dados do **CEP** — nome, endereço, contatos (§15) | O próprio comitê | `dossie-submissao-cep.md` |
| Se a **via digital basta** ou se é exigida via assinada (§11, §16) | CEP | idem, pergunta 2 |
| Se o participante pode pedir **eliminação do dado de pesquisa** já coletado (§13) | CEP + assessoria | idem, pergunta 3 |

---

## 7. O que acontece depois que este formulário voltar

1. Transcrevo as respostas para o termo, na linguagem acessível exigida pela resolução, e devolvo
   para sua revisão.
2. Regenero o texto que o participante lê **dentro do aplicativo** — ele é gerado do mesmo
   documento que vai ao comitê, e há uma verificação automática que falha se os dois divergirem.
   Isso existe para que o texto submetido e o texto exibido não se afastem sem ninguém notar.
3. Ajusto o número de sessões prescritas no cálculo de adesão (seção 4).
4. Junto com as respostas do CEP e do NIT, o termo fica pronto para a versão final — hoje ele está
   marcado como **rascunho** dentro do próprio aplicativo, deliberadamente, para que nenhum aceite
   de hoje seja lido depois como consentimento a um termo aprovado.

Fico à disposição para preencher isto junto, se for mais rápido do que escrever.

Augusto André
*Responsável técnico — projeto Sereno*

---

*Sereno — estudo-piloto de viabilidade. O aplicativo é ferramenta complementar experimental; não
substitui avaliação ou tratamento profissional. Frequências binaurais têm evidência científica
limitada e inconsistente — por isso estão sendo estudadas.*
