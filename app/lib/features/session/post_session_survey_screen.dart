import 'package:flutter/material.dart';
import '../../core/api_client.dart';
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
          .showSnackBar(const SnackBar(content: Text('Obrigado pelo retorno!')));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.status == 409 ? 'Você já respondeu esta sessão.' : e.toString());
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
        appBar: AppBar(title: const Text('Como foi a sessão')),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
            children: [
              LikertQuestion(
                prompt: 'Como você se sente agora? (0 muito mal – 4 muito bem)',
                min: 0, max: 4, value: _feeling,
                onChanged: (v) => setState(() => _feeling = v)),
              LikertQuestion(
                prompt: 'Quão relaxado(a) você está? (0 nada – 4 muito)',
                min: 0, max: 4, value: _relaxation,
                onChanged: (v) => setState(() => _relaxation = v)),
              LikertQuestion(
                prompt: 'Se foi à noite, acha que dormiu melhor? (opcional)',
                min: 0, max: 4, value: _sleptBetter,
                onChanged: (v) => setState(() => _sleptBetter = v)),
              LikertQuestion(
                prompt: 'O quanto gostou desta sessão? (0 nada – 4 muito)',
                min: 0, max: 4, value: _liked,
                onChanged: (v) => setState(() => _liked = v)),
              LikertQuestion(
                prompt: 'Como percebeu a intensidade do áudio? (0 fraca – 4 forte)',
                min: 0, max: 4, value: _intensity,
                onChanged: (v) => setState(() => _intensity = v)),
              const SizedBox(height: 12),
              const Text('Repetiria esta sessão?', style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Wrap(spacing: 8, children: [
                ChoiceChip(
                    label: const Text('Sim'),
                    selected: _wouldRepeat == true,
                    onSelected: (_) => setState(() => _wouldRepeat = true)),
                ChoiceChip(
                    label: const Text('Não'),
                    selected: _wouldRepeat == false,
                    onSelected: (_) => setState(() => _wouldRepeat = false)),
              ]),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: (_complete && !_loading) ? _submit : null,
                child: _loading
                    ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Enviar'),
              ),
            ],
          ),
        ),
      );
}
