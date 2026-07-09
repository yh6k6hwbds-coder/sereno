import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../core/theme.dart';

/// Visualização da sessão: uma onda de interferência que "respira" numa cadência
/// FIXA de tempo. É deliberadamente NÃO REATIVA ao áudio — se reagisse à amplitude
/// ou à frequência, o braço ativo (com batimento) e o sham (sem) poderiam parecer
/// diferentes, quebrando o cegamento. A animação depende só do relógio.
class BreathingWave extends StatefulWidget {
  final double height;
  const BreathingWave({super.key, this.height = 160});
  @override
  State<BreathingWave> createState() => _BreathingWaveState();
}

class _BreathingWaveState extends State<BreathingWave> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(seconds: 8));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Acessibilidade: respeita "movimento reduzido" do SO. Com a animação desligada,
    // mostra um quadro estático (não pisca, não repete) — e continua NÃO reativa ao áudio.
    final reduceMotion = MediaQuery.maybeOf(context)?.disableAnimations ?? false;
    if (reduceMotion) {
      if (_c.isAnimating) _c.stop();
      _c.value = 0.25; // quadro representativo, fixo
    } else if (!_c.isAnimating) {
      _c.repeat();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
        height: widget.height,
        width: double.infinity,
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, __) => CustomPaint(painter: _BreathingPainter(_c.value)),
        ),
      );
}

class _BreathingPainter extends CustomPainter {
  final double t; // 0..1, tempo (não áudio)
  _BreathingPainter(this.t);

  @override
  void paint(Canvas canvas, Size size) {
    final phase = 2 * math.pi * t;
    // amplitude "respira" suavemente entre 0.5 e 1.0 pela função do tempo
    final breathe = 0.75 + 0.25 * math.sin(phase);
    for (var layer = 0; layer < 3; layer++) {
      final paint = Paint()
        ..color = [SerenoColors.teal, SerenoColors.tealLight, SerenoColors.petrol][layer]
            .withOpacity(0.35 + 0.20 * layer)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..strokeCap = StrokeCap.round;
      final path = Path();
      const n = 180;
      for (var i = 0; i <= n; i++) {
        final x = i / n;
        final env = 0.35 + 0.65 * (math.cos(math.pi * x)).abs();
        final y = 0.5 +
            0.34 * breathe * env * math.sin(2 * math.pi * (2.5 + layer * 0.4) * x + phase);
        final px = x * size.width;
        final py = y * size.height;
        i == 0 ? path.moveTo(px, py) : path.lineTo(px, py);
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _BreathingPainter old) => old.t != t;
}
