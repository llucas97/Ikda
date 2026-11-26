import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'push_service.dart';

PushService createPlatformPush() => FirebasePushService();

class FirebasePushService implements PushService {
  bool _ready = false;

  @override
  Future<void> start({
    required void Function(PushOpen open) onOpen,
    required Future<void> Function(String token) onToken,
  }) async {
    if (_ready) return;
    try {
      await Firebase.initializeApp();
      _ready = true;
    } catch (e) {
      debugPrint('Firebase 준비 실패(설정 파일이 없으면 정상): $e');
      return;
    }
    final messaging = FirebaseMessaging.instance;
    FirebaseMessaging.onMessage.listen((_) => onOpen(const PushOpen('FOREGROUND', null, null)));
    FirebaseMessaging.onMessageOpenedApp.listen((m) => onOpen(_open(m)));
    final initial = await messaging.getInitialMessage();
    if (initial != null) onOpen(_open(initial));
    final token = await messaging.getToken();
    if (token != null) await onToken(token);
    messaging.onTokenRefresh.listen(onToken);
  }

  PushOpen _open(RemoteMessage m) => PushOpen(
        m.data['type'] as String?,
        m.data['documentId'] as String?,
        m.data['linkId'] as String?,
      );

  @override
  Future<void> stop() async {}
}
