import 'package:flutter/material.dart';

const _cyan = Color(0xFF12D6FF);
const _green = Color(0xFF26C281);
const _red = Color(0xFFEF4B5B);

Map<String, dynamic> _asMap(dynamic value) =>
    Map<String, dynamic>.from(value as Map? ?? const {});
String _fmt(dynamic value) {
  if (value == null || value.toString().isEmpty) return '—';
  if (value is num) return value.abs() >= 1000 ? value.toStringAsFixed(0) : value.toStringAsFixed(2);
  return value.toString();
}
double? _num(dynamic value) => value is num ? value.toDouble() : double.tryParse('$value');

class OrderFlowPage extends StatelessWidget {
  const OrderFlowPage({required this.selectedIndex, required this.market, required this.signals, super.key});
  final String selectedIndex;
  final Map<String, dynamic> market;
  final Map<String, dynamic> signals;

  @override
  Widget build(BuildContext context) {
    final m = _asMap(market[selectedIndex]);
    final s = _asMap(signals[selectedIndex]);
    final ind = _asMap(s['indicators']);
    final oi = _asMap(s['oi_summary']);
    final chain = (m['option_chain'] as List?) ?? const [];
    final delta = _num(s['delta'] ?? m['delta'] ?? oi['delta']);
    final volume = _num(m['volume'] ?? s['volume'] ?? ind['volume']);
    final callOi = _num(oi['call_oi']);
    final putOi = _num(oi['put_oi']);
    final fresh = m['live'] == true;
    return ListView(padding: const EdgeInsets.all(12), children: [
      Row(children: [const Expanded(child: Text('ORDER FLOW / FOOTPRINT MONITOR', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: .8)),), _pill(fresh ? 'LIVE' : 'DATA CHECK', fresh ? _green : Colors.orangeAccent)]),
      const SizedBox(height: 8),
      const Text('Backend-provided market/order-flow fields only. If aggressor-side trades or depth are unavailable, this page will not invent footprint cells.', style: TextStyle(color: Colors.white70, fontSize: 12)),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(selectedIndex, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
        Text('₹ ${_fmt(m['ltp'])}', style: const TextStyle(fontSize: 29, fontWeight: FontWeight.w900, color: _cyan)),
        Text('Source: ${m['feed_mode'] ?? m['source'] ?? 'UNKNOWN'} • Snapshot: ${m['timestamp'] ?? '—'}'),
        const Divider(height: 24),
        _metric('Net delta', delta == null ? 'NOT PROVIDED' : _fmt(delta), delta == null ? Colors.white54 : (delta >= 0 ? _green : _red)),
        _metric('Traded volume', volume == null ? 'NOT PROVIDED' : _fmt(volume), Colors.white),
        _metric('Call OI', callOi == null ? 'NOT PROVIDED' : _fmt(callOi), _red),
        _metric('Put OI', putOi == null ? 'NOT PROVIDED' : _fmt(putOi), _green),
        _metric('PCR', _fmt(oi['pcr']), _cyan),
        _metric('Option-chain rows', '${chain.length}', Colors.white),
        _metric('Data age', m['age_seconds'] == null ? 'UNKNOWN' : '${_fmt(m['age_seconds'])} sec', fresh ? _green : Colors.orangeAccent),
      ]))),
      const SectionLabel('ORDER FLOW READ'),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Text(
        !fresh ? 'WAIT — feed is not confirmed live. No buy/sell conclusion should be generated from stale data.'
        : delta == null ? 'WAIT — the backend has not supplied aggressor-side delta. LTP alone cannot determine buyer-initiated vs seller-initiated flow.'
        : delta > 0 ? 'Positive reported delta: buying pressure may be stronger. Confirm price acceptance, volume and option liquidity.'
        : delta < 0 ? 'Negative reported delta: selling pressure may be stronger. Confirm downside follow-through and option liquidity.'
        : 'Delta is neutral or balanced. Wait for a clear price/volume confirmation.',
        style: const TextStyle(fontSize: 14, height: 1.4),
      ))),
      const Text('Important: This view is not an exchange-certified footprint. Bid/ask depth and aggressor estimates must be explicitly provided by the backend; absent fields remain unavailable.', style: TextStyle(color: Colors.white60, fontSize: 11)),
    ]);
  }
}

class StrategyEngines15Page extends StatelessWidget {
  const StrategyEngines15Page({required this.selectedIndex, required this.market, required this.signals, required this.ai, super.key});
  final String selectedIndex;
  final Map<String, dynamic> market, signals, ai;

