import 'package:flutter/material.dart';

import '../app_state.dart';
import '../keys.dart';
import '../data/demo_robot_repository.dart';
import '../data/rosbridge_robot_repository.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// First screen: pick the robot. The prototype ships with the demo robot; a real
/// CHOTU is reached at ws://<pi-ip>:9090 (rosbridge on the Raspberry Pi 4).
class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, required this.app});
  final AppController app;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  final _url = TextEditingController(text: 'ws://chotu.local:9090');
  bool _busy = false;
  String? _error;

  Future<void> _go(bool demo) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.app.attach(demo ? DemoRobotRepository() : RosbridgeRobotRepository(_url.text.trim()));
    } catch (e) {
      setState(() => _error = 'Could not reach ${_url.text}: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: ListView(padding: const EdgeInsets.fromLTRB(22, 36, 22, 22), children: [
            const Text('CHOTU',
                style: TextStyle(fontSize: 44, fontWeight: FontWeight.w900, color: C.cyan, letterSpacing: 6)),
            const Text('Compact Home Operations & Tidying Unit', style: TextStyle(color: C.dim)),
            const SizedBox(height: 28),
            Center(
              child: Container(
                width: 170,
                height: 170,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(colors: [C.cyan.withOpacity(0.25), C.bg]),
                  border: Border.all(color: C.cyan.withOpacity(0.6), width: 2),
                ),
                child: const Icon(Icons.cleaning_services_rounded, size: 72, color: C.cyan),
              ),
            ),
            const SizedBox(height: 28),
            const Text('NEARBY ROBOTS', style: TextStyle(fontSize: 11, color: C.dim, letterSpacing: 1.4)),
            const SizedBox(height: 8),
            GlassCard(
              glow: C.cyan,
              child: Row(children: [
                const Icon(Icons.smart_toy_rounded, color: C.cyan),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('CHOTU-01', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                    Text('Demo robot - AtomQuest challenge room', style: TextStyle(color: C.dim, fontSize: 12)),
                  ]),
                ),
                FilledButton(
                  key: K.connect,
                  onPressed: _busy ? null : () => _go(true),
                  child: _busy
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Connect'),
                ),
              ]),
            ),
            const SizedBox(height: 18),
            const Text('CONNECT BY ADDRESS', style: TextStyle(fontSize: 11, color: C.dim, letterSpacing: 1.4)),
            const SizedBox(height: 8),
            GlassCard(
              child: Column(children: [
                TextField(
                  controller: _url,
                  decoration: const InputDecoration(
                      labelText: 'rosbridge URL', prefixIcon: Icon(Icons.wifi_rounded), border: InputBorder.none),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: OutlinedButton(onPressed: _busy ? null : () => _go(false), child: const Text('Connect')),
                ),
                if (_error != null) Text(_error!, style: const TextStyle(color: C.red, fontSize: 12)),
              ]),
            ),
            const SizedBox(height: 18),
            const Text('Your phone and CHOTU must be on the same Wi-Fi network.',
                textAlign: TextAlign.center, style: TextStyle(color: C.dim, fontSize: 12)),
          ]),
        ),
      );
}
