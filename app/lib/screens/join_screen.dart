import 'package:material_ui/material_ui.dart';

import '../models/family_link.dart';
import '../services/family_service.dart';
import '../state/app_store.dart';
import '../theme.dart';
import 'relation_picker.dart';

/// 6칸 숫자. 미리 보기 다음 연결하기 한 번.
class JoinScreen extends StatefulWidget {
  const JoinScreen({super.key, this.token});
  final String? token;

  @override
  State<JoinScreen> createState() => _JoinScreenState();
}

class _JoinScreenState extends State<JoinScreen> {
  final _digits = List<String>.filled(6, '');
  int _cursor = 0;
  InvitePreview? _preview;
  String? _error;
  bool _busy = false;
  String? _relation;
  final _nick = TextEditingController();

  @override
  void initState() {
    super.initState();
    if (widget.token != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _previewToken());
    }
  }

  @override
  void dispose() {
    _nick.dispose();
    super.dispose();
  }

  String get _code => _digits.join();

  Future<void> _previewToken() async {
    setState(() => _busy = true);
    try {
      final preview = await AppScope.read(context).family!.preview(token: widget.token);
      if (mounted) setState(() => _preview = preview);
    } on FamilyException catch (e) {
      if (mounted) setState(() => _error = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _previewCode() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final preview = await AppScope.read(context).family!.preview(code: _code);
      if (mounted) setState(() => _preview = preview);
    } on FamilyException catch (e) {
      if (mounted) setState(() => _error = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _accept() async {
    setState(() => _busy = true);
    try {
      await AppScope.read(context).family!.accept(
            code: widget.token == null ? _code : null,
            token: widget.token,
            label: _nick.text.trim().isEmpty ? null : _nick.text.trim(),
            relationCd: _relation,
          );
      if (!mounted) return;
      await AppScope.read(context).refreshFamily();
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } on FamilyException catch (e) {
      if (mounted) setState(() => _error = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _tap(String d) {
    if (_cursor >= 6) return;
    setState(() {
      _digits[_cursor] = d;
      _cursor++;
    });
    if (_cursor == 6) _previewCode();
  }

  @override
  Widget build(BuildContext context) {
    final preview = _preview;
    return Scaffold(
      appBar: AppBar(title: const Text('가족 연결')),
      backgroundColor: AppColors.canvas,
      body: SafeArea(
        child: preview == null ? _pad() : _confirm(preview),
      ),
    );
  }

  Widget _pad() {
    return ListView(padding: const EdgeInsets.fromLTRB(Space.s16, Space.s16, Space.s16, Space.s8), children: [
      const Text('가족에게 받은 번호를 넣어 주세요', textAlign: TextAlign.center, style: AppText.body),
      const SizedBox(height: Space.s16),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        for (var i = 0; i < 6; i++) ...[
          if (i == 3) const SizedBox(width: Space.s16),
          Container(
            width: 44,
            height: 64,
            alignment: Alignment.center,
            margin: const EdgeInsets.symmetric(horizontal: 4),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(Radii.r12),
              border: Border.all(color: i == _cursor ? AppColors.highlight : AppColors.line, width: 2),
            ),
            child: Text(_digits[i], style: AppText.heading1),
          ),
        ],
      ]),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(top: Space.s12),
          child: Text(_error!, textAlign: TextAlign.center, style: AppText.body.copyWith(color: AppColors.warnText)),
        ),
      const SizedBox(height: Space.s12),
      if (_busy)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: Space.s24),
          child: Center(child: CircularProgressIndicator(color: AppColors.ink)),
        )
      else
        _keys(),
    ]);
  }

  Widget _keys() {
    return GridView.count(
      crossAxisCount: 3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: Space.s8,
      crossAxisSpacing: Space.s8,
      childAspectRatio: 1.25,
      children: [
        for (final d in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', '지움'])
          d.isEmpty
              ? const SizedBox.shrink()
              : TextButton(
                  onPressed: () {
                    if (d == '지움') {
                      if (_cursor == 0) return;
                      setState(() {
                        _cursor--;
                        _digits[_cursor] = '';
                      });
                    } else {
                      _tap(d);
                    }
                  },
                  child: Text(d, style: d == '지움' ? AppText.heading2 : AppText.heading1),
                ),
      ],
    );
  }

  Widget _confirm(InvitePreview preview) {
    final options = preview.yourRole == 'CHILD' ? parentRelations : elderRelations;
    return ListView(padding: const EdgeInsets.all(Space.s16), children: [
      Text(preview.name, style: AppText.display),
      const SizedBox(height: Space.s8),
      Text(preview.alreadyLinked ? '이미 연결돼 있어요' : '이 분과 연결할까요?', style: AppText.body),
      const SizedBox(height: Space.s24),
      const Text('나는 이렇게 불러요', style: AppText.heading2),
      const SizedBox(height: Space.s12),
      RelationPicker(options: options, selected: _relation, onPick: (c) => setState(() => _relation = c)),
      const SizedBox(height: Space.s12),
      NicknameField(controller: _nick, hint: '어머니, 큰딸'),
      if (_error != null) ...[
        const SizedBox(height: Space.s12),
        Text(_error!, style: AppText.body.copyWith(color: AppColors.warnText)),
      ],
      const SizedBox(height: Space.s24),
      FilledButton(onPressed: _busy || preview.alreadyLinked ? null : _accept, child: const Text('연결하기')),
    ]);
  }
}
