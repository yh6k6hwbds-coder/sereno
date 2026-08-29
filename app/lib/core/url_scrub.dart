// Remoção de um parâmetro da barra de endereço, sem recarregar a página.
//
// Existe por causa do token de definição de senha (ADR-094/096): ele equivale à senha
// durante sua janela de validade, e deixá-lo na URL o expõe ao histórico do navegador e ao
// cabeçalho `Referer` de qualquer requisição que a página faça.
//
// **Por que não `SystemNavigator.routeInformationUpdated`:** foi a primeira tentativa e ela
// NÃO funciona aqui. Com a estratégia de URL padrão do Flutter web (hash), aquela chamada
// escreve a rota no FRAGMENTO — o resultado observado foi `?...&token=abc#/sereno/?...`, com
// o token intacto e um `#` a mais. É preciso mexer no `history` do navegador.
//
// Import condicional: na VM/mobile entra o stub (no-op), na web a implementação real.
export 'url_scrub_stub.dart' if (dart.library.html) 'url_scrub_web.dart';
