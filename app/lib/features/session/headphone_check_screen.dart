import 'dart:math';

import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/audio_player_port.dart';
import '../../services/just_audio_player.dart';
import '../../services/session_repository.dart';
import '../../shared/disclaimer_banner.dart';
import 'headphone_test_tone.dart';
import 'session_player_screen.dart';

/// Verificação DICÓTICA de fones (G4) — pré-condição da sessão.
///
/// O protocolo exige que, antes de cada sessão, o participante identifique **em qual orelha**
/// soou um sinal de teste, e que a sessão não seja liberada em caso de falha. Antes disto a
/// tela pedia apenas uma confirmação ("meus fones estão conectados"): declaração, não
/// verificação — e fone em uma orelha só, ou saída em mono, passaria batido, justamente o que
/// impede o fenômeno binaural de existir.
///
/// São [kRounds] rodadas com a orelha sorteada a cada vez. Errar **reinicia** o teste (novo
/// sorteio): quem chuta acerta uma rodada em duas, mas o teste inteiro só em quatro. O que se
/// envia ao servidor descreve a tentativa aceita — e quantas tentativas foram necessárias.
///
/// O sinal de teste é idêntico nos dois braços e não carrega condição (ver [HeadphoneTestTone]).
class HeadphoneCheckScreen extends StatefulWidget {
  final SessionRepository repo;
  final String protocolHandle;
  final AudioPlayerPort? player;   // injetável nos testes; produção usa just_audio
  final Random? random;            // injetável nos testes (sorteio determinístico)

  /// Rodadas exigidas. O servidor recusa menos que 2 (acerto por acaso alto demais).
  static const int kRounds = 2;

  // Handle NEUTRO quanto ao braço. O protocolo do piloto fixa a faixa delta (batimento de
  // 3 Hz sobre portadora de 250 Hz) e não há personalização nesta fase — por isso é
  // constante, e não escolha do participante nem do recomendador (ADR-100).
  const HeadphoneCheckScreen({
    super.key,
    required this.repo,
    this.protocolHandle = 'delta',
    this.player,
    this.random,
  });

  @override
  State<HeadphoneCheckScreen> createState() => _HeadphoneCheckScreenState();
}

class _HeadphoneCheckScreenState extends State<HeadphoneCheckScreen> {
  late final AudioPlayerPort _player = widget.player ?? JustAudioPlayer();
  late final Random _rng = widget.random ?? Random();

  final List<bool> _drawnLeft = [];   // orelhas sorteadas na tentativa em curso
  int _round = 0;                     // rodadas já acertadas nesta tentativa
  int _attempts = 1;                  // tentativas até aqui (reinicia ao errar)
  bool _playing = false;              // sinal tocando/tocado, aguardando resposta
  bool _answered = false;             // já respondeu a rodada atual
  bool _failed = false;               // errou: precisa refazer
  bool _loading = false;              // criando a sessão
  bool _passed = false;               // teste concluído

  @override
  void dispose() {
    if (widget.player == null) _player.dispose();   // só descarta o que este widget criou
    super.dispose();
  }

  Future<void> _playSignal() async {
    final left = _rng.nextBool();
    setState(() {
      _drawnLeft.add(left);
      _playing = true;
      _answered = false;
      _failed = false;
    });
    await _player.loadBytes(HeadphoneTestTone.forEar(left: left));
    await _player.setVolume(audioGain);   // mesmo teto do estímulo (G3)
    await _player.play();
  }

  Future<void> _answer(bool leftChosen) async {
    if (!_playing || _answered) return;
    final acertou = leftChosen == _drawnLeft.last;
    await _player.pause();
    if (!mounted) return;
    if (!acertou) {
      // Falhou: recomeça do zero, com novo sorteio (uma rodada certa não fica "guardada").
      setState(() {
        _drawnLeft.clear();
        _round = 0;
        _attempts += 1;
        _playing = false;
        _answered = true;
        _failed = true;
      });
      return;
    }
    setState(() {
      _round += 1;
      _playing = false;
      _answered = true;
      _passed = _round >= HeadphoneCheckScreen.kRounds;
    });
  }

  Future<void> _start() async {
    setState(() => _loading = true);
    try {
      final s = await widget.repo.start(
        protocolHandle: widget.protocolHandle,
        headphoneCheck: HeadphoneCheckResult(
          rounds: _round,
          errors: 0,                    // a tentativa aceita não tem erro, por construção
          attempts: _attempts,
          ears: _drawnLeft.map((l) => l ? 'L' : 'R').join(),
        ),
        audioGain: audioGain,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => SessionPlayerScreen.production(repo: widget.repo, session: s)));
    } on ApiException catch (e) {
      _snack(e.toString());
    } catch (_) {
      if (mounted) _snack(AppLocalizations.of(context).connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.prepSession), backgroundColor: SerenoColors.paper, elevation: 0),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: SingleChildScrollView(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SizedBox(height: 12),
              const Icon(Icons.headphones_rounded, size: 64, color: SerenoColors.petrol),
              const SizedBox(height: 16),
              Text(t.useStereoHeadphones, textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 10),
              Text(t.headphoneBody, textAlign: TextAlign.center,
                  style: const TextStyle(color: SerenoColors.muted, height: 1.4)),
              const SizedBox(height: 20),
              _statusCard(t),
              const SizedBox(height: 16),
              if (!_passed) ..._testControls(t),
              if (_passed)
                FilledButton(
                  onPressed: _loading ? null : _start,
                  child: _loading
                      ? const SizedBox(
                          height: 22,
                          width: 22,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : Text(t.startSession),
                ),
              const SizedBox(height: 16),
              const DisclaimerBanner(),
            ]),
          ),
        ),
      ),
    );
  }

  Widget _statusCard(AppLocalizations t) {
    final String texto;
    if (_passed) {
      texto = t.headphoneCheckPassed;
    } else if (_failed) {
      texto = t.headphoneCheckFailed;
    } else if (_playing) {
      texto = t.headphoneCheckWhichEar;
    } else {
      texto = t.headphoneCheckIntro;
    }
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _failed ? SerenoColors.alert.withOpacity(0.12) : SerenoColors.paper,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _failed ? SerenoColors.alert : SerenoColors.border, width: 1),
      ),
      child: Column(children: [
        Text(texto, textAlign: TextAlign.center, style: const TextStyle(height: 1.4)),
        const SizedBox(height: 8),
        Text(t.headphoneCheckProgress(_round, HeadphoneCheckScreen.kRounds),
            style: const TextStyle(color: SerenoColors.muted, fontSize: 12)),
      ]),
    );
  }

  List<Widget> _testControls(AppLocalizations t) => [
        if (!_playing)
          FilledButton.tonal(
            onPressed: _playSignal,
            child: Text(_round == 0 && _attempts == 1 && !_failed
                ? t.headphoneCheckPlay
                : t.headphoneCheckPlayAgain),
          ),
        if (_playing) ...[
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _answer(true),
                icon: const Icon(Icons.volume_down_rounded),
                label: Text(t.headphoneCheckLeft),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _answer(false),
                icon: const Icon(Icons.volume_up_rounded),
                label: Text(t.headphoneCheckRight),
              ),
            ),
          ]),
        ],
      ];
}
