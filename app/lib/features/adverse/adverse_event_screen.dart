import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/outcomes_repository.dart';

/// Relato de evento adverso (B6). Para gravidade alta, reforça a orientação de buscar
/// ajuda (192 / CVV 188) — coerente com "ferramenta complementar". Bem-estar em 1º lugar.
class AdverseEventScreen extends StatefulWidget {
  final OutcomesRepository repo;
  final String? sessionId;
  const AdverseEventScreen({super.key, required this.repo, this.sessionId});
  @override
  State<AdverseEventScreen> createState() => _AdverseEventScreenState();
}

class _AdverseEventScreenState extends State<AdverseEventScreen> {
  final _type = TextEditingController();
  final _action = TextEditingController();
  String? _severity; // mild | moderate | severe
  bool _loading = false;

  bool get _complete => _type.text.trim().length >= 2 && _severity != null;

  Future<void> _submit() async {
    if (!_complete || _loading) return;
    setState(() => _loading = true);
    try {
      await widget.repo.reportAdverseEvent(
          type: _type.text.trim(), severity: _severity!,
          sessionId: widget.sessionId, action: _action.text.trim().isEmpty ? null : _action.text.trim());
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(AppLocalizations.of(context).adverseThanks)));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.toString());
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
    final urgent = _severity == 'severe';
    final severityOptions = [('mild', t.sevMild), ('moderate', t.sevModerate), ('severe', t.sevSevere)];
    return Scaffold(
      appBar: AppBar(title: Text(t.reportProblem)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            Text(t.adverseIntro, style: const TextStyle(height: 1.4)),
            const SizedBox(height: 12),
            TextField(
              controller: _type,
              decoration: InputDecoration(labelText: t.adverseWhat),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 12),
            Text(t.severity, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, children: [
              for (final opt in severityOptions)
                ChoiceChip(
                  label: Text(opt.$2),
                  selected: _severity == opt.$1,
                  onSelected: (_) => setState(() => _severity = opt.$1),
                  selectedColor: opt.$1 == 'severe' ? SerenoColors.alert : SerenoColors.teal,
                  labelStyle: TextStyle(color: _severity == opt.$1 ? Colors.white : null),
                ),
            ]),
            const SizedBox(height: 12),
            TextField(
              controller: _action,
              decoration: InputDecoration(labelText: t.adverseAction),
            ),
            if (urgent) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                    color: SerenoColors.alert.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(12)),
                child: Text(
                  t.adverseUrgent,
                  style: const TextStyle(color: SerenoColors.alert, fontWeight: FontWeight.w600, height: 1.4),
                ),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton(
              onPressed: (_complete && !_loading) ? _submit : null,
              child: _loading
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(t.adverseSubmit),
            ),
          ],
        ),
      ),
    );
  }
}
