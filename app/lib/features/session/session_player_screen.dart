import 'dart:async';
import 'package:flutter/material.dart';
import '../../core/config.dart';
import '../../core/theme.dart';
import '../../services/session_repository.dart';
import '../../shared/breathing_wave.dart';

/// Reprodução da sessão. A UI é IDÊNTICA para todos os participantes — não há qualquer
/// informação de braço aqui (só o handle neutro e o hash do áudio). A visualização é
/// temporal (não reativa ao áudio), preservando o cegamento. Registra duração efetiva
/// e interrupções, e encerra via /sessions/{id}/complete.
///
/// Observação honesta: a reprodução bit-a-bit do arquivo (por content_hash) depende de
/// um endpoint de entrega de áudio ainda pendente no backend; aqui o tempo é conduzido
/// por relógio para exercitar o fluxo e a telemetria.
class SessionPlayerScreen extends StatefulWidget {
  final SessionRepository repo;
  final SessionStart session;
  const SessionPlayerScreen({super.key, required this.repo, required this.session});
  @override
  State<SessionPlayerScreen> createState() => _SessionPlayerScreenState();
}

class _SessionPlayerScreenState extends State<SessionPlayerScreen> {
  Timer? _timer;
  int _remaining = sessionDurationSeconds;
  int _effective = 0;
  int _interruptions = 0;
  bool _paused = false;
  bool _finishing = false;

  @override
  void initState() {
    super.initState();
    _resume();
  }

  void _tick(Timer _) {
    if (_paused) return;
    setState(() {
      _effective += 1;
      _remaining -= 1;
    });
    if (_remaining <= 0) _finish(auto: true);
  }

  void _resume() {
    _timer ??= Timer.periodic(const Duration(seconds: 1), _tick);
    if (_paused) setState(() => _paused = false);
  }

  void _pause() {
    setState(() {
      _paused = true;
      _interruptions += 1; // cada pausa conta como interrupção
    });
  }

  Future<void> _finish({bool auto = false}) async {
    if (_finishing) return;
    _finishing = true;
    _timer?.cancel();
    try {
      await widget.repo.complete(widget.session.sessionId,
          effectiveSeconds: _effective, interruptions: _interruptions);
    } catch (_) {/* telemetria best-effort; poderia enfileirar para reenvio */}
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
    super.dispose();
  }

  String get _clock {
    final m = (_remaining ~/ 60).toString().padLeft(2, '0');
    final s = (_remaining % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: SerenoColors.night,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 28),
            child: Column(children: [
              const Spacer(),
              const BreathingWave(height: 180),
              const SizedBox(height: 40),
              Text(_clock,
                  style: const TextStyle(
                      fontFamily: 'IBM Plex Mono', fontSize: 52, color: Colors.white, letterSpacing: 2)),
              const SizedBox(height: 8),
              Text(_paused ? 'Pausado' : 'Em sessão',
                  style: const TextStyle(color: SerenoColors.tealLight, letterSpacing: 1)),
              const Spacer(),
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                IconButton.filled(
                  iconSize: 34,
                  style: IconButton.styleFrom(backgroundColor: SerenoColors.petrol, padding: const EdgeInsets.all(18)),
                  onPressed: _paused ? _resume : _pause,
                  icon: Icon(_paused ? Icons.play_arrow_rounded : Icons.pause_rounded, color: Colors.white),
                ),
                const SizedBox(width: 20),
                IconButton.filled(
                  iconSize: 34,
                  style: IconButton.styleFrom(backgroundColor: SerenoColors.alert, padding: const EdgeInsets.all(18)),
                  onPressed: _finishing ? null : () => _finish(),
                  icon: const Icon(Icons.stop_rounded, color: Colors.white),
                ),
              ]),
              const SizedBox(height: 14),
              const Text('Feche os olhos e respire com calma.',
                  style: TextStyle(color: Color(0xFF9DB2BD), fontSize: 13)),
            ]),
          ),
        ),
      );
}
