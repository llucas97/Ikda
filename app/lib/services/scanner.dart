import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';

import '../screens/analyzing_screen.dart';
import 'capture_flow.dart';
import 'image_source_io.dart' if (dart.library.js_interop) 'image_source_web.dart' as source;

/// 서류 사진을 받는다. 모바일은 문서 스캐너, 웹은 사진 파일 고르기.
/// 취소하면 null, 실패하면 안내 메시지를 띄우고 null.
Future<List<XFile>?> scanDocument(BuildContext context) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    return await source.pickDocumentImages();
  } catch (e) {
    if (kDebugMode && !kIsWeb) {
      // 에뮬레이터 등 카메라가 없는 환경에서는 사진 없이 가짜 분석으로 화면만 확인
      debugPrint('scanner unavailable: $e');
      return const [];
    }
    messenger.showSnackBar(
      const SnackBar(
        content: Text(kIsWeb ? '사진을 열 수 없어요.\n다시 골라 주세요.' : '카메라를 열 수 없어요.\n설정에서 카메라 허용을 눌러주세요.'),
      ),
    );
    return null;
  }
}

/// 홈에서 호출: 찍고 → 품질 확인 → 분석.
Future<void> startDocumentCapture(BuildContext context) async {
  final nav = Navigator.of(context);
  final images = await scanDocument(context);
  if (images == null || !context.mounted) return;
  if (images.isEmpty) {
    await nav.push(MaterialPageRoute<void>(builder: (_) => const AnalyzingScreen(images: [])));
    return;
  }
  await runCapture(context, images, fromScanner: !kIsWeb);
}

/// 사진첩에서 여러 장. 스캐너 잘림 안내는 하지 않는다.
Future<void> startGalleryCapture(BuildContext context) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    final images = await source.pickGalleryImages();
    if (images == null || !context.mounted) return;
    await runCapture(context, images, fromScanner: false);
  } catch (e) {
    debugPrint('gallery: $e');
    messenger.showSnackBar(const SnackBar(content: Text('사진을 열 수 없어요.\n다시 골라 주세요.')));
  }
}
