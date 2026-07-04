import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/theme.dart';
import '../../services/participant_repository.dart';
import '../../shared/disclaimer_banner.dart';
import '../home/home_screen.dart';

/// Consentimento (TCLE): resumo em linguagem simples + confirmações. O participante
/// só prossegue ao aceitar; a decisão é enviada ao backend (registro versionado + hash).
class ConsentScreen extends StatefulWidget {
  final ParticipantRepository repo;
  const ConsentScreen({super.key, required this.repo});
  @override
  State<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends State<ConsentScreen> {
  bool _read = false, _agree = false, _lgpd = false, _loading = false;
  bool get _canProceed => _read && _agree && _lgpd && !_loading;

  static const _summary = [
    'O estudo avalia um app de sessões de áudio (frequências binaurais) para relaxamento e sono.',
    'Você fará questionários e sessões de ~20 min, com fones, por 4 semanas.',
    'Os riscos são mínimos; você pode interromper e registrar qualquer desconforto.',
    'Seus dados são tratados de forma confidencial e pseudonimizada (LGPD).',
    'A participação é voluntária; você pode sair a qualquer momento, sem prejuízo.',
  ];

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      await widget.repo.recordConsent(version: tcleVersion, accepted: true);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on ApiException catch (e) {
      _snack(e.toString());
    } catch (_) {
      _snack('Falha de conexão. Tente novamente.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Termo de Consentimento'), backgroundColor: SerenoColors.paper, elevation: 0),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(
              child: ListView(children: [
                const Text('Leia o resumo em linguagem simples:',
                    style: TextStyle(color: SerenoColors.muted)),
                const SizedBox(height: 12),
                ..._summary.map((t) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 6, right: 10),
                          child: Icon(Icons.circle, size: 6, color: SerenoColors.teal),
                        ),
                        Expanded(child: Text(t, style: const TextStyle(height: 1.4))),
                      ]),
                    )),
                const SizedBox(height: 8),
                CheckboxListTile(
                  value: _read,
                  onChanged: (v) => setState(() => _read = v ?? false),
                  title: const Text('Li e entendi as informações'),
                  contentPadding: EdgeInsets.zero,
                ),
                CheckboxListTile(
                  value: _agree,
                  onChanged: (v) => setState(() => _agree = v ?? false),
                  title: const Text('Concordo em participar'),
                  contentPadding: EdgeInsets.zero,
                ),
                CheckboxListTile(
                  value: _lgpd,
                  onChanged: (v) => setState(() => _lgpd = v ?? false),
                  title: const Text('Autorizo o uso dos meus dados conforme a LGPD'),
                  contentPadding: EdgeInsets.zero,
                ),
              ]),
            ),
            FilledButton(
              onPressed: _canProceed ? _submit : null,
              child: _loading
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Text('Concordar e continuar'),
            ),
            const SizedBox(height: 8),
            const Text('Você pode retirar o consentimento quando quiser.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: SerenoColors.muted)),
            const SizedBox(height: 12),
            const DisclaimerBanner(),
          ]),
        ),
      ),
    );
  }
}
