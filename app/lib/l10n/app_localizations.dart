import 'package:flutter/widgets.dart';

/// Internacionalização (E5/ADR-070) — delegate MANUAL, sem code-gen.
///
/// Decisão: um mapa de strings por locale, resolvido por um `LocalizationsDelegate`
/// próprio, em vez do pipeline ARB/intl com geração. Motivo: é mínimo, totalmente
/// testável e não depende de um passo de build (o ambiente de dev não tem SDK Flutter;
/// a validação é o CI). Migrar para ARB/intl é evolução futura, sem quebrar as telas
/// (elas só consomem `AppLocalizations.of(context)`).
///
/// pt-BR é o idioma do piloto (padrão/fallback); `en` prova a internacionalização.
/// As strings pt-BR são idênticas às originais das telas — assim widgets testados sem
/// localização na árvore seguem passando pelo fallback pt-BR.
class AppLocalizations {
  final Locale locale;
  const AppLocalizations(this.locale);

  /// Tolerante: sem localização na árvore (ex.: um widget testado isolado), cai no
  /// pt-BR — o idioma padrão do piloto. Nunca lança.
  static AppLocalizations of(BuildContext context) =>
      Localizations.of<AppLocalizations>(context, AppLocalizations) ??
      const AppLocalizations(Locale('pt'));

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  static const List<Locale> supportedLocales = [Locale('pt'), Locale('en')];

