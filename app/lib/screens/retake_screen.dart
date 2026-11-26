import 'dart:typed_data';

import 'package:material_ui/material_ui.dart';

import '../services/photo_quality.dart';
import '../services/speech.dart';
import '../theme.dart';
import '../utils/keep_all.dart';
import '../widgets/illustrations.dart';
import '../widgets/ph_icons.dart';

enum RetakeChoice { retake, sendAnyway, cancel }

/// 사진이 흔들리거나 어두울 때. 큰 그림, 한 문장, 다시 찍기 / 그래도 보내기.
class RetakeScreen extends StatefulWidget {
  const RetakeScreen({
    super.key,
    required this.page,
    required this.total,
    required this.problem,
    required this.allowAnyway,
    this.thumbnail,
  });

  final int page;
  final int total;
  final PhotoProblem problem;
  final bool allowAnyway;
  final Uint8List? thumbnail;

  @override
  State<RetakeScreen> createState() => _RetakeScreenState();
}

class _RetakeScreenState extends State<RetakeScreen> {
  final _speech = Speech();

  @override
  void initState() {
    super.initState();
    _speech.init(onDone: () {});
  }

  @override
  void dispose() {
    _speech.stop();
    super.dispose();
  }

  String get _sentence {
    final base = widget.problem.message;
    return widget.total > 1 ? '${widget.page}번째 사진: $base' : base;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('다시 찍어 주세요')),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(Space.s16, Space.s8, Space.s16, Space.s16),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight - Space.s24),
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  if (widget.thumbnail != null) ...[
                    ClipRRect(
                      borderRadius: BorderRadius.circular(Radii.r16),
                      child: Image.memory(widget.thumbnail!, height: 160, width: double.infinity, fit: BoxFit.cover),
                    ),
                    const SizedBox(height: Space.s12),
                  ],
                  Illustration(illoForProblem(widget.problem.code), size: widget.thumbnail == null ? 140 : 96),
                  const SizedBox(height: Space.s12),
                  Text(_sentence.keepAll, textAlign: TextAlign.center, style: AppText.heading2),
                  TextButton.icon(
                    onPressed: () => _speech.speak(_sentence),
                    icon: const Icon(PhosphorIconsBold.speakerHigh, size: 28),
                    label: const Text('읽어 주기'),
                  ),
                ]),
              ),
            );
          },
        ),
      ),
      bottomNavigationBar: ColoredBox(
        color: AppColors.canvas,
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(Space.s16),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              FilledButton(
                onPressed: () => Navigator.pop(context, RetakeChoice.retake),
                child: const Text('다시 찍기'),
              ),
              if (widget.allowAnyway) ...[
                const SizedBox(height: Space.s12),
                OutlinedButton(
                  onPressed: () => Navigator.pop(context, RetakeChoice.sendAnyway),
                  child: const Text('그래도 보내기'),
                ),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}
