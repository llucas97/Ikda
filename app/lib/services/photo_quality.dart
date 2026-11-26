import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as im;

/// 서버 app/quality.py 와 같은 지표. 긴 변 1000px 흑백, 가장자리 3px 를 자른 뒤 8×8 칸.
/// 앱은 더 엄격하고, 어르신은 '그래도 보내기'를 고를 수 있다.
class PhotoMetrics {
  const PhotoMetrics({
    required this.width,
    required this.height,
    required this.sharpness,
    required this.mean,
    required this.clipped,
    required this.content,
    required this.edgeSides,
  });

  final int width;
  final int height;
  final double sharpness;
  final double mean;
  final double clipped;
  final double content;
  final int edgeSides;
}

class PhotoProblem {
  const PhotoProblem(this.code, this.message, {this.weak = false});
  final String code;
  final String message;
  /// 잘림처럼 막지 않고 안내만 하는 문제.
  final bool weak;
}

const photoMessages = {
  'photo_small': '사진이 너무 작아요. 서류에 조금 더 가까이 대고 다시 찍어 주세요.',
  'photo_dark': '사진이 너무 어두워요. 불을 켜거나 밝은 곳에서 다시 찍어 주세요.',
  'photo_bright': '빛이 반사돼서 글씨가 안 보여요. 형광등 바로 아래를 피해서 다시 찍어 주세요.',
  'photo_blank': '서류가 잘 안 보여요. 서류 전체가 화면에 나오게 다시 찍어 주세요.',
  'photo_blurry': '사진이 흔들렸어요. 휴대폰을 꼭 잡고 다시 찍어 주세요.',
  'photo_edge': '서류 끝이 잘렸을 수 있어요. 네 모서리가 다 보이게 다시 찍어 주세요.',
};

PhotoMetrics? measurePhoto(Uint8List bytes) {
  final decoded = im.decodeImage(bytes);
  if (decoded == null) return null;
  var img = im.grayscale(decoded);
  final longSide = math.max(img.width, img.height);
  if (longSide > 1000) {
    final scale = 1000 / longSide;
    img = im.copyResize(img, width: math.max(1, (img.width * scale).round()),
        height: math.max(1, (img.height * scale).round()), interpolation: im.Interpolation.linear);
  }
  final width = decoded.width;
  final height = decoded.height;
  if (img.width > 8 && img.height > 8) {
    img = im.copyCrop(img, x: 2, y: 2, width: img.width - 4, height: img.height - 4);
  }
  final lum = _luma(img);
  final lap = _laplacian(lum, img.width, img.height);
  // 커널이 가장자리 1px 을 그대로 두므로 한 줄 더 자른다.
  final inner = _crop1(lum, img.width, img.height);
  final lapInner = _crop1(lap, img.width, img.height);
  final w = inner.$2;
  final h = inner.$3;
  const grid = 8;
  final tileStd = <List<double>>[];
  final sharp = <double>[];
  for (var gy = 0; gy < grid; gy++) {
    final row = <double>[];
    for (var gx = 0; gx < grid; gx++) {
      final x0 = gx * w ~/ grid;
      final y0 = gy * h ~/ grid;
      final x1 = (gx + 1) * w ~/ grid;
      final y1 = (gy + 1) * h ~/ grid;
      if (x1 <= x0 || y1 <= y0) {
        row.add(0);
        continue;
      }
      final std = _std(inner.$1, w, x0, y0, x1, y1);
      row.add(std);
      if (std > 10) sharp.add(_variance(lapInner.$1, w, x0, y0, x1, y1));
    }
    tileStd.add(row);
  }
  final content = sharp.length / (grid * grid);
  sharp.sort();
  final sharpness = sharp.length > 1
      ? sharp[(sharp.length * 0.9).floor()]
      : (sharp.isEmpty ? 0.0 : sharp.first);
  var sum = 0.0;
  var clipped = 0;
  for (final v in inner.$1) {
    sum += v;
    if (v >= 250) clipped++;
  }
  final n = inner.$1.length;
  final mean = n == 0 ? 0.0 : sum / n;
  final sides = [
    tileStd.first,
    tileStd.last,
    [for (final r in tileStd) r.first],
    [for (final r in tileStd) r.last],
  ];
  final edgeSides = sides.where((s) => s.where((v) => v > 20).length >= grid * 0.75).length;
  return PhotoMetrics(
    width: width,
    height: height,
    sharpness: sharpness,
    mean: mean,
    clipped: n == 0 ? 0 : clipped / n,
    content: content,
    edgeSides: edgeSides,
  );
}

