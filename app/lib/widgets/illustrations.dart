import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';

import '../models/document_result.dart';
import '../theme.dart';

/// 직접 그린 평면 일러스트 (외부 이미지·이모지 없이 CustomPainter).
/// 모든 그림은 100×100 격자 위에 그리고 크기에 맞춰 늘린다.
/// 색은 팔레트 안에서만, 외곽선 굵기는 한 가지(격자 기준 2.6).
enum Illo { bill, medicine, hospital, paper, contract, notice, calendarDone, folder, plant, blur, dark, glare, tiny, cropped }

Illo illoFor(DocType t) => switch (t) {
      DocType.bill => Illo.bill,
      DocType.medicine => Illo.medicine,
      DocType.hospital => Illo.hospital,
      DocType.contract => Illo.contract,
      DocType.publicNotice => Illo.notice,
      DocType.other => Illo.paper,
    };

/// 다시 찍기 화면. 문제 코드 → 그림.
Illo illoForProblem(String code) => switch (code) {
      'photo_blurry' => Illo.blur,
      'photo_dark' => Illo.dark,
      'photo_bright' => Illo.glare,
      'photo_small' => Illo.tiny,
      'photo_edge' => Illo.cropped,
      _ => Illo.paper,
    };

class Illustration extends StatelessWidget {
  const Illustration(this.kind, {super.key, this.size = 96, this.semanticLabel});
  final Illo kind;
  final double size;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final painter = CustomPaint(size: Size.square(size), painter: _IlloPainter(kind));
    return semanticLabel == null
        ? ExcludeSemantics(child: painter)
        : Semantics(label: semanticLabel, image: true, child: painter);
  }
}

class _IlloPainter extends CustomPainter {
  _IlloPainter(this.kind);
  final Illo kind;

  late Canvas _c;
  late double _k;

  static const _stroke = 2.6;

  Offset p(double x, double y) => Offset(x * _k, y * _k);
  Rect r(double l, double t, double rt, double b) => Rect.fromLTRB(l * _k, t * _k, rt * _k, b * _k);
  Paint fill(Color c) => Paint()..color = c;
  Paint get line => Paint()
    ..color = AppColors.outline
    ..style = PaintingStyle.stroke
    ..strokeWidth = _stroke * _k
    ..strokeJoin = StrokeJoin.round
    ..strokeCap = StrokeCap.round;

  void shape(Path path, Color c) {
    _c.drawPath(path, fill(c));
    _c.drawPath(path, line);
  }

  void rrect(double l, double t, double rt, double b, double rad, Color c, {bool stroke = true}) {
    final rr = RRect.fromRectAndRadius(r(l, t, rt, b), Radius.circular(rad * _k));
    _c.drawRRect(rr, fill(c));
    if (stroke) _c.drawRRect(rr, line);
  }

  void bar(double x1, double x2, double y, Color c, {double w = 4}) {
    _c.drawLine(p(x1, y), p(x2, y), Paint()
      ..color = c
      ..strokeWidth = w * _k
      ..strokeCap = StrokeCap.round);
  }

  void circle(double x, double y, double rad, Color c, {bool stroke = true}) {
    _c.drawCircle(p(x, y), rad * _k, fill(c));
    if (stroke) _c.drawCircle(p(x, y), rad * _k, line);
  }

  void shadow(double cx, double y, double w) {
    _c.drawOval(Rect.fromCenter(center: p(cx, y), width: w * _k, height: 6 * _k),
        fill(AppColors.outline.withValues(alpha: 0.12)));
  }

  @override
  void paint(Canvas canvas, Size size) {
    _c = canvas;
    _k = size.width / 100;
    switch (kind) {
      case Illo.bill:
        _bill();
      case Illo.medicine:
        _medicine();
      case Illo.hospital:
        _hospital();
      case Illo.paper:
        _paper(stamp: false);
      case Illo.contract:
        _contract();
      case Illo.notice:
        _paper(stamp: true);
      case Illo.calendarDone:
        _calendar();
      case Illo.folder:
        _folder();
      case Illo.plant:
        _plant();
      case Illo.blur:
        _shake();
      case Illo.dark:
        _dark();
      case Illo.glare:
        _glare();
      case Illo.tiny:
        _tiny();
      case Illo.cropped:
        _cropped();
    }
  }

