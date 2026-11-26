/// PDF → JPEG. 기기(io)에서만 pdfrx 를 불러 오고, 웹·그 밖은 빈 목록이다.
/// `flutter test` 가 이 파일을 임포트해도, io 가 있는 VM 은 구현 파일을 컴파일한다.
/// 리눅스에서 플러그인 네이티브 빌드가 Clang 을 요구하는 이유는 README 를 본다.
export 'pdf_raster_stub.dart' if (dart.library.io) 'pdf_raster_io.dart';
