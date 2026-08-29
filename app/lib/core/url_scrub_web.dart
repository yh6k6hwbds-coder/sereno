// ignore_for_file: deprecated_member_use
import 'dart:html' as html;

/// Remove `name` da query da barra de endereço, **sem recarregar** e sem criar entrada nova
/// no histórico (`replaceState`) — a entrada anterior é que carregava o segredo.
///
/// Não invalida o token: quem o queima é o consumo no servidor (uso único). Isto encurta o
/// rastro — histórico e `Referer` deixam de carregá-lo.
///
/// `dart:html` (legado) em vez de `package:web`: evita acrescentar dependência ao `pubspec`
/// por duas linhas. O build web deste projeto é JS, não wasm, onde ele segue funcionando.
/// Migrar para `package:web` é pré-requisito se um dia o alvo virar wasm.
void scrubQueryParam(String name) {
  try {
    final atual = Uri.parse(html.window.location.href);
    if (!atual.queryParameters.containsKey(name)) return;
    final limpa = atual.replace(
      queryParameters: Map<String, String>.from(atual.queryParameters)..remove(name),
    );
    // `queryParameters: {}` vazio ainda deixaria um `?` pendurado; normaliza tirando-o.
    final destino = limpa.hasQuery ? limpa.toString() : limpa.toString().replaceAll('?', '');
    html.window.history.replaceState(null, '', destino);
  } catch (_) {
    // Nunca derrubar a tela por causa da barra de endereço: sem a limpeza a pessoa ainda
    // consegue definir a senha, que é o que ela veio fazer.
  }
}
