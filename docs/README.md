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
- `comunicacao-pendencias-orientadora.md` — carta-resumo do que falta para o piloto começar,
  organizada por dono; é o documento que se envia primeiro (os demais são anexos que ela cita).

### Os três documentos de cobrança (um por dono)

A carta acima diz *o que* falta; estes três são o que se **envia a cada dono** para que ele responda.
Cada um termina com campos a preencher — a pendência fecha quando a folha volta preenchida.

- `solicitacao-nit-base-legal.md` — **NIT / assessoria / DPO**: as 6 decisões da F1 como perguntas
  objetivas, com opções mapeadas e folha de resposta (§8). **A decisão 1 bloqueia a coleta.**
- `formulario-protocolo-clinico.md` — **pesquisadora responsável**: os 14 campos que só o protocolo
  tem (F2.2) e que travam o TCLE. Três deles mexem no sistema, não só no texto — ver §4.
- `dossie-submissao-cep.md` — **CEP**: estado da submissão documento a documento, as 5 perguntas ao
  comitê (F2.1–F2.5) e o que declarar sobre proteção de dados. Substitui as §5 e §8 do
  `anexos-docx/Roteiro_Submissao_CEP.docx` (julho), que segue válido no resto.
- `tcle-rascunho.md` — rascunho do **TCLE** (A1/B2), para revisão da orientadora e do CEP. Ao
  aprovar, sincronizar `TCLE_CURRENT` (backend) e o resumo do app — ver §N4 do próprio rascunho.
- `relatorio-impacto-protecao-dados.md` — **RIPD/DPIA** (G2): riscos ao titular, mitigação e risco
  residual.
- `registro-operacoes-tratamento.md` — **ROPA** (G3, Art. 37): as 8 operações de tratamento.
- `politica-retencao-descarte.md` — retenção e descarte (E1/E2): inventário e prazos propostos.
- `plano-resposta-incidentes.md` — resposta a incidentes e notificação à ANPD (G4, Art. 48).

### Gerar PDF / DOCX destes documentos

Os arquivos para enviar (NIT, DPO, CEP, orientadora) são **gerados** dos `.md` acima — não há
segunda redação. Mesma regra do TCLE exibido no app.

```bash
python scripts/docs_to_pdf.py            # todos os PDFs (usa Edge/Chrome headless)
python scripts/docs_to_pdf.py tcle ripd  # só os indicados   ·  --list para as chaves
python scripts/md_to_docx.py pendencias  # versão editável (Word nativo)
```

Saída na pasta acima do repositório, com a data no nome (`Sereno_<Doc>_AAAA-MM-DD.pdf`). Cada
documento leva uma **tarja de status própria** dizendo o que falta nele — nenhum está aprovado.
Requer `pip install markdown python-docx`.

## Operação

- `deploy-fly.md` — deploy do backend na Fly (runbook). **Abre com a ordem de execução dos dez
  itens da Fase F3**, com o que destrava cada um e o que acontece se ficar de fora.
- `scripts/tcle_version.py` — verifica (`--check`, roda no CI) e troca a versão vigente do TCLE nos
  4 lugares que a declaram. Ao sair o parecer do CEP: `python scripts/tcle_version.py 1.0.0`.
- `rodar-por-tunel.md` — demo local + túnel Cloudflare (sem cartão/deploy).