  static const Map<String, Map<String, String>> _values = {
    'pt': {
      // Comuns
      'connectionError': 'Falha de conexão. Tente novamente.',
      // Home
      'greeting': 'Boa noite,',
      'ready': 'tudo pronto',
      'startSession': 'Iniciar sessão',
      'sessionMeta': '~20 min · use fones',
      'records': 'Registros',
      'baseline': 'Linha de base',
      'sleepDiary': 'Diário de sono',
      'followup': 'Seguimento',
      'reportProblem': 'Relatar um problema',
      'logout': 'Sair',
      'disclaimer':
          'Ferramenta complementar. Não substitui avaliação ou tratamento profissional.',
      // Login/OTP
      'otpRequestPrompt': 'Entre com o seu código de estudo para receber um código de acesso.',
      'otpVerifyPrompt': 'Digite o código de 6 dígitos enviado ao seu e-mail.',
      'otpStudyCodeLabel': 'Código de estudo',
      'otpCodeLabel': 'Código',
      'otpSendCode': 'Enviar código',
      'otpEnter': 'Entrar',
      'otpBack': 'Voltar',
      'otpSent': 'Se o código de estudo existir, enviamos um código ao seu e-mail.',
      // Preparar sessão (fones)
      'prepSession': 'Preparar sessão',
      'useStereoHeadphones': 'Use fones estéreo',
      'headphoneBody': 'As sessões usam áudio em dois canais. Conecte fones com fio, ajuste um '
          'volume confortável e prefira um ambiente tranquilo.',
      'headphonesConnected': 'Meus fones estéreo estão conectados',
      // Consentimento
      'consentTitle': 'Termo de Consentimento',
      'consentReadSummary': 'Leia o resumo em linguagem simples:',
      'consentRead': 'Li e entendi as informações',
      'consentAgree': 'Concordo em participar',
      'consentLgpd': 'Autorizo o uso dos meus dados conforme a LGPD',
      'consentContinue': 'Concordar e continuar',
      'consentWithdraw': 'Você pode retirar o consentimento quando quiser.',
      // Comuns (ações)
      'back': 'Voltar',
      'send': 'Enviar',
      'yes': 'Sim',
      'no': 'Não',
      // Player de sessão
      'playerLoadError': 'Não foi possível carregar o áudio. Verifique a conexão e tente novamente.',
      'playerPreparing': 'Preparando o áudio…',
      'playerPaused': 'Pausado',
      'playerInSession': 'Em sessão',
      'playerDoneTitle': 'Sessão concluída',
      'playerDoneAuto': 'Sessão finalizada. Como foi para você?',
      'playerDoneManual': 'Sessão encerrada. Registramos o tempo efetivo.',
      'playerAnswerQuick': 'Responder rápido',
      'playerBackHome': 'Voltar ao início',
      'playerBreathe': 'Feche os olhos e respire com calma.',
      // Pós-sessão
      'surveyTitle': 'Como foi a sessão',
      'surveyFeeling': 'Como você se sente agora? (0 muito mal – 4 muito bem)',
      'surveyRelaxation': 'Quão relaxado(a) você está? (0 nada – 4 muito)',
      'surveySleptBetter': 'Se foi à noite, acha que dormiu melhor? (opcional)',
      'surveyLiked': 'O quanto gostou desta sessão? (0 nada – 4 muito)',
      'surveyIntensity': 'Como percebeu a intensidade do áudio? (0 fraca – 4 forte)',
      'surveyWouldRepeat': 'Repetiria esta sessão?',
      'surveyThanks': 'Obrigado pelo retorno!',
      'surveyAlready': 'Você já respondeu esta sessão.',
      // B2 linha de base
      'baselineTitle': 'Como você tem estado',
      'baselineIntro': 'Algumas perguntas sobre as últimas semanas. Não há respostas certas ou '
          'erradas — responda com sinceridade.',
      'gad7GroupTitle': 'Nas últimas 2 semanas…',
      'baselineSubmit': 'Enviar respostas',
      'baselineThanks': 'Respostas registradas. Obrigado!',
      'baselineAlready': 'Sua linha de base já foi registrada.',
      // B4 diário de sono
      'diaryTitle': 'Diário de sono',
      'diaryAwakenings': 'Quantas vezes acordou',
      'diaryDuration': 'Horas dormidas',
      'diaryQuality': 'Como avalia a qualidade do sono? (0 muito ruim – 4 muito boa)',
      'diarySubmit': 'Registrar',
      'diaryThanks': 'Diário registrado. Bom descanso!',
      'diaryAlready': 'O diário de hoje já foi registrado.',
      // B5 seguimento
      'susGroupTitle': 'Sobre o app (1 discordo totalmente – 5 concordo totalmente)',
      'blindingQuestion': 'O estudo tem dois grupos de áudio (A e B). Qual você acha que recebeu?',
      'groupA': 'Grupo A',
      'groupB': 'Grupo B',
      'dontKnow': 'Não sei',
      'followupSubmit': 'Enviar seguimento',
      'followupThanks': 'Seguimento registrado. Obrigado!',
      'followupAlready': 'Seu seguimento já foi registrado.',
      // B6 evento adverso
      'adverseIntro': 'Conte o que aconteceu. Seu bem-estar vem primeiro.',
      'adverseWhat': 'O que aconteceu?',
      'severity': 'Gravidade',
      'sevMild': 'Leve',
      'sevModerate': 'Moderado',
      'sevSevere': 'Grave',
      'adverseAction': 'O que você fez? (opcional)',
      'adverseUrgent': 'Procure atendimento o quanto antes. Em emergência, ligue 192. '
          'Se houver sofrimento emocional, o CVV atende no 188.',
      'adverseSubmit': 'Enviar relato',
      'adverseThanks': 'Relato registrado. Cuide-se.',
      // PSQI (compartilhado B2/B5)
      'minutesToFallAsleep': 'Minutos para adormecer',
      'psqiHeader': 'Seu sono no último mês',
      'psqiHoursSlept': 'Horas realmente dormidas',
      'psqiHoursInBed': 'Horas na cama',
      'psqiDisturbHeader': 'Com que frequência seu sono foi perturbado por…',
    },
    'en': {
      'connectionError': 'Connection failed. Please try again.',
      'greeting': 'Good evening,',
      'ready': "you're all set",
      'startSession': 'Start session',
      'sessionMeta': '~20 min · use headphones',
      'records': 'Records',
      'baseline': 'Baseline',
      'sleepDiary': 'Sleep diary',
      'followup': 'Follow-up',
      'reportProblem': 'Report a problem',
      'logout': 'Log out',
      'disclaimer':
          'Complementary tool. It does not replace professional evaluation or treatment.',
      'otpRequestPrompt': 'Enter your study code to receive an access code.',
      'otpVerifyPrompt': 'Enter the 6-digit code sent to your e-mail.',
      'otpStudyCodeLabel': 'Study code',
      'otpCodeLabel': 'Code',
      'otpSendCode': 'Send code',
      'otpEnter': 'Enter',
      'otpBack': 'Back',
      'otpSent': 'If the study code exists, we sent a code to your e-mail.',
      'prepSession': 'Prepare session',
      'useStereoHeadphones': 'Use stereo headphones',
      'headphoneBody': 'Sessions use two-channel audio. Connect wired headphones, set a '
          'comfortable volume and prefer a quiet environment.',
      'headphonesConnected': 'My stereo headphones are connected',
      'consentTitle': 'Consent Form',
      'consentReadSummary': 'Read the plain-language summary:',
      'consentRead': 'I have read and understood the information',
      'consentAgree': 'I agree to participate',
      'consentLgpd': 'I authorize the use of my data under the LGPD',
      'consentContinue': 'Agree and continue',
      'consentWithdraw': 'You can withdraw your consent at any time.',
      'back': 'Back',
      'send': 'Send',
      'yes': 'Yes',
      'no': 'No',
      'playerLoadError': 'Could not load the audio. Check your connection and try again.',
      'playerPreparing': 'Preparing the audio…',
      'playerPaused': 'Paused',
      'playerInSession': 'In session',
      'playerDoneTitle': 'Session complete',
      'playerDoneAuto': 'Session finished. How was it for you?',
      'playerDoneManual': 'Session ended. We recorded the effective time.',
      'playerAnswerQuick': 'Quick answer',
      'playerBackHome': 'Back to start',
      'playerBreathe': 'Close your eyes and breathe calmly.',
      'surveyTitle': 'How was the session',
      'surveyFeeling': 'How do you feel now? (0 very bad – 4 very good)',
      'surveyRelaxation': 'How relaxed are you? (0 not at all – 4 very)',
      'surveySleptBetter': 'If it was at night, do you think you slept better? (optional)',
      'surveyLiked': 'How much did you like this session? (0 not at all – 4 very)',
      'surveyIntensity': 'How did you perceive the audio intensity? (0 weak – 4 strong)',
      'surveyWouldRepeat': 'Would you repeat this session?',
      'surveyThanks': 'Thanks for your feedback!',
      'surveyAlready': 'You have already answered this session.',
      'baselineTitle': 'How you have been',
      'baselineIntro': 'A few questions about the last weeks. There are no right or wrong answers — '
          'answer honestly.',
      'gad7GroupTitle': 'In the last 2 weeks…',
      'baselineSubmit': 'Submit answers',
      'baselineThanks': 'Answers recorded. Thank you!',
      'baselineAlready': 'Your baseline has already been recorded.',
      'diaryTitle': 'Sleep diary',
      'diaryAwakenings': 'How many times you woke up',
      'diaryDuration': 'Hours slept',
      'diaryQuality': 'How do you rate your sleep quality? (0 very poor – 4 very good)',
      'diarySubmit': 'Record',
      'diaryThanks': 'Diary recorded. Rest well!',
      'diaryAlready': "Today's diary has already been recorded.",
      'susGroupTitle': 'About the app (1 strongly disagree – 5 strongly agree)',
      'blindingQuestion': 'The study has two audio groups (A and B). Which do you think you received?',
      'groupA': 'Group A',
      'groupB': 'Group B',
      'dontKnow': "I don't know",
      'followupSubmit': 'Submit follow-up',
      'followupThanks': 'Follow-up recorded. Thank you!',
      'followupAlready': 'Your follow-up has already been recorded.',
      'adverseIntro': 'Tell us what happened. Your well-being comes first.',
      'adverseWhat': 'What happened?',
      'severity': 'Severity',
      'sevMild': 'Mild',
      'sevModerate': 'Moderate',
      'sevSevere': 'Severe',
      'adverseAction': 'What did you do? (optional)',
      'adverseUrgent': 'Seek care as soon as possible. In an emergency, call 192. '
          'If there is emotional distress, CVV is available at 188.',
      'adverseSubmit': 'Submit report',
      'adverseThanks': 'Report recorded. Take care.',
      'minutesToFallAsleep': 'Minutes to fall asleep',
      'psqiHeader': 'Your sleep in the last month',
      'psqiHoursSlept': 'Hours actually slept',
      'psqiHoursInBed': 'Hours in bed',
      'psqiDisturbHeader': 'How often was your sleep disturbed by…',
    },
  };

