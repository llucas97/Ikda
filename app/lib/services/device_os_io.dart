import 'dart:io' show Platform;

String deviceOs() {
  if (Platform.isIOS) return 'IOS';
  if (Platform.isAndroid) return 'ANDROID';
  return 'WEB';
}

bool get isIosDevice => Platform.isIOS;
