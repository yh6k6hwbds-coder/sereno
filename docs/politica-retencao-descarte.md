# Política de Retenção e Descarte de Dados — Sereno (piloto) · RASCUNHO

> **Status: RASCUNHO TÉCNICO para validação.** Este documento propõe uma política de retenção
> e descarte **ancorada no que o sistema realmente coleta e nos mecanismos já implementados**.
> Os **prazos** e a **aprovação** são **decisão do CEP e da assessoria jurídica/NIT** — os valores
> aqui marcados `[a confirmar]` são propostas com justificativa, não determinações. Este texto
> **sinaliza, não decide** (conforme `CLAUDE.md`); não substitui parecer jurídico nem ético.
>
> Atende aos itens **E1** (política com prazos) e **E2** (expurgo agendado) do
> `docs/lgpd-nit-checklist.md`. Base legal geral: LGPD (Lei 13.709/2018), Art. 15–16; exceção de
> pesquisa Art. 16, II; normas de ética em pesquisa (Res. CNS 466/2012 e 510/2016).

---

## 1. Escopo e objetivo
Definir **por quanto tempo** cada categoria de dado do estudo é mantida, **por qual motivo**, e
**como** é descartada ao fim do prazo — de modo que o tratamento se limite ao necessário para a
finalidade (pesquisa de viabilidade), preservando a integridade científica (cegamento, auditoria)
e os direitos do titular.

Aplica-se ao backend do Sereno (PostgreSQL) e aos artefatos correlatos (chave selada, backups,
logs). **Não** cobre documentos institucionais fora do sistema (ex.: vias físicas do TCLE), que
seguem a política do CEP/instituição.

## 2. Definições
- **PII direta** — dado que identifica diretamente o titular (nome, e-mail de contato). No Sereno,
  fica **cifrada e separada** do dado de pesquisa (`contact_info`; AES-256-GCM com envelope, ADR-088).
- **Dado de pesquisa pseudonimizado** — respostas de instrumentos, sessões, telemetria, ligados ao
  titular apenas pelo `study_code` (pseudônimo), sem PII direta.
- **Pseudonimização** — remoção do vínculo direto ao titular, mantendo o dado analisável sob código.
- **Eliminação** — remoção efetiva do dado. Para dado cifrado, admite-se **crypto-shredding**
  (descarte irreversível da chave torna o ciphertext inutilizável).
- **Retenção** — período em que o dado é mantido para a finalidade ou por obrigação legal/ética.
- **Data lock** — congelamento do dataset ao fim da coleta; momento em que a chave A/B→condição
  (cegamento) é aberta para a análise.

## 3. Princípios
1. **Minimização** (Art. 6, III): coleta-se só o necessário — PII limitada a contato; pesquisa sob
   pseudônimo.
2. **Limitação de finalidade** (Art. 6, I): os dados servem ao piloto de viabilidade; não são
   reaproveitados fora disso sem nova base.
3. **Retenção mínima** (Art. 15–16): mantém-se pelo menor prazo compatível com a finalidade e com a
   **exceção de pesquisa** (Art. 16, II), que permite conservar o dado **pseudonimizado** para a
   pesquisa mesmo após o término do tratamento original.
4. **Separação e cegamento**: PII cifrada e separada; braço sempre **codificado (A/B)**; a chave de
   condição só abre no data lock.
5. **Auditoria imutável**: a trilha de auditoria é **append-only** e nunca é editada/apagada — nem
   pela eliminação de dados do titular.

## 4. Inventário de dados e cronograma de retenção

Prazos `[a confirmar]` = proposta a ser validada pelo CEP/assessoria. A referência recorrente
"**5 anos após o encerramento/publicação**" segue a prática comum das normas do CNS para registros
de pesquisa — **sujeita a confirmação**.

