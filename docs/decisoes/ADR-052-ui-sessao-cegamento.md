# ADR-052 — UI de sessão idêntica e visualização não reativa (cegamento no cliente)

- **Status:** Aceito
- **Data:** 2026-07-04
- **Etapas relacionadas:** 2 (estímulo), 3 (UX), integra ADR-046 (resolução cega no servidor)
- **Contexto de origem:** 12ª fatia (a tela de sessão no Flutter)

## Contexto
O servidor já resolve ativo/sham sem vazar o braço (ADR-046). Mas o cegamento também pode
vazar na INTERFACE: se a tela reagisse ao áudio, o braço ativo (com batimento) e o sham
(sem) poderiam parecer diferentes.

## Decisão
1. **UI idêntica para todos**: a tela de sessão não recebe nem exibe qualquer informação de
   braço — apenas o handle neutro (banda) e o `content_hash`.
2. **Visualização NÃO REATIVA ao áudio**: a onda "respira" numa cadência FIXA de tempo
   (`AnimationController` por relógio), nunca a partir de amplitude/frequência do sinal.
3. **Verificação de fones como pré-condição também no cliente** (o servidor também recusa).
4. **Telemetria**: duração efetiva e interrupções (pausas) enviadas em `/sessions/{id}/complete`.

## Alternativas consideradas
- **Visualizador reativo ao áudio (espectro/onda do sinal).** Rejeitado: quebraria o cegamento.
- **Mostrar banda/beat/tempo específico do braço.** Rejeitado: idem.

## Consequências
- **Positivas:** cegamento preservado na ponta visual; UI consistente entre braços.
- **Pendência honesta:** a reprodução bit-a-bit do arquivo (por `content_hash`) depende de um
  endpoint de entrega de áudio ainda inexistente no backend; hoje o tempo é conduzido por
  relógio para exercitar fluxo e telemetria. A camada de áudio real é próxima fatia.
- **Pendências de cliente:** empacotar fontes; Riverpod + go_router; testes de widget;
  reenvio de telemetria offline.

## Conformidade
Revisão de UI deve garantir: nenhuma dependência da visualização em relação ao sinal de áudio;
nenhuma exibição de braço/condição; verificação de fones antes de iniciar.
