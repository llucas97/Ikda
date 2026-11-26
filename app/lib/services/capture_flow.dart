import 'dart:typed_data';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';

import '../models/family_link.dart';
import '../screens/analyzing_screen.dart';
import '../screens/retake_screen.dart';
import '../state/app_store.dart';
import '../theme.dart';
import 'photo_quality.dart';
import 'scanner.dart';
import 'share_intake_io.dart' if (dart.library.js_interop) 'share_intake_web.dart' as files;

/// 스캐너·공유·사진첩이 같은 길로 들어온다.
/// 품질 검사 → (문제면 다시 찍기) → 누구 서류인지 → 분석.
Future<void> runCapture(BuildContext context, List<XFile> images, {required bool fromScanner}) async {
  if (images.isEmpty) return;
  final checked = await _gate(context, images, fromScanner: fromScanner);
  if (checked == null || !context.mounted) return;
  final store = AppScope.read(context);
  final targets = store.links.where((l) => l.canSend).toList();
  int? linkId;
  if (targets.isNotEmpty) {
    final picked = await showDocumentOwner(context, targets);
    if (picked == null || !context.mounted) {
      await _cleanup(checked);
      return;
    }
    linkId = picked.linkId;
  }
  final loggedIn = AppScope.authOf(context).user != null;
  await Navigator.of(context).push(MaterialPageRoute<void>(
    builder: (_) => AnalyzingScreen(images: checked, linkId: linkId, save: loggedIn && linkId == null),
  ));
  await _cleanup(checked);
}

Future<List<XFile>?> _gate(BuildContext context, List<XFile> images, {required bool fromScanner}) async {
  final problems = <({int page, PhotoProblem problem, Uint8List? thumb})>[];
  for (var i = 0; i < images.length; i++) {
    final bytes = await images[i].readAsBytes();
    final metrics = await measurePhotoAsync(bytes);
    if (metrics == null) continue;
    final found = appProblems(metrics, fromScanner: fromScanner);
    if (found.isEmpty) continue;
    problems.add((page: i + 1, problem: found.first, thumb: bytes));
  }
  if (problems.isEmpty) return images;
  if (!context.mounted) return null;
  final first = problems.first;
  final result = await Navigator.of(context).push<RetakeChoice>(MaterialPageRoute(
    builder: (_) => RetakeScreen(
      page: first.page,
      total: images.length,
      problem: first.problem,
      thumbnail: first.thumb,
      allowAnyway: true,
    ),
  ));
  if (result == null || result == RetakeChoice.cancel) return null;
  if (result == RetakeChoice.retake) {
    if (!context.mounted) return null;
    final again = await scanDocument(context);
    if (again == null || again.isEmpty) return null;
    return _gate(context, again, fromScanner: true);
  }
  return images;
}

Future<void> _cleanup(List<XFile> images) async {
  if (kIsWeb) return;
  await files.deleteTempFiles(images);
}

/// 시트를 닫으면 null. 내 서류는 linkId 가 null 인 선택.
Future<OwnerPick?> showDocumentOwner(BuildContext context, List<FamilyLink> targets) {
  return showModalBottomSheet<OwnerPick>(
    context: context,
    backgroundColor: AppColors.canvas,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(Radii.r24))),
    builder: (ctx) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.s16, Space.s24, Space.s16, Space.s16),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('누구 서류인가요?', style: AppText.heading2),
          const SizedBox(height: Space.s16),
          FilledButton(onPressed: () => Navigator.pop(ctx, const OwnerPick.mine()), child: const Text('내 서류')),
          const SizedBox(height: Space.s12),
          for (final link in targets) ...[
            OutlinedButton(
              onPressed: () => Navigator.pop(ctx, OwnerPick.family(link.linkId)),
              child: Text('${link.display} 서류'),
            ),
            const SizedBox(height: Space.s12),
          ],
        ]),
      ),
    ),
  );
}

class OwnerPick {
  const OwnerPick.mine() : linkId = null;
  const OwnerPick.family(this.linkId);
  final int? linkId;
}
