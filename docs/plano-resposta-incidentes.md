# Plano de Resposta a Incidentes de Segurança — Sereno (piloto) · RASCUNHO

> **Status: RASCUNHO TÉCNICO para validação.** Propõe um fluxo de resposta a incidentes de
> segurança **ancorado nos mecanismos já implementados** no Sereno. Prazos legais, o gatilho de
> notificação e os contatos são **decisão do Encarregado (DPO)/NIT/assessoria** — os itens marcados
> `[a confirmar]` (prazos) e `[a preencher]` (contatos/responsáveis) exigem definição institucional.
> Este texto **sinaliza, não decide** (`CLAUDE.md`) e não substitui parecer jurídico.
>
> Atende ao item **G4** do `docs/lgpd-nit-checklist.md`. Base legal: LGPD Art. 46–48; comunicação de
> incidente conforme o **Regulamento da ANPD** (Res. CD/ANPD nº 15/2024) `[confirmar versão vigente]`.

---

## 1. Escopo e objetivo
Definir **como detectar, conter, avaliar, notificar e aprender** com um incidente de segurança que
afete dados pessoais tratados pelo Sereno — de forma proporcional ao risco, preservando a
integridade científica (cegamento) e os direitos dos titulares.

Aplica-se ao backend (PostgreSQL), aos segredos custodiados (chaves, chave selada A/B) e aos
canais correlatos (e-mail de OTP/alertas). Incidentes **operacionais sem dado pessoal** (ex.: queda
de serviço sem exposição) seguem o tratamento técnico usual e só entram aqui se houver risco a dados.

## 2. Definições
- **Incidente de segurança** — evento que compromete confidencialidade, integridade ou
  disponibilidade de dados (acesso indevido, vazamento, alteração/perda não autorizada, indisponibilidade).
- **Violação de dados pessoais** — incidente que afeta dados pessoais e **pode acarretar risco ou
  dano relevante** aos titulares (gatilho de notificação, Art. 48).
- **Incidente de integridade científica** — específico deste estudo: exposição da **chave selada
  A/B→condição** ou de qualquer dado que **quebre o cegamento**. Trata-se em paralelo à via de LGPD.

## 3. Papéis e responsabilidades `[a preencher]`
| Papel | Responsabilidade no incidente | Quem |
|---|---|---|
| **Encarregado (DPO)** | Decide se há risco relevante; conduz/aprova a notificação à ANPD e aos titulares; ponto focal | `[a preencher]` |
| **Pesquisador responsável / orientadora** | Avalia impacto científico (cegamento, protocolo); comunica o CEP quando cabível | `[a preencher]` |
| **Responsável técnico (mantenedor)** | Detecção, contenção, erradicação, coleta de evidências (logs/auditoria) | `[a preencher]` |
| **Instituição (UNINTA/NIT)** | Suporte jurídico, comunicação institucional | `[a preencher]` |

Canal de acionamento e escalonamento (24/7 durante a coleta): `[a preencher]`.

## 4. Classificação de severidade
A severidade combina **qual categoria de dado** foi afetada (ver `docs/politica-retencao-descarte.md`)
com a **probabilidade de dano** ao titular. A PII fica **cifrada e separada** (envelope, ADR-088) — um
acesso ao banco **sem a chave** tende a rebaixar a severidade.

| Nível | Exemplos | Resposta |
|---|---|---|
| **Crítico** | Vazamento de PII **com** a chave; exposição da **chave selada A/B** (quebra de cegamento); comprometimento de admin | Acionamento imediato; contenção emergencial; provável notificação ANPD + titulares + CEP |
| **Alto** | Acesso indevido a dado de pesquisa pseudonimizado; credencial de staff comprometida | Contenção no mesmo dia; avaliação formal de risco/notificação |
| **Médio** | Exposição de metadados sem PII/braço; tentativa de brute force contida pelo rate limit | Registro + monitoramento reforçado; avaliar necessidade de notificação |
| **Baixo** | Erro de config sem exposição; indisponibilidade curta sem perda | Tratamento técnico; registro no log de incidentes |

## 5. Fluxo de resposta (fases)
1. **Detecção** — a partir dos sinais do §6 ou de aviso externo.
2. **Registro e triagem** — abrir registro do incidente (data/hora, quem detectou, o que se sabe);
   classificar severidade (§4). Preservar evidências (a **auditoria é append-only**, ADR-086).
3. **Contenção** — estancar o dano (playbook §7): revogar tokens, desativar staff, rotacionar
   chaves, isolar o serviço, colocar a segurança em `fail-closed` (`SECURITY_FAIL_OPEN=0`, ADR-079).
