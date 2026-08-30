import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/outcomes_repository.dart';
import '../../shared/disclaimer_banner.dart';
import '../../shared/likert_group.dart';

/// Avaliação de SEGURANÇA (G5/ADR-102) — PHQ-9, com finalidade de segurança.
///
/// **Não é desfecho do estudo** e a tela **não mostra escore**: um número de gravidade sem
/// profissional junto é lido como diagnóstico, e o app é ferramenta complementar. Quem calcula
/// e guarda o escore é o servidor; a tela devolve orientação de cuidado — sempre, com ou sem
/// gatilho — e avisa quando a equipe vai entrar em contato.
///
/// Enunciados próprios e curtos, como no GAD-7 (nunca o texto verbatim do instrumento); a
/// redação validada em PT-BR entra quando for licenciada.
class SafetyCheckScreen extends StatefulWidget {
  final OutcomesRepository repo;
  final String moment;
  const SafetyCheckScreen({super.key, required this.repo, this.moment = 'intermediaria'});

  @override
  State<SafetyCheckScreen> createState() => _SafetyCheckScreenState();
}

class _SafetyCheckScreenState extends State<SafetyCheckScreen> {
  List<int?> _phq9 = List<int?>.filled(9, null);
  bool _ok = false;
  bool _loading = false;

  Future<void> _submit() async {
    if (!_ok || _loading) return;
    setState(() => _loading = true);
    try {
      final r = await widget.repo.submitSafetyCheck(
          phq9: _phq9.cast<int>(), moment: widget.moment);
      if (!mounted) return;
      await _showGuidance(
        encaminhado: r['referral_opened'] == true,
        guidance: (r['guidance'] as String?) ?? '',
      );
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.toString());
    } catch (_) {
      if (mounted) _snack(AppLocalizations.of(context).connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _showGuidance({required bool encaminhado, required String guidance}) {
    final t = AppLocalizations.of(context);
    return showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: Text(encaminhado ? t.safetyReferralTitle : t.safetyThanksTitle),
        content: Text(
          encaminhado ? '${t.safetyReferralBody}\n\n$guidance' : guidance,
          style: const TextStyle(height: 1.4),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: Text(t.ok)),
        ],
      ),
    );
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.safetyTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            Text(t.safetyIntro, style: const TextStyle(height: 1.4)),
            const SizedBox(height: 8),
            Text(t.safetyHelpNow,
                style: const TextStyle(height: 1.4, color: SerenoColors.muted)),
            const SizedBox(height: 16),
            LikertGroup(
              title: t.phq9GroupTitle,
              prompts: t.phq9Prompts,
              onChanged: (v, ok) => setState(() {
                _phq9 = v;
                _ok = ok;
              }),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: (_ok && !_loading) ? _submit : null,
              child: _loading
                  ? const SizedBox(
                      height: 22, width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(t.safetySubmit),
            ),
            const SizedBox(height: 16),
            const DisclaimerBanner(),
          ],
        ),
      ),
    );
  }
}