  void _page() {
    rrect(22, 14, 78, 88, 4, AppColors.surface);
    bar(30, 70, 28, AppColors.inkSub, w: 3);
    bar(30, 62, 40, AppColors.accentMid, w: 3);
    bar(30, 66, 52, AppColors.accentMid, w: 3);
  }

  void _brackets() {
    final ink = line..color = AppColors.ink;
    void arm(double x1, double y1, double x2, double y2, double x3, double y3) {
      final path = Path()
        ..moveTo(x1 * _k, y1 * _k)
        ..lineTo(x2 * _k, y2 * _k)
        ..lineTo(x3 * _k, y3 * _k);
      _c.drawPath(path, ink);
    }

    arm(18, 30, 18, 18, 30, 18);
    arm(82, 30, 82, 18, 70, 18);
    arm(18, 70, 18, 82, 30, 82);
    arm(82, 70, 82, 82, 70, 82);
  }

  void _shake() {
    _page();
    _brackets();
    bar(28, 74, 64, AppColors.highlight, w: 6);
  }

  void _dark() {
    rrect(18, 12, 82, 88, 6, AppColors.ink);
    bar(30, 70, 40, AppColors.accentMid, w: 3);
    bar(30, 58, 52, AppColors.accentMid, w: 3);
  }

  void _glare() {
    _page();
    circle(62, 36, 16, AppColors.highlight, stroke: false);
  }

  void _tiny() {
    _brackets();
    rrect(40, 36, 60, 64, 2, AppColors.surface);
  }

  void _cropped() {
    _brackets();
    rrect(8, 28, 92, 78, 2, AppColors.surface);
    bar(14, 40, 40, AppColors.highlight, w: 5);
  }

  // 영수증 모양 고지서 + 동전
  void _bill() {
    shadow(50, 94, 64);
    final body = Path()..moveTo(22 * _k, 10 * _k)..lineTo(78 * _k, 10 * _k)..lineTo(78 * _k, 86 * _k);
    const teeth = 7;
    const step = 56 / teeth;
    for (var i = 0; i < teeth; i++) {
      final x = 78 - step * i;
      body.lineTo((x - step / 2) * _k, 91 * _k);
      body.lineTo((x - step) * _k, 86 * _k);
    }
    body.close();
    shape(body, AppColors.surface);
    // 머리띠
    final head = Path()
      ..addRRect(RRect.fromRectAndCorners(r(22, 10, 78, 26)));
    _c.drawPath(head, fill(AppColors.accent));
    _c.drawPath(body, line);
    circle(31, 18, 3.4, AppColors.surface, stroke: false);
    bar(38, 62, 18, AppColors.surface, w: 3.4);
    // 줄
    bar(30, 66, 35, AppColors.line, w: 4);
    bar(30, 56, 44, AppColors.line, w: 4);
    // 금액 칸
    rrect(29, 52, 71, 70, 4, AppColors.accentSoft, stroke: false);
    bar(35, 60, 61, AppColors.accent, w: 5);
    // 동전 (₩)
    circle(76, 76, 15, AppColors.amber);
    circle(76, 76, 10.5, AppColors.amberSoft, stroke: false);
    final w = Path()
      ..moveTo(69.5 * _k, 70 * _k)
      ..lineTo(72.5 * _k, 82 * _k)
      ..lineTo(76 * _k, 73 * _k)
      ..lineTo(79.5 * _k, 82 * _k)
      ..lineTo(82.5 * _k, 70 * _k);
    _c.drawPath(w, line);
    _c.drawLine(p(68.5, 76), p(83.5, 76), line);
  }

