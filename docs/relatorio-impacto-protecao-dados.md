# Relatório de Impacto à Proteção de Dados Pessoais (RIPD/DPIA) — Sereno (piloto) · RASCUNHO

> **Status: RASCUNHO TÉCNICO para validação.** Este documento organiza, na estrutura de um RIPD
> (**LGPD Art. 5º, XVII e Art. 38**), a descrição dos tratamentos, os **riscos aos titulares** e as
> **medidas de mitigação** já implementadas no Sereno. É **insumo** para o RIPD formal, que é
> **elaborado sob responsabilidade do controlador (UNINTA)** e do **Encarregado/DPO**.
>
> **O que este documento NÃO é:** parecer jurídico, e não é a decisão sobre a base legal. A avaliação
> de **necessidade e proporcionalidade** (§4) e a **conclusão** (§10) trazem a leitura **técnica** dos
> riscos; o juízo jurídico e ético é do NIT/assessoria e do **CEP**. Este texto **sinaliza, não
> decide** (`CLAUDE.md`). Itens `[a confirmar]` / `[a preencher]` exigem decisão humana.
>
> Atende ao item **G2** do `docs/lgpd-nit-checklist.md`. Insumos: `registro-operacoes-tratamento.md`
> (ROPA, G3), `politica-retencao-descarte.md` (E1/E2), `plano-resposta-incidentes.md` (G4) e os ADRs
> em `docs/decisoes/`.

---

## 1. Por que este relatório é necessário

O RIPD é exigível quando o tratamento pode gerar **risco às liberdades civis e aos direitos
fundamentais** (Art. 38; Art. 10, §3º). O Sereno reúne, simultaneamente, os fatores que a prática
regulatória associa a alto risco:

1. **Dado sensível de saúde** (Art. 11) — sono, ansiedade, eventos adversos.
2. **Titulares em posição potencialmente vulnerável** — pessoas com queixa de sono/ansiedade,
   possivelmente estudantes vinculados à própria instituição que conduz a pesquisa (ver R-09).
3. **População pequena e concentrada** (N≈40, uma instituição, uma cidade) — o que eleva
   materialmente o risco de **reidentificação** de dado pseudonimizado (ver R-01).
4. **Tecnologia experimental** com registro de `feature_vector` para modelagem futura.

A conclusão prática: o RIPD aqui **não é formalidade** — dois dos riscos abaixo (R-01 e R-02) são
específicos deste desenho e não seriam capturados por um checklist genérico.

## 2. Identificação `[a preencher]`

- **Controlador:** UNINTA (Centro Universitário INTA), Sobral/CE. `[dados/representante legal]`
- **Encarregado (DPO):** `[a preencher — nome, contato público]` (item G1, **pendente**)
- **Pesquisador responsável / orientadora:** Dra. Bianca Régia Silva. `[contato]`
- **Responsável técnico (elaboração do insumo):** mantenedor do repositório.
- **Data desta versão:** 2026-07-22 · **Versão:** rascunho 1
- **Operadores:** ver ROPA §4 (Fly.io, provedor SMTP `[a definir]`, GitHub Pages).

## 3. Escopo, metodologia e limites

**Escopo:** o backend do Sereno (PostgreSQL em `gru`/BR), o app Flutter e os artefatos correlatos
(chave selada A/B, backups, logs), no **piloto de 4 semanas, N≈40**. **Fora do escopo:** documentos
institucionais fora do sistema (vias físicas do TCLE, atas do CEP) e tratamentos futuros não
construídos (vestíveis persistidos, ML de decisão) — que exigiriam **revisão deste RIPD** (§11).

**Metodologia:** (a) inventário das operações a partir do ROPA (8 operações, OP-01…08); (b)
identificação de riscos **na perspectiva do titular** — o dano que a pessoa sofre, não o prejuízo da
instituição; (c) classificação por **probabilidade × impacto**, na mesma escala do plano de
incidentes (Baixo/Médio/Alto/Crítico), para que um risco previsto aqui e um incidente real lá sejam
falados na mesma língua; (d) medidas de mitigação **rastreáveis a código/ADR**; (e) **risco
residual** declarado com honestidade, inclusive quando permanece Alto.

