import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/api_client.dart';
import 'core/config.dart';
import 'core/theme.dart';
import 'l10n/app_localizations.dart';
import 'services/participant_repository.dart';
import 'services/progress_repository.dart';
import 'services/session_store.dart';
import 'features/auth/otp_screen.dart';
import 'features/home/home_screen.dart';
import 'features/staff/setup_password_screen.dart';

/// Raiz do app. Compõe os serviços (store → api → repositório) e decide a tela inicial
/// pela sessão persistida (auto-login). À medida que crescer, considerar Riverpod +
/// go_router (ver ADR-050); aqui mantemos injeção simples por construtor.
class SerenoApp extends StatelessWidget {
  const SerenoApp({super.key});

  @override
  Widget build(BuildContext context) {
    final store = SessionStore();
    final api = ApiClient(store);
    final repo = ParticipantRepository(api, store);
    // Link de convite/redefinição de senha da EQUIPE (ADR-096): só existe na web e só
    // quando há token na URL. Vem ANTES do AuthGate de propósito — quem chega por esse
    // link não é participante e não deve cair no login por código de estudo, nem ver a
    // Home de uma sessão que porventura esteja guardada neste navegador.
    final setupToken = staffSetupToken;
    return MaterialApp(
      title: 'Sereno',
      debugShowCheckedModeBanner: false,
      theme: buildSerenoTheme(),
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: setupToken != null
          ? SetupPasswordScreen(api: api, token: setupToken)
          : AuthGate(store: store, repo: repo),
    );
  }
}

/// Roteia entre login (OTP) e Home conforme haja uma sessão persistida.
class AuthGate extends StatefulWidget {
  final SessionStore store;
  final ParticipantRepository repo;
  const AuthGate({super.key, required this.store, required this.repo});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  late final Future<bool> _authenticated = widget.store.isAuthenticated();

  @override
  Widget build(BuildContext context) => FutureBuilder<bool>(
        future: _authenticated,
        builder: (context, snap) {
          if (!snap.hasData) {
            return const Scaffold(body: Center(child: CircularProgressIndicator()));
          }
          return snap.data!
              ? HomeScreen(progressRepo: ProgressRepository(ApiClient(widget.store)))
              : OtpScreen(repo: widget.repo);
        },
      );
}
