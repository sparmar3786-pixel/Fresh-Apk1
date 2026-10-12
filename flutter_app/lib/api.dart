import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'config.dart';

class FreshApi {
  FreshApi([String? baseUrl]) : baseUrl = baseUrl ?? AppConfig.backendUrl;

  final String baseUrl;

  Uri _uri(String path) {
    final normalized = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    if (!normalized.startsWith('https://') ||
        normalized.contains('10.0.2.2') ||
        normalized.contains('localhost') ||
        normalized.contains('127.0.0.1')) {
      throw Exception(
        'Backend must be a public HTTPS URL. Invalid base URL: $normalized',
      );
    }
    return Uri.parse(normalized + path);
  }

  Future<String> _deviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString('fresh_device_id');
    if (id == null || id.length < 43) {
      final bytes = List<int>.generate(32, (_) => Random.secure().nextInt(256));
      id = base64UrlEncode(bytes).replaceAll('=', '');
      await prefs.setString('fresh_device_id', id);
    }
    return id;
  }

  Future<Map<String, String>> _headers() async => {
        'accept': 'application/json',
        'content-type': 'application/json',
        'X-Device-Id': await _deviceId(),
      };

  Future<Map<String, dynamic>> getJson(String path) async {
    final response = await http
        .get(_uri(path), headers: await _headers())
        .timeout(const Duration(seconds: 30));
    return _decode(response);
  }

  Future<Map<String, dynamic>> postJson(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await http
        .post(
          _uri(path),
          headers: await _headers(),
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 30));
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    dynamic decoded;
    try {
      decoded = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
    } catch (_) {
      throw Exception('HTTP ${response.statusCode}: ${response.body}');
    }
    if (response.statusCode >= 400) {
      final detail = decoded is Map ? (decoded['detail'] ?? decoded) : decoded;
      throw Exception('HTTP ${response.statusCode}: $detail');
    }
    if (decoded is! Map) {
      throw Exception('HTTP ${response.statusCode}: invalid JSON response');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<Map<String, dynamic>> health() => getJson('/health');
  Future<Map<String, dynamic>> metadata() => getJson('/v1/metadata');
  Future<Map<String, dynamic>> angelStatus() => getJson('/v1/angel/status');
  Future<Map<String, dynamic>> testOpenAI() =>
      postJson('/v1/providers/openai/test', {});
  Future<Map<String, dynamic>> testSearchProviders() =>
      postJson('/v1/providers/search/test', {});

  Future<Map<String, dynamic>> saveCredentials(
    Map<String, dynamic> body,
  ) =>
      postJson('/v1/settings/credentials', body);

  Future<void> checkBackend() async {
    // Always probe the same base URL used by this FreshApi instance. Using the
    // compile-time default here made custom backend URLs appear offline.
    final uri = _uri('/health');
    final response = await http
        .get(uri, headers: await _headers())
        .timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      final body = response.body.trim();
      throw Exception(
        'Backend health check failed at $uri: HTTP ${response.statusCode}'
        '${body.isEmpty ? '' : ' — ${body.length > 240 ? body.substring(0, 240) : body}'}',
      );
    }
  }

  Future<Map<String, dynamic>> connectAngel(
    Map<String, dynamic> body,
  ) async {
    await checkBackend();
    return postJson('/v1/angel/connect', body);
  }

  Future<Map<String, dynamic>> syncInstruments() =>
      postJson('/v1/instruments/sync', {});

  Future<Map<String, dynamic>> startStream(List<String> indexes) =>
      postJson('/v1/stream/start', {'indexes': indexes});

  Future<Map<String, dynamic>> signals({int emaFast = 8, int emaSlow = 13}) =>
      getJson('/v1/signals?ema_fast=$emaFast&ema_slow=$emaSlow');

  Future<Map<String, dynamic>> liveExecutionStatus() => getJson('/v1/live/status');

  Future<Map<String, dynamic>> executeLiveSignal({
    required String index,
    required int lots,
    required String confirmation,
    required String requestId,
  }) => postJson('/v1/live/execute-signal', {
        'index': index,
        'lots': lots,
        'confirmation': confirmation,
        'request_id': requestId,
      });

  Future<Map<String, dynamic>> liveOrders() => getJson('/v1/live/orders');
}
