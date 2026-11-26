import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// 결과를 소리로 읽어주는 얇은 래퍼 (flutter_tts, 웹도 지원).
class Speech {
  final FlutterTts _tts = FlutterTts();

  Future<void> init({required void Function() onDone}) async {
    await _tts.setLanguage('ko-KR');
    // 기본 속도 기준이 OS마다 달라서 따로 (iOS 0.5 / Android 1.0 이 보통 속도)
    final ios = !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;
    await _tts.setSpeechRate(ios ? 0.42 : 0.8);
    _tts.setCompletionHandler(onDone);
  }

  Future<void> speak(String text) => _tts.speak(text);
  Future<void> stop() => _tts.stop();
}