4. **Erradicação e recuperação** — remover a causa (corrigir a falha, girar segredos expostos),
   restaurar a operação a partir de estado íntegro.
5. **Avaliação de risco** — o DPO avalia se há **risco/dano relevante** ao titular (categoria de
   dado, cifra, alcance, reversibilidade) → decide sobre notificação.
6. **Notificação** (§8) — quando cabível: ANPD, titulares e, se afetar dado de pesquisa/cegamento, o CEP.
7. **Pós-incidente** — relatório final, lições aprendidas, correções preventivas, atualização deste plano.

## 6. Detecção — sinais disponíveis × pendências
**Já disponível (rastreável a código/ADR):**
- **Logs estruturados JSON** sem PII/braço (ADR-067) — método/rota/status/latência.
- **Métricas Prometheus** (ADR-080): volume, taxa de erro (4xx/5xx), latência por rota; **entrega de
  e-mail** por desfecho `emails_total{sent|failed}` (ADR-085) — pico de `failed` é sinal.
- **Trilha de auditoria append-only** (ADR-086) — ações sensíveis (login/desbloqueio/export/erase/
  staff) auditadas; evidência imutável para investigação.
- **Rate limit + denylist de `jti`** (ADR-064/078) — tentativas de abuso deixam rastro (429).
- **Guard de produção** (ADR-077) — recusa subir com config insegura (previne classe de incidente).

**Pendências (não automatizadas):**
- **Alertas** sobre as métricas (ex.: subir Alertmanager para disparar quando `failed`/`5xx`/latência
  ultrapassar limiar) — hoje a observação é manual.
- **Monitoramento de integridade** de acessos ao banco/segredos fora da aplicação.
- Canal/turno de plantão durante a coleta `[a preencher]`.

## 7. Playbook de contenção por tipo
- **Credencial de staff comprometida** → `POST /v1/staff/{id}/deactivate` (suspende o acesso já
  emitido; RBAC confere no banco — ADR-081) + logout/denylist do `jti` (ADR-064); rotacionar a senha.
- **Token/sessão suspeita** → revogar por `jti` (denylist); se generalizado, `fail-closed` temporário.
- **Suspeita de vazamento de PII** → avaliar se a **chave** foi exposta; se sim, **rotacionar a chave
  de PII** (ADR-087) e considerar **crypto-shredding** (a rotação por id viabiliza), reduzindo o
  ciphertext antigo a inútil; medir o alcance pelos logs/auditoria.
- **Exposição da chave selada A/B** → **incidente de integridade científica**: congelar, avaliar
  impacto no cegamento com a orientadora, **comunicar o CEP**, decidir sobre continuidade/reselagem.
- **Abuso/força-bruta/DoS** → endurecer rate limit; `SECURITY_FAIL_OPEN=0`; bloquear origem na borda.
- **Comprometimento de provedor (e-mail/host)** → suspender a integração; avaliar dado exposto ao
  operador; acionar o DPA/contato do operador (ver checklist F2/F3).

## 8. Notificação (Art. 48)
- **Gatilho:** incidente que **possa acarretar risco ou dano relevante** ao titular. A cifra e a
  separação da PII entram na avaliação de risco.
- **Prazo (ANPD):** proposta de **até 3 dias úteis** a partir do conhecimento do incidente, conforme
  o Regulamento da ANPD — `[confirmar prazo/versão vigente com a assessoria]`.
- **A quem:** **ANPD** e **titulares afetados**; se envolver dado de pesquisa ou o cegamento, também
  o **CEP** (via pesquisador responsável).
- **Conteúdo mínimo** (Art. 48 §1, resumido): natureza dos dados; titulares afetados (nº/categorias);
  medidas técnicas/de segurança adotadas; riscos; medidas de mitigação. **Sem** expor novos dados
  pessoais na própria comunicação.
- **Registro:** toda notificação e decisão de (não) notificar é documentada no registro do incidente.

## 9. Registro e evidências
Cada incidente gera um **registro** (recomenda-se um log de incidentes fora do sistema, `[definir
local]`) com: identificação, linha do tempo, severidade, dados/titulares afetados, ações de
contenção/erradicação, decisão de notificação (e sua justificativa) e lições. A **auditoria
append-only** do sistema serve de fonte primária imutável para a linha do tempo.

## 10. Testes e revisão
- **Revisar** este plano a cada mudança relevante de arquitetura, ao fim do piloto ou quando a
  assessoria/CEP recomendar.
- **Exercitar** ao menos um cenário de mesa antes do piloto com dados reais (ex.: "credencial de
  pesquisador vazou") para validar contatos, prazos e o playbook.
- **Este é um rascunho técnico e requer aprovação institucional (DPO/NIT) antes do piloto com dados reais.**