  static const Map<String, List<String>> _consentSummary = {
    'pt': [
      'O estudo avalia um app de sessões de áudio (frequências binaurais) para relaxamento e sono.',
      'Você fará questionários e sessões de ~20 min, com fones, por 4 semanas.',
      'Os riscos são mínimos; você pode interromper e registrar qualquer desconforto.',
      'Seus dados são tratados de forma confidencial e pseudonimizada (LGPD).',
      'A participação é voluntária; você pode sair a qualquer momento, sem prejuízo.',
    ],
    'en': [
      'The study evaluates an app of audio sessions (binaural beats) for relaxation and sleep.',
      'You will complete questionnaires and ~20-min sessions, with headphones, over 4 weeks.',
      'Risks are minimal; you may stop and report any discomfort.',
      'Your data is handled confidentially and pseudonymized (LGPD).',
      'Participation is voluntary; you may leave at any time, without penalty.',
    ],
  };

  static const Map<String, List<String>> _gad7 = {
    'pt': [
      'Sentiu-se nervoso(a), ansioso(a) ou muito tenso(a)?',
      'Não conseguiu parar ou controlar as preocupações?',
      'Preocupou-se demais com coisas diferentes?',
      'Teve dificuldade para relaxar?',
      'Ficou tão inquieto(a) que era difícil ficar parado(a)?',
      'Irritou-se ou aborreceu-se com facilidade?',
      'Sentiu medo, como se algo ruim fosse acontecer?',
    ],
    'en': [
      'Felt nervous, anxious or very tense?',
      "Couldn't stop or control worrying?",
      'Worried too much about different things?',
      'Had trouble relaxing?',
      'Was so restless it was hard to sit still?',
      'Became easily annoyed or irritable?',
      'Felt afraid, as if something bad might happen?',
    ],
  };

