import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart';

/// 초대 링크. ilgeodeurim://family/join?t= 와 https://도메인/f/{token}
class DeepLinks {
  DeepLinks({required this.onToken});
  final void Function(String token) onToken;
  final _links = AppLinks();
  bool _started = false;

  Future<void> start() async {
    if (_started || kIsWeb) return;
    _started = true;
    try {
      final initial = await _links.getInitialLink();
      final token = tokenOf(initial);
      if (token != null) onToken(token);
      _links.uriLinkStream.listen((uri) {
        final next = tokenOf(uri);
        if (next != null) onToken(next);
      });
    } catch (e) {
      debugPrint('deep link: $e');
    }
  }

  static String? tokenOf(Uri? uri) {
    if (uri == null) return null;
    if (uri.scheme == 'ilgeodeurim' && uri.host == 'family') {
      final t = uri.queryParameters['t'];
      if (t != null && t.isNotEmpty) return t;
    }
    if ((uri.scheme == 'https' || uri.scheme == 'http') && uri.pathSegments.length >= 2 && uri.pathSegments.first == 'f') {
      return uri.pathSegments[1];
    }
    return null;
  }
}
