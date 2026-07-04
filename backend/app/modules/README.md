# Módulos do backend (fronteiras explícitas)

| Módulo | Responsabilidade |
|---|---|
| identity | contas de participante/staff, autenticação, sessão |
| consent | TCLE (versão, hash, aceite, revogação) |
| allocation | randomização em blocos; **braço codificado**; chave A/B selada |
| sessions | telemetria de sessão (protocolo+hash, tempos, interrupções) |
| instruments | pontuação **versionada** de PSQI/GAD-7/SUS (`instruments_scoring.py`) |
| recommender | recomendação **por regras** (`recommender.py`) — só biblioteca validada |
| research | painel/exportação pseudonimizada + plano de análise (`analysis_plan.py`) |
| audit | trilha **append-only** de acesso/alteração |

Regra transversal: **nenhum módulo expõe o braço (ativo/sham)**.
