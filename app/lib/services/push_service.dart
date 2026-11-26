import 'package:flutter/foundation.dart';

import 'push_service_io.dart' if (dart.library.js_interop) 'push_service_web.dart' as impl;

/// 푸시를 누르면 서류 화면으로. 설정이 없거나 가짜 모드면 아무 것도 하지 않는다.
abstract class PushService {
  Future<void> start({required void Function(PushOpen open) onOpen, required Future<void> Function(String token) onToken});
  Future<void> stop();
}

class PushOpen {
  const PushOpen(this.type, this.documentId, this.linkId);
  final String? type;
  final String? documentId;
  final String? linkId;
}

PushService createPushService({required bool enabled}) =>
    (!enabled || kIsWeb) ? NoopPushService() : impl.createPlatformPush();

class NoopPushService implements PushService {
  @override
  Future<void> start({required void Function(PushOpen open) onOpen, required Future<void> Function(String token) onToken}) async {}
  @override
  Future<void> stop() async {}
}
