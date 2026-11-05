// 문제(지연·이슈)·임박·보류·PO 대기 전체 목록.
//
// 홈의 '지금 봐야 할 것' 은 프로젝트로 묶어서 다섯 줄만 보여준다.
// 여기서는 모델 한 건씩, 오래 밀린 것부터 전부 늘어놓는다.
// 홈·프로젝트 화면과 같은 /home/alerts 를 본다 — 세 화면이 같은 값을 쓴다.
import 'package:flutter/material.dart';

import '../design/typography.dart';
import '../models/division.dart';
import '../services/divisions_service.dart';
import '../services/home_alerts_service.dart';
import '../utils/status_words.dart';
import 'division_projects_screen.dart';
import 'project_overview_screen.dart';
import '../config/owner_label.dart';

class AlertListScreen extends StatefulWidget {
  /// '문제' = 지연+이슈 (홈에서 들어오는 기본) · '' = 전부
  /// · '지연' · '이슈' · '임박' · '정상' · 'PO 대기'
  /// (화면에 보이는 말은 utils/status_words.dart 에서 정한다)
  final String initialFilter;

  const AlertListScreen({super.key, this.initialFilter = ''});

  @override
  State<AlertListScreen> createState() => _AlertListScreenState();
}

class _AlertListScreenState extends State<AlertListScreen> {
  late Future<HomeAlerts> _future;
  late String _filter;

  /// 줄을 눌렀을 때 사업부 화면으로 보내려면 사업부 객체가 있어야 한다.
  /// 못 받아도 화면은 떠야 하니 빈 목록으로 둔다 (그때는 전처럼 프로젝트로 연다).
  List<Division> _divisions = const [];

  /// 칩으로 보여주는 다섯 가지. 화면에 쓰는 말은 StatusWords 가 정한다
  /// (정상 · 일정 지연 · 집중관리 · 특이사항 · PO 대기).
  ///
  /// 2026-11-03 — '문제' 와 '전체' 를 뺐다.
  /// Min: "지금 위에 탭/pill을 정상, 일정지연, 집중관리, 특이사항,
  ///       PO 대기 로만 보이게 변경햐줘"
  ///
  /// '문제' 는 지연+특이사항을 합친 것이고 '전체' 는 그 위에 임박까지
  /// 더한 것이라, 같은 건이 칩 세 개에 겹쳐 세어졌다 — 18 · 18 · 19 가
  /// 나란히 서서 어느 것이 무엇인지 알 수 없었다.
  static const List<String> _kChips = ['정상', '지연', '임박', '이슈', 'PO 대기'];

  @override
  void initState() {
    super.initState();
    // 칩에 없는 값으로 열리면 아무 칩도 안 눌린 빈 화면이 된다 — 첫 칩으로.
    // (홈 카드는 정상 · 지연 · 이슈 · 임박 만 넘긴다. 전부 칩에 있다.)
    final want = widget.initialFilter.trim();
    _filter = _kChips.contains(want) ? want : _kChips.first;
    _future = HomeAlertsService.fetch();
    _loadDivisions();
  }

  Future<void> _loadDivisions() async {
    try {
      final d = await DivisionsService.fetchAll();
      if (!mounted) return;
      setState(() => _divisions = d);
    } catch (_) {}
  }

  /// 칩 하나가 보여줄 목록. 보류·PO 대기는 지연 목록과 별개다.
  List<AlertModel> _listFor(HomeAlerts a) {
    switch (_filter) {
      case '문제':
        return a.blockers;
      case '지연':
        return a.alerts.where((m) => m.kind == '지연').toList();
      case '이슈':
        return a.alerts.where((m) => m.kind == '이슈').toList();
      case '임박':
        return a.alerts.where((m) => m.kind == '임박').toList();
      case '보류':
        return a.holds;
      case '정상':
        return a.normals;
      case 'PO 대기':
        return a.poWaits;
      default:
        return a.alerts;
    }
  }

  Future<void> _refresh() async {
    setState(() => _future = HomeAlertsService.fetch());
    await _future;
  }

