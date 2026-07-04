# shared-contracts

`openapi.yaml` é a **fonte de verdade** da API `/v1`. Regra: **alterou a API →
atualize aqui ANTES do código**. Gere os tipos do cliente Flutter a partir deste
arquivo (ex.: openapi-generator) para front e back não divergirem.
Erros seguem problem+json (RFC 9457). Validado no CI.
