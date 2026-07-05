import 'package:flutter/material.dart';
import 'likert_question.dart';

/// Seção de sono (base do PSQI) — itens BRUTOS; o escore é calculado/versionado no
/// servidor. Enunciados próprios e curtos (nunca o texto verbatim do instrumento).
/// Notifica o pai a cada mudança com o JSON parcial e se está completa.
///
/// Simplificação do piloto: `hours_slept`/`hours_in_bed` são números diretos (não
/// time-pickers deitar→levantar) — reduz superfície de UI; refinar depois (ADR-073).
class PsqiSection extends StatefulWidget {
  final void Function(Map<String, dynamic> json, bool complete) onChanged;
  const PsqiSection({super.key, required this.onChanged});

  @override
  State<PsqiSection> createState() => _PsqiSectionState();
}

class _PsqiSectionState extends State<PsqiSection> {
  // Itens de frequência/qualidade (0–3).
  final Map<String, int?> _scale = {
    'subjective_quality': null,
    'cannot_sleep_30min_freq': null,
    'medication_freq': null,
    'stay_awake_freq': null,
    'enthusiasm_problem': null,
  };
  // Distúrbios do sono (9 itens, 0–3).
  final List<int?> _disturb = List<int?>.filled(9, null);

  final _latency = TextEditingController();
  final _hoursSlept = TextEditingController();
  final _hoursInBed = TextEditingController();

  static const _prompts = {
    'subjective_quality': 'No último mês, como avalia sua qualidade de sono? (0 muito boa – 3 muito ruim)',
    'cannot_sleep_30min_freq': 'Com que frequência levou mais de 30 min para adormecer?',
    'medication_freq': 'Com que frequência usou medicação para dormir?',
    'stay_awake_freq': 'Com que frequência teve dificuldade de ficar acordado durante o dia?',
    'enthusiasm_problem': 'Quanta dificuldade teve para manter o ânimo nas atividades?',
  };
  static const _disturbPrompts = [
    'acordou no meio da noite/de manhã cedo', 'precisou ir ao banheiro',
    'não conseguiu respirar bem', 'tossiu ou roncou alto', 'sentiu muito frio',
    'sentiu muito calor', 'teve sonhos ruins', 'sentiu dores', 'outro motivo',
  ];

  @override
  void dispose() {
    _latency.dispose();
    _hoursSlept.dispose();
    _hoursInBed.dispose();
    super.dispose();
  }

  double? _num(TextEditingController c) => double.tryParse(c.text.replaceAll(',', '.'));

  void _notify() {
    final latency = int.tryParse(_latency.text);
    final slept = _num(_hoursSlept);
    final inBed = _num(_hoursInBed);
    final complete = !_scale.values.contains(null) &&
        !_disturb.contains(null) &&
        latency != null &&
        slept != null &&
        inBed != null;
    final json = <String, dynamic>{
      ..._scale,
      'latency_min': latency,
      'hours_slept': slept,
      'hours_in_bed': inBed,
      'disturbance_items': _disturb,
    };
    widget.onChanged(json, complete);
  }

  Widget _numField(String label, TextEditingController c) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: TextField(
          controller: c,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: label),
          onChanged: (_) => _notify(),
        ),
      );

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Seu sono no último mês',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          _numField('Minutos para adormecer', _latency),
          _numField('Horas realmente dormidas', _hoursSlept),
          _numField('Horas na cama', _hoursInBed),
          for (final key in _scale.keys)
            LikertQuestion(
              prompt: _prompts[key]!,
              value: _scale[key],
              onChanged: (v) => setState(() {
                _scale[key] = v;
                _notify();
              }),
            ),
          const SizedBox(height: 8),
          const Text('Com que frequência seu sono foi perturbado por…',
              style: TextStyle(fontWeight: FontWeight.w600)),
          for (var i = 0; i < _disturb.length; i++)
            LikertQuestion(
              prompt: _disturbPrompts[i],
              value: _disturb[i],
              onChanged: (v) => setState(() {
                _disturb[i] = v;
                _notify();
              }),
            ),
        ],
      );
}
