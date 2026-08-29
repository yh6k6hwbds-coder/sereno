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

/// E5/ADR-070 — i18n + acessibilidade (semântica de botão, movimento reduzido).
///
/// **ADR-097 mudou o que se testa aqui.** O estudo é pt-BR: o TCLE que vincula o participante
/// só existe em português, então o app **não oferece** inglês — resolve qualquer idioma de
/// aparelho para pt-BR. Os testes de tela, portanto, provam a RESTRIÇÃO (aparelho em inglês →
/// interface em pt-BR), e não mais a troca de idioma. A tradução `en` continua existindo e
/// segue testada na camada de strings, para que reabrir o inglês seja mexer numa lista.

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

  testWidgets('aparelho em inglês continua vendo pt-BR (ADR-097)', (t) async {
    // O `WidgetsApp` resolve o locale pedido contra `supportedLocales`, que hoje só tem pt.
    await t.pumpWidget(_app(const HomeScreen(), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Iniciar sessão'), findsOneWidget);
    expect(find.text('Start session'), findsNothing);
    expect(find.textContaining('Não substitui'), findsOneWidget);
  });

  test('o app oferece só pt-BR, mas a tradução en segue viva (ADR-070/097)', () {
    expect(AppLocalizations.supportedLocales, [const Locale('pt')]);
    expect(AppLocalizations.translatedLocales, contains(const Locale('en')));
    // A camada de strings continua completa: reabrir o inglês é devolver 'en' a
    // `supportedLocales` — junto com um TCLE em inglês, que é o que falta de verdade.
    const en = AppLocalizations(Locale('en'));
    expect(en.startSession, 'Start session');
    expect(en.consentTitle, 'Consent Form');
    expect(en.tcleFullTitle, 'Full consent form');
    expect(en.gad7Prompts, isNotEmpty);
    expect(en.susPrompts, isNotEmpty);
  });

  test('o delegate RECUSA en enquanto o estudo for pt-BR', () {
    // Se isto passar a aceitar `en`, alguém consentiria por uma interface traduzida cujo
    // documento correspondente não existe — é o ponto do ADR-097.
    expect(AppLocalizations.delegate.isSupported(const Locale('en')), isFalse);
    expect(AppLocalizations.delegate.isSupported(const Locale('pt')), isTrue);
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

  testWidgets('OTP: pt-BR, inclusive com o aparelho em inglês', (t) async {
    await t.pumpWidget(_app(OtpScreen(repo: _prepo()), locale: const Locale('pt')));
    await t.pumpAndSettle();
    expect(find.text('Enviar código'), findsOneWidget);

    await t.pumpWidget(_app(OtpScreen(repo: _prepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Enviar código'), findsOneWidget);
    expect(find.text('Send code'), findsNothing);
  });

  testWidgets('Consentimento em pt-BR, mesmo com o aparelho em inglês', (t) async {
    await t.pumpWidget(_app(ConsentScreen(repo: _prepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Termo de Consentimento'), findsOneWidget);
    expect(find.text('Concordar e continuar'), findsOneWidget);
    expect(find.textContaining('binaurais'), findsOneWidget);      // resumo em pt
    expect(find.text('Agree and continue'), findsNothing);
    // O acesso ao termo INTEGRAL precisa existir: sem ele, o que a tela oferece é só o
    // resumo — e resumo não é consentimento informado. Fica abaixo da dobra (o resumo tem
    // 7 tópicos), então é preciso rolar — como o participante faz para chegar às
    // confirmações, que vêm logo depois.
    await t.scrollUntilVisible(find.text('Ler o termo completo'), 200);
    expect(find.text('Ler o termo completo'), findsOneWidget);
  });

  testWidgets('Pós-sessão em pt-BR com o aparelho em inglês', (t) async {
    await t.pumpWidget(_app(
        PostSessionSurveyScreen(repo: _orepo(), sessionId: 's1'), locale: const Locale('en')));
    await t.pumpAndSettle();
    // Itens do topo (o ListView é lazy: botão/últimos itens ficam abaixo da dobra).
    expect(find.text('Como foi a sessão'), findsOneWidget);              // AppBar
    expect(find.textContaining('Como você se sente agora'), findsOneWidget); // 1º prompt
  });

  testWidgets('B2–B6: títulos de AppBar em pt-BR com o aparelho em inglês', (t) async {
    // Só os títulos (topo, sempre visíveis); o conteúdo fica em ListView lazy.
    await t.pumpWidget(_app(BaselineScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Como você tem estado'), findsOneWidget);

    await t.pumpWidget(_app(SleepDiaryScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Diário de sono'), findsOneWidget);

    await t.pumpWidget(_app(FollowupScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Seguimento'), findsOneWidget);

    await t.pumpWidget(_app(AdverseEventScreen(repo: _orepo()), locale: const Locale('en')));
    await t.pumpAndSettle();
    expect(find.text('Relatar um problema'), findsOneWidget);
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