  static const Map<String, List<String>> _sus = {
    'pt': [
      'Gostaria de usar este app com frequência.',
      'Achei o app desnecessariamente complexo.',
      'Achei o app fácil de usar.',
      'Precisaria de ajuda para conseguir usar o app.',
      'As funções do app são bem integradas.',
      'Há inconsistências demais no app.',
      'A maioria aprenderia a usar o app rapidamente.',
      'Achei o app trabalhoso de usar.',
      'Senti-me confiante ao usar o app.',
      'Precisei aprender muita coisa antes de usar.',
    ],
    'en': [
      'I would like to use this app frequently.',
      'I found the app unnecessarily complex.',
      'I found the app easy to use.',
      'I would need help to be able to use the app.',
      'The app functions are well integrated.',
      'There is too much inconsistency in the app.',
      'Most people would learn to use the app quickly.',
      'I found the app cumbersome to use.',
      'I felt confident using the app.',
      'I needed to learn a lot before I could use it.',
    ],
  };

  static const Map<String, List<String>> _psqiDisturb = {
    'pt': [
      'acordou no meio da noite/de manhã cedo', 'precisou ir ao banheiro',
      'não conseguiu respirar bem', 'tossiu ou roncou alto', 'sentiu muito frio',
      'sentiu muito calor', 'teve sonhos ruins', 'sentiu dores', 'outro motivo',
    ],
    'en': [
      'woke in the middle of the night/early morning', 'needed to use the bathroom',
      'could not breathe well', 'coughed or snored loudly', 'felt too cold',
      'felt too hot', 'had bad dreams', 'felt pain', 'another reason',
    ],
  };

