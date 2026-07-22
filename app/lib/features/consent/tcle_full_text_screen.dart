import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import '../../core/config.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';

/// Texto INTEGRAL do TCLE, exigido para que o consentimento seja informado — o resumo
/// da tela anterior não substitui o termo, só o antecipa.
///
/// O conteúdo vem do asset `assets/tcle/tcle-pt.txt`, **gerado** de `docs/tcle-rascunho.md`
/// (o arquivo que vai ao CEP) por `scripts/sync_tcle.py`. O app não guarda uma segunda
/// redação do termo: se guardasse, o texto submetido ao comitê e o texto lido pelo
/// participante divergiriam sem ninguém perceber. O CI falha se saírem de sincronia.
///
/// Formato do asset — uma linha por bloco, com prefixo (evita depender de um renderizador
/// de Markdown): `H|` seção · `P|` parágrafo · `B|` item · `!|` destaque · `#` comentário.
class TcleFullTextScreen extends StatefulWidget {
  /// Origem do texto. Injetável **porque o teste de widget não consegue esperar I/O real**:
  /// dentro de `pumpAndSettle` o tempo é falso, a leitura do asset não completa e o
  /// indicador de carga gira até estourar. Em produção é sempre o asset empacotado.
  final Future<String> Function()? loadText;

  const TcleFullTextScreen({super.key, this.loadText});

  static const assetPath = 'assets/tcle/tcle-pt.txt';

  /// Exposto para teste: o parser é a única lógica desta tela.
  static List<TcleBlock> parse(String raw) {
    final blocks = <TcleBlock>[];
    for (final line in raw.split('\n')) {
      if (line.isEmpty || line.startsWith('#')) continue;
      final sep = line.indexOf('|');
      if (sep <= 0) continue;
      blocks.add(TcleBlock(line.substring(0, sep), line.substring(sep + 1)));
    }
    return blocks;
  }

  @override
  State<TcleFullTextScreen> createState() => _TcleFullTextScreenState();
}

/// Bloco do termo já classificado. Público de propósito: `parse` faz parte da
/// superfície testável desta tela.
class TcleBlock {
  final String kind, text;
  const TcleBlock(this.kind, this.text);
}

class _TcleFullTextScreenState extends State<TcleFullTextScreen> {
  List<TcleBlock>? _blocks;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final raw = await (widget.loadText ??
          () => rootBundle.loadString(TcleFullTextScreen.assetPath))();
      if (mounted) setState(() => _blocks = TcleFullTextScreen.parse(raw));
    } catch (_) {
      // Sem o termo não há consentimento informado: falhar visível é melhor que uma
      // tela vazia que o participante interpretaria como "não há mais nada a ler".
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(t.tcleFullTitle),
        backgroundColor: SerenoColors.paper,
        elevation: 0,
      ),
      body: SafeArea(
        child: _failed
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(t.tcleLoadError, textAlign: TextAlign.center),
                ),
              )
            : _blocks == null
                ? const Center(child: CircularProgressIndicator())
                : ListView(
                    padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
                    children: [
                      const _DraftNotice(),
                      const SizedBox(height: 8),
                      ..._blocks!.map(_render),
                    ],
                  ),
      ),
    );
  }

  Widget _render(TcleBlock b) {
    switch (b.kind) {
      case 'H':
        return Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 8),
          child: Text(b.text,
              style: const TextStyle(
                  fontFamily: 'Fraunces',
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                  color: SerenoColors.ink)),
        );
      case 'B':
        return Padding(
          padding: const EdgeInsets.only(bottom: 8, left: 4),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Padding(
              padding: EdgeInsets.only(top: 7, right: 10),
              child: Icon(Icons.circle, size: 5, color: SerenoColors.teal),
            ),
            Expanded(
              child: Text(b.text,
                  style: const TextStyle(height: 1.45, color: SerenoColors.ink)),
            ),
          ]),
        );
      case '!':
        // Destaques são os avisos que o termo não pode deixar passar (não é tratamento,
        // recusa sem prejuízo, dado sensível). Recebem peso visual próprio.
        return Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xFFEEF3F5),
            borderRadius: BorderRadius.circular(12),
            border: const Border(
                left: BorderSide(color: SerenoColors.teal, width: 3),
                top: BorderSide(color: SerenoColors.border),
                right: BorderSide(color: SerenoColors.border),
                bottom: BorderSide(color: SerenoColors.border)),
          ),
          child: Text(b.text,
              style: const TextStyle(
                  height: 1.45, color: SerenoColors.ink, fontWeight: FontWeight.w600)),
        );
      default:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(b.text,
              style: const TextStyle(height: 1.5, color: SerenoColors.ink)),
        );
    }
  }
}

/// Aviso de que o texto ainda não foi aprovado pelo CEP. Enquanto `tcleVersion` carregar
/// o sufixo `-rascunho`, ninguém deve ler esta tela como um termo em vigor.
class _DraftNotice extends StatelessWidget {
  const _DraftNotice();

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final isDraft = tcleVersion.contains('rascunho');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (isDraft)
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: const Color(0xFFFDF1E7),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: SerenoColors.alert),
          ),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.warning_amber_rounded, size: 18, color: SerenoColors.alert),
            const SizedBox(width: 10),
            Expanded(
              child: Text(t.tcleDraftWarning,
                  style: const TextStyle(
                      fontSize: 12, color: SerenoColors.ink, height: 1.35)),
            ),
          ]),
        ),
      const SizedBox(height: 10),
      Text('${t.tcleVersionLabel}: $tcleVersion',
          style: const TextStyle(fontSize: 12, color: SerenoColors.muted)),
      if ((Localizations.maybeLocaleOf(context)?.languageCode ?? 'pt') != 'pt') ...[
        const SizedBox(height: 6),
        Text(t.tcleOnlyPortuguese,
            style: const TextStyle(fontSize: 12, color: SerenoColors.muted, height: 1.35)),
      ],
    ]);
  }
}
