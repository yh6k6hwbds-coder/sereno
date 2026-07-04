# ADR-059 — Cifra de campo para PII (AES-256-GCM / AEAD) + custódia de chave

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Fatia C4 do ROADMAP (LGPD; pré-requisito do OTP por e-mail)
- **Relaciona-se com:** ADR-026 (PII cifrada e separada), ADR-056 (auditoria), ADR-047 (OTP)

## Contexto
A tabela `contact_info` já existe com colunas binárias (`enc_name`, `enc_email`), separada do
dado de pesquisa. Faltava **populá-la com PII cifrada em repouso** e um caminho de decifração
para o envio (entrega de OTP por e-mail é D1). Exigência de LGPD e decisão inegociável
(PII cifrada e separada).

## Decisão
1. **AES-256-GCM (AEAD)** para cifra de campo, em `core/pii_crypto.py`. A PII é cifrada **na
   aplicação** antes de tocar o banco; o token guardado é `nonce(12) || ciphertext+tag` (bytes
   crus na coluna `LargeBinary`).
2. **Chave via ambiente/cofre:** `PII_ENC_KEY` = base64 de 32 bytes, **nunca versionada**. Se
   ausente/ inválida, a operação **falha explicitamente** (`PiiKeyMissing`) — jamais cifrar com
   chave fraca ou default.
3. **AAD amarra o ciphertext ao contexto:** `contact_info|{participant_id}|{campo}`. Assim um
   valor não pode ser movido de linha nem trocado de campo (name↔email) — a decifração falha
   (`InvalidTag`). Reforça a separação/integridade da PII.
4. **Decifra só no envio:** o endpoint de captura nunca ecoa PII (resposta neutra `stored`); a
   decifração acontece no momento de usar (OTP por e-mail, D1). RBAC: `enroll:write` (staff).
5. **Auditado sem PII:** a captura grava `contact.stored` na trilha append-only (C1), com o
   participante e o autor, **sem** nome/e-mail.

## Alternativas consideradas
- **Fernet (AES-128-CBC + HMAC).** Rejeitada: não tem AAD; o binding participante/campo (que
  impede troca de linha/campo) sai de graça com GCM. GCM-256 é o padrão AEAD moderno.
- **Envelope/KMS completo agora** (chave de dados cifrada por chave-mestra no KMS). Adiada: a
  custódia em cofre/KMS é de produção (D3/nuvem). No piloto, chave única via `PII_ENC_KEY` — o
  código isola `_key()`, então trocar para envelope/KMS depois é local.
- **`pydantic[email]`/`email-validator`.** Evitada por ora: uma dependência a mais só para
  validar formato; um regex modesto basta no piloto (validação forte de e-mail = deliverability,
  responsabilidade do envio em D1).
- **Guardar base64 em coluna texto.** Rejeitada: as colunas já são binárias; bytes crus evitam
  overhead e ambiguidade de encoding.

## Consequências
- **Positivas:** PII protegida em repouso, separada do dado de pesquisa, com binding forte por
  AAD; nada de PII em resposta, log ou auditoria. Suíte: 78 → 87 testes.
- **Custo/tradeoff (visão do analista):**
  - **Sem rotação/versão de chave** ainda: um único `PII_ENC_KEY`. Se a chave mudar, o
    ciphertext antigo fica ilegível. Para rotação, prefixar um **byte de versão de chave** ao
    token e manter um chaveiro — anotado como pendência (antes de dado real em produção).
  - **Falha fechada:** sem a chave, o endpoint responde 500 (proposital — melhor recusar do que
    cifrar/ler inseguro). Em produção a chave vem do cofre no boot.
  - A **decifração** (uso da PII) vive na fatia D1 (SMTP/OTP); aqui só gravamos + expomos a
    função de decifra para esse consumo.
- **Pendências:** rotação de chave (versão no token + chaveiro); custódia via KMS/cofre (D3);
  direitos do titular / expurgo de PII (D4) apagando `contact_info` sem violar a auditoria.

## Conformidade
CI verde exige `tests/test_contact.py`: o dado gravado é **ciphertext** (não texto claro) e a
resposta é neutra; **round-trip** decifra com chave+AAD corretos; o **AAD** impede troca de
campo e de linha (`InvalidTag`); **sem a chave certa não há leitura**; upsert por participante;
a captura gera evento de auditoria **sem PII**; negações 401/403/404/422.
