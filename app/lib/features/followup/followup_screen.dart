import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../services/outcomes_repository.dart';
import '../../shared/likert_group.dart';
import '../../shared/psqi_section.dart';
import '../baseline/baseline_screen.dart' show gad7Prompts;

/// Seguimento (B5): GAD-7 + PSQI + SUS (usabilidade) + item de integridade do cegamento.
/// O item de cegamento capta só o PALPITE, com rótulos codificados neutros (A/B/não sei) —
/// a UI NUNCA sugere qual é o ativo/sham.
const susPrompts = <String>[
  'Gostaria de usar este app com frequência.',
  'Achei o app desnecessariamente complexo.',
  'Achei o app fácil de usar.',
  'Precisaria de ajuda para conseguir usar o app.',
  'As funções do app são bem integradas.',
  'Há inconsistências demais no app.',
  'A maioria aprenderia a usar o app rapidamente.',
  'Achei o app trabalhoso de usar.',
  'Senti-me confiante ao usar o app.',
  'Precisei aprender muita coisa antes de usar.',
];

class FollowupScreen extends StatefulWidget {
  final OutcomesRepository repo;
  const FollowupScreen({super.key, required this.repo});
  @override
  State<FollowupScreen> createState() => _FollowupScreenState();
}

class _FollowupScreenState extends State<FollowupScreen> {
  List<int?> _gad7 = List<int?>.filled(7, null);
  bool _gad7ok = false;
  Map<String, dynamic> _psqi = {};
  bool _psqiok = false;
  List<int?> _sus = List<int?>.filled(10, null);
  bool _susok = false;
  String? _guess; // 'A' | 'B' | 'nao_sei'
  bool _loading = false;

  bool get _complete => _gad7ok && _psqiok && _susok && _guess != null;

  Future<void> _submit() async {
    if (!_complete || _loading) return;
    setState(() => _loading = true);
    try {
      await widget.repo.submitFollowup(
          gad7: _gad7.cast<int>(), psqi: _psqi, sus: _sus.cast<int>(), blindingGuess: _guess!);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Seguimento registrado. Obrigado!')));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.status == 409 ? 'Seu seguimento já foi registrado.' : e.toString());
    } catch (_) {
      _snack('Falha de conexão. Tente novamente.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Seguimento')),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
            children: [
              LikertGroup(
                title: 'Nas últimas 2 semanas…',
                prompts: gad7Prompts,
                onChanged: (v, ok) => setState(() {
                  _gad7 = v;
                  _gad7ok = ok;
                })),
              const SizedBox(height: 16),
              PsqiSection(onChanged: (json, ok) => setState(() {
                    _psqi = json;
                    _psqiok = ok;
                  })),
              const SizedBox(height: 16),
              LikertGroup(
                title: 'Sobre o app (1 discordo totalmente – 5 concordo totalmente)',
                prompts: susPrompts, min: 1, max: 5,
                onChanged: (v, ok) => setState(() {
                  _sus = v;
                  _susok = ok;
                })),
              const SizedBox(height: 16),
              const Text('O estudo tem dois grupos de áudio (A e B). Qual você acha que recebeu?',
                  style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Wrap(spacing: 8, children: [
                for (final opt in const [('A', 'Grupo A'), ('B', 'Grupo B'), ('nao_sei', 'Não sei')])
                  ChoiceChip(
                    label: Text(opt.$2),
                    selected: _guess == opt.$1,
                    onSelected: (_) => setState(() => _guess = opt.$1),
                    selectedColor: SerenoColors.teal,
                    labelStyle: TextStyle(color: _guess == opt.$1 ? Colors.white : null),
                  ),
              ]),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: (_complete && !_loading) ? _submit : null,
                child: _loading
                    ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Enviar seguimento'),
              ),
            ],
          ),
        ),
      );
}
