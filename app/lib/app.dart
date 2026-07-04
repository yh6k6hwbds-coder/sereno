import 'package:flutter/material.dart';
import 'core/api_client.dart';
import 'core/theme.dart';
import 'services/participant_repository.dart';
import 'services/session_store.dart';
import 'features/auth/otp_screen.dart';

/// Raiz do app. Compõe os serviços (store → api → repositório) e abre o fluxo de
/// acesso. À medida que o app cresce, considerar Riverpod + go_router (ver ADR-049).
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
      home: OtpScreen(repo: repo),
    );
  }
}
