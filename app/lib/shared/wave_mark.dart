import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../core/theme.dart';

/// Elemento de assinatura: a onda de interferência (dois senos próximos) — a
/// marca do "Sereno". Estático e discreto; respeita movimento reduzido.
class WaveMark extends StatelessWidget {
  final double height;
  final Color color;
  const WaveMark({super.key, this.height = 40, this.color = SerenoColors.teal});

  @override
  Widget build(BuildContext context) => SizedBox(
        height: height,
        width: double.infinity,
        child: CustomPaint(painter: _WavePainter(color)),
      );
}

class _WavePainter extends CustomPainter {
  final Color color;
  _WavePainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final path = Path();
    const n = 160;
    for (var i = 0; i <= n; i++) {
      final x = i / n;
      // envelope de batimento (cresce e diminui) * portadora
      final env = 0.30 + 0.70 * (math.cos(math.pi * 1.0 * x)).abs();
      final y = 0.5 + 0.42 * env * math.sin(2 * math.pi * 3.0 * x);
      final px = x * size.width;
      final py = y * size.height;
      i == 0 ? path.moveTo(px, py) : path.lineTo(px, py);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _WavePainter old) => old.color != color;
}
