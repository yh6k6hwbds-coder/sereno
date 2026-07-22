# docs — fonte de verdade

Markdown é a fonte de verdade para o desenvolvimento; os `.docx` em
`anexos-docx/` são as versões para humanos/CEP/relatório. Ao mudar uma decisão,
atualize o Markdown **e** registre em `decisoes/`.

- `01-arquitetura.md` … `07-analise.md` — as sete etapas.
- `decisoes/` — Architecture Decision Records (índice em `decisoes/README.md`).
- `anexos-docx/` — documentos Word completos de cada etapa + índice + roteiro CEP.
- `ROADMAP.md` — backlog de fatias verticais (o que está feito e o que falta).

## Pacote LGPD / NIT (rascunhos técnicos)

Material de apoio para o NIT, o Encarregado/DPO e o CEP. **Nenhum destes é parecer jurídico** —
sinalizam, não decidem; itens `[a confirmar]` exigem decisão institucional (ver `CLAUDE.md`).

- `lgpd-nit-checklist.md` — **porta de entrada**: mapeamento item a item do que já existe em código
  (✅/🟡/⬜), com as ações priorizadas ao NIT. Companheiro visual: `lgpd-nit-checklist.html`.
- `relatorio-impacto-protecao-dados.md` — **RIPD/DPIA** (G2): riscos ao titular, mitigação e risco
  residual.
- `registro-operacoes-tratamento.md` — **ROPA** (G3, Art. 37): as 8 operações de tratamento.
- `politica-retencao-descarte.md` — retenção e descarte (E1/E2): inventário e prazos propostos.
- `plano-resposta-incidentes.md` — resposta a incidentes e notificação à ANPD (G4, Art. 48).

## Operação

- `deploy-fly.md` — deploy do backend na Fly (runbook).
- `rodar-por-tunel.md` — demo local + túnel Cloudflare (sem cartão/deploy).
