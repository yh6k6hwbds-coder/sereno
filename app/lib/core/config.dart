/// Configuração do cliente. A base da API é fixada em build por --dart-define
/// (ex.: flutter build --dart-define=API_BASE_URL=https://api.sereno.example/v1).
const String _compiledApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000/v1',
);

/// Base da API em uso. Na **web**, aceita um override em runtime pelo parâmetro
/// de URL `?api=<https-url>` — assim o app publicado pode ser apontado para outro
/// backend (ex.: um túnel novo) **sem recompilar**: basta abrir o link com o
/// parâmetro. Só aceita `https` (evita mixed-content e aponta apenas para destinos
/// seguros). No mobile/desktop, `Uri.base` não traz o parâmetro e cai no valor de
/// build. Ver docs/rodar-por-tunel.md.
String get apiBaseUrl {
  final override = Uri.base.queryParameters['api'];
  if (override != null && override.startsWith('https://')) {
    return override.endsWith('/')
        ? override.substring(0, override.length - 1)
        : override;
  }
  return _compiledApiBaseUrl;
}

/// Token de definição de senha de staff vindo do link do e-mail (`?token=…`), só na **web**.
///
/// O convite/redefinição (ADR-094) manda um link; esta é a ponta que o recebe (ADR-096). No
/// mobile `Uri.base` não traz query, então devolve `null` e o app abre normalmente para o
/// participante — a tela de staff nunca aparece para quem não veio pelo link.
///
/// Não valida o formato além do tamanho: quem julga o token é o servidor, com resposta
/// genérica. Filtrar aqui só serve para não abrir a tela com lixo de URL.
String? get staffSetupToken {
  final t = Uri.base.queryParameters['token'];
  if (t == null || t.length < 20 || t.length > 200) return null;
  return t;
}

/// Versão vigente do TCLE — deve casar com `TCLE_CURRENT` no backend (divergente → 409).
/// O sufixo `-rascunho` marca texto que ainda NÃO passou pelo CEP (`docs/tcle-rascunho.md`);
/// ao sair o parecer, vira `1.0.0` aqui, no backend e no resumo de `app_localizations.dart`.
const String tcleVersion = '0.1.0-rascunho';

/// Ganho digital da reprodução (G3 — "intensidade calibrada com limite imposto por software").
///
/// O aplicativo **não oferece controle de volume**: toca sempre com este ganho, declara-o ao
/// iniciar a sessão e o servidor recusa acima do teto configurado (`AUDIO_MAX_GAIN`). Assim o
/// participante não tem como ultrapassar o limite do estudo pelo app.
///
/// O valor absoluto em dB(A) **não** é decidido aqui: depende do transdutor e do aparelho, e
/// sai da calibração em acoplador de orelha (etapa (i) do protocolo). É por isso que o ganho é
/// fixado em build e não escolhido em código: quando a calibração disser qual valor
/// corresponde a 60 dB(A), troca-se o build, não o programa.
///
/// Em milésimos porque `double.fromEnvironment` não existe em Dart — só `int`, `bool` e
/// `String`. Ex.: `flutter build apk --dart-define=AUDIO_GAIN_MILLI=650` → ganho 0,65.
const double audioGain =
    int.fromEnvironment('AUDIO_GAIN_MILLI', defaultValue: 800) / 1000.0;

/// Duração padrão da sessão em segundos (metadado neutro — igual nos dois braços).
/// Futuro: receber do protocolo via campo neutro na resposta de início.
const int sessionDurationSeconds = 1200; // 20 min
