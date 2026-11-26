import 'package:material_ui/material_ui.dart';

import '../models/family_link.dart';
import '../services/family_service.dart';
import '../state/app_store.dart';
import '../theme.dart';
import '../utils/keep_all.dart';

/// 대표가 이 가족의 보기·대신 보내기·지우기·알림을 켠다.
class FamilyPermissionScreen extends StatefulWidget {
  const FamilyPermissionScreen({super.key, required this.link});
  final FamilyLink link;

  @override
  State<FamilyPermissionScreen> createState() => _FamilyPermissionScreenState();
}

class _FamilyPermissionScreenState extends State<FamilyPermissionScreen> {
  late bool _view = widget.link.canView;
  late bool _edit = widget.link.canEdit;
  late bool _delete = widget.link.canDelete;
  late bool _notify = widget.link.notification;
  bool _busy = false;

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      await AppScope.read(context).family!.updatePermissions(
            widget.link.linkId,
            canView: _view,
            canEdit: _edit,
            canDelete: _delete,
            notification: _notify,
          );
      if (!mounted) return;
      await AppScope.read(context).refreshFamily();
      if (mounted) Navigator.pop(context);
    } on FamilyException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.userMessage)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.link.display)),
      body: ListView(padding: const EdgeInsets.all(Space.s16), children: [
        Text('이 가족의 권한을 골라 주세요'.keepAll, style: AppText.body),
        const SizedBox(height: Space.s16),
        _row('서류를 볼 수 있어요', _view, (v) => setState(() => _view = v)),
        _row('대신 보낼 수 있어요', _edit, (v) => setState(() => _edit = v)),
        _row('서류를 지울 수 있어요', _delete, (v) => setState(() => _delete = v)),
        _row('알림을 받아요', _notify, (v) => setState(() => _notify = v)),
        const SizedBox(height: Space.s24),
        FilledButton(onPressed: _busy ? null : _save, child: const Text('저장')),
      ]),
    );
  }

  Widget _row(String label, bool value, ValueChanged<bool> onChanged) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(label, style: AppText.title),
      value: value,
      activeThumbColor: AppColors.ink,
      activeTrackColor: AppColors.highlight,
      onChanged: onChanged,
    );
  }
}
