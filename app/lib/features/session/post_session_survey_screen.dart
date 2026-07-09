import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../l10n/app_localizations.dart';
import '../../services/outcomes_repository.dart';
import '../../shared/likert_question.dart';

/// Micro-questionário pós-sessão (B3): itens 0–4 + "repetiria?". Idêntico entre braços.
class PostSessionSurveyScreen extends StatefulWidget {
  final OutcomesRepository repo;
  final String sessionId;
  const PostSessionSurveyScreen({super.key, required this.repo, required this.sessionId});
  @override
  State<PostSessionSurveyScreen> createState() => _PostSessionSurveyScreenState();
}

class _PostSessionSurveyScreenState extends State<PostSessionSurveyScreen> {
  int? _feeling, _relaxation, _sleptBetter, _liked, _intensity;
  bool? _wouldRepeat;
  bool _loading = false;

  bool get _complete =>
      _feeling != null && _relaxation != null && _liked != null &&
      _intensity != null && _wouldRepeat != null;

  Future<void> _submit() async {
    if (!_complete || _loading) return;
    setState(() => _loading = true);
    try {
      await widget.repo.submitSurvey(widget.sessionId,
          feeling: _feeling!, relaxation: _relaxation!, sleptBetter: _sleptBetter,
          liked: _liked!, intensity: _intensity!, wouldRepeat: _wouldRepeat!);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(AppLocalizations.of(context).surveyThanks)));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.status == 409
          ? AppLocalizations.of(context).surveyAlready
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
      appBar: AppBar(title: Text(t.surveyTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            LikertQuestion(
              prompt: t.surveyFeeling,
              min: 0, max: 4, value: _feeling,
              onChanged: (v) => setState(() => _feeling = v)),
            LikertQuestion(
              prompt: t.surveyRelaxation,
              min: 0, max: 4, value: _relaxation,
              onChanged: (v) => setState(() => _relaxation = v)),
            LikertQuestion(
              prompt: t.surveySleptBetter,
              min: 0, max: 4, value: _sleptBetter,
              onChanged: (v) => setState(() => _sleptBetter = v)),
            LikertQuestion(
              prompt: t.surveyLiked,
              min: 0, max: 4, value: _liked,
              onChanged: (v) => setState(() => _liked = v)),
            LikertQuestion(
              prompt: t.surveyIntensity,
              min: 0, max: 4, value: _intensity,
              onChanged: (v) => setState(() => _intensity = v)),
            const SizedBox(height: 12),
            Text(t.surveyWouldRepeat, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, children: [
              ChoiceChip(
                  label: Text(t.yes),
                  selected: _wouldRepeat == true,
                  onSelected: (_) => setState(() => _wouldRepeat = true)),
              ChoiceChip(
                  label: Text(t.no),
                  selected: _wouldRepeat == false,
                  onSelected: (_) => setState(() => _wouldRepeat = false)),
            ]),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: (_complete && !_loading) ? _submit : null,
              child: _loading
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(t.send),
            ),
          ],
        ),
      ),
    );
  }
}
