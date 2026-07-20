# Registro das Operações de Tratamento de Dados (ROPA) — Sereno (piloto) · RASCUNHO

> **Status: RASCUNHO TÉCNICO para validação.** Consolida as operações de tratamento de dados
> pessoais do Sereno na estrutura do **Art. 37 da LGPD**, a partir do inventário técnico já
> levantado. É **insumo** para o registro formal que o **controlador (UNINTA)** deve manter — a
> **base legal**, a identificação do controlador/Encarregado e a adoção formal são **decisão
> institucional/jurídica** (`[a confirmar]` / `[a preencher]`). Este texto **sinaliza, não decide**
> (`CLAUDE.md`) e não substitui parecer.
>
> Atende ao item **G3** do `docs/lgpd-nit-checklist.md`. Complementa: `politica-retencao-descarte.md`
> (retenção) e `plano-resposta-incidentes.md` (incidentes). Bases legais: LGPD Art. 7 (dados comuns)
> e **Art. 11** (dados sensíveis de saúde); pesquisa Art. 11, II, "c".

---

## 1. Identificação `[a preencher]`
- **Controlador:** UNINTA (Centro Universitário INTA), Sobral/CE. `[dados/representante]`
- **Encarregado (DPO):** `[a preencher — nome/contato]`
- **Pesquisador responsável / orientadora:** Dra. Bianca Régia Silva. `[contato]`
- **Operadores (processadores):** Fly.io (hospedagem + PostgreSQL, região `gru`/BR), provedor de
  e-mail/SMTP `[a definir]`, GitHub Pages (entrega do app web). Ver §4 e checklist F2/F3.

## 2. Como ler este registro
Cada bloco abaixo é uma **operação de tratamento**. Campos padronizados: finalidade · titulares ·
categorias de dados · base legal `[a confirmar]` · operadores/destinatários · transferência
internacional · retenção (→ política) · medidas de segurança (→ checklist/ADR). "Sensível" = dado
de saúde (Art. 11). PII fica **cifrada e separada**; braço sempre **codificado (A/B)**.

---

## 3. Operações de tratamento

### OP-01 · Cadastro e contato do participante
- **Finalidade:** comunicação com o participante e autenticação sem senha (OTP).
- **Titulares:** participantes do estudo.
- **Dados:** nome e e-mail de contato — **PII direta, cifrada** (`contact_info`, AES-256-GCM
  envelope); artefato transitório de OTP (`otp_challenge`, hash).
- **Base legal `[a confirmar]`:** consentimento do titular (Art. 7, I) para o contato.
- **Operadores/destinatários:** provedor SMTP (envio do OTP); Fly.io (hospedagem).
- **Transferência internacional:** provedor SMTP/host podem ser estrangeiros — ver Art. 33 (F2).
- **Retenção:** durante a participação; eliminada no encerramento/na revogação (política §4).
- **Segurança:** cifra em repouso + separação (ADR-088); OTP nunca logado (ADR-063/085);
  eliminação via `erase` (ADR-066) e revogação self-service (ADR-089).

### OP-02 · Consentimento (TCLE)
- **Finalidade:** registrar e comprovar o consentimento (e sua revogação).
- **Titulares:** participantes.
- **Dados:** versão do TCLE, aceite/recusa, `revoked_at`, hash de conteúdo, **`ip_address`**
  (`consent_record`).
- **Base legal `[a confirmar]`:** execução/documentação do consentimento; evidência.
- **Destinatários:** equipe de pesquisa (UNINTA).
- **Transferência internacional:** não (além da hospedagem).
- **Retenção:** prazo do registro de pesquisa (proposta 5 anos, `[a confirmar]`); minimizar
  `ip_address` no encerramento (política §4).
- **Segurança:** auditado (`consent.recorded`/`consent.withdrawn`); auditoria append-only (ADR-086).

### OP-03 · Triagem / elegibilidade
- **Finalidade:** avaliar elegibilidade e critérios de segurança (contraindicações).
- **Titulares:** candidatos a participantes.
- **Dados:** respostas de triagem — **dado de saúde (sensível)**, pseudonimizado (`screening`).
- **Base legal `[a confirmar]`:** **Art. 11** — consentimento específico e/ou estudos em saúde
  (Art. 11, II, "c"), articulado com o CEP.
- **Destinatários:** equipe de pesquisa.
- **Transferência internacional:** não (além da hospedagem).
- **Retenção:** prazo do registro de pesquisa (política §4).
- **Segurança:** pseudonimização; RBAC no servidor; sem exposição do braço.

### OP-04 · Coleta de dados de pesquisa (desfechos e telemetria)
- **Finalidade:** medir os desfechos exploratórios (ansiedade/sono/usabilidade) e a adesão.
- **Titulares:** participantes alocados.
- **Dados — sensíveis, pseudonimizados:** instrumentos GAD-7/PSQI/SUS (`baseline_assessment`,
  `followup_assessment`), sessões e telemetria (`session`, `post_session_survey`), diário de sono
  (`sleep_diary`), **eventos adversos** (`adverse_event`), recomendações (`recommendation_log`).
