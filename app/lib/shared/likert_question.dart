import 'package:flutter/material.dart';
import '../core/theme.dart';

/// Pergunta de escala (Likert) reutilizável: um enunciado + opções [min..max].
/// Enunciados são PRÓPRIOS/curtos — nunca o texto verbatim dos instrumentos validados.
class LikertQuestion extends StatelessWidget {
  final String prompt;
  final int min;
  final int max;
  final int? value;
  final ValueChanged<int> onChanged;

  const LikertQuestion({
    super.key,
    required this.prompt,
    required this.onChanged,
    this.value,
    this.min = 0,
    this.max = 3,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(prompt, style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              for (var i = min; i <= max; i++)
                ChoiceChip(
                  label: Text('$i'),
                  selected: value == i,
                  onSelected: (_) => onChanged(i),
                  selectedColor: SerenoColors.teal,
                  labelStyle: TextStyle(color: value == i ? Colors.white : null),
                ),
            ],
          ),
        ]),
      );
}