| Categoria | Tabelas / dados | Contém PII? | Retenção proposta `[a confirmar]` | Gatilho e forma de descarte |
|---|---|---|---|---|
| **PII de contato** | `contact_info` (nome/e-mail cifrados) | Sim (cifrada) | Durante a participação; eliminar em até **30 dias** após o encerramento da coleta **ou** na revogação/pedido do titular, o que ocorrer primeiro | Eliminação da linha + crypto-shredding; já disponível via `erase` (ADR-066) e revogação self-service (ADR-089) |
| **Artefatos de autenticação** | `otp_challenge` (hash de OTP, expiração) | Indireto | **Transitório** — expurgar registros expirados/consumidos (proposta: **diário**; nunca > 24 h) | Expurgo agendado (job) — **pendência E2**; hoje removidos no `erase` |
| **Evidência de consentimento** | `consent_record` (versão, aceite, `revoked_at`, hash, `ip_address`) | `ip_address` é pessoal | Igual ao dado de pesquisa (**5 anos** pós-encerramento) — é a prova do consentimento | Ao fim do prazo: eliminar; **minimizar `ip_address`** no encerramento da coleta (manter só a evidência) `[a confirmar]` |
| **Identificação pseudônima** | `participant` (study_code, status), `allocation` (braço A/B) | Não (pseudônimo) | **5 anos** pós-encerramento (chave do dataset) | Eliminação/anonimização ao fim do prazo, junto ao dataset |
| **Dado de pesquisa** | `screening`, `baseline_assessment`, `followup_assessment`, `session`, `post_session_survey`, `sleep_diary`, `adverse_event`, `recommendation_log` | Não (pseudonimizado) | **5 anos** após encerramento/publicação (exceção de pesquisa, Art. 16 II) | Ao fim do prazo: eliminação ou **anonimização** definitiva |
| **Trilha de auditoria** | `audit_log` (sem PII, sem braço; append-only) | Não | **5 anos** (alinhado ao dado de pesquisa) `[a confirmar]` | Append-only durante a retenção (ADR-086); ao fim, expurgo controlado e registrado |
| **Chave selada A/B→condição** | Custodiada fora do banco (secret/cofre) | Não | Até o **data lock** + conclusão das análises previstas no protocolo | Destruição da chave após o uso previsto (encerra o cegamento de forma definitiva) |
| **Biblioteca de estímulos** | `audio_protocol` (parâmetros/hashes) | Não | Enquanto o estudo/estudos derivados usarem | Não é dado pessoal; descarte por decisão técnica |
| **Dados de equipe** | `staff_user` (e-mail, papel, MFA) | Sim (de staff, não de sujeito) | Durante o vínculo + política institucional | **Desativar, não apagar** (preserva autoria da auditoria, ADR-081); eliminação por processo de RH/PI |
| **Backups** | Dumps do Postgres | Herda das tabelas | Igual ou menor que o dado de origem; ciclo curto de rotação `[a confirmar]` | Rotação/expiração dos backups; o descarte só é completo quando os backups também expiram |

## 5. Gatilhos de descarte
1. **Revogação de consentimento / pedido do titular** (self-service ADR-089; eliminação por admin
   ADR-066): encerra a participação, marca `withdrawn`, elimina a PII de contato. O dado de pesquisa
   **já coletado** é **retido pseudonimizado** (exceção de pesquisa) — isso deve constar no TCLE.
2. **Encerramento da coleta / data lock**: minimização de `ip_address`; abertura da chave A/B para
   análise; início da contagem do prazo de retenção do dataset.
3. **Fim do prazo de retenção**: eliminação/anonimização do dataset e expurgo controlado da auditoria.
4. **Expurgo de transitórios** (OTP): contínuo/agendado, independente do ciclo do estudo.

## 6. Como é operado hoje (mecanismos) × o que falta
**Já implementado (rastreável a código/ADR):**
- Eliminação da PII e marcação `withdrawn`: `POST /v1/participants/{id}/erase` (ADR-066).
- Revogação self-service pelo titular: `POST /v1/participants/me/consent/withdraw` (ADR-089).
- PII cifrada com envelope + rotação de chave (base para crypto-shredding) — ADR-087/088.
- Auditoria append-only garantida no banco (ADR-086); retida, nunca editada.
- Status do titular (`active`/`withdrawn`/`completed`) — controle de ciclo de vida.

**Pendências desta política (não automatizadas ainda):**
- **Expurgo agendado** de OTP expirados e de datasets ao fim do prazo (**item E2** — job/rotina).
- **Minimização de `ip_address`** no encerramento da coleta.
- **Rotina de descarte** ao fim da retenção (dataset + auditoria + backups) com registro do descarte.
- Política de **rotação/expiração de backups** alinhada aos prazos.

## 7. Eliminação segura
- **Dado em claro**: `DELETE` da linha.
- **Dado cifrado (PII)**: `DELETE` **e/ou** crypto-shredding (descarte da chave da época, viável
  com a rotação por id de chave do ADR-088).
- **Backups**: o descarte só se completa quando os backups que contêm o dado também expiram — por
  isso o ciclo de backup deve ser ≤ ao prazo de retenção do dado mais sensível.
- **Auditoria**: nunca é editada; ao fim do seu prazo, o expurgo é **controlado e registrado**
  (quem, quando, quais faixas), preservando a cadeia de custódia.

## 8. Papéis e responsabilidades `[a confirmar]`
- **Encarregado (DPO)** — decide/aprova prazos, responde ao titular, supervisiona o descarte.
- **Pesquisador responsável / orientadora** — decisões de protocolo (data lock, retenção de pesquisa).
- **Responsável técnico (mantenedor)** — executa os mecanismos (erase, expurgo, rotação de chave) e
  registra os descartes.

## 9. Revisão e versionamento
Rever a cada mudança de protocolo, ao fim do piloto, ou quando a assessoria/CEP recomendar. Cada
mecanismo citado é rastreável ao ADR correspondente; ao mudar um mecanismo, atualizar esta política
e o ADR. **Este é um rascunho técnico e requer aprovação institucional antes do piloto com dados reais.**