  static const names = <(String, String)>[
    ('EMA crossover', 'ema_fast / ema_slow'),
    ('MACD momentum', 'macd_hist'),
    ('RSI 14', 'rsi14'),
    ('VWAP bias', 'vwap'),
    ('Bollinger bands', 'bb_upper / bb_lower'),
    ('ATR volatility', 'atr14'),
    ('Mean reversion', 'RSI 14 + Z-score 20'),
    ('Bollinger reversion', 'bb_upper / bb_lower / price'),
    ('ATR volatility guard', 'atr14'),
    ('OI + premium flow', 'premium_change / oi_change'),
    ('Put-call ratio', 'pcr'),
    ('OI flow imbalance', 'CE vs PE OI changes'),
    ('Supertrend direction', 'supertrend_direction'),
    ('ADX trend strength', 'adx14'),
    ('Stochastic momentum', 'stochastic_k14 / stochastic_d3'),
    ('Multi-timeframe alignment', 'timeframe_analysis'),
    ('Execution liquidity + risk gate', 'bid / ask spread + live_validation'),
  ];

  @override
  Widget build(BuildContext context) {
    final m = _asMap(market[selectedIndex]);
    final s = _asMap(signals[selectedIndex]);
    final ind = _asMap(s['indicators']);
    final oi = _asMap(s['oi_summary']);
    final research = _asMap(_asMap(s['timeframe_analysis'])['research_pack']);
    final researchChecks = _asMap(research['checks']);
    final confluenceChecks = _asMap(_asMap(s['confluence'])['checks']);
    final validation = _asMap(s['live_validation']);
    final aiRow = _asMap(ai[selectedIndex]);
    final decision = (validation['decision'] ?? s['decision'] ?? 'WAIT').toString();
    final fresh = m['live'] == true;
    final rows = <Map<String, String>>[
      _row(ind, ['ema_fast','ema_slow'], _compare(ind['ema_fast'], ind['ema_slow'])),
      _row(ind, ['macd_hist'], _direction(ind['macd_hist'])),
      _row(ind, ['rsi14'], _rsi(ind['rsi14'])),
      _row(ind, ['vwap'], _compare(m['ltp'], ind['vwap'])),
      _row(ind, ['bb_upper','bb_lower'], _bands(m['ltp'], ind['bb_lower'], ind['bb_upper'])),
      _row(ind, ['atr14'], ind['atr14'] == null ? 'UNKNOWN' : 'VALUE AVAILABLE'),
      _row(researchChecks, ['mean_reversion'], _state(researchChecks['mean_reversion'])),
      _row(ind, ['bb_upper','bb_lower'], _bands(m['ltp'], ind['bb_lower'], ind['bb_upper'])),
      _row(ind, ['atr14'], ind['atr14'] == null ? 'UNKNOWN' : 'VOLATILITY MEASURED'),
      _row(researchChecks, ['option_oi_premium_flow'], _state(researchChecks['option_oi_premium_flow'])),
      _row(oi, ['pcr'], _pcr(oi['pcr'])),
      _row(confluenceChecks, ['oi_flow'], _state(confluenceChecks['oi_flow'])),
      _row(ind, ['supertrend_direction'], _directionLabel(ind['supertrend_direction'])),
      _row(ind, ['adx14'], _adx(ind['adx14'])),
      _row(ind, ['stochastic_k14','stochastic_d3'], _compare(ind['stochastic_k14'], ind['stochastic_d3'])),
      _row(_asMap(s['timeframe_analysis']), ['research_pack'], research.isEmpty ? 'UNKNOWN' : 'RESEARCH PACK AVAILABLE'),
      _row(validation, ['verdict','decision'], validation['verdict']?.toString().toUpperCase() ?? 'NOT VALIDATED'),
    ];
    return ListView(padding: const EdgeInsets.all(12), children: [
      const Text('15 STRATEGY ENGINES', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
      const SizedBox(height: 5),
      const Text('Every engine reads the current backend payload. UNKNOWN means that field was not supplied; the app does not fabricate indicator values.', style: TextStyle(color: Colors.white70, fontSize: 12)),
      Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Expanded(child: Text(selectedIndex, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900))), _pill(fresh ? 'LIVE DATA' : 'NOT LIVE', fresh ? _green : Colors.orangeAccent)]),
        Text('Market price: ₹ ${_fmt(m['ltp'])}'),
        const SizedBox(height: 8),
        Text('Validated output: $decision', style: TextStyle(fontSize: 19, fontWeight: FontWeight.w900, color: decision.contains('BUY') && validation['verdict'] == 'PASS' ? _green : Colors.orangeAccent)),
        Text('OpenRouter review: ${aiRow['action'] ?? aiRow['decision'] ?? 'NOT AVAILABLE'}'),
        Text('OpenRouter rationale: ${(aiRow['why'] as List? ?? const []).join(' • ')}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
      ]))),
      for (var i = 0; i < names.length; i++)
        Card(child: ListTile(
          leading: CircleAvatar(radius: 15, child: Text('${i + 1}', style: const TextStyle(fontSize: 12))),
          title: Text(names[i].$1, style: const TextStyle(fontWeight: FontWeight.w800)),
          subtitle: Text('Inputs: ${names[i].$2}'),
          trailing: SizedBox(width: 100, child: Text(rows[i]['status'] ?? 'UNKNOWN', textAlign: TextAlign.end, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: (rows[i]['status'] ?? '').contains('BULL') || (rows[i]['status'] ?? '').contains('PASS') ? _green : (rows[i]['status'] ?? '').contains('BEAR') || (rows[i]['status'] ?? '').contains('BLOCK') ? _red : Colors.orangeAccent))),
        )),
      Card(child: ListTile(leading: const Icon(Icons.shield_outlined), title: const Text('Fail-safe rule'), subtitle: Text('Signal requires fresh data, validation PASS and a CALL BUY / PUT BUY candidate. Current validation blocks: ${(validation['blocks'] as List? ?? const []).join(', ').isEmpty ? 'none reported' : (validation['blocks'] as List).join(', ')}'))),
      const Text('Research tool only—not a guarantee of profit. Paper-test all engines with slippage and costs before risking capital.', style: TextStyle(color: Colors.white60, fontSize: 11)),
    ]);
  }

  static Map<String, String> _row(Map<String, dynamic> source, List<String> keys, String status) {
    final present = keys.any((k) => source[k] != null);
    return {'status': present ? status : 'UNKNOWN'};
  }
  static String _state(dynamic v) { final row = _asMap(v); return (row['state'] ?? 'UNKNOWN').toString().toUpperCase(); }
  static String _directionLabel(dynamic v) { final x = (v ?? '').toString().toUpperCase(); return x.isEmpty || x == 'N/A' ? 'UNKNOWN' : x; }
  static String _direction(dynamic v) { final n = _num(v); return n == null ? 'UNKNOWN' : n > 0 ? 'BULLISH' : n < 0 ? 'BEARISH' : 'NEUTRAL'; }
  static String _compare(dynamic a, dynamic b) { final x = _num(a), y = _num(b); return x == null || y == null ? 'UNKNOWN' : x > y ? 'BULLISH' : x < y ? 'BEARISH' : 'NEUTRAL'; }
  static String _rsi(dynamic v) { final n = _num(v); return n == null ? 'UNKNOWN' : n >= 55 ? 'BULLISH' : n <= 45 ? 'BEARISH' : 'NEUTRAL'; }
  static String _pcr(dynamic v) { final n = _num(v); return n == null ? 'UNKNOWN' : n > 1.1 ? 'PUT OI HEAVIER' : n < .9 ? 'CALL OI HEAVIER' : 'BALANCED'; }
  static String _adx(dynamic v) { final n = _num(v); return n == null ? 'UNKNOWN' : n >= 25 ? 'TREND STRONG' : 'TREND WEAK'; }
  static String _bands(dynamic p, dynamic l, dynamic u) { final x = _num(p), lo = _num(l), hi = _num(u); return x == null || lo == null || hi == null ? 'UNKNOWN' : x > hi ? 'ABOVE UPPER BAND' : x < lo ? 'BELOW LOWER BAND' : 'INSIDE BANDS'; }
}

Widget _pill(String label, Color color) => Container(
  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
  decoration: BoxDecoration(color: color.withValues(alpha: .12), borderRadius: BorderRadius.circular(18), border: Border.all(color: color.withValues(alpha: .45))),
  child: Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w900)),
);
Widget _metric(String title, String value, Color color) => Padding(
  padding: const EdgeInsets.symmetric(vertical: 4),
  child: Row(children: [Expanded(child: Text(title, style: const TextStyle(color: Colors.white70))), Text(value, style: TextStyle(fontWeight: FontWeight.w800, color: color))]),
);
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.label, {super.key});
  final String label;
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.fromLTRB(4, 12, 4, 6), child: Text(label, style: const TextStyle(fontWeight: FontWeight.w900, letterSpacing: .7)));
}
