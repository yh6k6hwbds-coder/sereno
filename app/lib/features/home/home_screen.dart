import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/participant_repository.dart';
import '../../services/progress_repository.dart';
import '../../services/session_repository.dart';
import '../../services/outcomes_repository.dart';
import '../../services/audio_cache_key.dart';
import '../../services/session_store.dart';
import '../../shared/disclaimer_banner.dart';
import '../auth/otp_screen.dart';
import '../session/headphone_check_screen.dart';
import '../baseline/baseline_screen.dart';
import '../diary/sleep_diary_screen.dart';
import '../followup/followup_screen.dart';
import '../adverse/adverse_event_screen.dart';
import '../safety/safety_check_screen.dart';

/// Início pós-consentimento. CTA de sessão + acesso às telas de registro (baseline,
/// diário, seguimento, relato de EA). Serviços a partir do armazenamento seguro.
///
/// O andamento no protocolo (G6) vem do servidor: é ele que sabe quando a avaliação
/// intermediária (T2) é devida e se a participação foi descontinuada. A tela é útil
/// **antes** de a resposta chegar e continua útil se ela não chegar — sem rede, mostra o
/// que sempre mostrou, e o cartão do T2 simplesmente não aparece. Perder um convite é
/// melhor do que travar a tela inicial de quem só quer ouvir a sessão do dia.
class HomeScreen extends StatefulWidget {
  /// Injetável para teste: sem ele a Home tentaria falar com a API no `pumpWidget`.
  final ProgressRepository? progressRepo;
  const HomeScreen({super.key, this.progressRepo});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  ProtocolProgress? _progress;

  @override
  void initState() {
    super.initState();
    _loadProgress();
  }

  Future<void> _loadProgress() async {
    final repo = widget.progressRepo;
    if (repo == null) return;
    try {
      final p = await repo.myProgress();
      if (mounted) setState(() => _progress = p);
    } catch (_) {
      // Andamento é informação acessória: falhar aqui não pode estragar a Home.
    }
  }

  SessionRepository _sessionRepo() {
    final store = SessionStore();
    return SessionRepository(ApiClient(store), store);
  }

  OutcomesRepository _outcomesRepo() => OutcomesRepository(ApiClient(SessionStore()));

  Future<void> _logout(BuildContext context) async {
    final store = SessionStore();
    await store.clear(); // encerra a sessão (armazenamento seguro limpo)
    // O áudio guardado no aparelho sai junto: sem a chave ele já seria ilegível, mas
    // deixar o arquivo para trás não tem propósito — e ele é dado do estudo (ADR-103).
    await productionAudioCache().clear();
    await AudioCacheKey().forget();
    if (!context.mounted) return;
    final repo = ParticipantRepository(ApiClient(store), store);
    Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => OtpScreen(repo: repo)), (route) => false);
  }

  void _open(BuildContext context, Widget screen) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  Widget _navTile(BuildContext context, IconData icon, String label, Widget screen) => Card(
        margin: const EdgeInsets.only(bottom: 10),
        child: ListTile(
          leading: Icon(icon, color: SerenoColors.petrol),
          title: Text(label),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _open(context, screen),
        ),
      );

  /// Convite ao T2 — só quando o servidor diz que é devido. É a única coisa que faz da
  /// "2ª semana" do protocolo um momento e não um parágrafo.
  Widget _t2Card(BuildContext context, AppLocalizations t) => Card(
        margin: const EdgeInsets.only(bottom: 16),
        color: SerenoColors.petrol.withOpacity(0.08),
        child: ListTile(
          leading: const Icon(Icons.event_note_outlined, color: SerenoColors.petrol),
          title: Text(t.t2CardTitle, style: const TextStyle(fontWeight: FontWeight.w700)),
          subtitle: Text(_progress!.t2Late ? t.t2CardLate : t.t2CardBody),
          isThreeLine: true,
          trailing: const Icon(Icons.chevron_right),
          onTap: () async {
            await Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => SafetyCheckScreen(repo: _outcomesRepo())));
            await _loadProgress();   // respondeu? o convite some
          },
        ),
      );

  /// Descontinuado: a sessão não abre mais, e a tela precisa dizer isso sem parecer punição.
  Widget _discontinuedCard(AppLocalizations t) => Card(
        margin: const EdgeInsets.only(bottom: 16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t.discontinuedTitle,
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 8),
            Text(t.discontinuedBody, style: const TextStyle(color: SerenoColors.muted)),
          ]),
        ),
      );

  Widget _startSessionCta(BuildContext context, AppLocalizations t) => Semantics(
        // CTA primário: semântica explícita de botão rotulado (acessibilidade).
        button: true,
        label: t.startSession,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () => _open(context, HeadphoneCheckScreen(repo: _sessionRepo())),
          child: Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
                color: SerenoColors.teal, borderRadius: BorderRadius.circular(16)),
            child: Row(children: [
              const Icon(Icons.play_circle_fill, color: Colors.white, size: 40),
              const SizedBox(width: 14),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(t.startSession,
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w700, fontSize: 16)),
                  Text(t.sessionMeta, style: const TextStyle(color: Color(0xFFDCEFF2))),
                ]),
              ),
              const Icon(Icons.chevron_right, color: Colors.white),
            ]),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final p = _progress;
    final descontinuado = p != null && p.isDiscontinued;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            tooltip: t.logout,
            icon: const Icon(Icons.logout_rounded),
            onPressed: () => _logout(context),
          ),
        ],
      ),
      // O aviso de escopo fica FORA da lista que rola: a postura científica pede um aviso
      // "persistente na interface", e no fim de uma lista ele só existe para quem rola até
      // lá — foi o que aconteceu quando a tela ganhou mais um atalho (ADR-102).
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
              children: [
                Text(t.greeting, style: const TextStyle(color: SerenoColors.muted)),
                Text(t.ready, style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 20),
                if (descontinuado) _discontinuedCard(t),
                if (p != null && p.t2Due) _t2Card(context, t),
                // Sem o CTA quando a participação foi descontinuada: o servidor recusaria a
                // sessão com 403, e oferecer um botão que não funciona é pior que não oferecer.
                if (!descontinuado) _startSessionCta(context, t),
                const SizedBox(height: 24),
                Text(t.records, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                const SizedBox(height: 10),
                _navTile(context, Icons.assignment_outlined, t.baseline, BaselineScreen(repo: _outcomesRepo())),
                _navTile(context, Icons.nightlight_outlined, t.sleepDiary, SleepDiaryScreen(repo: _outcomesRepo())),
                _navTile(context, Icons.event_available_outlined, t.followup, FollowupScreen(repo: _outcomesRepo())),
                _navTile(context, Icons.favorite_border, t.safetyTitle,
                    SafetyCheckScreen(repo: _outcomesRepo())),
                _navTile(context, Icons.report_gmailerrorred_outlined, t.reportProblem,
                    AdverseEventScreen(repo: _outcomesRepo())),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.fromLTRB(24, 8, 24, 16),
            child: DisclaimerBanner(),
          ),
        ]),
      ),
    );
  }
}
