import 'package:image_picker/image_picker.dart';

/// 웹: 스캐너가 없으니 사진 파일을 고른다 (최대 5장). 취소하면 null.
Future<List<XFile>?> pickDocumentImages() async {
  final files = await ImagePicker().pickMultiImage(limit: 5, imageQuality: 85, maxWidth: 2000);
  return files.isEmpty ? null : files;
}

Future<List<XFile>?> pickGalleryImages() => pickDocumentImages();
