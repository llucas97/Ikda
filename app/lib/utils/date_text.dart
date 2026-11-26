const _weekdays = ['월', '화', '수', '목', '금', '토', '일'];

/// "11월 25일 (화)"
String formatKoreanDate(DateTime d) => '${d.month}월 ${d.day}일 (${_weekdays[d.weekday - 1]})';

/// "화요일"
String weekdayLong(DateTime d) => '${_weekdays[d.weekday - 1]}요일';

/// 남은 날짜를 어르신이 이해하기 쉬운 말로
String ddayText(DateTime due, {DateTime? now}) {
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  final day = DateTime(due.year, due.month, due.day);
  final diff = day.difference(today).inDays;
  if (diff < 0) return '기한 지남';
  if (diff == 0) return '오늘까지';
  if (diff == 1) return '내일까지';
  return '$diff일 남음';
}

/// 3일 이내면 급함
bool isUrgent(DateTime due, {DateTime? now}) {
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  return DateTime(due.year, due.month, due.day).difference(today).inDays <= 3;
}