  static const Map<String, Map<String, String>> _psqiScale = {
    'pt': {
      'subjective_quality': 'No último mês, como avalia sua qualidade de sono? (0 muito boa – 3 muito ruim)',
      'cannot_sleep_30min_freq': 'Com que frequência levou mais de 30 min para adormecer?',
      'medication_freq': 'Com que frequência usou medicação para dormir?',
      'stay_awake_freq': 'Com que frequência teve dificuldade de ficar acordado durante o dia?',
      'enthusiasm_problem': 'Quanta dificuldade teve para manter o ânimo nas atividades?',
    },
    'en': {
      'subjective_quality': 'In the last month, how do you rate your sleep quality? (0 very good – 3 very poor)',
      'cannot_sleep_30min_freq': 'How often did it take more than 30 min to fall asleep?',
      'medication_freq': 'How often did you use sleep medication?',
      'stay_awake_freq': 'How often did you have trouble staying awake during the day?',
      'enthusiasm_problem': 'How much trouble did you have keeping up enthusiasm for activities?',
    },
  };

  String _t(String key) =>
      _values[locale.languageCode]?[key] ?? _values['pt']![key] ?? key;

  // Comuns
  String get connectionError => _t('connectionError');
  // Home
  String get greeting => _t('greeting');
  String get ready => _t('ready');
  String get startSession => _t('startSession');
  String get sessionMeta => _t('sessionMeta');
  String get records => _t('records');
  String get baseline => _t('baseline');
  String get sleepDiary => _t('sleepDiary');
  String get followup => _t('followup');
  String get reportProblem => _t('reportProblem');
  String get logout => _t('logout');
  String get disclaimer => _t('disclaimer');
  // Login/OTP
  String get otpRequestPrompt => _t('otpRequestPrompt');
  String get otpVerifyPrompt => _t('otpVerifyPrompt');
  String get otpStudyCodeLabel => _t('otpStudyCodeLabel');
  String get otpCodeLabel => _t('otpCodeLabel');
  String get otpSendCode => _t('otpSendCode');
  String get otpEnter => _t('otpEnter');
  String get otpBack => _t('otpBack');
  String get otpSent => _t('otpSent');
  // Preparar sessão
  String get prepSession => _t('prepSession');
  String get useStereoHeadphones => _t('useStereoHeadphones');
  String get headphoneBody => _t('headphoneBody');
  String get headphonesConnected => _t('headphonesConnected');
  // Consentimento
  String get consentTitle => _t('consentTitle');
  String get consentReadSummary => _t('consentReadSummary');
  String get consentRead => _t('consentRead');
  String get consentAgree => _t('consentAgree');
  String get consentLgpd => _t('consentLgpd');
  String get consentContinue => _t('consentContinue');
  String get consentWithdraw => _t('consentWithdraw');
  List<String> get consentSummary =>
      _consentSummary[locale.languageCode] ?? _consentSummary['pt']!;
  // Comuns (ações)
  String get back => _t('back');
  String get send => _t('send');
  String get yes => _t('yes');
  String get no => _t('no');
  // Player de sessão
  String get playerLoadError => _t('playerLoadError');
  String get playerPreparing => _t('playerPreparing');
  String get playerPaused => _t('playerPaused');
  String get playerInSession => _t('playerInSession');
  String get playerDoneTitle => _t('playerDoneTitle');
  String get playerDoneAuto => _t('playerDoneAuto');
  String get playerDoneManual => _t('playerDoneManual');
  String get playerAnswerQuick => _t('playerAnswerQuick');
  String get playerBackHome => _t('playerBackHome');
  String get playerBreathe => _t('playerBreathe');
  // Pós-sessão
  String get surveyTitle => _t('surveyTitle');
  String get surveyFeeling => _t('surveyFeeling');
  String get surveyRelaxation => _t('surveyRelaxation');
  String get surveySleptBetter => _t('surveySleptBetter');
  String get surveyLiked => _t('surveyLiked');
  String get surveyIntensity => _t('surveyIntensity');
  String get surveyWouldRepeat => _t('surveyWouldRepeat');
  String get surveyThanks => _t('surveyThanks');
  String get surveyAlready => _t('surveyAlready');
  // B2 linha de base
  String get baselineTitle => _t('baselineTitle');
  String get baselineIntro => _t('baselineIntro');
  String get gad7GroupTitle => _t('gad7GroupTitle');
  String get baselineSubmit => _t('baselineSubmit');
  String get baselineThanks => _t('baselineThanks');
  String get baselineAlready => _t('baselineAlready');
  List<String> get gad7Prompts => _gad7[locale.languageCode] ?? _gad7['pt']!;
  // B4 diário
  String get diaryTitle => _t('diaryTitle');
  String get diaryAwakenings => _t('diaryAwakenings');
  String get diaryDuration => _t('diaryDuration');
  String get diaryQuality => _t('diaryQuality');
  String get diarySubmit => _t('diarySubmit');
  String get diaryThanks => _t('diaryThanks');
  String get diaryAlready => _t('diaryAlready');
  String diaryToday(String date) =>
      locale.languageCode == 'en' ? "Today's entry ($date)." : 'Registro de hoje ($date).';
  // B5 seguimento
  String get susGroupTitle => _t('susGroupTitle');
  String get blindingQuestion => _t('blindingQuestion');
  String get groupA => _t('groupA');
  String get groupB => _t('groupB');
  String get dontKnow => _t('dontKnow');
  String get followupSubmit => _t('followupSubmit');
  String get followupThanks => _t('followupThanks');
  String get followupAlready => _t('followupAlready');
  List<String> get susPrompts => _sus[locale.languageCode] ?? _sus['pt']!;
  // B6 evento adverso
  String get adverseIntro => _t('adverseIntro');
  String get adverseWhat => _t('adverseWhat');
  String get severity => _t('severity');
  String get sevMild => _t('sevMild');
  String get sevModerate => _t('sevModerate');
  String get sevSevere => _t('sevSevere');
  String get adverseAction => _t('adverseAction');
  String get adverseUrgent => _t('adverseUrgent');
  String get adverseSubmit => _t('adverseSubmit');
  String get adverseThanks => _t('adverseThanks');
  // PSQI
  String get minutesToFallAsleep => _t('minutesToFallAsleep');
  String get psqiHeader => _t('psqiHeader');
  String get psqiHoursSlept => _t('psqiHoursSlept');
  String get psqiHoursInBed => _t('psqiHoursInBed');
  String get psqiDisturbHeader => _t('psqiDisturbHeader');
  List<String> get psqiDisturbPrompts =>
      _psqiDisturb[locale.languageCode] ?? _psqiDisturb['pt']!;
  Map<String, String> get psqiScalePrompts =>
      _psqiScale[locale.languageCode] ?? _psqiScale['pt']!;
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) =>
      AppLocalizations.supportedLocales.any((l) => l.languageCode == locale.languageCode);

  @override
  Future<AppLocalizations> load(Locale locale) async => AppLocalizations(locale);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}
