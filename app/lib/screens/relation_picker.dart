import 'package:material_ui/material_ui.dart';

import '../theme.dart';
import '../widgets/ph_icons.dart';

/// 어르신이 크게 고르는 관계. 노란 테두리는 고른 칸만.
/// 칸을 낮춰 412×915 한 화면에 질문·별명·버튼과 함께 들어가게 한다.
class RelationPicker extends StatelessWidget {
  const RelationPicker({super.key, required this.options, required this.selected, required this.onPick});

  final List<(String, String)> options;
  final String? selected;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: Space.s8,
      crossAxisSpacing: Space.s8,
      childAspectRatio: 1.72,
      children: [
        for (final (code, label) in options)
          _Cell(code: code, label: label, selected: selected == code, onTap: () => onPick(code)),
      ],
    );
  }
}

class _Cell extends StatelessWidget {
  const _Cell({required this.code, required this.label, required this.selected, required this.onTap});
  final String code;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: Material(
        color: selected ? AppColors.highlightSoft : AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radii.r16),
          side: BorderSide(color: selected ? AppColors.highlight : AppColors.line, width: selected ? 3 : 1),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(Radii.r16),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            RelationGlyph(code, size: 40),
            const SizedBox(height: Space.s4),
            Text(label, maxLines: 1, style: AppText.title),
          ]),
        ),
      ),
    );
  }
}

/// 관계마다 다른 단순한 먹색 그림. 기타는 점 세 개이고 빨간 점은 쓰지 않는다.
class RelationGlyph extends StatelessWidget {
  const RelationGlyph(this.code, {super.key, this.size = 40});
  final String code;
  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(painter: _RelationGlyphPainter(code)),
    );
  }
}

class _RelationGlyphPainter extends CustomPainter {
  _RelationGlyphPainter(this.code);
  final String code;

  @override
  void paint(Canvas canvas, Size size) {
    final k = size.shortestSide / 100;
    Offset p(double x, double y) => Offset(x * k, y * k);
    final ink = Paint()
      ..color = AppColors.ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.4 * k
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()..color = AppColors.ink;

    void head(double x, double y, double r) => canvas.drawCircle(p(x, y), r * k, fill);

    void skirt(double x, double top, double bottom, double half) {
      final path = Path()
        ..moveTo(p(x, top).dx, p(x, top).dy)
        ..lineTo(p(x - half, bottom).dx, p(x - half, bottom).dy)
        ..lineTo(p(x + half, bottom).dx, p(x + half, bottom).dy)
        ..close();
      canvas.drawPath(path, fill);
    }

    void legs(double x, double y, {double reach = 16}) {
      canvas.drawLine(p(x, y), p(x, y + 20), ink);
      canvas.drawLine(p(x, y + 20), p(x - reach, y + 40), ink);
      canvas.drawLine(p(x, y + 20), p(x + reach, y + 40), ink);
    }

    void hat(double x, double y) {
      canvas.drawLine(p(x - 16, y), p(x + 16, y), ink);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(center: p(x, y - 8), width: 18 * k, height: 10 * k),
          Radius.circular(2 * k),
        ),
        fill,
      );
    }

    void bun(double x, double y) => canvas.drawCircle(p(x, y), 6 * k, ink);
    void cane(double x) => canvas.drawLine(p(x, 46), p(x + 4, 90), ink);
    void ring(double x, double y) => canvas.drawCircle(p(x, y), 8 * k, ink);

    switch (code) {
      case 'DAUGHTER':
        head(50, 28, 12);
        skirt(50, 46, 90, 22);
      case 'SON':
        head(50, 24, 12);
        legs(50, 40);
      case 'DAUGHTER_IN_LAW':
        head(40, 28, 11);
        skirt(40, 46, 90, 18);
        ring(74, 58);
      case 'SON_IN_LAW':
        head(38, 24, 11);
        legs(38, 40, reach: 12);
        ring(76, 58);
      case 'GRANDCHILD':
        head(50, 34, 9);
        legs(50, 48, reach: 12);
      case 'SPOUSE':
        head(34, 38, 12);
        head(66, 38, 12);
        canvas.drawLine(p(34, 54), p(66, 54), ink);
      case 'MOTHER':
        bun(50, 12);
        head(50, 30, 12);
        skirt(50, 48, 92, 22);
      case 'FATHER':
        hat(50, 16);
        head(50, 32, 11);
        legs(50, 48);
      case 'GRANDMOTHER':
        bun(42, 14);
        head(42, 32, 11);
        skirt(42, 48, 90, 18);
        cane(72);
      case 'GRANDFATHER':
        hat(40, 14);
        head(40, 32, 11);
        legs(40, 48, reach: 12);
        cane(74);
      default:
        for (final x in [28.0, 50.0, 72.0]) {
          canvas.drawCircle(p(x, 50), 7 * k, fill);
        }
    }
  }

  @override
  bool shouldRepaint(_RelationGlyphPainter old) => old.code != code;
}

/// 별명. 비워도 된다.
class NicknameField extends StatelessWidget {
  const NicknameField({super.key, required this.controller, required this.hint});
  final TextEditingController controller;
  final String hint;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      style: AppText.title,
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: AppText.title.copyWith(color: AppColors.inkSub),
        filled: true,
        fillColor: AppColors.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: Space.s16, vertical: Space.s16),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(Radii.r16), borderSide: const BorderSide(color: AppColors.line)),
        prefixIcon: const Icon(PhosphorIconsBold.user, color: AppColors.ink),
      ),
    );
  }
}
