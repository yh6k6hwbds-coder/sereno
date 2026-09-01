import 'dart:async';
import 'package:flutter/material.dart';
import '../../core/config.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/session_repository.dart';
import '../../services/outcomes_repository.dart';
import '../../services/audio_player_port.dart';
import '../../services/just_audio_player.dart';
import '../../services/telemetry_queue.dart';
import '../../shared/breathing_wave.dart';
import 'post_session_survey_screen.dart';

/// Reprodução da sessão (A2). A UI é IDÊNTICA para todos os participantes — não há
/// qualquer informação de braço aqui (só o handle neutro e o hash do áudio). A
/// visualização ([BreathingWave]) é temporal, NÃO reativa ao áudio — preservando o
/// cegamento. O áudio é baixado (verificado bit-a-bit) e tocado por uma porta isolável;
/// a telemetria (duração efetiva, interrupções **e sua duração**, volume médio e máximo
/// aplicados, item de relaxamento) é enviada e, se a rede cair, enfileirada para reenvio —
/// é o registro por sessão que o protocolo lista em "Registro e monitoramento" (G10).
///
/// O botão de interrupção imediata fica **visível durante toda a sessão**, como o protocolo
/// e o TCLE prometem.
class SessionPlayerScreen extends StatefulWidget {
  final SessionRepository repo;
  final SessionStart session;
  final AudioPlayerPort player;
  final TelemetrySender telemetry;

  const SessionPlayerScreen({
    super.key,
    required this.repo,
    required this.session,
    required this.player,
    required this.telemetry,
  });

  /// Constrói a tela com as implementações reais (just_audio + fila em disco).
  factory SessionPlayerScreen.production({
    Key? key,
    required SessionRepository repo,
    required SessionStart session,
  }) {
    final sender = TelemetrySender(
      (item) => repo.complete(item.sessionId,
          effectiveSeconds: item.effectiveSeconds,
          interruptions: item.interruptions,
          pausedSeconds: item.pausedSeconds,
          gainMean: item.gainMean,
          gainPeak: item.gainPeak,
          relaxation0to10: item.relaxation0to10),
      FileTelemetryQueue(),
    );
    return SessionPlayerScreen(
      key: key,
      repo: repo,
      session: session,
      player: JustAudioPlayer(),
      telemetry: sender,
    );
  }

  @override
  State<SessionPlayerScreen> createState() => _SessionPlayerScreenState();
}

class _SessionPlayerScreenState extends State<SessionPlayerScreen> {
  Timer? _timer;
  int _effective = 0;
  int _interruptions = 0;
  /// Duração acumulada das interrupções — o protocolo pede "interrupções E SUA DURAÇÃO",
  /// e a contagem sozinha não distingue quem pausou 5 s de quem pausou meia hora.
  int _pausedSeconds = 0;
  /// Volume aplicado, MEDIDO e não presumido: o ganho é travado (G3), então hoje médio e
  /// máximo coincidem — mas quem registra o que reproduziu não pode partir do que pretendia.
  double _gainNow = 0;
  double _gainSum = 0;
  double _gainPeak = 0;
  /// Item único de relaxamento (0–10) desta sessão; `null` enquanto não respondido.
  int? _relaxation;
  bool _paused = false;
  bool _finishing = false;
  bool _loading = true; // baixando/carregando o áudio
  bool _error = false;  // falha ao baixar/carregar o áudio (texto vem do locale)

  @override
  void initState() {
    super.initState();
    // Reenvia telemetria pendente de sessões anteriores (best-effort, sem bloquear a UI).
    widget.telemetry.flush();
    _prepare();
  }

  Future<void> _prepare() async {
    try {
      // Uma vez por protocolo, não por sessão: a fonte vem do cache cifrado do aparelho
      // quando o servidor confirma que o artefato não mudou (ADR-103).
      final fonte = await widget.repo.obtainAudio(widget.session.sessionId,
          contentHash: widget.session.contentHash);
      await widget.player.load(fonte);
      // Ganho TRAVADO (G3): a tela não tem controle de volume, e este é o mesmo valor
      // declarado ao servidor no início da sessão.
      await widget.player.setVolume(audioGain);
      _gainNow = audioGain;
      await widget.player.play();
      if (!mounted) return;
      setState(() => _loading = false);
      _timer = Timer.periodic(const Duration(seconds: 1), _tick);
      // Fim natural do áudio encerra a sessão.
      widget.player.onComplete.then((_) {
        if (mounted && !_finishing) _finish(auto: true);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = true;
      });
    }
  }

  void _tick(Timer _) {
    if (_paused) {
      _pausedSeconds += 1;   // fora do setState: não muda nada na tela
      return;
    }
    setState(() {
      _effective += 1; // conta só o tempo efetivamente ouvido
      // Integra o ganho no tempo OUVIDO: a média é do que soou, não do relógio de parede.
      _gainSum += _gainNow;
      if (_gainNow > _gainPeak) _gainPeak = _gainNow;
    });
  }

  Future<void> _pause() async {
    await widget.player.pause();
    if (!mounted) return;
    setState(() {
      _paused = true;
      _interruptions += 1; // cada pausa conta como interrupção
    });
  }

  Future<void> _resume() async {
    await widget.player.play();
    if (!mounted) return;
    setState(() => _paused = false);
  }

  /// O que esta sessão registra, no formato em que vai para o servidor e para a fila.
  PendingComplete get _registro => PendingComplete(
        sessionId: widget.session.sessionId,
        effectiveSeconds: _effective,
        interruptions: _interruptions,
        pausedSeconds: _pausedSeconds,
        // Sem tempo ouvido não há volume aplicado a relatar — nulo, não zero (e o
        // servidor recusa ganho zero, que não é um volume, é a ausência de um).
        gainMean: _effective > 0 ? _gainSum / _effective : null,
        gainPeak: _gainPeak > 0 ? _gainPeak : null,
        relaxation0to10: _relaxation,
      );

