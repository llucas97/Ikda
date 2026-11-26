import 'package:flutter/widgets.dart';

/// 한국어 어절 단위 줄바꿈 (CSS `word-break: keep-all` 흉내).
///
/// Flutter는 한글을 글자마다 줄바꿈할 수 있어서 "챙 / 기기"처럼 단어가 잘린다.
/// 어절 안의 글자 사이에 WORD JOINER(U+2060)를 넣어 띄어쓰기에서만 줄이 바뀌게 한다.
/// 한 어절이 한 줄보다 길면 Flutter가 알아서 강제로 자른다.
extension KeepAll on String {
  String get keepAll => split(' ').map((w) => w.characters.join('\u2060')).join(' ');

  /// 날짜처럼 절대 끊기면 안 되는 짧은 묶음 (띄어쓰기도 줄바꿈 금지)
  String get noBreak => replaceAll(' ', '\u00A0').characters.join('\u2060');
}

extension NoBreakParts on String {
  /// "32,400원 · 11월 25일 (수)" 처럼 ' · '로 나뉜 조각 안에서는 줄바꿈하지 않는다.
  String get noBreakParts => split(' · ').map((s) => s.noBreak).join(' · ');
}
