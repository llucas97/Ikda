import 'dart:async';
import 'dart:io';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';

import '../services/analysis_service.dart';
import '../services/photo_quality.dart';
import '../services/scanner.dart';
import '../state/app_store.dart';
import '../theme.dart';
import '../utils/keep_all.dart';
import '../widgets/illustrations.dart';
import '../widgets/ph_icons.dart';
import 'result_screen.dart';
import 'retake_screen.dart';

/// 분석 중: 큰 그림 + 3단계 + 진행 막대. 위치가 고정돼 흔들리지 않는다.
class AnalyzingScreen extends StatefulWidget {
  const AnalyzingScreen({super.key, required this.images, this.linkId, this.save = false});
  final List<XFile> images;
  final int? linkId;
  final bool save;

  @override
  State<AnalyzingScreen> createState() => _AnalyzingScreenState();
}

class _AnalyzingScreenState extends State<AnalyzingScreen> {
  static const _steps = ['서류 분류', '내용 분석', '결과 안내'];

  int _step = 0;
  Timer? _timer;
  String? _error;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 1400), (_) {
      if (_step < _steps.length - 1) setState(() => _step++);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  Future<void> _run() async {
    setState(() {
      _error = null;
      _step = 0;
    });
    try {
      final result = await AppScope.read(context).analyze(
        widget.images,
        linkId: widget.linkId,
        save: widget.save,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(builder: (_) => ResultScreen(result: result)),
      );
    } on AnalysisException catch (e) {
      if (e.blocksSend && mounted) {
        final choice = await Navigator.of(context).push<RetakeChoice>(MaterialPageRoute(
          builder: (_) => RetakeScreen(
            page: e.page ?? 1,
            total: widget.images.length,
            problem: PhotoProblem(e.code!, e.userMessage),
            allowAnyway: false,
          ),
        ));
        if (!mounted) return;
        if (choice == RetakeChoice.retake) {
          final images = await scanDocument(context);
          if (images == null || !mounted) return;
          Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
            builder: (_) => AnalyzingScreen(images: images, linkId: widget.linkId, save: widget.save),
          ));
        }
        return;
      }
      if (mounted) setState(() => _error = e.userMessage);
    } catch (_) {
      if (mounted) setState(() => _error = '잠시 문제가 생겼어요.\n조금 뒤에 다시 해 주세요.');
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final failed = _error != null;
    return Scaffold(
      appBar: AppBar(title: Text(failed ? '다시 찍어 주세요' : '서류 읽는 중')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Space.s16, Space.s8, Space.s16, Space.s24),
          children: failed ? _errorBody() : _loadingBody(),
        ),
      ),
      bottomNavigationBar: _BottomArea(
        child: failed
            ? FilledButton.icon(
                icon: const Icon(PhosphorIconsBold.camera, size: 28),
                label: const Text('다시 찍기'),
                onPressed: () async {
                  final nav = Navigator.of(context);
                  final images = await scanDocument(context);
                  if (images == null) return;
                  nav.pushReplacement(
                    MaterialPageRoute<void>(
                        builder: (_) => AnalyzingScreen(images: images, linkId: widget.linkId, save: widget.save)),
                  );
                },
              )
            : FilledButton.icon(
                onPressed: null,
                icon: const Icon(PhosphorIconsBold.hourglassMedium, size: 28),
                label: const Text('잠시만'),
              ),
      ),
    );
  }

  List<Widget> _loadingBody() => [
        // 큰 그림 판
        Container(
          height: 280,
          decoration: BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(Radii.r24)),
          alignment: Alignment.center,
          child: widget.images.isNotEmpty
              ? ClipRRect(
                  borderRadius: BorderRadius.circular(Radii.r12),
                  // 웹은 blob: 주소, 모바일은 파일 경로
                  child: kIsWeb
                      ? Image.network(widget.images.first.path, height: 220, fit: BoxFit.cover)
                      : Image.file(File(widget.images.first.path), height: 220, fit: BoxFit.cover),
                )
              : const ScanBrackets(
                  color: AppColors.accent,
                  padding: 20,
                  child: _ScanningDoc(size: 168),
                ),
        ),
        const SizedBox(height: Space.s24),
        _Stepper(steps: _steps, current: _step),
        const SizedBox(height: Space.s24),
        // 기다림 안내 + 진행 막대
        Container(
          padding: const EdgeInsets.all(Space.s24),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(Radii.r16),
            border: Border.all(color: AppColors.line),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('잠시만 기다려 주세요'.keepAll, style: AppText.heading2),
            const SizedBox(height: Space.s16),
            ClipRRect(
              borderRadius: BorderRadius.circular(Radii.r8),
              child: TweenAnimationBuilder<double>(
                tween: Tween(end: (_step + 1) / (_steps.length + 0.5)),
                duration: const Duration(milliseconds: 1200),
                curve: kEase,
                builder: (_, v, __) => LinearProgressIndicator(
                  value: v,
                  minHeight: 12,
                  backgroundColor: AppColors.accentSoft,
                  color: AppColors.accent,
                ),
              ),
            ),
          ]),
        ),
      ];

  List<Widget> _errorBody() => [
        Container(
          height: 240,
          decoration: BoxDecoration(color: AppColors.warnBg, borderRadius: BorderRadius.circular(Radii.r24)),
          alignment: Alignment.center,
          child: const Illustration(Illo.paper, size: 140),
        ),
        const SizedBox(height: Space.s24),
        Text(_error!.keepAll, style: AppText.heading2, textAlign: TextAlign.center),
        const SizedBox(height: Space.s24),
        OutlinedButton(onPressed: _run, child: const Text('이 사진으로 다시')),
      ];
}