**Limite de confiabilidade:** a avaliação cobre o que é verificável no sistema (código, testes, CI).
Riscos que dependem de **conduta humana** (quem tem acesso, como o TCLE é aplicado, como o convite é
feito) são apontados, mas não podem ser medidos aqui — dependem do CEP e do NIT.

## 4. Necessidade e proporcionalidade

| Critério | Avaliação técnica | Situação |
|---|---|---|
| **Finalidade específica** | Pesquisa de **viabilidade** de 4 semanas; ansiedade e sono são desfechos **exploratórios** (não há claim de eficácia) | 🟡 Escopo travado no `CLAUDE.md`; texto do TCLE **pendente** (A1/B2) |
| **Base legal** | Dado sensível → **Art. 11**; tipicamente consentimento específico e destacado (I) e/ou estudo em saúde (II, "c"), articulado com Res. CNS 466/2012 | ⬜ **Decisão do NIT/assessoria (A2)** — *bloqueia o piloto com dados reais* |
| **Adequação** | Os dados coletados (GAD-7, PSQI, SUS, telemetria de sessão, diário, EA) correspondem 1:1 aos desfechos declarados no protocolo | ✅ |
| **Necessidade / minimização** | PII limitada a **nome e e-mail**; nada de CPF, endereço, telefone, documento ou dado clínico além dos instrumentos versionados. Pesquisa opera sob `study_code` | ✅ (Art. 6, III) |
| **Proporcionalidade do risco** | Intervenção não invasiva, áudio em faixas seguras validadas por FFT; recomendador **por regras**, ML nunca decide ao vivo | ✅ (inegociáveis #3 e #5) |
| **Alternativa menos invasiva** | Coleta anônima pura foi considerada e é **inviável**: o desenho exige seguimento longitudinal do mesmo participante (linha de base → sessões → seguimento) e contato para OTP e para conduta em evento adverso. A pseudonimização é o menor tratamento compatível com a finalidade | ✅ justificado |

**Leitura técnica:** o tratamento é proporcional à finalidade **desde que** a base legal (A2) seja
definida e o TCLE reflita fielmente a retenção pós-revogação (D3). Sem A2, o restante fica suspenso.

## 5. Descrição do tratamento e ciclo de vida do dado

Detalhe por operação no **ROPA** (`registro-operacoes-tratamento.md`, OP-01…08). Resumo do fluxo:

```
Convite → Triagem (saúde, sensível) → TCLE (consentimento versionado, com IP)
   → Contato (nome/e-mail CIFRADOS, separados)  → OTP por e-mail → app
   → Linha de base (GAD-7/PSQI) → Randomização (braço CODIFICADO A/B; chave SELADA fora do banco)
   → Sessões de áudio + telemetria → Diário → Pós-sessão → Evento adverso (alerta à equipe, sem PII)
   → Seguimento → DATA LOCK (abre a chave A/B) → Export pseudonimizado → Análise cega
   → Retenção (proposta 5 anos [a confirmar]) → Eliminação/anonimização
```

**Duas separações estruturam a proteção** e devem ser lidas juntas:
- **PII ⟂ pesquisa** — o contato vive cifrado (envelope DEK/KEK, ADR-088) e separado do dado de
  pesquisa, que só conhece o `study_code`.
- **Braço ⟂ todo mundo** — nenhuma permissão de RBAC revela ativo/sham; a chave A/B→condição é
  custodiada fora do banco e o guard de produção **recusa subir** com o default público (ADR-077).

## 6. Consulta a partes interessadas

| Parte | Situação |
|---|---|
| **CEP/CONEP** | Submissão em preparação (G5) — é a instância que avalia risco ao participante e aprova o TCLE |
| **Encarregado (DPO)** | ⬜ Não designado (G1) — **este RIPD não pode ser concluído formalmente sem ele** |
| **NIT / assessoria jurídica** | Consulta pendente sobre A2 (base legal), F2/F3 (DPAs) e G6 (SaMD/ANVISA) |
| **Titulares / representantes** | Não consultados. **Sugestão:** teste de compreensão do TCLE com 2–3 pessoas do perfil antes da submissão — mede se o consentimento é de fato informado, que é o pressuposto da base legal `[a confirmar com o CEP]` |

## 7. Riscos aos titulares

Escala: **Probabilidade** (Baixa/Média/Alta) × **Impacto ao titular** (Baixo/Médio/Alto/Muito alto).
"Residual" = risco **depois** das medidas já implementadas (§8).

| # | Risco ao titular | Prob. | Impacto | Nível | Residual |
|---|---|---|---|---|---|
| **R-01** | **Reidentificação** do dataset pseudonimizado por singularização (N≈40, uma instituição; idade+sexo+padrão de sono podem tornar um caso único) | Média | Alto | **Alto** | 🟠 Médio |
| **R-02** | **Vazamento do vínculo** "esta pessoa participa de um estudo de ansiedade/sono" — o vínculo é, por si só, dado sensível, mesmo sem as respostas | Baixa | Muito alto | **Alto** | 🟢 Baixo |
| **R-03** | Acesso indevido a dado de pesquisa por **pessoa da própria equipe** (insider) além do necessário | Média | Alto | **Alto** | 🟠 Médio |
| **R-04** | **Quebra de cegamento** — participante descobre o braço; frustra o estudo e pode gerar decepção/nocebo em quem descobre estar no sham | Baixa | Médio | **Médio** | 🟢 Baixo |
| **R-05** | **Dano à saúde** por adiar cuidado profissional, tomando o app como tratamento | Média | Muito alto | **Alto** | 🟠 Médio |
| **R-06** | **Evento adverso** relatado e não percebido a tempo pela equipe | Baixa | Alto | **Médio** | 🟠 Médio |
| **R-07** | **Comprometimento do e-mail** do participante → acesso à conta via OTP | Baixa | Alto | **Médio** | 🟢 Baixo |
| **R-08** | **Uso além da finalidade** (*function creep*): dado do piloto reaproveitado para modelo/produto sem nova base legal | Média | Alto | **Alto** | 🟠 Médio |
| **R-09** | **Consentimento viciado por assimetria de poder** — participante que é aluno/paciente de quem convida sente-se pressionado a aceitar ou a não desistir | Média | Alto | **Alto** | 🔴 **Alto** |
| **R-10** | **Retenção além do necessário** — dado que deveria ser expurgado permanece (transitórios já cobertos; **dataset** não, e prazos não aprovados) | Alta | Médio | **Alto** | 🔴 **Alto** |
| **R-11** | **Perda/indisponibilidade** de dado de pesquisa (falha de backup) — participante colaborou e o dado se perde | Baixa | Médio | **Médio** | 🟠 Médio |
| **R-12** | **Transferência internacional** / acesso por operador estrangeiro sem DPA | Média | Médio | **Médio** | 🟠 Médio |
| **R-13** | Vazamento de **PII em log/métrica/mensagem de erro** | Baixa | Alto | **Médio** | 🟢 Baixo |
| **R-14** | Inclusão de **titular sem plena capacidade** (menor de idade; pessoa em crise aguda) sem o cuidado adicional exigido | Baixa | Muito alto | **Alto** | 🟠 Médio `[a confirmar critérios com o CEP]` |

## 8. Medidas de mitigação (rastreáveis a código/ADR)

| # | Medidas já implementadas | Evidência |
|---|---|---|
| R-01 | Pseudonimização por `study_code`; export **sem PII e sem condição** (só A/B); dataset de ML **offline**, com índice ordinal e **sem hora de parede** (evita correlação temporal); RBAC nos endpoints de pesquisa | ADR-061/083; `test_export.py`, `test_ml_features.py` |
| R-02 | PII **cifrada** (AES-256-GCM, envelope DEK/KEK; AAD amarra participante+campo) e **separada** da pesquisa; alerta de EA à equipe **sem PII**; auditoria sem PII | ADR-059/087/088/085/086 |
| R-03 | RBAC no servidor (nenhuma permissão revela o braço); **MFA obrigatório**; auditoria **append-only no banco** (trigger aborta UPDATE/DELETE mesmo do dono); lifecycle de staff (suspender invalida o token já emitido); desbloqueio exige **duas pessoas** | ADR-043/074/086/081/075 |
| R-04 | Sham ativo (Δf=0) com **UI idêntica**; visualização **não reativa** ao áudio; handle neutro ao cliente; headers de áudio neutros; 429 do endpoint público idêntico nos dois braços; guard de produção da chave selada | Inegociáveis #1/#2; ADR-053/077/082/090 |
| R-05 | Aviso persistente "ferramenta complementar, não substitui cuidado profissional"; postura anti-*overclaim* obrigatória em toda copy; tela de EA grave reforça **192/CVV 188** | `CLAUDE.md` (postura científica); ADR-073 |
| R-06 | `POST /adverse-events` sempre acessível — **inclusive após a retirada do consentimento** (segurança acima da conveniência do estudo); notificação à equipe em EA moderate/severe; guardrail de tolerabilidade de-escalona a recomendação | ADR-089; ADR-063/085; ADR-068 |
| R-07 | OTP **só como hash**, uso único, expira, tentativas limitadas, **nunca logado**; rate limit por IP real; denylist de `jti` | ADR-063/064/078/085 |
| R-08 | Escopo travado (`CLAUDE.md`); **ML nunca decide ao vivo** (teste guarda que ingerir vestível não cria recomendação); vestíveis são *seam* que **descarta** por padrão; features ML só consolidam o já registrado | Inegociável #5; ADR-068/083/084 |
| R-10 | Eliminação da PII (`erase`), revogação **self-service**, crypto-shredding viável pela rotação por id de chave, status do titular; **expurgo dos transitórios de OTP** (idempotente, auditado só na contagem, nunca apaga desafio vivo) | ADR-066/089/087/088; **ADR-091** |
| R-11 | Migrações versionadas; integridade no banco (FK/CHECK/UNIQUE); `/ready` real evita servir réplica com banco fora | ADR-065/090 |
| R-12 | **Residência dos dados no Brasil** (`gru`/São Paulo) | ADR-076; inegociável #6 |
| R-13 | Logs JSON só com método/rota/status/latência; métricas com rótulo por **template** de rota; erros em problem+json sem eco de dado; corpo do `/ready` sem DSN/host/credencial | ADR-067/080/090 |

### 8.1. Riscos com mitigação **incompleta** — leitura honesta

- **R-09 (assimetria de poder) — residual ALTO, e nenhum código resolve.** É o risco mais alto deste
  relatório e é inteiramente **procedimental**: depende de *quem convida*, de como o convite é
  redigido e de a desistência não ter custo. Medidas a decidir com o CEP: convite por pessoa **sem
  vínculo de avaliação** com o candidato; TCLE explicitando que recusar/desistir **não afeta nota,
  atendimento ou vínculo**; canal de desistência que não passe pelo pesquisador. **O sistema já
  contribui no que lhe cabe** — a retirada é self-service e não exige justificar-se a ninguém
  (ADR-089) —, mas isso é o fim do problema, não o começo dele.
- **R-10 (retenção) — residual ALTO, agora por motivo mais estreito.** Avançou: os **transitórios de
  autenticação** (OTP expirados) já têm expurgo implementado, idempotente e auditado (ADR-091) — era
  o único prazo da política que não dependia de aprovação do CEP. Continua **Alto** por duas razões
  que não mudaram: (a) o expurgo do **dataset de pesquisa** não existe e **não pode existir** antes de
  os prazos do E1 serem aprovados — sem prazo, não há o que agendar; (b) mesmo o expurgo pronto
  **só roda se alguém o agendar** (cron/máquina agendada), o que hoje não está configurado. Enquanto
  isso, a política de retenção segue mais **intenção** do que controle — menos do que era, ainda não
  o suficiente.
- **R-01 (reidentificação) — residual MÉDIO, irredutível por desenho.** Com N≈40 numa única
  instituição, nenhuma medida técnica elimina a singularização: quem tenha acesso ao dataset **e**
  conheça o grupo pode inferir casos. Mitigação real é **de governança**: restringir a circulação do
  dataset, exigir compromisso de não reidentificação de quem o acessa e **não publicar dados
  individualizados** (só agregados) `[a alinhar com o CEP]`.
- **R-03 (insider) — residual MÉDIO.** RBAC, MFA e auditoria append-only tornam o acesso indevido
  **rastreável**, não impossível: um pesquisador legítimo com `research:read` vê o dataset. Não há
  alerta automático sobre padrão anômalo de acesso (pendência de G4/D5). Mitigação de governança:
  conceder o papel mínimo e revisar a lista de staff periodicamente (`GET /v1/staff` já expõe papel,
  MFA, ativo e **último acesso** — ADR-090).
- **R-05 (adiar cuidado) — residual MÉDIO.** O aviso é persistente e a copy é controlada, mas a
  adesão do participante ao aviso não é observável pelo sistema. O CEP deve avaliar se o critério de
  exclusão cobre quem está em quadro que exija cuidado imediato.
- **R-12 (operadores) — residual MÉDIO.** Residência BR está garantida; **faltam os DPAs** (F2/F3) e
  a análise do Art. 33 para Fly.io/GitHub/SMTP, que são empresas estrangeiras ainda que a região seja
  brasileira.
- **R-14 (capacidade) — depende dos critérios de triagem** definidos com o CEP; hoje a elegibilidade é
  regra versionada, mas **quais** critérios entram é decisão do protocolo, não do código.
- **C11/C12 (transversal):** custódia de chave ainda em env/secret (adaptador **KMS/Vault** pendente,
  com o *seam* pronto) e **pentest externo** não realizado.

## 9. Medidas adicionais recomendadas (ainda não implementadas)

Ordenadas por impacto na redução de risco ao titular:

1. **Definir a base legal (A2)** e refletir no TCLE — *pré-condição de tudo* (R-09, e todo o resto).
2. **Salvaguardas contra assimetria de poder** no recrutamento (R-09) — decisão do CEP.
3. **Aprovar prazos de retenção (E1)**, **agendar** o expurgo já pronto e implementar o expurgo do
   dataset (E2) (R-10).
4. **Designar o Encarregado + canal do titular** (G1/D4) — sem isso o Art. 18 fica sem porta de entrada.
5. **Termo de compromisso de não reidentificação** para quem acessa o dataset (R-01).
6. **DPAs com operadores** + análise do Art. 33 (R-12).
7. **Alertas automáticos** (falha de e-mail, padrão anômalo de acesso) — fecha detecção de R-03/R-06.
8. **Adaptador KMS/Vault** (C11) e **pentest externo** (C12) antes de dado real em produção.
9. **Minimizar `ip_address`** do consentimento no encerramento da coleta (proporcionalidade).

## 10. Conclusão técnica preliminar

Do ponto de vista **técnico**, as medidas de segurança do Art. 46 estão implementadas em profundidade
e são **verificáveis** (297 testes, CI em 5 jobs, cada medida rastreável a um ADR): cifra com envelope
e separação de PII, MFA obrigatório, RBAC que não revela o braço, auditoria append-only garantida
**no banco**, residência no Brasil, observabilidade sem PII. Para os riscos de natureza técnica, o
residual é **Baixo a Médio**.

**O risco relevante que resta não é técnico.** Os dois residuais **Altos** — R-09 (assimetria de
poder no consentimento) e R-10 (retenção: dataset sem expurgo e sem prazo aprovado) — não se resolvem com
código: dependem de decisão do CEP, do NIT/DPO e da assessoria. Some-se que a **base legal (A2) ainda
não está definida**, o que por si só impede o início do tratamento de dados reais.

**Recomendação técnica:** o piloto **não deve iniciar coleta com dados reais** antes de (a) base legal
definida e refletida no TCLE, (b) Encarregado designado com canal ao titular, (c) prazos de retenção
aprovados, e (d) salvaguardas de recrutamento acordadas com o CEP. Os itens (a)–(d) são
**institucionais** — nenhum depende de desenvolvimento. **A decisão sobre risco residual aceitável e
sobre eventual consulta prévia à ANPD (Art. 38) é do controlador, ouvido o Encarregado; não é uma
conclusão que este documento possa dar.**

## 11. Revisão

Este RIPD deve ser **revisto** — não apenas atualizado — quando: mudar a **finalidade** ou a base
legal; entrar um **novo operador** ou transferência internacional; a **construção pós-piloto** for
autorizada (vestíveis persistidos, storage de áudio em nuvem, KMS, qualquer uso de ML que influencie
decisão); mudar o **N** ou o perfil dos participantes; ocorrer **incidente** de severidade Alta ou
Crítica (`plano-resposta-incidentes.md` §4); ou ao **fim do piloto**, antes de qualquer estudo
derivado. Cada medida citada é rastreável ao ADR correspondente — ao mudar um mecanismo, atualize o
ADR **e** este relatório.

**Rascunho técnico. Requer adoção e validação institucional (DPO/NIT/assessoria) e articulação com o
CEP antes do piloto com dados reais.**
