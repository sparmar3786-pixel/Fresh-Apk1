import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class SignalNotifications {
  SignalNotifications._();
  static final SignalNotifications instance = SignalNotifications._();
  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  Future<void> initialize() async {
    if (_ready) return;
    const settings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _plugin.initialize(settings);
    final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
    await android?.requestNotificationsPermission();
    await android?.createNotificationChannel(const AndroidNotificationChannel(
      'fresh_validated_signals',
      'Fresh validated trading signals',
      description: 'Only fresh-data, risk-validated CALL BUY / PUT BUY alerts',
      importance: Importance.max,
    ));
    _ready = true;
  }

  Future<void> showValidatedSignal({required String index, required String decision, required String detail}) async {
    await initialize();
    await _plugin.show(
      (index + decision).hashCode & 0x7fffffff,
      'Fresh Algo • $index • $decision',
      detail,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'fresh_validated_signals',
          'Fresh validated trading signals',
          channelDescription: 'Only fresh-data, risk-validated CALL BUY / PUT BUY alerts',
          importance: Importance.max,
          priority: Priority.high,
          category: AndroidNotificationCategory.recommendation,
        ),
      ),
    );
  }
}
