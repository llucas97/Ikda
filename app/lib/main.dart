import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:material_ui/material_ui.dart';

import 'config.dart';
import 'screens/home_screen.dart';
import 'screens/join_screen.dart';
import 'screens/login_screen.dart';
import 'screens/result_screen.dart';
import 'services/analysis_service.dart';
import 'services/auth_service.dart';
import 'services/capture_flow.dart';
import 'services/deep_links.dart';
import 'services/document_repository.dart';
import 'services/document_sync.dart';
import 'services/family_service.dart';
import 'services/push_service.dart';
import 'services/reminders.dart';
import 'services/share_intake.dart';
import 'services/token_store.dart';
import 'state/app_store.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (!AppConfig.useMock && AppConfig.kakaoNativeAppKey.isNotEmpty) {
    await KakaoSdk.init(nativeAppKey: AppConfig.kakaoNativeAppKey);
  }
  final tokenStore = TokenStore();
  final auth = AppConfig.useMock
      ? MockAuthService(store: tokenStore)
      : HttpAuthService(serverUrl: AppConfig.serverUrl, store: tokenStore);
  await auth.restore();

  final reminders = createReminders();
  try {
    await reminders.init();
  } catch (e) {
    debugPrint('알림 준비 실패: $e');
  }
  final repository = PrefsDocumentRepository();
  final store = AppStore(
    analysisService: AppConfig.useMock
        ? MockAnalysisService()
        : HttpAnalysisService(AppConfig.serverUrl, accessToken: auth.accessToken),
    repository: repository,
    reminders: reminders,
    family: AppConfig.useMock
        ? MockFamilyService()
        : HttpFamilyService(AppConfig.serverUrl, accessToken: auth.accessToken),
    sync: AppConfig.useMock
        ? null
        : DocumentSync(baseUrl: AppConfig.serverUrl, local: repository, accessToken: auth.accessToken),
  );
  await store.load();
  runApp(IlgeodeurimApp(store: store, auth: auth));
}

class IlgeodeurimApp extends StatelessWidget {
  const IlgeodeurimApp({super.key, required this.store, required this.auth});

  final AppStore store;
  final AuthService auth;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      store: store,
      auth: auth,
      child: MaterialApp(
        title: '읽다',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        // 시스템 글자 크기는 존중하되, 너무 커져서 화면이 깨지지 않게 상한을 둔다.
        builder: (context, child) {
          final mq = MediaQuery.of(context);
          return MediaQuery(
            data: mq.copyWith(
              textScaler: mq.textScaler.clamp(minScaleFactor: 1.0, maxScaleFactor: 1.3),
            ),
            child: child!,
          );
        },
        home: const SessionShell(),
      ),
    );
  }
}

/// 저장된 세션이 있거나 '나중에'를 눌렀으면 홈. 처음이면 로그인.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.authOf(context);
    return ListenableBuilder(
      listenable: auth,
      builder: (context, _) {
        final showHome = auth.user != null || (auth.skipped && !AppConfig.requireLogin);
        return showHome ? const HomeScreen() : const LoginScreen(asGate: true);
      },
    );
  }
}

/// 공유·초대 링크·푸시. 로그인 전이면 받아 두었다가 홈에 들어간 뒤 연다.
class SessionShell extends StatefulWidget {
  const SessionShell({super.key});

  @override
  State<SessionShell> createState() => _SessionShellState();
}

class _SessionShellState extends State<SessionShell> with WidgetsBindingObserver {
  ShareIntake? _share;
  PushService? _push;
  AuthService? _auth;
  bool _booted = false;
  bool _signedIn = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _boot());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _auth?.removeListener(_onAuth);
    super.dispose();
  }

  Future<void> _boot() async {
    if (_booted || !mounted) return;
    _booted = true;
    final store = AppScope.read(context);
    final auth = AppScope.authOf(context);
    _auth = auth;
    _signedIn = auth.user != null;
    auth.addListener(_onAuth);
    if (_signedIn) await store.onLogin();
    final links = DeepLinks(onToken: (token) {
      AppScope.read(context).pendingJoinToken = token;
      _openJoin();
    });
    await links.start();
    _share = ShareIntake(onMedia: _takeShare);
    await _share!.start();
    _push = createPushService(enabled: !AppConfig.useMock);
    await _push!.start(onOpen: _onPush, onToken: _onToken);
  }

  void _onAuth() {
    if (!mounted) return;
    final auth = AppScope.authOf(context);
    final store = AppScope.read(context);
    final signed = auth.user != null;
    if (signed && !_signedIn) {
      store.onLogin();
    } else if (!signed && _signedIn) {
      store.onLogout();
    }
    _signedIn = signed;
    final home = signed || (auth.skipped && !AppConfig.requireLogin);
    if (!home) return;
    _openJoin();
    if (store.pendingShare.isNotEmpty) {
      final files = List.of(store.pendingShare);
      store.pendingShare = [];
      _takeShare(files);
    }
  }

  void _openJoin() {
    if (!mounted) return;
    final auth = AppScope.authOf(context);
    final store = AppScope.read(context);
    final token = store.pendingJoinToken;
    final home = auth.user != null || (auth.skipped && !AppConfig.requireLogin);
    if (token == null || !home) return;
    store.pendingJoinToken = null;
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => JoinScreen(token: token)));
  }

  void _takeShare(List<XFile> files) {
    if (!mounted || files.isEmpty) return;
    final auth = AppScope.authOf(context);
    final store = AppScope.read(context);
    final home = auth.user != null || (auth.skipped && !AppConfig.requireLogin);
    if (!home) {
      store.pendingShare = List.of(files);
      return;
    }
    runCapture(context, files, fromScanner: false).whenComplete(() => _share?.reset());
  }

  void _onPush(PushOpen open) {
    if (!mounted) return;
    final store = AppScope.read(context);
    if (open.type == 'FOREGROUND') {
      store.syncNow();
      store.refreshFamily();
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(const SnackBar(content: Text('가족이 서류를 보냈어요')));
      return;
    }
    _openDocument(open.documentId);
  }

  Future<void> _openDocument(String? id) async {
    if (id == null || !mounted) return;
    final store = AppScope.read(context);
    await store.syncNow();
    await store.refreshFamily();
    if (!mounted) return;
    final doc = store.documents.where((d) => d.id == id).firstOrNull ??
        store.familyDocs.where((d) => d.id == id).firstOrNull;
    if (doc == null) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => ResultScreen(result: doc, fromHistory: true)),
    );
  }

  Future<void> _onToken(String token) {
    final platform = switch (defaultTargetPlatform) {
      TargetPlatform.iOS => 'IOS',
      TargetPlatform.android => 'ANDROID',
      _ => 'WEB',
    };
    return AppScope.authOf(context).registerPushToken(token, platform: platform);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !mounted) return;
    final store = AppScope.read(context);
    if (AppScope.authOf(context).user == null) return;
    store.syncNow();
    store.refreshFamily();
  }

  @override
  Widget build(BuildContext context) => const AuthGate();
}
