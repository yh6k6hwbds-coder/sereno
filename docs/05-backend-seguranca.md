# Etapa 5 — Backend, banco e segurança
Fonte: `anexos-docx/Etapa5_Backend_Seguranca.docx` · código: `../backend/app/core/models.py`, `../shared-contracts/openapi.yaml`, `../scripts/security_reference.py`.
- Schema PostgreSQL (15 tabelas/118 colunas, validado); API `/v1` (OpenAPI validado).
- argon2id + JWT + MFA + RBAC (demonstrados); **nenhuma permissão revela o braço**.
- LGPD operacional; auditoria append-only; OWASP API Top 10.
