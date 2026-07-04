import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../services/session_repository.dart';
import '../../shared/disclaimer_banner.dart';
import 'session_player_screen.dart';

/// Pré-condição de fidelidade: o áudio binaural exige fones ESTÉREO. Sem confirmação,
/// não se inicia (o servidor também recusa). Handle da banda é neutro quanto ao braço.
class HeadphoneCheckScreen extends StatefulWidget {
  final SessionRepository repo;
  final String protocolHandle;
  const HeadphoneCheckScreen({super.key, required this.repo, this.protocolHandle = 'alpha'});
  @override
  State<HeadphoneCheckScreen> createState() => _HeadphoneCheckScreenState();
}

class _HeadphoneCheckScreenState extends State<HeadphoneCheckScreen> {
  bool _ok = false, _loading = false;

  Future<void> _start() async {
    setState(() => _loading = true);
    try {
      final s = await widget.repo.start(protocolHandle: widget.protocolHandle, headphonesOk: _ok);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => SessionPlayerScreen(repo: widget.repo, session: s)));
    } on ApiException catch (e) {
      _snack(e.toString());
    } catch (_) {
      _snack('Falha de conexão. Tente novamente.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Preparar sessão'), backgroundColor: SerenoColors.paper, elevation: 0),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SizedBox(height: 12),
              const Icon(Icons.headphones_rounded, size: 72, color: SerenoColors.petrol),
              const SizedBox(height: 20),
              Text('Use fones estéreo', textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 10),
              const Text(
                'As sessões usam áudio em dois canais. Conecte fones com fio, ajuste um '
                'volume confortável e prefira um ambiente tranquilo.',
                textAlign: TextAlign.center,
                style: TextStyle(color: SerenoColors.muted, height: 1.4),
              ),
              const SizedBox(height: 20),
              CheckboxListTile(
                value: _ok,
                onChanged: (v) => setState(() => _ok = v ?? false),
                title: const Text('Meus fones estéreo estão conectados'),
                contentPadding: EdgeInsets.zero,
              ),
              const Spacer(),
              FilledButton(
                onPressed: (_ok && !_loading) ? _start : null,
                child: _loading
                    ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Iniciar sessão'),
              ),
              const SizedBox(height: 12),
              const DisclaimerBanner(),
            ]),
          ),
        ),
      );
}
