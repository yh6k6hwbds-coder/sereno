import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../services/participant_repository.dart';
import '../../services/session_repository.dart';
import '../../services/session_store.dart';
import '../../shared/disclaimer_banner.dart';
import '../auth/otp_screen.dart';
import '../session/headphone_check_screen.dart';

/// Início pós-consentimento. Abre a preparação da sessão. (Próximas fatias: pós-sessão,
/// diário, seguimento.) Serviços construídos a partir do armazenamento seguro
/// compartilhado — a ser migrado para injeção via Riverpod (ADR-050).
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  SessionRepository _repo() {
    final store = SessionStore();
    return SessionRepository(ApiClient(store), store);
  }

  Future<void> _logout(BuildContext context) async {
    final store = SessionStore();
    await store.clear(); // encerra a sessão (armazenamento seguro limpo)
    if (!context.mounted) return;
    final repo = ParticipantRepository(ApiClient(store), store);
    Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => OtpScreen(repo: repo)), (route) => false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          elevation: 0,
          actions: [
            IconButton(
              tooltip: 'Sair',
              icon: const Icon(Icons.logout_rounded),
              onPressed: () => _logout(context),
            ),
          ],
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SizedBox(height: 8),
              const Text('Boa noite,', style: TextStyle(color: SerenoColors.muted)),
              Text('tudo pronto', style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 20),
              InkWell(
                borderRadius: BorderRadius.circular(16),
                onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => HeadphoneCheckScreen(repo: _repo()))),
                child: Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(color: SerenoColors.teal, borderRadius: BorderRadius.circular(16)),
                  child: const Row(children: [
                    Icon(Icons.play_circle_fill, color: Colors.white, size: 40),
                    SizedBox(width: 14),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Iniciar sessão',
                            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 16)),
                        Text('~20 min · use fones', style: TextStyle(color: Color(0xFFDCEFF2))),
                      ]),
                    ),
                    Icon(Icons.chevron_right, color: Colors.white),
                  ]),
                ),
              ),
              const Spacer(),
              const DisclaimerBanner(),
            ]),
          ),
        ),
      );
}
