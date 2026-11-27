# 읽다 개발 노트

개발 현황, 실제 AI 테스트 결과, 향후 계획입니다.

## 목차

- [지금까지 된 것](#지금까지-된-것)
- [실제 AI 테스트 결과](#실제-ai-테스트-결과)
- [다음에 할 일](#다음에-할-일)
- [개발 환경 참고사항](#개발-환경-참고사항)

---

## 지금까지 된 것

### 앱 (Flutter)

- **이름**: `읽다` (홈 머리글, 앱 제목, Android 라벨, iOS 표시 이름, 웹 제목/manifest)
  - 패키지·번들 ID는 `com.ilgeodeurim.ilgeodeurim` (스토어 출시 전 변경 가능)

- **디자인**:
  - 먹색 `#1F1D1A` (텍스트·강조)
  - 종이 `#FFFDF8` (배경)
  - 형광 노랑 `#F2C230` (밑줄·촬영 버튼·선택 항목만 사용)
  - 노란 색은 넓은 면적에 쓰지 않음

- **사진 받기**:
  - 모바일: 문서 스캐너 (`cunning_document_scanner` 3.x, 최대 5장)
  - 웹: 사진 파일 고르기 (`image_picker`)

- **분석 서비스** (`HttpAnalysisService`):
  - 사진을 multipart로 서버에 업로드
  - JSON 응답을 받아 화면에 표시
  - 금액·기한은 서버가 준 `amount`/`dueDate` 그대로 사용

- **로컬 저장**:
  - 서류와 할 일(완료·알림 여부)을 기기에 저장 (`shared_preferences`, 웹은 localStorage)
  - 껐다 켜도 유지됨
  - 사진은 저장하지 않음

- **알림**:
  - 기한 **하루 전 아침 9시**, **당일 아침 9시** (한국 시간)
  - 분석 직후 자동 예약
  - '하루 전 알림' 버튼으로 끄고 켬
  - '다 했어요' 또는 서류 삭제 시 알림 취소
  - 권한은 첫 알림 설정 시 요청 (Android 13+, iOS)
  - 웹은 알림 없음

- **지난 서류 관리**:
  - 목록에서 열어서 확인
  - '지우기' 버튼 (할 일·알림도 함께 삭제)

- **로그인**:
  - 카카오·구글 버튼 (공식 디자인 가이드 준수)
  - 안전한 토큰 저장 (`flutter_secure_storage`)
  - 만료 전 자동 갱신
  - 로그아웃·탈퇴 기능
  - `USE_MOCK`이면 키 없이 가짜 로그인
  - **주의**: Flutter가 개발 PC에 없어 `flutter analyze`는 아직 미실행

- **Android**:
  - minSdk 24, desugaring
  - 알림 수신기·재부팅 복원
  - 카카오 로그인 액티비티·카카오톡 쿼리
  - 권한: INTERNET, CAMERA, POST_NOTIFICATIONS, RECEIVE_BOOT_COMPLETED

- **iOS**:
  - NSCameraUsageDescription, NSPhotoLibraryUsageDescription
  - 알림 delegate

### 서버 (Python FastAPI)

- **API 엔드포인트**:
  - `POST /api/analyze`: 사진 분석
  - `GET /health`: 서버 상태 확인

- **AI 제공자 교체**:
  - fake / Gemini / Anthropic (환경변수로 선택)
  - 키가 없으면 자동으로 fake 모드

- **모델 라우팅**:
  - 싼 모델로 서류 종류 분류
  - 약봉투·계약서는 좋은 모델로 에스컬레이션
  - 나머지는 기본 모델 사용

- **구조화 출력**:
  - Gemini: `responseJsonSchema`
  - Claude: 강제 도구 호출 + 지시문 캐싱

- **결과 검증·정리** (Pydantic):
  - 날짜 형식 통일
  - 금액 "32,400원" → `32400` (정수)
  - 모르는 서류 종류 → `other`

- **개인정보 보호**:
  - 사진은 요청 처리 중 메모리에만 보관
  - 디스크·로그에 저장하지 않음
  - 파일 내용(매직 바이트)으로 사진 여부 확인

- **사진 품질 검사** (Pillow):
  - AI 호출 전 검사하여 비용 절약
  - 흐림·어두움·과노출·빈 사진·너무 작은 사진 거부
  - 몇 번째 사진인지 알려줌
  - 압축 폭탄 거부

- **가족 연결** (3단계 A):
  - 6자리 초대 번호 (HMAC 저장, 30분, 한 번만, 틀림 횟수 제한)
  - 초대 링크 지원
  - 한 번 눌러 수락
  - 어느 쪽이든 연결 끊기 가능
  - 감사 기록 (`ct_family_log`)

- **서버 서류 보관**:
  - `ct_document` 등에 결과 텍스트만 저장
  - 동기화 (`since` 파라미터, 삭제 표시)
  - 주인/연결된 자녀 권한 확인
  - 자녀가 어르신 대신 보내기
  - 어르신이 자녀에게 나누기

- **푸시 알림**:
  - FCM HTTP v1 (서비스 계정 키는 환경변수 경로로)
  - 가짜 발송기 (개발·테스트용)
  - 발송 기록 (`ct_push_log`)
  - 죽은 토큰 자동 비활성화
  - 잠금 화면에 제목·금액 표시 안 함 (개인정보 보호)

---

## 실제 AI 테스트 결과

**테스트 일자**: 2026-11-16  
**AI**: Gemini  
**샘플**: `server/samples/*.jpg` (가짜 정보로 만든 고지서·약봉투·검사 안내문·통신 계약서·건강검진 안내)

### 성능

- **처리 시간**: 한 건당 5~10초
- **토큰 사용**:
  - 분류: 약 1,100 입력 + 10 출력
  - 분석: 약 1,600~1,900 입력 + 300~500 출력 (생각 포함)

### 비용 (유료 등급 기준, 1달러=1,450원)

- **보통 서류**: 약 4원
  - 2027년 정가 적용 시: 약 8원
- **약·계약서** (Pro 모델 사용 시): 약 15원

### 주의사항

> **현재 키는 무료 등급**
> - Pro 모델 사용 불가 (한도 0, 자동으로 Flash로 대체)
> - 무료 등급 데이터는 Google이 서비스 개선에 사용할 수 있음
> - **실제 어르신 서류에는 반드시 유료 등급 키 사용 필요**

### 테스트 재실행 방법

```bash
cd server
AI_PROVIDER=gemini DEBUG_USAGE=1 uvicorn app.main:app --port 8001

# 다른 터미널에서
curl -F "images=@samples/bill.jpg;type=image/jpeg" localhost:8001/api/analyze
```

실제 Gemini 응답은 `server/samples/results/*.json`에 저장되어 있습니다 (`_v2`는 지시문 개선 후 버전).

---

## 다음에 할 일

### 1. 실제 키로 정확도 확인

- 실제 고지서·약봉투 사진 20~30장 준비
- Gemini/Claude 비교 테스트
- 지시문(프롬프트) 다듬기
- 오류 사례 수집 및 개선

### 2. 3단계 B — 앱 기능 완성

앱 코드는 대부분 작성되었으나 실제 기기에서 테스트가 필요합니다.

**필요한 작업**:
- 기기에서 스캐너 동작 확인
- 공유 메뉴 동작 확인 (카카오톡·갤러리 등에서 사진 공유)
- 푸시 알림 수신 확인
- 가족 연결 흐름 완전 테스트

**설정 방법**: 위 "Firebase 푸시 알림 설정" 섹션 참조

### 3. 인증 나머지

기본 로그인 기능은 완성되었으나 추가 필요한 작업:

- 로그인·refresh 요청 수 제한 (rate limit)
- 오래된 세션 행 정리 작업
- 카카오·구글 로그인 자체는 키만 넣으면 작동 (출시 안내 참고)

### 4. 배포

- 서버를 Cloud Run 등에 https로 배포
- `SERVER_URL`을 운영 주소로 변경
- `CORS_ORIGINS`를 실제 앱 주소로 좁히기
- 비용 모니터링 설정
- 로그 및 에러 추적 설정

### 5. 앱 마무리

- 실제 기기에서 스캐너·알림 흐름 확인 (Android 13+/iOS 권한)
- 앱 아이콘 최종 확인
- 릴리스 빌드 키 해시 등록 (카카오·구글·Play Console)

### 6. 기타 개선

- 기기 시간대 따라가기 (현재는 Asia/Seoul 고정)
- 사진 품질 기준 실제 데이터로 재조정
- 에러 메시지 개선
- 오프라인 모드 개선

### 7. Rust 전환 계획 검토

서버만 Rust로 옮기는 권장안과 단계, 위험은 [docs/rust-migration-plan.md](docs/rust-migration-plan.md)에 정리했다. 착수 전에 그 문서의 미결정 항목을 정한다. 이 항목은 계획 검토이며, 앱·서버 구현은 아직 바꾸지 않는다.

---

## 개발 환경 참고사항

### Flutter 환경

- **현재 상태**: 개발 PC에 Flutter가 설치되지 않음
- **결과**: `flutter analyze` 및 `flutter test`를 실행하지 못함
- **코드 작성**: Dart 패키지 README (kakao_flutter_sdk_user 2.1, google_sign_in 7.2)에 맞춰 작성
- **다음 단계**: Flutter가 설치된 환경에서 분석 및 테스트 필요

### Linux 테스트 환경

Linux에서 `flutter test`를 빌드할 때 `pdfrx` (PDFium) 플러그인이 Clang을 요구할 수 있습니다.

**필요한 패키지**:
```bash
sudo apt install clang cmake ninja-build libgtk-3-dev libclang-dev
```

**배경**:
- PDF를 JPEG로 그리는 코드는 `app/lib/services/pdf_raster_io.dart`에만 존재
- `pdf_raster.dart`가 io일 때만 해당 파일을 임포트
- 웹과 `pdf_raster_stub.dart`는 `pdfrx`를 임포트하지 않음
- 앱 테스트는 직접 임포트하지 않지만, 플러그인 등록 때문에 Linux 테스트 바이너리 빌드 시 Clang 필요

### 디자인 검토

Impeccable 4.5.1 기준으로 앱 화면을 검토했습니다.

**검토 범위**:
- Dart 화면에서 기계적 지적 없음
- Flutter가 설치되지 않아 실제 기기·브라우저 화면은 확인 못 함

**다음 단계**:
- 작은 전화기에서 초대 번호, 관계 격자, 로그인 버튼이 한 화면에 들어오는지 확인
- 시스템 글자를 1.3배로 키웠을 때 촬영 버튼 글자가 잘리지 않는지 확인

자세한 디자인 검토 내역은 `docs/design-review.md` 참조.

---

## 프로젝트 구조

```
ilda/
├── app/          # Flutter 앱 (Android · iOS · Web)
│   ├── lib/      # Dart 소스 코드
│   ├── test/     # 단위 테스트
│   └── android/  # Android 플랫폼 코드
│   └── ios/      # iOS 플랫폼 코드
├── server/       # 분석 서버 (Python FastAPI)
│   ├── app/      # FastAPI 애플리케이션
│   ├── db/       # 데이터베이스 마이그레이션
│   ├── tests/    # 서버 테스트 (pytest)
│   └── samples/  # AI 테스트 샘플 사진 및 결과
├── docs/         # 문서
│   ├── setup.md       # 상세 설정 가이드
│   ├── api.md         # API 계약서
│   ├── dev-notes.md   # 개발 노트 (이 파일)
│   ├── auth-plan.md   # 인증 설계 문서
│   ├── phase3-plan.md # 3단계 (가족 연결) 설계
│   └── design-review.md # 디자인 검토
├── screenshots/  # 웹 빌드 + 가짜 AI 서버 화면
└── shots/        # 추가 화면 기록
```

---

## 테스트

### 서버 테스트

**실행**:
```bash
cd server
python -m pytest -q
```

**통과**: 163개 테스트 (2026-11 기준)

**주요 테스트**:
- 사진 품질 검사 (흐림·어두움·작음 감지)
- 가족 초대·수락·연결 끊기
- 서류 보관·동기화·권한
- 자녀 대신 보내기
- 푸시 알림 발송 및 죽은 토큰 처리
- 인증 (로그인·refresh·재사용 탐지·탈퇴)
- 사진이 DB에 저장되지 않음 확인

**Postgres 테스트**:
```bash
TEST_DATABASE_URL=postgresql://ilgeo:ilgeo@localhost:5432/ilgeodeurim python -m pytest -q
```

### 앱 테스트

**실행**:
```bash
cd app
flutter test
```

**현재 상태**: Flutter 미설치로 아직 실행 안 됨

---

## 마지막 업데이트

**날짜**: 2026-11-17  
**작성자**: AI 보조 (문서 정리 및 구조화)