  // 약국 봉투 + 캡슐 + 알약
  void _medicine() {
    shadow(50, 95, 66);
    final bag = Path()
      ..moveTo(24 * _k, 28 * _k)
      ..lineTo(76 * _k, 28 * _k)
      ..lineTo(73 * _k, 91 * _k)
      ..lineTo(27 * _k, 91 * _k)
      ..close();
    shape(bag, AppColors.surface);
    // 접힌 윗부분
    final fold = Path()
      ..moveTo(22 * _k, 14 * _k)
      ..lineTo(78 * _k, 14 * _k)
      ..lineTo(76 * _k, 28 * _k)
      ..lineTo(24 * _k, 28 * _k)
      ..close();
    shape(fold, AppColors.accentMid);
    bar(30, 70, 21, AppColors.outline.withValues(alpha: 0.35), w: 2);
    // 라벨 + 십자
    rrect(35, 44, 65, 74, 5, AppColors.accentSoft, stroke: false);
    rrect(46.5, 50, 53.5, 68, 1.5, AppColors.accent, stroke: false);
    rrect(41, 55.5, 59, 62.5, 1.5, AppColors.accent, stroke: false);
    // 캡슐
    _c.save();
    _c.translate(80 * _k, 80 * _k);
    _c.rotate(-math.pi / 4.5);
    final cap = RRect.fromRectAndRadius(Rect.fromCenter(center: Offset.zero, width: 28 * _k, height: 12 * _k),
        Radius.circular(6 * _k));
    _c.drawRRect(cap, fill(AppColors.surface));
    _c.save();
    _c.clipRect(Rect.fromLTRB(0, -8 * _k, 16 * _k, 8 * _k));
    _c.drawRRect(cap, fill(AppColors.amber));
    _c.restore();
    _c.drawRRect(cap, line);
    _c.drawLine(Offset(0, -6 * _k), Offset(0, 6 * _k), line);
    _c.restore();
    // 둥근 알약
    circle(18, 84, 8, AppColors.surface);
    _c.drawLine(p(13, 84), p(23, 84), line);
  }

  // 병원 건물 + 간판 십자
  void _hospital() {
    shadow(50, 94, 76);
    rrect(18, 36, 82, 92, 2, AppColors.surface);
    final roof = Path()..addRect(r(18, 36, 82, 46));
    _c.drawPath(roof, fill(AppColors.accentMid));
    _c.drawRRect(RRect.fromRectAndRadius(r(18, 36, 82, 92), Radius.circular(2 * _k)), line);
    _c.drawLine(p(18, 46), p(82, 46), line);
    // 간판
    circle(50, 24, 13, AppColors.surface);
    rrect(47, 16, 53, 32, 1.2, AppColors.coral, stroke: false);
    rrect(42, 21, 58, 27, 1.2, AppColors.coral, stroke: false);
    _c.drawLine(p(50, 37), p(50, 37), line);
    // 창문
    for (final y in [52.0, 64.0]) {
      for (final x in [25.0, 59.0, 71.0]) {
        rrect(x - 4, y, x + 4, y + 7, 1, AppColors.accentSoft);
      }
    }
    rrect(36, 52, 44, 59, 1, AppColors.accentSoft);
    rrect(36, 64, 44, 71, 1, AppColors.accentSoft);
    // 문
    rrect(43, 74, 57, 92, 1, AppColors.accent);
    _c.drawLine(p(50, 74), p(50, 92), Paint()
      ..color = AppColors.accentMid
      ..strokeWidth = 1.6 * _k);
  }

  // 모서리 접힌 종이 (+ 관공서 도장)
  void _paper({required bool stamp}) {
    shadow(50, 94, 60);
    final body = Path()
      ..moveTo(24 * _k, 8 * _k)
      ..lineTo(62 * _k, 8 * _k)
      ..lineTo(78 * _k, 24 * _k)
      ..lineTo(78 * _k, 90 * _k)
      ..lineTo(24 * _k, 90 * _k)
      ..close();
    shape(body, AppColors.surface);
    final corner = Path()
      ..moveTo(62 * _k, 8 * _k)
      ..lineTo(62 * _k, 24 * _k)
      ..lineTo(78 * _k, 24 * _k)
      ..close();
    shape(corner, AppColors.accentSoft);
    bar(32, 52, 22, AppColors.accent, w: 5);
    bar(32, 70, 36, AppColors.line);
    bar(32, 66, 46, AppColors.line);
    bar(32, 70, 56, AppColors.line);
    bar(32, 54, 66, AppColors.line);
    if (stamp) {
      circle(64, 76, 10, AppColors.coral.withValues(alpha: 0.18), stroke: false);
      _c.drawCircle(p(64, 76), 10 * _k, Paint()
        ..color = AppColors.coral
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4 * _k);
      _c.drawCircle(p(64, 76), 3 * _k, fill(AppColors.coral));
    }
  }

