import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/participant_repository.dart';
import '../../services/session_repository.dart';
import '../../services/outcomes_repository.dart';
import '../../services/session_store.dart';
import '../../shared/disclaimer_banner.dart';
import '../auth/otp_screen.dart';
import '../session/headphone_check_screen.dart';
import '../baseline/baseline_screen.dart';
import '../diary/sleep_diary_screen.dart';
import '../followup/followup_screen.dart';
import '../adverse/adverse_event_screen.dart';

/// Início pós-consentimento. CTA de sessão + acesso às telas de registro (baseline,
/// diário, seguimento, relato de EA). Serviços a partir do armazenamento seguro.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  SessionRepository _sessionRepo() {
    final store = SessionStore();
    return SessionRepository(ApiClient(store), store);
  }

  OutcomesRepository _outcomesRepo() => OutcomesRepository(ApiClient(SessionStore()));

  Future<void> _logout(BuildContext context) async {
    final store = SessionStore();
    await store.clear(); // encerra a sessão (armazenamento seguro limpo)
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

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
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
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          children: [
            Text(t.greeting, style: const TextStyle(color: SerenoColors.muted)),
            Text(t.ready, style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 20),
            // CTA primário: semântica explícita de botão rotulado (acessibilidade).
            Semantics(
              button: true,
              label: t.startSession,
              child: InkWell(
                borderRadius: BorderRadius.circular(16),
                onTap: () => _open(context, HeadphoneCheckScreen(repo: _sessionRepo())),
                child: Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(color: SerenoColors.teal, borderRadius: BorderRadius.circular(16)),
                  child: Row(children: [
                    const Icon(Icons.play_circle_fill, color: Colors.white, size: 40),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(t.startSession,
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 16)),
                        Text(t.sessionMeta, style: const TextStyle(color: Color(0xFFDCEFF2))),
                      ]),
                    ),
                    const Icon(Icons.chevron_right, color: Colors.white),
                  ]),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Text(t.records, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 10),
            _navTile(context, Icons.assignment_outlined, t.baseline, BaselineScreen(repo: _outcomesRepo())),
            _navTile(context, Icons.nightlight_outlined, t.sleepDiary, SleepDiaryScreen(repo: _outcomesRepo())),
            _navTile(context, Icons.event_available_outlined, t.followup, FollowupScreen(repo: _outcomesRepo())),
            _navTile(context, Icons.report_gmailerrorred_outlined, t.reportProblem,
                AdverseEventScreen(repo: _outcomesRepo())),
            const SizedBox(height: 16),
            const DisclaimerBanner(),
          ],
        ),
      ),
    );
  }
}
