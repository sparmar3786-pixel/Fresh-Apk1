class AppConfig {
  static const String backendUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'https://fresh-algo-signal-gateway-v2.onrender.com',
  );

  static Uri get healthUri => Uri.parse(
        '${backendUrl.replaceAll(RegExp(r'/+$'), '')}/health',
      );
}