  Widget _chip(String label, int n, bool on, VoidCallback tap, Color tint) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: GestureDetector(
        onTap: tap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: on ? tint : const Color(0xFFF1F5F9),
            borderRadius: BorderRadius.circular(99),
            border: Border.all(color: on ? tint : const Color(0xFFE5E7EB)),
          ),
          child: Text('$label $n',
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                color: on ? Colors.white : const Color(0xFF4B5563),
              )),
        ),
      ),
    );
  }

  static Color _tintOf(String kind) {
    switch (kind) {
      case '지연':
        return const Color(0xFFDC2626);
      case '이슈':
        return const Color(0xFFEA580C);
      case '임박':
        return const Color(0xFFF59E0B);
      case '정상':
        return const Color(0xFF196B24);
      case 'PO 대기':
        return const Color(0xFFB45309);
      default:
        return const Color(0xFF6B7280); // 보류 · 드롭예정
    }
  }

  static Color _softOf(String kind) {
    switch (kind) {
      case '지연':
        return const Color(0xFFFEE2E2);
      case '이슈':
        return const Color(0xFFFFEDD5);
      case '임박':
        return const Color(0xFFFEF3C7);
      case '정상':
        return const Color(0xFFD1FAE5);
      case 'PO 대기':
        return const Color(0xFFFEF3C7);
      default:
        return const Color(0xFFF3F4F6);
    }
  }

  Widget _card(AlertModel m) {
    final tint = _tintOf(m.kind);
    return GestureDetector(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ProjectOverviewScreen(
          projectKey: m.projectKey,
          projectName: m.project,
        ),
      )),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE5E7EB)),
        ),
        child: Row(children: [
          Container(
            width: 4, height: 44,
            decoration: BoxDecoration(
                color: tint, borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Text(m.project,
                    style: const TextStyle(
                        fontSize: 11, fontWeight: FontWeight.w700,
                        color: Color(0xFF6B7280))),
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 1),
                  decoration: BoxDecoration(
                    color: _softOf(m.kind),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(StatusWords.of(m.kind),
                      style: TextStyle(
                          fontSize: 10, fontWeight: FontWeight.w800, color: tint)),
                ),
              ]),
              const SizedBox(height: 3),
              Text(m.model,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.bodyStrong.copyWith(fontSize: 14)),
              const SizedBox(height: 2),
              // 이슈는 적어 둔 내용이 곧 이유다. 공정·예정일보다 먼저 보여준다.
              if (m.issue.isNotEmpty)
                Text(m.issue,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 12, height: 1.35, color: Color(0xFF374151)))
              else
                Text(
                    [
                      if (m.stage.isNotEmpty) m.stage,
                      if (m.expected.isNotEmpty) '완료예정 ${m.expected}',
                      if (m.days != null && m.days! > 0) '${m.days}일 경과',
                    ].join(' · '),
                    style:
                        const TextStyle(fontSize: 11.5, color: Color(0xFF6B7280))),
              if (m.note.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(m.note,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 11, color: Color(0xFF9CA3AF))),
                ),
            ]),
          ),
          const Icon(Icons.chevron_right, color: Color(0xFFCBD5E1)),
        ]),
      ),
    );
  }

  /// 한 줄에 '어디가 몇 건'.
  ///
  /// 품번을 192줄 늘어놓아도 읽을 사람이 없다. '어디가 몇 건' 만 보고,
  /// 자세한 건 눌러서 들어가 본다.
  ///
  /// 2026-11-03 — 프로젝트로 세우면 125줄이다 (Smac 113 · 파워박스 80 ·
  /// SM 78 …). 홈 카드는 이미 사업부로 접어서 보여주는데 여기만 프로젝트로
  /// 늘어놓으니, 같은 '정상 1191' 을 눌렀는데 화면마다 다른 것이 나왔다.
  /// Min: "전체 사업부 들어가면 여기서도 사업부로 보였으면 좋겠는데"
  Widget _projectRow(AlertProject p, Color tint) {
    Division? div;
    for (final d in _divisions) {
      if (d.id == p.key) {
        div = d;
        break;
      }
    }
    return GestureDetector(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => div != null
            ? DivisionProjectsScreen(division: div)
            : ProjectOverviewScreen(
                projectKey: p.key,
                projectName: p.label,
              ),
      )),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.fromLTRB(14, 14, 12, 14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE5E7EB)),
        ),
        child: Row(children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(color: tint, shape: BoxShape.circle),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(p.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.bodyStrong.copyWith(fontSize: 14.5)),
                // '반도체사업부 238건' 만 보면 몇 군데가 모인 건지 모른다
                if (p.projects > 0)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text('${ownerLabelOf(p.key)} ${p.projects}곳',
                        style: const TextStyle(
                            fontSize: 12, color: Color(0xFF7C8594))),
                  ),
              ],
            ),
          ),
          Text('${p.count}건',
              style: TextStyle(
                  fontSize: 13.5, fontWeight: FontWeight.w800, color: tint)),
          const Icon(Icons.chevron_right, color: Color(0xFFCBD5E1)),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F6F8),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        title: Text(StatusWords.of(_filter),
            style: AppText.bodyStrong.copyWith(fontSize: 17)),
        iconTheme: const IconThemeData(color: Color(0xFF111827)),
      ),
      body: FutureBuilder<HomeAlerts>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator(strokeWidth: 2));
          }
          final a = snap.data ?? HomeAlerts.empty;
          if (!a.loaded) {
            return const Center(
                child: Text('현황을 불러오지 못했습니다',
                    style: TextStyle(color: Color(0xFFDC2626))));
          }
          final list = _listFor(a);
          // 사업부로 접은 것이 있으면 그것을 쓴다. 서버가 못 주는 옛 버전에
          // 붙어도 화면이 비지 않게 프로젝트 목록으로 떨어진다.
          final byProject = (_filter == '정상')
              ? (a.byKindDiv['정상']?.isNotEmpty == true
                  ? a.byKindDiv['정상']!
                  : (a.byKind['정상'] ?? const <AlertProject>[]))
              : const <AlertProject>[];
          return Column(children: [
            Container(
              width: double.infinity,
              color: Colors.white,
              padding: const EdgeInsets.fromLTRB(16, 10, 8, 10),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                // 칩 글자는 사람이 읽는 말, 걸러내는 값은 서버가 쓰는 말.
                //
                // 2026-11-03 — '문제' 와 '전체' 를 뺐다 (_kChips 주석 참고).
                child: Row(children: [
                  _chip(StatusWords.normal, a.normal, _filter == '정상',
                      () => setState(() => _filter = '정상'),
                      const Color(0xFF196B24)),
                  _chip(StatusWords.delayed, a.delayed, _filter == '지연',
                      () => setState(() => _filter = '지연'),
                      const Color(0xFFDC2626)),
                  _chip(StatusWords.soon, a.soon, _filter == '임박',
                      () => setState(() => _filter = '임박'),
                      const Color(0xFFF59E0B)),
                  _chip(StatusWords.issue, a.issue, _filter == '이슈',
                      () => setState(() => _filter = '이슈'),
                      const Color(0xFFEA580C)),
                  _chip('PO 대기', a.poWait, _filter == 'PO 대기',
                      () => setState(() => _filter = 'PO 대기'),
                      const Color(0xFFB45309)),
                ]),
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: byProject.isNotEmpty
                    ? ListView.builder(
                        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                        itemCount: byProject.length,
                        itemBuilder: (_, i) =>
                            _projectRow(byProject[i], _tintOf(_filter)),
                      )
                    : list.isEmpty
                    ? ListView(children: const [
                        SizedBox(height: 80),
                        Center(
                            child: Text('해당하는 항목이 없습니다',
                                style: TextStyle(color: Color(0xFF9CA3AF)))),
                      ])
                    : ListView.builder(
                        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                        itemCount: list.length,
                        itemBuilder: (_, i) => _card(list[i]),
                      ),
              ),
            ),
          ]);
        },
      ),
    );
  }
}
