# Sereno — o que falta para o piloto começar

> **Para:** Dra. Bianca Régia Silva (orientadora) · **De:** Augusto André
> **Data:** 22 de julho de 2026 · **Assunto:** pendências para iniciar a coleta do estudo-piloto

**Resumo:** o desenvolvimento do aplicativo e do servidor está concluído e testado. O que impede o
piloto de começar não é software — são decisões institucionais, éticas e jurídicas que não posso
tomar. Este documento lista essas pendências, organizadas por quem precisa resolvê-las, e indica o
material que já preparei para apoiar cada uma.

> ⚠️ **BLOQUEIO PRINCIPAL**
>
> **A base legal para o tratamento de dados sensíveis de saúde ainda não foi definida.** Enquanto
> isso não for resolvido pelo NIT / assessoria jurídica, **não devemos coletar dados reais de
> participantes**. Este item não depende de nenhum outro: pode e deve ser tratado primeiro. Todos os
> demais podem avançar em paralelo.

## 1. Situação atual

O sistema está funcional de ponta a ponta: cadastro e triagem do participante, consentimento
registrado com versão e data, questionários de linha de base, sorteio dos grupos com sigilo, sessões
de áudio, diário de sono, questionários de seguimento, registro de eventos adversos, exportação de
dados sem identificação e relatório de análise cego.

- **349 testes automatizados** (307 no servidor, 42 no aplicativo), todos passando.
- Dados de identificação **criptografados e separados** dos dados da pesquisa; análise feita sobre
  dados pseudonimizados (sem nome).
- Sorteio duplo-cego: nem o participante nem a equipe sabem o grupo durante o estudo.
- Registro de auditoria das ações sensíveis, que não pode ser apagado nem alterado.
- Hospedagem **configurada** para servidor em território brasileiro (São Paulo).

*Observação:* o sistema roda hoje em ambiente de testes. Ainda **não está publicado em servidor
definitivo** — isso depende de contratação (seção 5) e, antes disso, da definição da base legal.

Preparei também os documentos exigidos pela LGPD e pelo comitê de ética — todos em versão
preliminar, listados na seção 6.

## 2. O que preciso da senhora (ou do protocolo de pesquisa)

Estes itens não existem em nenhum documento do projeto e **só podem vir do protocolo clínico**. Sem
eles o termo de consentimento fica incompleto:

| Informação | Onde faz falta |
|---|---|
| **Critérios de inclusão e exclusão** (quem pode participar; idade mínima; condições que impeçam a participação) | Seção 4 do termo de consentimento e regra de triagem do sistema |
| **Número de sessões por semana** e duração total da participação | Seção 5 do termo de consentimento |
| **Título oficial do estudo** e dados de contato da equipe | Cabeçalho e seção 15 do termo |
| **Serviço de saúde de referência** para encaminhamento, caso um participante precise | Seção 8 do termo (junto de CVV 188 e SAMU 192) |

## 3. O que precisa ir ao Comitê de Ética (CEP)

| Pendência | Observação |
|---|---|
| **Aprovação do termo de consentimento** | Redigi uma versão preliminar completa, na estrutura da Resolução CNS nº 466/2012, para sua revisão |
| **O aceite no aplicativo substitui a assinatura?** | O sistema registra data, hora e versão do termo aceito. Falta confirmar se isso basta ou se é exigida também uma via assinada |
| **Retenção após desistência** | Hoje o termo informa que os dados já coletados são mantidos sem identificação. Confirmar se o participante pode pedir a exclusão também desses dados |
| **Prazo de guarda dos dados** | Proposto: 5 anos após o encerramento. Precisa de aprovação |

> ⚠️ **PONTO QUE MERECE ATENÇÃO ESPECIAL**
>
> **Risco de constrangimento no convite.** Se o participante for convidado por alguém que o avalia
> academicamente, aceitar (ou não desistir) deixa de ser uma escolha inteiramente livre. O termo já
> afirma, em destaque, que recusar ou desistir não afeta notas, vínculo ou atendimento — mas **texto
> não resolve isso sozinho**.
>
> Sugestão para avaliarmos com o CEP: que o convite seja feito por pessoa **sem vínculo de
> avaliação** com o candidato, e que a desistência não precise passar pelo pesquisador (no
> aplicativo, o participante já pode sair sozinho, sem falar com ninguém).