  Future<void> _finish({bool auto = false}) async {
    if (_finishing) return;
    _finishing = true;
    _timer?.cancel();
    await widget.player.pause();
    // Envia ANTES de perguntar o item de relaxamento: a adesão é desfecho primário e não
    // pode depender de o participante responder (ou de o app sobreviver até lá). A resposta
    // vai num segundo envio, que o servidor trata como complemento — nunca como apagamento.
    await widget.telemetry.submit(_registro);
    if (!mounted) return;
    final t = AppLocalizations.of(context);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogCtx) => StatefulBuilder(
        builder: (_, setDialogState) => AlertDialog(
          title: Text(t.playerDoneTitle),
          content: _doneContent(t, auto, setDialogState),
          actions: [
            TextButton(
              onPressed: () {
                // Encaixa o pós-sessão (B3) desta sessão; ao enviar, volta ao início.
                final nav = Navigator.of(dialogCtx);
                nav.pop();
                nav.pushReplacement(MaterialPageRoute(
                    builder: (_) => PostSessionSurveyScreen(
                        repo: OutcomesRepository(widget.repo.api),
                        sessionId: widget.session.sessionId)));
              },
              child: Text(t.playerAnswerQuick),
            ),
            TextButton(
              onPressed: () => Navigator.of(dialogCtx)..pop()..pop(),
              child: Text(t.playerBackHome),
            ),
          ],
        ),
      ),
    );
  }

  /// Conteúdo do diálogo de conclusão: o aviso de fim mais o **item único de percepção de
  /// relaxamento de 0 a 10** que o protocolo pede por sessão (G10).
  ///
  /// Ele vive aqui, e não no questionário pós-sessão (que é opcional e usa escalas de 0 a 4),
  /// justamente porque o protocolo o quer em **toda** sessão. Escolher um número dispara um
  /// envio complementar — o encerramento já foi para o servidor antes desta pergunta.
  Widget _doneContent(AppLocalizations t, bool auto, StateSetter setDialogState) =>
      SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(auto ? t.playerDoneAuto : t.playerDoneManual),
          const SizedBox(height: 16),
          Text(t.playerRelaxPrompt, style: const TextStyle(fontSize: 13)),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (var n = 0; n <= 10; n++)
              ChoiceChip(
                label: Text('$n'),
                selected: _relaxation == n,
                onSelected: (_) {
                  setDialogState(() => _relaxation = n);
                  // Offline, este envio SUBSTITUI o da fila: o arquivo é por sessão, e este
                  // registro é um superconjunto do anterior.
                  widget.telemetry.submit(_registro);
                },
              ),
          ]),
          if (_relaxation != null) ...[
            const SizedBox(height: 8),
            Text(t.playerRelaxThanks,
                style: const TextStyle(fontSize: 12, color: SerenoColors.tealLight)),
          ],
        ]),
      );

  @override
  void dispose() {
    _timer?.cancel();
    widget.player.dispose();
    super.dispose();
  }

  String get _clock {
    final m = (_effective ~/ 60).toString().padLeft(2, '0');
    final s = (_effective % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: SerenoColors.night,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 28),
            child: _error ? _errorView() : _playerView(),
          ),
        ),
      );

  Widget _errorView() {
    final t = AppLocalizations.of(context);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.wifi_off_rounded, color: SerenoColors.alert, size: 56),
        const SizedBox(height: 16),
        Text(t.playerLoadError, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white)),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(t.back),
        ),
      ],
    );
  }

  Widget _playerView() {
    final t = AppLocalizations.of(context);
    return Column(children: [
        const Spacer(),
        // Visualização NÃO reativa ao áudio (só tempo) — não recebe sinal de áudio.
        const BreathingWave(height: 180),
        const SizedBox(height: 40),
        if (_loading) ...[
          const CircularProgressIndicator(color: SerenoColors.tealLight),
          const SizedBox(height: 16),
          Text(t.playerPreparing, style: const TextStyle(color: SerenoColors.tealLight)),
        ] else ...[
          Text(_clock,
              style: const TextStyle(
                  fontFamily: 'IBM Plex Mono', fontSize: 52, color: Colors.white, letterSpacing: 2)),
          const SizedBox(height: 8),
          Text(_paused ? t.playerPaused : t.playerInSession,
              style: const TextStyle(color: SerenoColors.tealLight, letterSpacing: 1)),
        ],
        const Spacer(),
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          IconButton.filled(
            iconSize: 34,
            style: IconButton.styleFrom(
                backgroundColor: SerenoColors.petrol, padding: const EdgeInsets.all(18)),
            onPressed: _loading ? null : (_paused ? _resume : _pause),
            icon: Icon(_paused ? Icons.play_arrow_rounded : Icons.pause_rounded, color: Colors.white),
          ),
          const SizedBox(width: 20),
          IconButton.filled(
            iconSize: 34,
            style: IconButton.styleFrom(
                backgroundColor: SerenoColors.alert, padding: const EdgeInsets.all(18)),
            onPressed: (_loading || _finishing) ? null : () => _finish(),
            icon: const Icon(Icons.stop_rounded, color: Colors.white),
          ),
        ]),
        const SizedBox(height: 14),
        Text(t.playerBreathe,
            style: const TextStyle(color: Color(0xFF9DB2BD), fontSize: 13)),
      ]);
  }
}
