import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../l10n/app_localizations.dart';
import '../../services/outcomes_repository.dart';
import '../../shared/likert_question.dart';

/// Diário de sono (B4): um registro por dia (hoje). Só a data é obrigatória;
/// os demais campos são opcionais. O servidor recusa duplicidade do dia (409).
class SleepDiaryScreen extends StatefulWidget {
  final OutcomesRepository repo;
  const SleepDiaryScreen({super.key, required this.repo});
  @override
  State<SleepDiaryScreen> createState() => _SleepDiaryScreenState();
}

class _SleepDiaryScreenState extends State<SleepDiaryScreen> {
  final _latency = TextEditingController();
  final _awakenings = TextEditingController();
  final _duration = TextEditingController();
  int? _quality;
  bool _loading = false;

  String get _today => DateTime.now().toIso8601String().split('T').first;

  @override
  void dispose() {
    _latency.dispose();
    _awakenings.dispose();
    _duration.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      await widget.repo.submitDiary(
        date: _today,
        latencyMin: int.tryParse(_latency.text),
        awakenings: int.tryParse(_awakenings.text),
        durationH: double.tryParse(_duration.text.replaceAll(',', '.')),
        quality: _quality,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(AppLocalizations.of(context).diaryThanks)));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.status == 409
          ? AppLocalizations.of(context).diaryAlready
          : e.toString());
    } catch (_) {
      _snack(AppLocalizations.of(context).connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Widget _numField(String label, TextEditingController c, {bool decimal = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: TextField(
          controller: c,
          keyboardType: TextInputType.numberWithOptions(decimal: decimal),
          decoration: InputDecoration(labelText: label),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.diaryTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            Text(t.diaryToday(_today), style: const TextStyle(height: 1.4)),
            const SizedBox(height: 8),
            _numField(t.minutesToFallAsleep, _latency),
            _numField(t.diaryAwakenings, _awakenings),
            _numField(t.diaryDuration, _duration, decimal: true),
            LikertQuestion(
              prompt: t.diaryQuality,
              min: 0, max: 4, value: _quality,
              onChanged: (v) => setState(() => _quality = v)),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _loading ? null : _submit,
              child: _loading
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(t.diarySubmit),
            ),
          ],
        ),
      ),
    );
  }
}
