# Etapa 6 — Motor de recomendação por regras
Fonte: `anexos-docx/Etapa6_Recomendador.docx` · código: `../backend/app/modules/recommender/recommender.py`.
- **Regras transparentes e versionadas**; guardrails (contraindicação, de-escalonamento).
- **Só seleciona dentro da biblioteca validada** (invariante); registro `entrada→regra→saída`.
- `feature_vector` para ML futuro — **ML não decide ao vivo**. Coerência = exploratória.
