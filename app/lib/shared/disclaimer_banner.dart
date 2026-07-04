import 'package:flutter/material.dart';
import '../core/theme.dart';

/// Aviso persistente de escopo (ferramenta complementar). Presente em todo o fluxo.
class DisclaimerBanner extends StatelessWidget {
  const DisclaimerBanner({super.key});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFEEF3F5),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: SerenoColors.border),
        ),
        child: Row(children: [
          const Icon(Icons.info_outline, size: 18, color: SerenoColors.muted),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Ferramenta complementar. Não substitui avaliação ou tratamento profissional.',
              style: TextStyle(fontSize: 12, color: SerenoColors.muted, height: 1.3),
            ),
          ),
        ]),
      );
}
