import 'package:cross_file/cross_file.dart';
import 'package:cunning_document_scanner/cunning_document_scanner.dart';
import 'package:image_picker/image_picker.dart';

/// 모바일: 문서 스캐너(테두리 인식 → 자동 촬영 → 기울기/그림자 보정).
/// 취소하면 null.
Future<List<XFile>?> pickDocumentImages() async {
  final result = await CunningDocumentScanner.scanDocuments(noOfPages: 5);
  if (result == null) return null;
  return result.images.map(XFile.new).toList();
}

/// 사진첩. 최대 5장. 취소하면 null.
Future<List<XFile>?> pickGalleryImages() async {
  final files = await ImagePicker().pickMultiImage(limit: 5, imageQuality: 85, maxWidth: 2000);
  return files.isEmpty ? null : files;
}
