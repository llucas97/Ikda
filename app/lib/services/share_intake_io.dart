import 'dart:io';

import 'package:cross_file/cross_file.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';

import 'pdf_raster.dart' as pdf;

Future<List<XFile>> initialShared() async {
  final files = await ReceiveSharingIntent.instance.getInitialMedia();
  return _convert(files);
}

Stream<List<XFile>> sharedStream() =>
    ReceiveSharingIntent.instance.getMediaStream().asyncMap(_convert);

Future<void> resetShared() => ReceiveSharingIntent.instance.reset();

Future<List<XFile>> _convert(List<SharedMediaFile> files) async {
  final out = <XFile>[];
  for (final file in files) {
    final path = file.path;
    final lower = path.toLowerCase();
    if (lower.endsWith('.pdf') || file.mimeType == 'application/pdf') {
      out.addAll(await pdfToJpegs(XFile(path)));
    } else if (file.type == SharedMediaType.image || _isImage(lower)) {
      out.add(XFile(path, mimeType: file.mimeType));
    }
  }
  return out;
}

bool _isImage(String path) =>
    path.endsWith('.jpg') || path.endsWith('.jpeg') || path.endsWith('.png') || path.endsWith('.heic') || path.endsWith('.webp');

/// PDF 는 서버가 사진을 받으므로 쪽에서 JPEG 로 그린다. pdfrx 는 io 구현에만 있다.
Future<List<XFile>> pdfToJpegs(XFile file) => pdf.pdfToJpegs(file);

Future<void> deleteTempFiles(List<XFile> files) async {
  for (final file in files) {
    try {
      final f = File(file.path);
      if (await f.exists()) await f.delete();
    } catch (_) {}
  }
}