- **Base legal `[a confirmar]`:** **Art. 11** (pesquisa em saúde), com o CEP.
- **Destinatários:** equipe de pesquisa; alerta de EA à equipe (sem PII, ADR-085).
- **Transferência internacional:** não (além da hospedagem).
- **Retenção:** prazo do registro de pesquisa (proposta 5 anos pós-encerramento, `[a confirmar]`).
- **Segurança:** pseudonimização (`study_code`); RBAC; braço codificado; recomendador por regras
  (ML não decide ao vivo, ADR-068).

### OP-05 · Randomização, alocação e cegamento
- **Finalidade:** alocar o participante e manter o duplo-cego (integridade científica).
- **Titulares:** participantes.
- **Dados:** braço **codificado A/B** (`allocation`); a **chave A/B→condição** é custodiada **fora
  do banco** (secret/cofre) e só abre no *data lock*.
- **Base legal `[a confirmar]`:** vinculada à OP-04 (execução da pesquisa).
- **Destinatários:** ninguém recebe a condição em claro (nenhuma permissão revela o braço).
- **Transferência internacional:** não.
- **Retenção:** chave destruída após o data lock/análises (política §4).
- **Segurança:** chave selada; guard de produção recusa default público (ADR-077); desbloqueio
  controlado a duas pessoas (ADR-075).

### OP-06 · Análise de pesquisa
- **Finalidade:** análise cega (viabilidade/desfechos) e consolidação offline para modelagem futura.
- **Titulares:** participantes (dados agregados/pseudonimizados).
- **Dados:** export pseudonimizado (CSV), relatório cego, dataset de features ML (offline).
- **Base legal `[a confirmar]`:** pesquisa (Art. 11), continuidade da OP-04.
- **Destinatários:** equipe de pesquisa (RBAC `research:read`/`export:request`).
- **Transferência internacional:** não.
- **Retenção:** artefatos derivados seguem o prazo do registro de pesquisa (política §4).
- **Segurança:** sem PII e **sem a condição** nos artefatos (só A/B); ML nunca decide ao vivo
  (ADR-083); auditado.

### OP-07 · Gestão de acesso da equipe (staff)
- **Finalidade:** autenticar e autorizar pesquisadores/admins.
- **Titulares:** **equipe de pesquisa** (não sujeitos de pesquisa).
- **Dados:** e-mail, papel, segredo de MFA, hash de senha (`staff_user`).
- **Base legal `[a confirmar]`:** execução da relação/legítimo interesse institucional.
- **Destinatários:** administração do estudo.
- **Transferência internacional:** não (além da hospedagem).
- **Retenção:** durante o vínculo; conta **desativada, não apagada** (autoria, ADR-081).
- **Segurança:** argon2id + JWT + **MFA obrigatório** (ADR-043/074); RBAC; lifecycle (ADR-081).

### OP-08 · Segurança, observabilidade e auditoria
- **Finalidade:** proteger o sistema e manter trilha de responsabilização.
- **Titulares:** participantes e equipe (indiretamente).
- **Dados:** logs (sem PII/braço), métricas agregadas, trilha de auditoria (sem PII), IP para rate
  limit, `jti` em denylist.
- **Base legal `[a confirmar]`:** cumprimento de dever de segurança (Art. 46) / legítimo interesse.
- **Destinatários:** administração/segurança.
- **Transferência internacional:** não (além da hospedagem).
- **Retenção:** auditoria alinhada ao registro de pesquisa (política §4); logs/métricas por ciclo
  operacional `[a confirmar]`.
- **Segurança:** logs JSON sem PII (ADR-067); métricas sem PII (ADR-080); auditoria **append-only no
  banco** (ADR-086); rate limit + denylist (ADR-064/078).

---

## 4. Operadores e transferência internacional (resumo)
| Operador | Papel | Dado tratado | Residência | Transferência internacional |
|---|---|---|---|---|
| **Fly.io** | Hospedagem + PostgreSQL | Todas as tabelas | Região `gru`/BR (ADR-076) | Empresa estrangeira — analisar Art. 33 `[a confirmar]` (F2) |
| **Provedor SMTP** `[a definir]` | Envio de OTP/alertas | E-mail de contato (em trânsito) | `[a definir]` | Avaliar (F3); DPA pendente |
| **GitHub Pages** | Entrega do app web (estático) | Não recebe dado de pesquisa server-side | EUA | Entrega de front-end; avaliar no mapeamento (F2) |

**Pendências (checklist F2/F3):** firmar **DPAs** com os operadores e concluir a análise de
transferência internacional. Residência dos dados no Brasil já garantida no host (ADR-076).

## 5. Direitos dos titulares (referência)
Acesso/portabilidade (`GET .../data`), eliminação (`POST .../erase`), revogação self-service
(`POST .../consent/withdraw`) — ver checklist §D e ADR-066/089. Canal formal do Encarregado: **D4,
pendente**.

## 6. Manutenção
Este registro deve ser **mantido atualizado pelo controlador** e revisado a cada mudança de operação
(nova coleta, novo operador, mudança de finalidade/base legal). Cada medida de segurança citada é
rastreável ao ADR correspondente. **Rascunho técnico — requer adoção/validação institucional (DPO/NIT)
e a definição da base legal (item A2) antes do piloto com dados reais.**
