import 'package:flutter/material.dart';
import 'likert_question.dart';

/// Grupo de itens Likert (ex.: GAD-7 = 7 itens 0–3; SUS = 10 itens 1–5). Gerencia a
/// lista de respostas e notifica o pai com os valores e se está completo. Enunciados
/// próprios/curtos — nunca o texto verbatim do instrumento.
class LikertGroup extends StatefulWidget {
  final String title;
  final List<String> prompts;
  final int min;
  final int max;
  final void Function(List<int?> values, bool complete) onChanged;

  const LikertGroup({
    super.key,
    required this.title,
    required this.prompts,
    required this.onChanged,
    this.min = 0,
    this.max = 3,
  });

  @override
  State<LikertGroup> createState() => _LikertGroupState();
}

class _LikertGroupState extends State<LikertGroup> {
  late final List<int?> _values = List<int?>.filled(widget.prompts.length, null);

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          for (var i = 0; i < widget.prompts.length; i++)
            LikertQuestion(
              prompt: widget.prompts[i],
              min: widget.min,
              max: widget.max,
              value: _values[i],
              onChanged: (v) => setState(() {
                _values[i] = v;
                widget.onChanged(_values, !_values.contains(null));
              }),
            ),
        ],
      );
}
