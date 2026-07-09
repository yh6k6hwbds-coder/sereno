import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/outcomes_repository.dart';
import '../../shared/likert_group.dart';
import '../../shared/psqi_section.dart';

/// Seguimento (B5): GAD-7 + PSQI + SUS (usabilidade) + item de integridade do cegamento.
/// O item de cegamento capta só o PALPITE, com rótulos codificados neutros (A/B/não sei) —
/// a UI NUNCA sugere qual é o ativo/sham. Enunciados localizados em AppLocalizations.
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
          .showSnackBar(SnackBar(content: Text(AppLocalizations.of(context).followupThanks)));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.status == 409
          ? AppLocalizations.of(context).followupAlready
          : e.toString());
    } catch (_) {
      _snack(AppLocalizations.of(context).connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final guessOptions = [('A', t.groupA), ('B', t.groupB), ('nao_sei', t.dontKnow)];
    return Scaffold(
      appBar: AppBar(title: Text(t.followup)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            LikertGroup(
              title: t.gad7GroupTitle,
              prompts: t.gad7Prompts,
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
              title: t.susGroupTitle,
              prompts: t.susPrompts, min: 1, max: 5,
              onChanged: (v, ok) => setState(() {
                _sus = v;
                _susok = ok;
              })),
            const SizedBox(height: 16),
            Text(t.blindingQuestion, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, children: [
              for (final opt in guessOptions)
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
                  : Text(t.followupSubmit),
            ),
          ],
        ),
      ),
    );
  }
}
