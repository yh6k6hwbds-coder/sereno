import 'dart:async';
import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../services/session_repository.dart';
import '../../services/audio_player_port.dart';
import '../../services/just_audio_player.dart';
import '../../services/telemetry_queue.dart';
import '../../shared/breathing_wave.dart';

/// Reprodução da sessão (A2). A UI é IDÊNTICA para todos os participantes — não há
/// qualquer informação de braço aqui (só o handle neutro e o hash do áudio). A
/// visualização ([BreathingWave]) é temporal, NÃO reativa ao áudio — preservando o
/// cegamento. O áudio é baixado (verificado bit-a-bit) e tocado por uma porta isolável;
/// a telemetria (duração efetiva, interrupções) é enviada e, se a rede cair, enfileirada
/// para reenvio.
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
          effectiveSeconds: item.effectiveSeconds, interruptions: item.interruptions),
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
  bool _paused = false;
  bool _finishing = false;
  bool _loading = true; // baixando/carregando o áudio
  String? _error;

  @override
  void initState() {
    super.initState();
    // Reenvia telemetria pendente de sessões anteriores (best-effort, sem bloquear a UI).
    widget.telemetry.flush();
    _prepare();
  }

  Future<void> _prepare() async {
    try {
      final bytes = await widget.repo.downloadAudio(widget.session.sessionId);
      await widget.player.loadBytes(bytes);
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
        _error = 'Não foi possível carregar o áudio. Verifique a conexão e tente novamente.';
      });
    }
  }

  void _tick(Timer _) {
    if (_paused) return;
    setState(() => _effective += 1); // conta só o tempo efetivamente ouvido
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

  Future<void> _finish({bool auto = false}) async {
    if (_finishing) return;
    _finishing = true;
    _timer?.cancel();
    await widget.player.pause();
    // Envia; se falhar, fica na fila e será reenviado depois.
    await widget.telemetry.submit(PendingComplete(
      sessionId: widget.session.sessionId,
      effectiveSeconds: _effective,
      interruptions: _interruptions,
    ));
    if (!mounted) return;
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        title: const Text('Sessão concluída'),
        content: Text(auto
            ? 'Sessão finalizada. Obrigado por participar.'
            : 'Sessão encerrada. Registramos o tempo efetivo.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context)..pop()..pop(),
            child: const Text('Voltar ao início'),
          ),
        ],
      ),
    );
  }

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
            child: _error != null ? _errorView() : _playerView(),
          ),
        ),
      );

  Widget _errorView() => Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.wifi_off_rounded, color: SerenoColors.alert, size: 56),
          const SizedBox(height: 16),
          Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white)),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Voltar'),
          ),
        ],
      );

  Widget _playerView() => Column(children: [
        const Spacer(),
        // Visualização NÃO reativa ao áudio (só tempo) — não recebe sinal de áudio.
        const BreathingWave(height: 180),
        const SizedBox(height: 40),
        if (_loading) ...[
          const CircularProgressIndicator(color: SerenoColors.tealLight),
          const SizedBox(height: 16),
          const Text('Preparando o áudio…', style: TextStyle(color: SerenoColors.tealLight)),
        ] else ...[
          Text(_clock,
              style: const TextStyle(
                  fontFamily: 'IBM Plex Mono', fontSize: 52, color: Colors.white, letterSpacing: 2)),
          const SizedBox(height: 8),
          Text(_paused ? 'Pausado' : 'Em sessão',
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
        const Text('Feche os olhos e respire com calma.',
            style: TextStyle(color: Color(0xFF9DB2BD), fontSize: 13)),
      ]);
}
