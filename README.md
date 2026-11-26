# 읽다

서류(고지서·약봉투·병원 안내문·계약서 등)를 사진으로 찍으면 AI가 쉬운 말로 정리하고, 중요한 금액과 기한을 알려 주는 어르신용 앱입니다. 자녀가 부모님 대신 서류를 찍어 보내고, 푸시 알림으로 기한을 미리 알려 드릴 수 있습니다.

## 주요 기능

- **사진 찍기 → 쉬운 요약**: 문서 스캐너로 촬영하면 AI가 내용을 분석하고 쉬운 말로 정리
- **음성 읽기**: 분석 결과를 음성으로 들려 줌
- **기한 알림**: 고지서 납부일, 병원 예약일을 하루 전과 당일 아침에 푸시 알림
- **가족 연결**: 자녀가 어르신을 초대해 연결하고, 대신 서류를 찍어 보낼 수 있음
- **로그인**: 카카오·구글 로그인 지원

## 화면

<img src="shots/05-home.png" width="250" alt="홈 화면" /> <img src="shots/13-result-bill.png" width="250" alt="분석 결과" /> <img src="shots/17-family-tree.png" width="250" alt="가족 화면" />

## 기술 스택

- **앱**: Flutter (Dart) — Android, iOS, Web
- **서버**: Python FastAPI + SQLAlchemy (ORM) + PostgreSQL
- **배포**: Docker Compose

## 빠르게 시작하기

### 1) 서버 실행

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# .env 파일 준비 (예시 복사 후 필요한 값 채우기)
cp .env.example .env

# AI 키 없이 실행 (가짜 AI — 앱↔서버 흐름 시험용)
AI_PROVIDER=fake uvicorn app.main:app --host 0.0.0.0 --port 8000

# 실제 AI로 실행 (Gemini 추천: 빠르고 저렴)
# GEMINI_API_KEY=your_key_here uvicorn app.main:app --host 0.0.0.0 --port 8000

# 테스트
python -m pytest -q
```

서버가 잘 시작됐는지 확인: `curl localhost:8000/health` → `{"ok":true}`

**Postgres 사용 시** (선택):
```bash
# 저장소 루트에서
docker compose up -d
DATABASE_URL=postgresql://ilgeo:ilgeo@localhost:5432/ilgeodeurim python db/migrate.py
```

### 2) 앱 실행

```bash
cd app
flutter pub get

# 서버 없이 화면만 보기 (가짜 분석)
flutter run

# 서버에 연결하기
flutter run --dart-define=SERVER_URL=http://10.0.2.2:8000     # Android 에뮬레이터
flutter run --dart-define=SERVER_URL=http://localhost:8000    # 웹
# flutter run --dart-define=SERVER_URL=http://192.168.0.10:8000  # 실제 폰 (같은 Wi-Fi)

# 가짜 모드 명시적으로 켜기 (서버 주소가 있어도 가짜 분석)
flutter run --dart-define=USE_MOCK=true

# 분석 및 테스트
flutter analyze && flutter test
```

> **참고**: 실제 폰에서 http:// 주소를 쓰려면 Android는 cleartext 허용, iOS는 ATS 예외가 필요합니다.

## 사용 방법

1. **서류 찍기**: 홈 화면에서 큰 노란 버튼을 눌러 고지서나 약봉투를 촬영
2. **결과 확인**: AI가 분석한 쉬운 요약, 금액, 기한을 확인
3. **음성으로 듣기**: 귀 모양 아이콘을 눌러 소리로 들음
4. **알림 받기**: 기한 하루 전과 당일 아침 9시에 자동으로 알림
5. **가족 연결** (선택): 자녀가 초대 번호로 어르신과 연결하고, 대신 서류를 보낼 수 있음

## 자세한 설정

- **서버 환경변수 및 설정**: `server/.env.example` 주석 참고
- **앱 설정 및 Firebase/로그인 준비**: [docs/setup.md](docs/setup.md)
- **API 계약**: [docs/api.md](docs/api.md)
- **개발 노트 및 계획**: [docs/dev-notes.md](docs/dev-notes.md)
- **사진 인증 복약 알람 기획**: [docs/med-photo-alarm-plan.md](docs/med-photo-alarm-plan.md)

## 라이선스

이 프로젝트는 개인 학습 및 시연용입니다.