/// 앱 기준. [fromScanner] 일 때만 잘림을 약한 안내로 넣는다.
List<PhotoProblem> appProblems(PhotoMetrics m, {required bool fromScanner}) {
  final out = <PhotoProblem>[];
  if (math.min(m.width, m.height) < 400 || math.max(m.width, m.height) < 600) {
    out.add(PhotoProblem('photo_small', photoMessages['photo_small']!));
  }
  if (m.mean < 55) {
    out.add(PhotoProblem('photo_dark', photoMessages['photo_dark']!));
  } else if (m.mean > 240 && m.clipped > 0.85) {
    out.add(PhotoProblem('photo_bright', photoMessages['photo_bright']!));
  } else if (m.content < 0.05) {
    out.add(PhotoProblem('photo_blank', photoMessages['photo_blank']!));
  } else if (m.sharpness < 90) {
    out.add(PhotoProblem('photo_blurry', photoMessages['photo_blurry']!));
  }
  if (fromScanner && m.edgeSides >= 3 && out.isEmpty) {
    out.add(PhotoProblem('photo_edge', photoMessages['photo_edge']!, weak: true));
  }
  return out;
}

Future<PhotoMetrics?> measurePhotoAsync(Uint8List bytes) => compute(measurePhoto, bytes);

Uint8List _luma(im.Image img) {
  final out = Uint8List(img.width * img.height);
  var i = 0;
  for (final p in img) {
    out[i++] = (p.rNormalized * 255).round().clamp(0, 255);
  }
  return out;
}

/// Pillow Kernel (0,1,0 / 1,-4,1 / 0,1,0) scale 1, offset 128. 가장자리는 원래 값.
Uint8List _laplacian(Uint8List src, int w, int h) {
  final out = Uint8List.fromList(src);
  for (var y = 1; y < h - 1; y++) {
    for (var x = 1; x < w - 1; x++) {
      final i = y * w + x;
      final v = src[i - w] + src[i - 1] - 4 * src[i] + src[i + 1] + src[i + w] + 128;
      out[i] = v.clamp(0, 255);
    }
  }
  return out;
}

(Uint8List, int, int) _crop1(Uint8List src, int w, int h) {
  if (w < 3 || h < 3) return (src, w, h);
  final nw = w - 2;
  final nh = h - 2;
  final out = Uint8List(nw * nh);
  var o = 0;
  for (var y = 1; y < h - 1; y++) {
    out.setRange(o, o + nw, src, y * w + 1);
    o += nw;
  }
  return (out, nw, nh);
}

double _std(Uint8List src, int w, int x0, int y0, int x1, int y1) {
  var n = 0;
  var sum = 0.0;
  for (var y = y0; y < y1; y++) {
    for (var x = x0; x < x1; x++) {
      sum += src[y * w + x];
      n++;
    }
  }
  if (n == 0) return 0;
  final mean = sum / n;
  var acc = 0.0;
  for (var y = y0; y < y1; y++) {
    for (var x = x0; x < x1; x++) {
      final d = src[y * w + x] - mean;
      acc += d * d;
    }
  }
  return math.sqrt(acc / n);
}

double _variance(Uint8List src, int w, int x0, int y0, int x1, int y1) {
  var n = 0;
  var sum = 0.0;
  for (var y = y0; y < y1; y++) {
    for (var x = x0; x < x1; x++) {
      sum += src[y * w + x];
      n++;
    }
  }
  if (n == 0) return 0;
  final mean = sum / n;
  var acc = 0.0;
  for (var y = y0; y < y1; y++) {
    for (var x = x0; x < x1; x++) {
      final d = src[y * w + x] - mean;
      acc += d * d;
    }
  }
  return acc / n;
}
