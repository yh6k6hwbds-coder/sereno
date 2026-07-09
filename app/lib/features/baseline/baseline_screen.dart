import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../l10n/app_localizations.dart';
import '../../services/outcomes_repository.dart';
import '../../shared/likert_group.dart';
import '../../shared/psqi_section.dart';

/// Linha de base (B2): GAD-7 + PSQI (itens brutos; escore versionado no servidor).
/// Não exibe o escore de forma alarmante — apenas confirma o registro. Enunciados
/// próprios (não o texto verbatim dos instrumentos), localizados em AppLocalizations.
class BaselineScreen extends StatefulWidget {
  final OutcomesRepository repo;
  const BaselineScreen({super.key, required this.repo});
  @override
  State<BaselineScreen> createState() => _BaselineScreenState();
}

class _BaselineScreenState extends State<BaselineScreen> {
  List<int?> _gad7 = List<int?>.filled(7, null);
  bool _gad7ok = false;
  Map<String, dynamic> _psqi = {};
  bool _psqiok = false;
  bool _loading = false;

  bool get _complete => _gad7ok && _psqiok;

  Future<void> _submit() async {
    if (!_complete || _loading) return;
    setState(() => _loading = true);
    try {
      await widget.repo.submitBaseline(gad7: _gad7.cast<int>(), psqi: _psqi);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(AppLocalizations.of(context).baselineThanks)));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.status == 409
          ? AppLocalizations.of(context).baselineAlready
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
    return Scaffold(
      appBar: AppBar(title: Text(t.baselineTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            Text(t.baselineIntro, style: const TextStyle(height: 1.4)),
            const SizedBox(height: 16),
            LikertGroup(
              title: t.gad7GroupTitle,
              prompts: t.gad7Prompts,
              onChanged: (v, ok) => setState(() {
                _gad7 = v;
                _gad7ok = ok;
              }),
            ),
            const SizedBox(height: 16),
            PsqiSection(onChanged: (json, ok) => setState(() {
                  _psqi = json;
                  _psqiok = ok;
                })),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: (_complete && !_loading) ? _submit : null,
              child: _loading
                  ? const SizedBox(
                      height: 22, width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(t.baselineSubmit),
            ),
          ],
        ),
      ),
    );
  }
}
