import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/features/safety/safety_check_screen.dart';
import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/services/outcomes_repository.dart';
import 'package:sereno/services/session_store.dart';
import 'package:sereno/shared/likert_question.dart';

/// Avaliação de segurança (G5/ADR-102) na tela do participante.
///
/// O que precisa ficar provado: a tela **não mostra escore**, sempre orienta, e quando o
/// servidor aciona o encaminhamento ela diz que a equipe vai entrar em contato e que as
/// sessões ficam pausadas — sem virar diagnóstico na tela.

class _Store extends SessionStore {
  @override
  Future<String?> accessToken() async => 'tok';
  @override
  Future<String?> refreshToken() async => null;
}

const _guidance = 'Se você estiver em sofrimento agora, procure ajuda: CVV 188 (24h, gratuito).';

/// Repositório com API falsa: devolve `referral_opened` conforme o teste pedir.
OutcomesRepository _repo({required bool referral, List<String>? enviados}) {
  final client = MockClient((req) async {
    enviados?.add(req.body);
    return http.Response(
      '{"status":"recorded","referral_opened":$referral,"guidance":"$_guidance"}',
      201,
      headers: const {'content-type': 'application/json; charset=utf-8'},
    );
  });
  return OutcomesRepository(ApiClient(_Store(), client: client));
}

Widget _app(Widget home) => MaterialApp(
      localizationsDelegates: const [AppLocalizations.delegate],
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

const _prompts = [
  'Teve pouco interesse ou pouco prazer em fazer as coisas?',
  'Sentiu-se para baixo, deprimido(a) ou sem esperança?',
  'Teve dificuldade para dormir ou dormiu demais?',
  'Sentiu-se cansado(a) ou com pouca energia?',
  'Teve falta de apetite ou comeu demais?',
  'Sentiu-se mal consigo mesmo(a), um fracasso ou que decepcionou pessoas?',
  'Teve dificuldade de concentração (ler, ver TV, estudar)?',
  'Ficou lento(a) ou, ao contrário, agitado(a) a ponto de outras pessoas notarem?',
  'Teve pensamentos de morte ou de se ferir de alguma forma?',
];

/// Responde os 9 itens. A lista é preguiçosa: cada item precisa ser rolado até a tela
/// antes de existir na árvore.
Future<void> _responderTudo(WidgetTester t, {int valor = 0}) async {
  for (final prompt in _prompts) {
    await t.scrollUntilVisible(find.text(prompt), 120,
        scrollable: find.byType(Scrollable).first);
    final chip = find.descendant(
      of: find.ancestor(of: find.text(prompt), matching: find.byType(LikertQuestion)),
      matching: find.widgetWithText(ChoiceChip, '$valor'),
    );
    await t.ensureVisible(chip.first);
    await t.pump(const Duration(milliseconds: 300));
    await t.tap(chip.first);
    await t.pump();
  }
}

Future<void> _enviar(WidgetTester t) async {
  await t.scrollUntilVisible(find.widgetWithText(FilledButton, 'Enviar'), 120,
      scrollable: find.byType(Scrollable).first);
  await t.tap(find.widgetWithText(FilledButton, 'Enviar'));
  for (var i = 0; i < 4; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  testWidgets('o botão só habilita com todos os itens respondidos', (t) async {
    await t.pumpWidget(_app(SafetyCheckScreen(repo: _repo(referral: false))));
    await t.pump();

    final botao = find.widgetWithText(FilledButton, 'Enviar');
    await t.scrollUntilVisible(botao, 120, scrollable: find.byType(Scrollable).first);
    expect(t.widget<FilledButton>(botao).onPressed, isNull);

    await _responderTudo(t);
    await t.scrollUntilVisible(botao, 120, scrollable: find.byType(Scrollable).first);
    expect(t.widget<FilledButton>(botao).onPressed, isNotNull);
  });

  testWidgets('sem gatilho: agradece e orienta, sem escore na tela', (t) async {
    final enviados = <String>[];
    await t.pumpWidget(_app(SafetyCheckScreen(repo: _repo(referral: false, enviados: enviados))));
    await t.pump();
    await _responderTudo(t);
    await _enviar(t);

    expect(find.text('Registrado'), findsOneWidget);
    expect(find.textContaining('CVV 188'), findsWidgets);
    // Nada de escore/gravidade na tela — o número fica com a equipe.
    expect(find.textContaining('pontos'), findsNothing);
    expect(find.textContaining('moderad'), findsNothing);
    // O cliente manda os itens BRUTOS; quem pontua é o servidor.
    expect(enviados.single, contains('phq9_items'));
    expect(enviados.single, contains('intermediaria'));
  });

  testWidgets('com gatilho: avisa do contato da equipe e da pausa das sessões', (t) async {
    await t.pumpWidget(_app(SafetyCheckScreen(repo: _repo(referral: true))));
    await t.pump();
    await _responderTudo(t, valor: 3);
    await _enviar(t);

    expect(find.text('Vamos falar com você'), findsOneWidget);
    expect(find.textContaining('pausadas'), findsOneWidget);
    expect(find.textContaining('prejuízo'), findsOneWidget);
  });

  testWidgets('o item de risco existe, é direto, e os contatos vêm antes das perguntas',
      (t) async {
    // Sem o item 9 não há rastreio; e eufemismo o tornaria ambíguo.
    await t.pumpWidget(_app(SafetyCheckScreen(repo: _repo(referral: false))));
    await t.pump();
    expect(find.textContaining('CVV 188'), findsOneWidget);   // antes de rolar a lista
    await t.scrollUntilVisible(find.text(_prompts.last), 120,
        scrollable: find.byType(Scrollable).first);
    expect(find.text(_prompts.last), findsOneWidget);
  });
}
