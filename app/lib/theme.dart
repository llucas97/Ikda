import 'package:material_ui/material_ui.dart';

import 'widgets/ph_icons.dart';

/// 디자인 토큰 (읽다: 따뜻한 종이 + 먹색 + 형광 노랑).
///
/// - 바탕 #FFFDF8, 본문·주요 버튼은 먹색 #1F1D1A (글자는 종이색).
/// - 노랑 #F2C230 은 형광펜처럼 아껴 쓴다. 금액·날짜 밑줄, 선택, 촬영 버튼.
///   밝은 바탕 위에 노란 글자는 쓰지 않는다.
/// - 긴급은 따뜻한 빨강. 자주 쓰지 않는다.
/// - 글자 크기는 18 이상(18/20/24/30/36), 굵기는 Bold(700)까지.
/// - 간격 4·8·12·16·24·32·40·48, 모서리 8·12·16·24.
class AppColors {
  static const canvas = Color(0xFFFFFDF8); // 따뜻한 종이
  static const surface = Color(0xFFF5F2EA); // 카드
  static const ink = Color(0xFF1F1D1A); // 본문·주요 버튼 (종이 위 약 16:1)
  static const inkSub = Color(0xFF575551); // 보조 (종이 위 약 7.4:1)
  static const line = Color(0xFFE6E1D6); // 테두리
  static const control = Color(0xFF76726A); // 조작 테두리 (종이 위 약 4.6:1)

  static const accent = Color(0xFF1F1D1A); // 주요 동작 = 먹색
  static const accentPressed = Color(0xFF000000);
  static const accentSoft = Color(0xFFF5F2EA); // 보조 면. 노랑으로 넓게 칠하지 않는다
  static const accentMid = Color(0xFFC9C2B4); // 그림의 중간 톤
  static const onAccent = Color(0xFFFFFDF8);
  static const outline = Color(0xFF1F1D1A);

  /// 형광. 밑줄·선택·촬영 버튼 채움. 글자색으로 쓰지 말 것.
  static const highlight = Color(0xFFF2C230);
  static const highlightPressed = Color(0xFFDDAE1F);
  static const highlightSoft = Color(0xFFFDF3D3);

  static const urgent = Color(0xFFC0392B); // 흰·종이 위 약 5.4:1 (큰 글자)
  static const urgentSoft = Color(0xFFF9E3DF);
  static const warnText = Color(0xFF8E2A1F); // 연한 빨강 위 약 7:1
  static const warnBg = Color(0xFFF9E3DF);
  static const warnLine = Color(0xFFE2B2A8);
  static const amber = highlight;
  static const amberSoft = highlightSoft;
  static const coral = urgent;
  static const neutralSoft = Color(0xFFF5F2EA);
}

class Space {
  static const s4 = 4.0, s8 = 8.0, s12 = 12.0, s16 = 16.0, s24 = 24.0;
  static const s32 = 32.0, s40 = 40.0, s48 = 48.0;
}

class Radii {
  static const r8 = 8.0, r12 = 12.0, r16 = 16.0, r24 = 24.0;
}

const kFont = 'IBMPlexSansKR';
const kEase = Cubic(0.22, 1, 0.36, 1);
const kTabular = [FontFeature.tabularFigures()];

class AppText {
  static const display = TextStyle(fontFamily: kFont, fontSize: 36, height: 40 / 36,
      fontWeight: FontWeight.w700, color: AppColors.ink, letterSpacing: -0.6);
  static const heading1 = TextStyle(fontFamily: kFont, fontSize: 30, height: 36 / 30,
      fontWeight: FontWeight.w700, color: AppColors.ink, letterSpacing: -0.4);
  static const heading2 = TextStyle(fontFamily: kFont, fontSize: 24, height: 32 / 24,
      fontWeight: FontWeight.w700, color: AppColors.ink, letterSpacing: -0.2);
  static const title = TextStyle(fontFamily: kFont, fontSize: 20, height: 28 / 20,
      fontWeight: FontWeight.w700, color: AppColors.ink);
  static const body = TextStyle(fontFamily: kFont, fontSize: 20, height: 30 / 20,
      fontWeight: FontWeight.w500, color: AppColors.ink);
  static const caption = TextStyle(fontFamily: kFont, fontSize: 18, height: 28 / 18,
      fontWeight: FontWeight.w500, color: AppColors.inkSub);
  static const chip = TextStyle(fontFamily: kFont, fontSize: 18, height: 24 / 18,
      fontWeight: FontWeight.w700);
  static const button = TextStyle(fontFamily: kFont, fontSize: 20, height: 28 / 20,
      fontWeight: FontWeight.w700);
}

/// 금액·날짜처럼 눈에 띄어야 하는 숫자 밑의 형광 막대.
class HighlightMark extends StatelessWidget {
  const HighlightMark({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.highlight, width: 8)),
      ),
      child: child,
    );
  }
}

ThemeData buildAppTheme() {
  const scheme = ColorScheme.light(
    primary: AppColors.accent,
    onPrimary: AppColors.onAccent,
    secondary: AppColors.highlight,
    onSecondary: AppColors.ink,
    surface: AppColors.surface,
    onSurface: AppColors.ink,
    onSurfaceVariant: AppColors.inkSub,
    outline: AppColors.control,
    outlineVariant: AppColors.line,
    error: AppColors.urgent,
  );
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    fontFamily: kFont,
    scaffoldBackgroundColor: AppColors.canvas,
    splashFactory: InkRipple.splashFactory,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(fontFamily: kFont, bodyColor: AppColors.ink, displayColor: AppColors.ink),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.canvas,
      surfaceTintColor: Colors.transparent,
      foregroundColor: AppColors.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      toolbarHeight: 72,
      titleSpacing: 0,
      titleTextStyle: AppText.heading2,
      iconTheme: IconThemeData(size: 28, color: AppColors.ink),
    ),
    actionIconTheme: ActionIconThemeData(
      backButtonIconBuilder: (_) => const Icon(PhosphorIconsBold.arrowLeft, size: 28),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(64),
        padding: const EdgeInsets.symmetric(horizontal: Space.s16, vertical: Space.s12),
        backgroundColor: AppColors.accent,
        foregroundColor: AppColors.onAccent,
        disabledBackgroundColor: AppColors.accentSoft,
        disabledForegroundColor: AppColors.inkSub,
        textStyle: AppText.button,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.r16)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(64),
        padding: const EdgeInsets.symmetric(horizontal: Space.s16, vertical: Space.s12),
        backgroundColor: AppColors.canvas,
        foregroundColor: AppColors.ink,
        surfaceTintColor: Colors.transparent,
        side: const BorderSide(color: AppColors.ink, width: 2),
        textStyle: AppText.button,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.r16)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(56, 48),
        foregroundColor: AppColors.ink,
        textStyle: AppText.caption.copyWith(fontWeight: FontWeight.w700),
      ),
    ),
    dividerTheme: const DividerThemeData(color: AppColors.line, thickness: 1, space: 1),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.canvas,
      modalBackgroundColor: AppColors.canvas,
      surfaceTintColor: Colors.transparent,
    ),
    dialogTheme: const DialogThemeData(
      backgroundColor: AppColors.canvas,
      surfaceTintColor: Colors.transparent,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.ink,
      contentTextStyle: AppText.body.copyWith(color: AppColors.onAccent),
      actionTextColor: AppColors.highlight,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.r12)),
    ),
  );
}
