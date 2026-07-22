import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/core/config.dart';
import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/features/consent/tcle_full_text_screen.dart';

/// Texto integral do TCLE na tela de consentimento.
///
/// O que estes testes protegem: o resumo de 7 tópicos **não** é o termo. Se o texto
/// integral deixar de aparecer (asset não empacotado, parser quebrado), o consentimento
/// deixa de ser informado — e isso falharia em silêncio, porque a tela continuaria abrindo.

/// Texto de exemplo para os testes de RENDERIZAÇÃO. O asset real é verificado à parte
/// (`o asset empacotado contém o termo INTEGRAL`): dentro de `pumpAndSettle` o tempo é
/// falso e a leitura real do bundle não completaria — a tela ficaria no indicador de carga.
const _amostra = '# comentario\n'
    'H|Termo de Consentimento Livre e Esclarecido\n'
    'P|Você está sendo convidado(a) a participar de um estudo.\n'
    'B|Um item da lista\n'
    '!|Este é o ponto mais importante deste documento.\n';

Future<String> _fake() async => _amostra;

/// Texto longo o bastante para exigir rolagem — o termo real tem ~107 blocos.
String _amostraLonga() {
  final b = StringBuffer('H|Termo de Consentimento Livre e Esclarecido\n');
  for (var i = 0; i < 60; i++) {
    b.write('P|Parágrafo número $i do termo.\n');
  }
  return b.toString();
}

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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('parser do asset', () {
    test('classifica os blocos por prefixo e ignora comentários', () {
      final blocks = TcleFullTextScreen.parse(
          '# comentario do gerador\n'
          'H|1. Convite\n'
          'P|Texto corrido.\n'
          'B|Um item\n'
          '!|Um destaque\n'
          '\n');
      expect(blocks.map((b) => b.kind).toList(), ['H', 'P', 'B', '!']);
      expect(blocks.first.text, '1. Convite');
    });

    test('preserva "|" dentro do texto (só o primeiro separa)', () {
      final blocks = TcleFullTextScreen.parse('P|a | b\n');
      expect(blocks.single.text, 'a | b');
    });

    test('descarta linha sem prefixo em vez de exibi-la crua', () {
      expect(TcleFullTextScreen.parse('sem prefixo\n'), isEmpty);
    });
  });

  testWidgets('o asset empacotado contém o termo INTEGRAL', (t) async {
    // Conteúdo, não renderização: o ListView é preguiçoso e só cria os blocos visíveis,
    // então procurar §8 na árvore de widgets falharia por rolagem, não por ausência.
    final raw = await rootBundle.loadString(TcleFullTextScreen.assetPath);
    final blocks = TcleFullTextScreen.parse(raw);
    final texto = blocks.map((b) => b.text).join('\n');

    // As 16 seções do termo (o resumo da tela anterior tem 7 tópicos — não é o termo).
    final secoes = blocks.where((b) => b.kind == 'H').length;
    expect(secoes, greaterThanOrEqualTo(16),
        reason: 'faltam seções do termo no asset — rode scripts/sync_tcle.py');

    // Trechos que carregam o peso ético: se algum sumir, o termo deixou de dizer o essencial.
    expect(texto, contains('Convite'));
    expect(texto, contains('NÃO é tratamento'));
    expect(texto, contains('CVV'));                        // canal de ajuda
    expect(texto, contains('limitadas e inconsistentes')); // postura científica
    expect(texto, contains('não afetará'));                // recusa sem prejuízo (R-09)
    expect(texto, contains('pseudonimizada'));             // retenção pós-desistência (§13)
  });

  testWidgets('abre no topo do termo', (t) async {
    await t.pumpWidget(_app(TcleFullTextScreen(loadText: _fake)));
    await t.pumpAndSettle();
    expect(find.textContaining('Termo de Consentimento'), findsWidgets);
  });

  testWidgets('avisa que é rascunho e mostra a versão', (t) async {
    await t.pumpWidget(_app(TcleFullTextScreen(loadText: _fake)));
    await t.pumpAndSettle();

    // Enquanto a versão carregar `-rascunho`, ninguém pode ler a tela como termo vigente.
    expect(tcleVersion.contains('rascunho'), isTrue,
        reason: 'se a versão saiu de rascunho, o aviso desta tela deve ser reavaliado');
    expect(find.textContaining('RASCUNHO'), findsOneWidget);
    expect(find.textContaining(tcleVersion), findsOneWidget);
  });

  testWidgets('em inglês, avisa que o termo oficial é em português', (t) async {
    await t.pumpWidget(_app(TcleFullTextScreen(loadText: _fake), locale: const Locale('en')));
    await t.pumpAndSettle();

    expect(find.text('Full consent form'), findsOneWidget);
    expect(find.textContaining('Portuguese'), findsOneWidget);
    // O corpo do termo segue em pt-BR (é o texto que vai ao CEP).
    expect(find.textContaining('Termo de Consentimento'), findsWidgets);
  });

  testWidgets('o termo é rolável até o fim (não pode ficar cortado)', (t) async {
    await t.pumpWidget(_app(TcleFullTextScreen(loadText: () async => _amostraLonga())));
    await t.pumpAndSettle();

    // O último bloco começa fora da tela: se não desse para chegar nele, o participante
    // aceitaria um termo que não teve como ler inteiro.
    const ultimo = 'Parágrafo número 59 do termo.';
    expect(find.text(ultimo), findsNothing);
    await t.scrollUntilVisible(find.text(ultimo), 300);
    expect(find.text(ultimo), findsOneWidget);
  });
}
