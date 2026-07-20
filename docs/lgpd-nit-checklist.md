# Checklist LGPD / NIT — Sereno (piloto)

> **O que é isto:** um **mapeamento técnico** do que já está implementado no Sereno frente às
> exigências usuais da LGPD (Lei 13.709/2018), como **material de apoio** para o NIT (Núcleo de
> Inovação Tecnológica da UNINTA), o Encarregado/DPO e a submissão ao CEP.
>
> **O que NÃO é:** parecer jurídico. As bases legais, o enquadramento de dados sensíveis de saúde,
> os prazos de retenção, os contratos com operadores e a designação de Encarregado **são decisões
> institucionais/jurídicas** — este documento sinaliza, não decide (conforme `CLAUDE.md`). Toda
> linha marcada "decisão do NIT/assessoria" exige validação humana antes do piloto com dados reais.

**Legenda de status**
- ✅ **Implementado** — existe em código e é verificado por teste/CI.
- 🟡 **Parcial** — mecanismo pronto no piloto; falta o passo de produção/formalização.
- ⬜ **Pendente (decisão institucional/jurídica)** — não é (só) código; precisa do NIT/DPO/assessoria.

Referências entre parênteses apontam para o arquivo de código ou o ADR (`docs/decisoes/`).

---

## A. Bases legais, finalidade e dados sensíveis

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| A1 | Finalidade específica e informada (pesquisa de viabilidade; ansiedade/sono exploratórios) | 🟡 | Escopo travado e documentado (`CLAUDE.md`, `docs/ROADMAP.md`); **falta** o texto de finalidade no TCLE ser validado pela assessoria. |
| A2 | Base legal do tratamento definida | ⬜ | **Decisão do NIT/assessoria.** Dado de saúde é **sensível** (Art. 11). Definir a base — tipicamente consentimento específico e destacado para pesquisa (Art. 11, I) e/ou estudos em saúde (Art. 11, II, "c"), articulada com a Res. CNS 466/2012 e o CEP. |
| A3 | Minimização de dados (coleta só do necessário) | ✅ | PII limitada a nome/e-mail de contato (`ContactInfo`); pesquisa usa `study_code` pseudônimo; sem coleta de dado clínico além dos instrumentos versionados (GAD‑7/PSQI/SUS). |
| A4 | Não uso para decisão automatizada clínica | ✅ | Recomendador **por regras**, ML nunca decide ao vivo (inegociável #5; `recommender/`, ADR‑068/083). Vestíveis não alimentam decisão (ADR‑084). |

## B. Consentimento (TCLE)

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| B1 | Registro de consentimento versionado, com data e evidência | ✅ | `ConsentRecord` (`tcle_version`, `accepted`, `ip_address`, hash do payload); `POST /v1/consent` recusa versão divergente da vigente (ADR do consentimento; `consent/`). |
| B2 | Consentimento **específico e destacado** para dado sensível | 🟡 | O mecanismo registra a versão aceita; **falta** o **conteúdo** do TCLE ser redigido/validado (assessoria + CEP) com destaque para dado de saúde. |
| B3 | Revogação do consentimento pelo titular | ✅ | Self‑service: `POST /v1/participants/me/consent/withdraw` carimba `revoked_at` + marca `withdrawn` e **bloqueia novas sessões** (`consent/router.py`, ADR‑089; testado). Retirar ≠ eliminar — o dado de pesquisa já coletado é retido pseudonimizado (ADR‑066) e a eliminação (Art. 18) segue como direito separado. |

## C. Segurança da informação (Art. 46) — medidas técnicas

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| C1 | PII cifrada em repouso, separada do dado de pesquisa | ✅ | AES‑256‑GCM na aplicação, AAD ligando participante+campo; chave em env/cofre, **falha explícita** sem chave (`core/pii_crypto.py`, ADR‑059). |
| C2 | Transporte cifrado (TLS/HTTPS) | ✅ | `force_https = true` no deploy (`fly.toml`, ADR‑076). |
| C3 | Autenticação forte de staff (senha + 2º fator) | ✅ | argon2id + JWT access/refresh + **MFA TOTP obrigatório** (ADR‑043/074); sem 2º fator, só token de cadastro restrito. |
| C4 | Autenticação de participante sem senha (OTP), sem vazar o código | ✅ | OTP por e‑mail, gravado só como hash, uso único, expira, tentativas limitadas; **nunca logado** (`participant_auth/`, ADR‑063/085). |
| C5 | Controle de acesso por papel (RBAC) no servidor | ✅ | Matriz `RBAC` server‑side; nenhuma permissão revela o braço (`core/security.py`, inegociável #2/#6). |
| C6 | Ciclo de vida de credenciais (desativar/rotacionar) | ✅ | Lifecycle de staff: desativar suspende o acesso já emitido; rotação de senha (ADR‑081). |
| C7 | Proteção contra abuso (rate limit) e revogação de token | ✅ | Rate limit por IP real atrás de proxy + denylist de `jti` (ADR‑064/078/079). |
| C8 | Trilha de auditoria **append‑only**, sem PII/braço | ✅ | **Duas camadas:** guard no ORM (`audit/service.py`, ADR‑056) **e** trigger no banco que aborta UPDATE/DELETE — mesmo por SQL cru e mesmo do dono da tabela (`core/audit_ddl.py`, migração `d4e5f6a7b8c9`, ADR‑086); testado (`test_audit_append_only_db.py`). Ações sensíveis auditadas (consentimento, alocação, export, erase, desbloqueio, staff). |
| C9 | Fail‑safe de configuração de produção | ✅ | Guard recusa subir sem a chave selada / com OTP‑no‑console (ADR‑077); postura de falha do Redis configurável (ADR‑079). |
| C10 | Observabilidade sem PII (logs/métricas) | ✅ | Logs JSON e métricas Prometheus só com método/rota/status; entrega de e‑mail observável sem corpo/código (ADR‑067/080/085). |
| C11 | Custódia de chaves em KMS/cofre gerenciado | 🟡 | **Seam + envelope prontos:** a chave de PII fica atrás da porta `KeyProvider` (ADR‑087); a cifra usa **envelope** (DEK por registro embrulhada pela KEK via `wrap`/`unwrap`), padrão real de KMS — a KEK nunca cifra a PII (`core/keyring.py`, `core/pii_crypto.py`, ADR‑088; testado). Rotação por id de chave. **Falta** o adaptador **KMS/Vault** real (a custódia hoje segue em env/secret gitignored) — implementa `wrap`/`unwrap` via API, sem tocar na cripto. `JWT_SECRET`/chave selada A/B seguem em env/secret. |
| C12 | Teste de intrusão / revisão de segurança independente | ⬜ | **Recomendado antes do piloto.** Há `/security-review` no fluxo de dev, mas um pentest externo é decisão do NIT. |

## D. Direitos do titular (Art. 18)

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| D1 | Acesso / portabilidade dos dados do titular | ✅ | `GET /v1/participants/{id}/data` reúne os dados do titular (PII decifrada do próprio), **sem** o braço; auditado (`data_rights/`, ADR‑066). |
| D2 | Eliminação da PII direta a pedido | ✅ | `POST /v1/participants/{id}/erase` remove contato cifrado + artefatos de OTP e marca `withdrawn`; auditado. |
| D3 | Retenção de dado de pesquisa pseudonimizado após eliminação | 🟡 | O `erase` **retém** o dado pseudonimizado (exceção de pesquisa da LGPD, ADR‑066) e **não** apaga a auditoria; **confirmar** com CEP/assessoria que a retenção pós‑revogação está descrita no TCLE. |
| D4 | Atendimento a titular via canal do Encarregado | ⬜ | **Decisão do NIT/DPO.** A **retirada de consentimento** já é self‑service (B3/ADR‑089); acesso e eliminação seguem operados pela equipe (admin, `user:manage`). **Falta** o canal público do Encarregado e o prazo de resposta (Art. 18, §5º). |

## E. Retenção, descarte e ciclo de vida

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| E1 | Política de retenção/descarte com **prazos** definidos | ⬜ | **Rascunho técnico pronto** (`docs/politica-retencao-descarte.md`) com inventário de dados e prazos **propostos** ancorados nos mecanismos existentes; **falta** a **aprovação institucional** (CEP/assessoria) dos prazos — é o que E1 mede. |
| E2 | Expurgo agendado ao fim do prazo | ⬜ | Não implementado (pendência do ADR‑066 e da política, §6). Job/rotina depende dos prazos de E1. |
| E3 | Marcação de status do titular (ativo/retirado/concluído) | ✅ | `Participant.status` com CHECK (`active`/`withdrawn`/`completed`). |

## F. Operadores e transferência internacional (Art. 33)

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| F1 | Residência dos dados no Brasil | ✅ | Backend + Postgres em `gru`/São Paulo (`fly.toml`, ADR‑076; inegociável #6). |
| F2 | Contrato/DPA com operadores (Fly.io, provedor SMTP, GitHub Pages) | ⬜ | **Decisão do NIT/jurídico.** Mapear operadores e firmar cláusulas de tratamento; avaliar que Fly.io/GitHub são empresas estrangeiras (ainda que a região seja BR) e o enquadramento de eventual transferência internacional (Art. 33). |
| F3 | Dado de contato enviado a provedor de e‑mail (OTP/alertas) | 🟡 | Entrega desacoplada e observável (ADR‑085); **falta** o DPA com o provedor SMTP e a política de bounces. |

## G. Governança e conformidade

| # | Item | Status | Evidência / Ação |
|---|------|--------|------------------|
| G1 | Encarregado (DPO) designado e publicado | ⬜ | **Decisão do NIT/UNINTA.** |
| G2 | Relatório de Impacto à Proteção de Dados (RIPD/DPIA) | ⬜ | **Recomendado** para dado sensível de saúde. Este checklist + os ADRs servem de insumo técnico. |
| G3 | Registro das operações de tratamento (Art. 37) | 🟡 | **Rascunho consolidado** (`docs/registro-operacoes-tratamento.md`): 8 operações (OP-01…08) com finalidade, dados, base legal, operadores, transferência, retenção e segurança. **Falta** o controlador **adotar/manter** o registro formal e definir a base legal (A2). |
| G4 | Plano de resposta a incidentes + notificação à ANPD (Art. 48) | ⬜ | **Rascunho técnico pronto** (`docs/plano-resposta-incidentes.md`): fases, severidade, playbook de contenção ancorado nos mecanismos existentes, notificação. **Falta** o NIT/DPO definir contatos/plantão, confirmar prazos e **aprovar**; alertas automáticos sobre métricas seguem pendência. |
| G5 | Aprovação do CEP/CONEP (ética em pesquisa) | 🟡 | Submissão em preparação (`docs/Roteiro_Submissao_CEP.docx`, anexos por etapa); a LGPD caminha junto do parecer ético. |
| G6 | Aplicabilidade SaMD/ANVISA (se houver claim clínico) | ⬜ | **Decisão do NIT/assessoria.** Copy mantém "ferramenta complementar, experimental" (postura científica do `CLAUDE.md`), o que reduz risco de enquadramento — mas confirmar. |

---

## Ações recomendadas ao NIT (priorizadas)

1. **Definir a base legal** do tratamento de dado sensível de saúde e refletir no TCLE (A2, B2). — *bloqueia o piloto com dados reais.*
2. **Designar o Encarregado (DPO)** e o canal de atendimento ao titular (G1, D4).
3. **Política de retenção/descarte** com prazos e expurgo (E1, E2).
4. **DPAs com operadores** (Fly.io, SMTP, GitHub Pages) e análise de transferência internacional (F2, F3).
5. **RIPD/DPIA** usando este checklist + ADRs como insumo (G2, G3).
6. **Plano de incidentes** e fluxo de notificação à ANPD (G4).
7. **Produção**: migrar chaves para KMS/cofre e considerar pentest externo (C11, C12).

## Como manter este documento
Cada linha ✅ é rastreável ao código/ADR citado; ao mudar um mecanismo, atualize a linha e o ADR
correspondente. Este arquivo é **material de apoio** e não substitui parecer do NIT/jurídico nem
do CEP.
