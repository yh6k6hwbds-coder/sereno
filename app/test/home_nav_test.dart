import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/features/home/home_screen.dart';

void main() {
  testWidgets('Home lista os registros e navega para a linha de base', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // As telas de registro (B2/B4/B5/B6) estão acessíveis a partir da Home.
    expect(find.text('Iniciar sessão'), findsOneWidget);
    expect(find.text('Linha de base'), findsOneWidget);
    expect(find.text('Diário de sono'), findsOneWidget);
    expect(find.text('Seguimento'), findsOneWidget);

    // Os últimos atalhos ficam abaixo da dobra na tela do teste: o `ListView` só constrói
    // o que está visível, então é preciso rolar até eles (e o aviso de escopo, fixo no
    // rodapé, não some ao rolar — é o ponto de ele estar fora da lista).
    await tester.dragUntilVisible(find.text('Relatar um problema'),
        find.byType(ListView), const Offset(0, -80));
    expect(find.text('Como você está'), findsOneWidget); // avaliação de segurança (ADR-102)
    expect(find.text('Relatar um problema'), findsOneWidget);
    expect(find.textContaining('Não substitui'), findsOneWidget);

    await tester.dragUntilVisible(
        find.text('Linha de base'), find.byType(ListView), const Offset(0, 80));
    await tester.pumpAndSettle(); // deixa a rolagem assentar antes do toque
    await tester.tap(find.text('Linha de base'));
    await tester.pumpAndSettle();
    expect(find.text('Como você tem estado'), findsOneWidget); // AppBar da BaselineScreen
  });
}