  // 계약서 + 펜
  void _contract() {
    _paper(stamp: false);
    final sig = Path()
      ..moveTo(32 * _k, 80 * _k)
      ..cubicTo(38 * _k, 70 * _k, 42 * _k, 86 * _k, 48 * _k, 78 * _k)
      ..cubicTo(52 * _k, 73 * _k, 54 * _k, 82 * _k, 58 * _k, 79 * _k);
    _c.drawPath(sig, line);
    _c.save();
    _c.translate(74 * _k, 66 * _k);
    _c.rotate(math.pi / 5);
    _c.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(-4 * _k, -22 * _k, 8 * _k, 30 * _k), Radius.circular(2 * _k)),
        fill(AppColors.amber));
    _c.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(-4 * _k, -22 * _k, 8 * _k, 30 * _k), Radius.circular(2 * _k)),
        line);
    final tip = Path()
      ..moveTo(-4 * _k, 8 * _k)
      ..lineTo(4 * _k, 8 * _k)
      ..lineTo(0, 15 * _k)
      ..close();
    shape(tip, AppColors.surface);
    _c.restore();
  }

  // 달력 + 체크 (빈 할 일)
  void _calendar() {
    shadow(48, 94, 70);
    rrect(14, 18, 78, 88, 6, AppColors.surface);
    final top = Path()
      ..addRRect(RRect.fromRectAndCorners(r(14, 18, 78, 34),
          topLeft: Radius.circular(6 * _k), topRight: Radius.circular(6 * _k)));
    _c.drawPath(top, fill(AppColors.accent));
    _c.drawRRect(RRect.fromRectAndRadius(r(14, 18, 78, 88), Radius.circular(6 * _k)), line);
    for (final x in [28.0, 64.0]) {
      rrect(x - 2.5, 10, x + 2.5, 24, 2.5, AppColors.surface);
    }
    for (var row = 0; row < 3; row++) {
      for (var col = 0; col < 4; col++) {
        circle(24 + col * 14.0, 46 + row * 13.0, 3, AppColors.line, stroke: false);
      }
    }
    circle(76, 76, 15, AppColors.accentMid);
    final ck = Path()
      ..moveTo(69 * _k, 76 * _k)
      ..lineTo(74 * _k, 81 * _k)
      ..lineTo(83 * _k, 71 * _k);
    _c.drawPath(ck, line..strokeWidth = 3.4 * _k);
  }

  // 서류 담긴 폴더 (빈 지난 서류)
  void _folder() {
    shadow(50, 94, 76);
    final back = Path()
      ..moveTo(12 * _k, 26 * _k)
      ..lineTo(38 * _k, 26 * _k)
      ..lineTo(44 * _k, 32 * _k)
      ..lineTo(88 * _k, 32 * _k)
      ..lineTo(88 * _k, 88 * _k)
      ..lineTo(12 * _k, 88 * _k)
      ..close();
    shape(back, AppColors.accentMid);
    rrect(24, 18, 70, 66, 2, AppColors.surface);
    bar(32, 58, 30, AppColors.line);
    bar(32, 62, 40, AppColors.line);
    final front = Path()
      ..moveTo(8 * _k, 46 * _k)
      ..lineTo(92 * _k, 46 * _k)
      ..lineTo(86 * _k, 88 * _k)
      ..lineTo(14 * _k, 88 * _k)
      ..close();
    shape(front, AppColors.accentSoft);
    bar(40, 60, 62, AppColors.accent, w: 5);
  }

  // 화분 (인사 카드)
  void _plant() {
    final leafL = Path()
      ..moveTo(50 * _k, 56 * _k)
      ..cubicTo(30 * _k, 54 * _k, 22 * _k, 36 * _k, 26 * _k, 24 * _k)
      ..cubicTo(42 * _k, 26 * _k, 52 * _k, 40 * _k, 50 * _k, 56 * _k)
      ..close();
    shape(leafL, AppColors.accentMid);
    final leafR = Path()
      ..moveTo(50 * _k, 56 * _k)
      ..cubicTo(52 * _k, 36 * _k, 64 * _k, 18 * _k, 80 * _k, 16 * _k)
      ..cubicTo(82 * _k, 34 * _k, 70 * _k, 52 * _k, 50 * _k, 56 * _k)
      ..close();
    shape(leafR, AppColors.accent);
    final pot = Path()
      ..moveTo(30 * _k, 58 * _k)
      ..lineTo(70 * _k, 58 * _k)
      ..lineTo(64 * _k, 90 * _k)
      ..lineTo(36 * _k, 90 * _k)
      ..close();
    shape(pot, AppColors.amber);
    rrect(27, 54, 73, 64, 2, AppColors.amberSoft);
  }

  @override
  bool shouldRepaint(_IlloPainter old) => old.kind != kind;
}