## 4. O que depende do NIT / assessoria jurídica

| Pendência | Situação |
|---|---|
| **Base legal** do tratamento de dado sensível de saúde (LGPD, Art. 11) | Bloqueia a coleta |
| **Encarregado de Proteção de Dados (DPO)** designado, com canal de contato divulgado ao participante | Pendente |
| **Contratos com fornecedores** (hospedagem, envio de e-mail) e análise de transferência internacional | Pendente |
| **Adoção formal** do relatório de impacto (RIPD) e do registro de operações (ROPA) | Rascunhos prontos |
| Confirmar que o app **não se enquadra como dispositivo médico** (ANVISA), dado que é apresentado como ferramenta complementar experimental | A confirmar |

## 5. Operacional (comigo)

São itens que já estão implementados e testados, mas dependem de infraestrutura contratada ou de uma
decisão prévia das seções anteriores. Assumo todos:

- Contratar o serviço de envio de e-mail (sem ele, o código de acesso não chega ao participante).
- Publicar o servidor em ambiente definitivo (depende de forma de pagamento).
- Programar a rotina automática de descarte de dados temporários.
- Atualizar a versão do termo no sistema assim que o CEP aprovar o texto.
- Avaliar uma revisão de segurança externa antes da coleta com dados reais.

## 6. Documentos já preparados para apoiar essas decisões

Todos são **rascunhos técnicos**, escritos a partir do que o sistema de fato faz. Servem de ponto de
partida e economizam trabalho de quem for decidir — mas nenhum substitui parecer jurídico ou do
comitê de ética:

- **Termo de Consentimento Livre e Esclarecido** — versão preliminar completa, 16 seções.
- **Relatório de Impacto à Proteção de Dados (RIPD)** — 14 riscos ao participante, com as medidas de
  proteção já implementadas e o risco que permanece.
- **Registro das Operações de Tratamento (ROPA)** — exigido pelo Art. 37 da LGPD.
- **Política de retenção e descarte** — o que é guardado, por quanto tempo e como é eliminado.
- **Plano de resposta a incidentes** — o que fazer em caso de vazamento, incluindo notificação à ANPD.
- **Checklist LGPD** — mapeamento item a item do que já está pronto e do que falta.

Posso enviar qualquer um deles, ou todos, no formato que preferir.

> **Observação importante sobre estes materiais.** Sou o responsável técnico do projeto, não
> profissional do direito nem membro do comitê de ética. Os documentos acima **sinalizam** o que a
> legislação e as normas costumam exigir e mostram o que o sistema já faz a respeito — mas as
> decisões (base legal, prazos, texto final do termo, aprovação ética) são de quem tem competência
> para tomá-las. Nada foi aprovado até aqui, e o termo de consentimento está marcado como rascunho
> dentro do próprio aplicativo, para que não seja confundido com um documento em vigor.

## 7. Sugestão de ordem

- **1º — Base legal** (NIT/jurídico): destrava todo o resto.
- **2º — Detalhes do protocolo** (seção 2 deste documento): completam o termo.
- **3º — Submissão ao CEP**, com o termo revisto e as salvaguardas de convite.
- **4º — DPO e prazos de guarda**, que podem correr em paralelo.
- **5º — Operacional** (comigo), quando houver o que colocar no ar.

Fico à disposição para detalhar qualquer ponto, apresentar o sistema funcionando ou acompanhar uma
reunião com o NIT.

Augusto André
*Responsável técnico — projeto Sereno*

---

*Sereno — estudo-piloto de viabilidade. O aplicativo é ferramenta complementar experimental; não
substitui avaliação ou tratamento profissional. Frequências binaurais têm evidência científica
limitada e inconsistente — por isso estão sendo estudadas.*
