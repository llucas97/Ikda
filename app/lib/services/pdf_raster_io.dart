import 'dart:io';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as im;
import 'package:pdfrx/pdfrx.dart';

/// PDF 는 서버가 사진을 받으므로 쪽에서 최대 5장을 JPEG 로 그린다. 150dpi 근처.
Future<List<XFile>> pdfToJpegs(XFile file) async {
  try {
    final data = await file.readAsBytes();
    final doc = await PdfDocument.openData(data);
    final out = <XFile>[];
    final n = doc.pages.length < 5 ? doc.pages.length : 5;
    for (var i = 0; i < n; i++) {
      final page = doc.pages[i];
      final scale = 150 / 72;
      final rendered = await page.render(
        fullWidth: page.width * scale,
        fullHeight: page.height * scale,
        backgroundColor: 0xFFFFFFFF,
      );
      if (rendered == null) continue;
      final image = im.Image.fromBytes(
        width: rendered.width,
        height: rendered.height,
        bytes: rendered.pixels.buffer,
        numChannels: 4,
        order: im.ChannelOrder.rgba,
      );
      final jpg = im.encodeJpg(image, quality: 85);
      final path = '${Directory.systemTemp.path}/ikda_pdf_${DateTime.now().microsecondsSinceEpoch}_$i.jpg';
      await File(path).writeAsBytes(jpg, flush: true);
      rendered.dispose();
      out.add(XFile(path, mimeType: 'image/jpeg', name: 'page${i + 1}.jpg'));
    }
    doc.dispose();
    return out;
  } catch (e) {
    debugPrint('pdf render: $e');
    return const [];
  }
}
