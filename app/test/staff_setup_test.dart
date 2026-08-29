import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/features/staff/setup_password_screen.dart';
import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/services/session_store.dart';

/// F4.7/ADR-096 — tela que recebe o link de convite/redefinição de senha da equipe.

/// Armazenamento em memória (o flutter_secure_storage usa platform channels).
class _FakeStore extends SessionStore {
  @override
  Future<String?> accessToken() async => null;
  @override
  Future<String?> refreshToken() async => null;
  @override
  Future<void> saveTokens(String a, String r) async {}
  @override
  Future<void> clear() async {}
  @override
  Future<bool> isAuthenticated() async => false;
}

/// Envolve a tela com localização explícita: sem isto o teste roda no locale do
/// ambiente (en_US no CI) e as buscas por texto em pt-BR falhariam.
///
/// Os delegates `Global*` são obrigatórios: em pt-BR o `DefaultMaterialLocalizations`
/// não se aplica (só cobre `en`), e `TextField`/`Tooltip` exigem `MaterialLocalizations`.
Widget _app(ApiClient api,
        {String token = 'token-de-uso-unico-com-tamanho-ok', Locale locale = const Locale('pt')}) =>
    MaterialApp(
      locale: locale,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: SetupPasswordScreen(api: api, token: token),
    );

ApiClient _api(MockClient mock) => ApiClient(_FakeStore(), client: mock);

/// Monta a tela E espera a localização carregar.
///
/// `_AppLocalizationsDelegate.load` é `async` (não devolve `SynchronousFuture`), então o
/// `Localizations` não renderiza NADA no primeiro quadro: sem este `pump` extra os finders
/// não acham nem o título nem os campos.
Future<void> _montar(WidgetTester tester, Widget app) async {
  await tester.pumpWidget(app);
  await tester.pump();
}

Future<void> _preencher(WidgetTester tester, String senha, String confirmacao,
    {String botao = 'Definir senha'}) async {
  final campos = find.byType(TextField);
  await tester.enterText(campos.at(0), senha);
  await tester.enterText(campos.at(1), confirmacao);
  // A tela rola: garantir que o botão está na viewport antes de tocar (a mensagem de erro
  // empurra o conteúdo para baixo, e um tap fora da tela falharia por hit test).
  await tester.ensureVisible(find.text(botao));
  await tester.pump();
  await tester.tap(find.text(botao));
  // Nada de pumpAndSettle: o botão troca por um CircularProgressIndicator, que anima em
  // repeat — o settle esperaria para sempre. Três quadros bastam para as continuações do
  // POST (mock, sem I/O real) e o setState do resultado.
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 10));
  await tester.pump(const Duration(milliseconds: 10));
}

void main() {
  testWidgets('define a senha e confirma o sucesso', (tester) async {
    late Map<String, dynamic> enviado;
    final mock = MockClient((req) async {
      enviado = jsonDecode(req.body) as Map<String, dynamic>;
      expect(req.url.path.endsWith('/staff/setup-password'), isTrue);
      return http.Response(jsonEncode({'status': 'password_set', 'mfa_enabled': false}), 200);
    });

    await _montar(tester, _app(_api(mock)));
    await _preencher(tester, 'Senha-Forte-123', 'Senha-Forte-123');

    expect(enviado['token'], 'token-de-uso-unico-com-tamanho-ok');
    expect(enviado['new_password'], 'Senha-Forte-123');
    expect(find.text('Senha definida'), findsOneWidget);
    expect(find.byType(TextField), findsNothing); // formulário sai de cena
  });

  testWidgets('conta com MFA avisa que o segundo fator continua valendo', (tester) async {
    final mock = MockClient((_) async =>
        http.Response(jsonEncode({'status': 'password_set', 'mfa_enabled': true}), 200));

    await _montar(tester, _app(_api(mock)));
    await _preencher(tester, 'Senha-Forte-123', 'Senha-Forte-123');

    // Definir senha não desliga o MFA (ADR-094); a tela precisa dizer isso, senão a
    // pessoa conclui que o segundo fator foi reiniciado junto.
    expect(find.textContaining('segundo fator (MFA) continua ativo'), findsOneWidget);
  });

  testWidgets('senha curta nem chega a chamar a API', (tester) async {
    var chamadas = 0;
    final mock = MockClient((_) async {
      chamadas++;
      return http.Response('{}', 200);
    });

    await _montar(tester, _app(_api(mock)));
    await _preencher(tester, 'curta', 'curta');

    // Erro de digitação não pode gastar o token de uso único nem uma tentativa do
    // rate limit do endpoint público.
    expect(chamadas, 0);
    // Texto exato: o `helperText` do campo também fala em 8 caracteres.
    expect(find.text('A senha precisa ter ao menos 8 caracteres.'), findsOneWidget);
  });

  testWidgets('confirmação divergente nem chega a chamar a API', (tester) async {
    var chamadas = 0;
    final mock = MockClient((_) async {
      chamadas++;
      return http.Response('{}', 200);
    });

    await _montar(tester, _app(_api(mock)));
    await _preencher(tester, 'Senha-Forte-123', 'Senha-Forte-124');

    expect(chamadas, 0);
    expect(find.textContaining('não são iguais'), findsOneWidget);
  });

  testWidgets('link inválido mostra o erro do servidor e mantém o formulário', (tester) async {
    final mock = MockClient((_) async => http.Response(
        jsonEncode({
          'title': 'Link inválido',
          'detail': 'Link inválido, expirado ou já utilizado.',
        }),
        401));

    await _montar(tester, _app(_api(mock)));
    await _preencher(tester, 'Senha-Forte-123', 'Senha-Forte-123');

    expect(find.textContaining('Link inválido, expirado ou já utilizado'), findsOneWidget);
    expect(find.text('Senha definida'), findsNothing);
    expect(find.byType(TextField), findsNWidgets(2)); // dá para tentar de novo
  });

  testWidgets('falha de conexão não deixa a tela travada carregando', (tester) async {
    final mock = MockClient((_) async => throw const FalhaDeRede());

    await _montar(tester, _app(_api(mock)));
    await _preencher(tester, 'Senha-Forte-123', 'Senha-Forte-123');

    expect(find.textContaining('Falha de conexão'), findsOneWidget);
    expect(find.text('Definir senha'), findsOneWidget); // botão voltou ao normal
  });

  testWidgets('aparelho em inglês vê a tela em pt-BR (ADR-097)', (tester) async {
    final mock = MockClient((_) async =>
        http.Response(jsonEncode({'status': 'password_set', 'mfa_enabled': false}), 200));

    // O estudo é pt-BR: o app não oferece inglês, nem para a equipe.
    await _montar(tester, _app(_api(mock), locale: const Locale('en')));
    expect(find.text('Definir sua senha'), findsOneWidget);
    expect(find.text('Set your password'), findsNothing);
    await _preencher(tester, 'Senha-Forte-123', 'Senha-Forte-123');
    expect(find.text('Senha definida'), findsOneWidget);
  });

  testWidgets('a senha começa oculta e o olho revela', (tester) async {
    final mock = MockClient((_) async => http.Response('{}', 200));
    await _montar(tester, _app(_api(mock)));

    TextField campo() => tester.widget<TextField>(find.byType(TextField).first);
    expect(campo().obscureText, isTrue);
    await tester.tap(find.byIcon(Icons.visibility_outlined));
    await tester.pump();
    expect(campo().obscureText, isFalse);
  });
}

/// Falha de rede qualquer (não vale importar dart:io num teste que também roda na web).
class FalhaDeRede implements Exception {
  const FalhaDeRede();
}