class _BottomArea extends StatelessWidget {
  const _BottomArea({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.surface,
      child: SafeArea(
        top: false,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Divider(),
          Padding(padding: const EdgeInsets.all(Space.s16), child: child),
        ]),
      ),
    );
  }
}

/// ●───○───○  가로 3단계
class _Stepper extends StatelessWidget {
  const _Stepper({required this.steps, required this.current});
  final List<String> steps;
  final int current;

  @override
  Widget build(BuildContext context) {
    Widget dot(int i) {
      final done = i < current;
      final now = i == current;
      return AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: kEase,
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: done ? AppColors.accent : AppColors.surface,
          border: Border.all(
            color: done || now ? AppColors.accent : AppColors.control,
            width: now ? 4 : 2,
          ),
        ),
        alignment: Alignment.center,
        child: done
            ? const Icon(PhosphorIconsBold.check, size: 26, color: AppColors.onAccent)
            : Text('${i + 1}',
                style: AppText.title.copyWith(color: now ? AppColors.accent : AppColors.inkSub)),
      );
    }

    return Column(children: [
      Row(children: [
        for (var i = 0; i < steps.length; i++) ...[
          if (i > 0)
            Expanded(
              child: Container(height: 4, color: i <= current ? AppColors.accent : AppColors.line),
            ),
          SizedBox(width: 72, child: Center(child: dot(i))),
        ],
      ]),
      const SizedBox(height: Space.s8),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        for (var i = 0; i < steps.length; i++)
          SizedBox(
            width: 96,
            child: Text(
              steps[i].noBreak,
              textAlign: i == 0 ? TextAlign.left : i == steps.length - 1 ? TextAlign.right : TextAlign.center,
              style: AppText.caption.copyWith(
                color: i <= current ? AppColors.ink : AppColors.inkSub,
                fontWeight: i == current ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
          ),
      ]),
    ]);
  }
}

/// 서류 그림 위로 먹색 선이 오르내린다 (이 앱의 유일한 반복 움직임)
class _ScanningDoc extends StatefulWidget {
  const _ScanningDoc({required this.size});
  final double size;

  @override
  State<_ScanningDoc> createState() => _ScanningDocState();
}

class _ScanningDocState extends State<_ScanningDoc> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.size;
    final reduce = MediaQuery.of(context).disableAnimations;
    return SizedBox(
      width: s,
      height: s,
      child: Stack(children: [
        Illustration(Illo.paper, size: s),
        if (!reduce)
          AnimatedBuilder(
            animation: _c,
            builder: (_, __) => Transform.translate(
              offset: Offset(0, s * (0.12 + 0.7 * kEase.transform(_c.value))),
              child: Container(
                margin: EdgeInsets.symmetric(horizontal: s * 0.14),
                height: 5,
                decoration: BoxDecoration(color: AppColors.accent, borderRadius: BorderRadius.circular(3)),
              ),
            ),
          ),
      ]),
    );
  }
}
