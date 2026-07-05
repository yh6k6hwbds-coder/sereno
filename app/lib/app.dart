import 'package:flutter/material.dart';
import 'core/api_client.dart';
import 'core/theme.dart';
import 'services/participant_repository.dart';
import 'services/session_store.dart';
import 'features/auth/otp_screen.dart';
import 'features/home/home_screen.dart';

/// Raiz do app. Compõe os serviços (store → api → repositório) e decide a tela inicial
/// pela sessão persistida (auto-login). À medida que crescer, considerar Riverpod +
/// go_router (ver ADR-050); aqui mantemos injeção simples por construtor.
class SerenoApp extends StatelessWidget {
  const SerenoApp({super.key});

  @override
  Widget build(BuildContext context) {
    final store = SessionStore();
    final repo = ParticipantRepository(ApiClient(store), store);
    return MaterialApp(
      title: 'Sereno',
      debugShowCheckedModeBanner: false,
      theme: buildSerenoTheme(),
      home: AuthGate(store: store, repo: repo),
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
          return snap.data! ? const HomeScreen() : OtpScreen(repo: widget.repo);
        },
      );
}