/// 스캔 모서리 괄호 [ ] (서류 찍기 버튼, 분석 화면)
class ScanBrackets extends StatelessWidget {
  const ScanBrackets({super.key, required this.child, this.color = AppColors.onAccent, this.padding = 20});
  final Widget child;
  final Color color;
  final double padding;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _BracketPainter(color),
      child: Padding(padding: EdgeInsets.all(padding), child: child),
    );
  }
}

class _BracketPainter extends CustomPainter {
  _BracketPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size s) {
    final pt = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final l = math.min(s.width, s.height) * 0.22;
    const o = 2.5;
    void corner(double x, double y, double dx, double dy) {
      final path = Path()
        ..moveTo(x, y + dy * l)
        ..lineTo(x, y + dy * 6)
        ..quadraticBezierTo(x, y, x + dx * 6, y)
        ..lineTo(x + dx * l, y);
      canvas.drawPath(path, pt);
    }

    corner(o, o, 1, 1);
    corner(s.width - o, o, -1, 1);
    corner(o, s.height - o, 1, -1);
    corner(s.width - o, s.height - o, -1, -1);
  }

  @override
  bool shouldRepaint(_BracketPainter old) => old.color != color;
}

/// 서류 찍기 버튼 안의 큰 카메라 (흰 선 그림)
class CameraDrawing extends StatelessWidget {
  const CameraDrawing({super.key, this.size = 120});
  final double size;

  @override
  Widget build(BuildContext context) =>
      ExcludeSemantics(child: CustomPaint(size: Size(size, size * 0.8), painter: _CameraPainter()));
}

class _CameraPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final k = s.width / 100;
    final white = Paint()..color = AppColors.ink;
    final soft = Paint()..color = AppColors.canvas;
    final ink = Paint()..color = AppColors.ink;
    // 윗 혹
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTRB(32 * k, 6 * k, 64 * k, 22 * k), Radius.circular(5 * k)), white);
    // 몸체
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTRB(6 * k, 16 * k, 94 * k, 78 * k), Radius.circular(12 * k)), white);
    // 렌즈
    final c = Offset(50 * k, 47 * k);
    canvas.drawCircle(c, 23 * k, ink);
    canvas.drawCircle(c, 17 * k, soft);
    canvas.drawCircle(c, 10 * k, ink);
    canvas.drawCircle(Offset(45 * k, 42 * k), 3.5 * k, white);
    // 플래시
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTRB(76 * k, 24 * k, 86 * k, 31 * k), Radius.circular(2 * k)), soft);
  }

  @override
  bool shouldRepaint(_CameraPainter old) => false;
}
