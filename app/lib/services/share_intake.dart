import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';

import 'share_intake_io.dart' if (dart.library.js_interop) 'share_intake_web.dart' as impl;

/// 다른 앱에서 공유로 들어온 사진. 콜드 스타트와 웜 스타트 둘 다.
class ShareIntake {
  ShareIntake({this.onMedia});

  final void Function(List<XFile> files)? onMedia;
  bool _started = false;

  Future<void> start() async {
    if (_started || kIsWeb) return;
    _started = true;
    final initial = await impl.initialShared();
    if (initial.isNotEmpty) onMedia?.call(initial);
    impl.sharedStream().listen((files) {
      if (files.isNotEmpty) onMedia?.call(files);
    });
  }

  Future<void> reset() => impl.resetShared();
}
