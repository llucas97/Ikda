import 'package:cross_file/cross_file.dart';

/// pdfrx 가 없는 환경. PDF 는 넘기지 않는다.
Future<List<XFile>> pdfToJpegs(XFile file) async => const [];
