import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/core/api_client.dart';
import 'package:sereno/services/session_store.dart';
import 'package:sereno/services/participant_repository.dart';
import 'package:sereno/services/outcomes_repository.dart';
import 'package:sereno/features/home/home_screen.dart';
import 'package:sereno/features/auth/otp_screen.dart';
import 'package:sereno/features/consent/consent_screen.dart';
import 'package:sereno/features/session/post_session_survey_screen.dart';
import 'package:sereno/features/baseline/baseline_screen.dart';
import 'package:sereno/features/diary/sleep_diary_screen.dart';
import 'package:sereno/features/followup/followup_screen.dart';
import 'package:sereno/features/adverse/adverse_event_screen.dart';
import 'package:sereno/shared/breathing_wave.dart';

/// E5/ADR-070 — i18n (pt-BR/en) + acessibilidade (semântica de botão, movimento reduzido).

Widget _app(Widget home, {Locale? locale}) => MaterialApp(
      locale: locale,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

/// Store em memória (o flutter_secure_storage usa platform channels) + repo com MockClient.
class _Store extends SessionStore {
  @override
  Future<String?> accessToken() async => 'tok';
  @override
  Future<String?> refreshToken() async => null;
}

ParticipantRepository _prepo() => ParticipantRepository(
    ApiClient(_Store(), client: MockClient((r) async => http.Response('{}', 200))), _Store());

OutcomesRepository _orepo() => OutcomesRepository(
    ApiClient(_Store(), client: MockClient((r) async => http.Response('{}', 201))));

void main() {
  testWidgets('Home em pt-BR (idioma padrão do piloto)', (t) async {
    await t.pumpWidget(_app(const HomeScreen(), locale: const Locale('pt')));
    await t.pumpAndSettle();
    expect(find.text('Iniciar sessão'), findsOneWidget);
    expect(find.textContaining('Não substitui'), findsOneWidget); // disclaimer persistente
  });

  testWidgets('Home em inglês quando o locale é en', (t) async {
    await t.pumpWidget(_app(const HomeScreen(), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Start session'), findsOneWidget);
    expect(find.text('Iniciar sessão'), findsNothing);
    expect(find.textContaining('does not replace'), findsOneWidget);
  });

  testWidgets('CTA de sessão expõe semântica de botão rotulada', (t) async {
    final handle = t.ensureSemantics();
    await t.pumpWidget(_app(const HomeScreen(), locale: const Locale('pt')));
    await t.pumpAndSettle();
    // RegExp: o label do botão combina o CTA com o subtítulo ("~20 min · use fones");
    // basta que a semântica do botão CONTENHA o rótulo do CTA.
    expect(find.bySemanticsLabel(RegExp('Iniciar sessão')), findsAtLeastNWidgets(1));
    handle.dispose();
  });

  testWidgets('OTP: pt-BR por padrão, en quando locale=en', (t) async {
    await t.pumpWidget(_app(OtpScreen(repo: _prepo()), locale: const Locale('pt')));
    await t.pumpAndSettle();
    expect(find.text('Enviar código'), findsOneWidget);

    await t.pumpWidget(_app(OtpScreen(repo: _prepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Send code'), findsOneWidget);
    expect(find.text('Study code'), findsOneWidget);
    expect(find.text('Enviar código'), findsNothing);
  });

  testWidgets('Consentimento em inglês', (t) async {
    await t.pumpWidget(_app(ConsentScreen(repo: _prepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Consent Form'), findsOneWidget);
    expect(find.text('Agree and continue'), findsOneWidget);
    expect(find.textContaining('binaural beats'), findsOneWidget); // resumo traduzido
  });

  testWidgets('Pós-sessão em inglês', (t) async {
    await t.pumpWidget(_app(
        PostSessionSurveyScreen(repo: _orepo(), sessionId: 's1'), locale: const Locale('en')));
    await t.pumpAndSettle();
    // Itens do topo (o ListView é lazy: botão/últimos itens ficam abaixo da dobra).
    expect(find.text('How was the session'), findsOneWidget); // AppBar
    expect(find.textContaining('How do you feel now'), findsOneWidget); // 1º prompt (en)
  });

  testWidgets('B2–B6: títulos de AppBar em inglês', (t) async {
    // Só os títulos (topo, sempre visíveis); o conteúdo fica em ListView lazy.
    await t.pumpWidget(_app(BaselineScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('How you have been'), findsOneWidget);

    await t.pumpWidget(_app(SleepDiaryScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Sleep diary'), findsOneWidget);

    await t.pumpWidget(_app(FollowupScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Follow-up'), findsOneWidget);

    await t.pumpWidget(_app(AdverseEventScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Report a problem'), findsOneWidget);
  });

  testWidgets('BreathingWave respeita movimento reduzido (assenta, sem repetir)', (t) async {
    await t.pumpWidget(_app(
      Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: const Scaffold(body: BreathingWave()),
        ),
      ),
      locale: const Locale('pt'),
    ));
    await t.pumpAndSettle(); // não trava: sem animação em repeat sob movimento reduzido
    expect(t.takeException(), isNull);
    expect(find.byType(BreathingWave), findsOneWidget);
  });
}
