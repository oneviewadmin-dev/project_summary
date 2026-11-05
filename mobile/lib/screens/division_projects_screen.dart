// 사업부 상세 화면 (디자인 A · 매출 우선).
//
// 첫 블록은 진행률(%)이 아니라 이 달의 매출이다.
// 경영진이 앱을 여는 순서가 "얼마 나갔나 → 왜 → 누구 때문에" 이기 때문에
// 화면도 그 순서로 내려간다.
//   1) 이번 달 매출 히어로 (사업부 합계)
//   2) 확인이 필요한 프로젝트 N건 (0건이면 숨김)
//   3) 프로젝트 — 매출 기여순 1열 리스트
//   4) 매출 계획이 없는 프로젝트는 접어둔다
//
// 데이터 소스
//  - DashboardService.fetchCards() : 상태(RED/ORANGE/GREEN), 마감일
//  - ProgressService.fetch()       : 진행률 / 모델 수
//  - OverviewService.fetch(divisionId:) : 월 매출·출하 (프로젝트별 + 합계)

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../design/design.dart';
import '../models/division.dart';
import '../models/dashboard.dart';
import '../services/dashboard_service.dart';
import '../services/progress_service.dart';
import '../services/favorites_service.dart';
import '../services/overview_service.dart';
import '../services/automotive_service.dart';
import '../models/automotive.dart';
import '../models/bloom_daily.dart';
import '../services/bloom_service.dart';
import '../widgets/bloom_plan_actual_card.dart';
import '../widgets/bloom_today_card.dart';
import '../widgets/purchase_status_card.dart';
import '../widgets/weekly_board_card.dart';
import '../widgets/daily_board_card.dart';
import '../services/division_board_service.dart';
import '../config/demo_board.dart';
import '../services/purchase_service.dart';
import '../models/purchase_status.dart';
import '../components/division/division_immediate_check.dart'
    show DivisionImmediateItem, ImmediatePriority;
import '../components/division/division_revenue_hero.dart';
import '../services/revenue_service.dart';
import '../components/division/division_attention_banner.dart';
import '../components/division/project_revenue_row.dart';
import '../components/division/automotive_hero_card.dart';
import '../components/division/automotive_row_card.dart';
import '../components/home/search_filter_row.dart';
import '../components/home/bottom_prompt_bar.dart';
import '../components/home/app_bottom_nav.dart';
import 'division_select_screen.dart' show DivisionSelectScreen;
import 'immediate_check_screen.dart';
import 'project_overview_screen.dart';
import 'revenue_detail_screen.dart';
import 'calendar_screen.dart';
import 'chat_screen.dart';
import '../config/owner_label.dart';
import '../config/customer_groups.dart';

class DivisionProjectsScreen extends StatefulWidget {
  final Division division;

  const DivisionProjectsScreen({
    super.key,
    required this.division,
  });

  @override
  State<DivisionProjectsScreen> createState() =>
      _DivisionProjectsScreenState();
}

class _DivisionProjectsScreenState extends State<DivisionProjectsScreen> {
  Set<String> _favoriteProjects = {};
  bool _isDivisionFavorite = false;
  String? _selectedProjectId;
  String _projectQuery = '';

  // 프로젝트 목록 필터/정렬
  _ProjectStatusFilter _statusFilter = _ProjectStatusFilter.all;
  _ProjectSort _sort = _ProjectSort.revenueDesc;
  bool _favoritesOnly = false;

  /// 매출 계획이 없는 프로젝트 그룹 펼침 여부

  late Future<List<DashboardCard>> _future;

  /// 진행률 요약 (백엔드 /projects-progress-summary)
  ProgressSummary _progress = ProgressSummary.empty;

  /// 이 사업부의 월 매출/출하 (백엔드 /overview?division_id=)
  OverviewSummary _overview = OverviewSummary.empty;
  bool _overviewLoading = true;

  /// 자동차사업부는 월 실적이 아니라 연 단위 계약이라 따로 받는다.
  /// (/divisions/automotive/summary — 고객사별 계약 매출·물량·원가 초과)
  AutoDivisionSummary _auto = AutoDivisionSummary.empty;
  bool _autoLoading = true;

  bool get _isAuto => widget.division.id == AutomotiveService.divisionId;

  /// 반도체사업부 매출은 주간보고 엑셀이 원본이다. 모델 판가로 계산한
  /// 값(/overview)과 숫자가 달라서, 홈에서는 $676만인데 사업부 화면은
  /// $400만이 떴다. 같은 사업부의 같은 달인데 화면마다 다르면 둘 다 못 믿는다.
  RevenueMonth _rev = RevenueMonth.empty;
  bool get _isSemi => widget.division.id == 'semiconductor';

  /// 주간보고 실적과 타겟을 쓸 수 있는 상태인지.
  bool get _useSheet => _isSemi && _rev.loaded && _rev.hasData;

  Future<void> _loadSheetRevenue() async {
    final r = await RevenueService.fetch();
    if (!mounted) return;
    setState(() => _rev = r);
  }

  /// 블룸은 '날짜 x 품목 x 공정' 이라 주차 실적이 아니라 일 보드를 본다.
  BloomDailyBoard _bloom = BloomDailyBoard.empty;
  bool get _isBloom => widget.division.id == BloomService.divisionId;

  Future<void> _loadBloom() async {
    final b = await BloomService.board(force: true);
    if (mounted) setState(() => _bloom = b);
  }

  /// 매입·지급 현황 (지금은 PCB 만 채워져 있다). 데이터가 없는 사업부는
  /// has_data=false 로 와서 카드가 통째로 빠진다.
  PurchaseStatus _purchase = PurchaseStatus.empty;

  /// 매입 현황이 있는 사업부는 그 카드만 본다. 매출·프로젝트는 아직
  /// 이 사업부 자료가 아니라서, 같이 두면 남의 숫자처럼 읽힌다.
  /// (다시 보여줄 때는 이 한 줄을 false 로)
  bool get _onlyPurchase => _purchase.hasData;

  // 아래 셋은 '그 사업부만 다른 틀을 쓴다' 는 뜻이다. 틀을 하나로 모은
  // 뒤로는 전부 false 가 되고, 전용 카드는 공통 틀 아래에서 따로 그린다.
  bool get _autoFrame => _isAuto && !kSameFrameForAll;
  bool get _bloomFrame => _isBloom && !kSameFrameForAll;
  bool get _purchaseFrame => _onlyPurchase && !kSameFrameForAll;

  /// 프로젝트 안에 있던 주차별 계획(주차 현황 보드)을 사업부 화면
  /// 위쪽으로 끌어올리는 사업부인가. 지금은 블룸만.
  bool get _divisionBoard => kDivisionBoardOn.contains(widget.division.id);

  /// 일 보고 자료가 날마다 들어오는 사업부인가 (ESS · 블룸).
  bool get _dailyBoard => kDailyBoardOn.contains(widget.division.id);

  /// 지금 목록에 뜬 매출이 보여주기용 예시인가 (버릴 코드).
  bool _demoRevenue = false;
  int _demoRev = 0;    // 예시 매출 합 (히어로에 올린다)
  int _demoPlan = 0;

  Future<void> _loadPurchase() async {
    final p = await PurchaseService.fetch(widget.division.id);
    if (mounted) setState(() => _purchase = p);
  }

  AutoProjectRow _autoOf(String key) {
    for (final r in _auto.projects) {
      if (r.key == key) return r;
    }
    // 아직 계약이 안 올라온 고객사. 빈 줄로 두고 '등록 전'으로 보여준다.
    return AutoProjectRow(
      key: key, label: '', products: 0, mass: 0, dev: 0,
      qty: 0, revenue: 0, yearQty: 0, yearRevenue: 0,
      share: 0, costRatio: null,
    );
  }

  @override
  void initState() {
    super.initState();
    _future = DashboardService.fetchCards();
    _loadFavorites();
    _loadProgress();
    _loadOverview();
    // 2026-10-23 — 안 그리는 카드의 자료는 받지 않는다.
    if (_autoFrame) _loadAuto();
    if (_bloomFrame) _loadBloom();
    if (_isSemi) _loadSheetRevenue();
    if (!kSameFrameForAll) _loadPurchase();
    // 국내 / 해외로 묶는 사업부(PCB)는 매출 기여순 대신 이름순이 기본 (2026-11-04)
    if (_grouped) _sort = _ProjectSort.name;
  }

  /// 고객사를 국내 / 해외(Lam · 아리스타 · 기타)로 묶어 보여 주나 (2026-11-04)
  ///
  /// 서버(/divisions 의 customer_groups)가 정한다 — 앱 배포 없이 바뀐다.
  /// 옛 서버라 안 보내 주면 앱에 적어 둔 값(customer_groups.dart)으로.
  bool get _grouped =>
      _groupOrder.isNotEmpty;

  List<List<String>> get _groupOrder =>
      widget.division.customerGroups.isNotEmpty
          ? widget.division.customerGroups
          : (customerGroupsOn(widget.division.id) ? kCustomerGroupOrder : const []);

  /// 그 고객사의 묶음 — 서버 값 먼저
  List<String> _groupOf(String projectId) {
    if (widget.division.customerGroups.isNotEmpty) {
      for (final p in widget.division.projects) {
        if (p.id == projectId && p.group != null) return p.group!;
      }
      return widget.division.customerGroups.first;
    }
    return customerGroupOf(widget.division.id, projectId) ?? const ['국내', ''];
  }

  /// 묶음 머리글 자리 — 위 버튼을 누르면 그 묶음으로 내려간다
  final Map<String, GlobalKey> _groupKeys = {};

  void _jumpTo(String gk) {
    final ctx = _groupKeys[gk]?.currentContext;
    if (ctx == null) return;
    Scrollable.ensureVisible(ctx,
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutCubic,
        alignment: 0.02);
  }

  Future<void> _loadAuto() async {
    if (mounted) setState(() => _autoLoading = true);
    // 사업부 합계 엔드포인트가 없는 서버에 붙어도 화면이 비지 않게
    // 고객사 키를 같이 넘긴다 (우회로에서 고객사별로 받아 모은다).
    final s = await AutomotiveService.division(
      keys: widget.division.projects.map((p) => p.id).toList(),
    );
    if (!mounted) return;
    setState(() {
      _auto = s;
      _autoLoading = false;
    });
  }

  Future<void> _loadProgress() async {
    final summary = await ProgressService.fetch();
    if (!mounted) return;
    setState(() => _progress = summary);
  }

  Future<void> _loadOverview() async {
    if (mounted) setState(() => _overviewLoading = true);
    final s = await OverviewService.fetch(divisionId: widget.division.id);
    if (!mounted) return;
    setState(() {
      _overview = s;
      _overviewLoading = false;
    });
  }

  /// 이번 달 남은 영업일(오늘 포함, 주말 제외). 공휴일은 반영하지 않는다.
  int _businessDaysLeft() {
    final now = DateTime.now();
    final last = DateTime(now.year, now.month + 1, 0).day;
    var n = 0;
    for (var d = now.day; d <= last; d++) {
      final wd = DateTime(now.year, now.month, d).weekday;
      if (wd <= DateTime.friday) n++;
    }
    return n;
  }

  /// 오늘이 속한 ISO 주차 라벨 ('W36').
  String _weekLabel() {
    final now = DateTime.now();
    final thursday = now.add(Duration(days: 4 - now.weekday));
    final jan1 = DateTime(thursday.year, 1, 1);
    final week = ((thursday.difference(jan1).inDays) / 7).floor() + 1;
    return 'W$week';
  }

  Future<void> _loadFavorites() async {
    final projs = await FavoritesService.loadAll();
    final isDivFav = await FavoritesService.isDivisionFavorite(widget.division.id);
    if (!mounted) return;
    setState(() {
      _favoriteProjects = projs;
      _isDivisionFavorite = isDivFav;
    });
  }

  Future<void> _toggleDivisionFavorite() async {
    final nowFav = await FavoritesService.toggleDivision(widget.division.id);
    if (!mounted) return;
    setState(() {
      _isDivisionFavorite = nowFav;
    });
  }

  // ── 자동차사업부 전용 블록 ─────────────────────────────────────────
  //
  // 반도체와 같은 카드를 쓰되 들어가는 말만 계약 기준으로 바꾼다.
  //   이번 달 실적 → 올해 계약 매출,  출하 → 계약 물량,  진행률 → 매출 비중
  // 그래서 사업부를 옮겨도 읽는 자리는 그대로다.

  Widget _autoHero() {
    final a = _auto;
    final y = a.years;
    final span = y.isEmpty ? '' : '${y.first}–${y.last} · ${y.length}년';
    final has = a.revenue > 0;
    return AutomotiveHeroCard(
      title: '계약 매출  ${a.year > 0 ? a.year : DateTime.now().year}년 / 전체',
      rightLabel: span,
      bigValue: has ? AutoFmt.eok(a.yearRevenue) : '',
      subValue: has ? '/ ${AutoFmt.eok(a.revenue)}' : '',
      // 원가율 = (판가 − 관리이윤) ÷ 판가. 물량으로 가중한 사업부 전체 값.
      pillText: a.costRatio == null ? '' : '원가율 ${AutoFmt.pct(a.costRatio, digits: 1)}',
      pillColor: AppColors.todayBlue,
      ratio: a.yearShare,
      barColor: AppColors.todayBlue,
      leftLabel: '계약 물량 (${a.year > 0 ? a.year : DateTime.now().year} → 전체)',
      leftValue: has
          ? '${AutoFmt.qtyShort(a.yearQty, unit: '')} → ${AutoFmt.qtyShort(a.qty)}'
          : '-',
      rightStatLabel: '고객사 · 제품',
      rightStatValue: has
          ? '${a.withContract}곳 · ${a.totalProducts}종'
          : '-',
      loading: _autoLoading && !a.loaded,
      loaded: a.loaded,
      emptyText: '등록된 계약이 없습니다',
    );
  }

  Widget _autoRow(_ProjectItem p) {
    final r = _autoOf(p.id);
    final has = r.hasContract;
    final dot = has ? AppColors.todayBlue : AppColors.statusGray;
    return AutomotiveRowCard(
      dotColor: dot,
      name: p.koreanName,
      value: has ? AutoFmt.eok(r.revenue) : '—',
      subValue: has ? '/ ${AutoFmt.qtyShort(r.qty)}' : '',
      ratio: r.share,
      barColor: AppColors.todayBlue,
      meta1: has ? '${_auto.year}년 ${AutoFmt.eok(r.yearRevenue)}' : '계약 미등록',
      meta2: '제품 ${r.products}종',
      trailing: !has
          ? '등록 전'
          : (r.costRatio == null
              ? '비중 ${(r.share * 100).round()}%'
              : '원가율 ${AutoFmt.pct(r.costRatio, digits: 1)}'),
      isFavorite: _favoriteProjects.contains(p.id),
      isSelected: _selectedProjectId == p.id,
      onTap: () => _tapProject(p.id, p.koreanName),
      onToggleFavorite: () => _toggleFavorite(p.id),
    );
  }

  Future<void> _refresh() async {
    setState(() {
      _future = DashboardService.fetchCards();
    });
    await Future.wait([
      _future,
      _loadProgress(),
      _loadOverview(),
      if (_autoFrame) _loadAuto(),
      if (_bloomFrame) _loadBloom(),
      if (!kSameFrameForAll) _loadPurchase(),
    ]);
  }

  String _statusLabel(String status) {
    switch (status.toUpperCase()) {
      case 'RED':
        return '지연';
      case 'YELLOW':
      case 'ORANGE':
        return '주의';
      case 'GREEN':
        return '정상';
      default:
        return '정상';
    }
  }

  String _headlineOf(DashboardCard c) {
    if (c.headline.trim().isNotEmpty) return c.headline.trim();
    if (c.summaryBullets.isEmpty) return c.projectLabel;

    var text = c.summaryBullets.first;
    text = text.replaceAll(RegExp(r'[*_`>#]'), '');
    text = text.replaceAll(RegExp(r'__[A-Za-z0-9_]+__'), '');
    text = text.replaceAll(RegExp(r'\([^)]*\)'), '');
    for (final sep in ['→', '->', '∎']) {
      final idx = text.indexOf(sep);
      if (idx > 0 && idx < 30) {
        text = text.substring(0, idx);
        break;
      }
    }
    text = text.trim();
    text = text.replaceAll(RegExp(r'(이|가|을|를|은|는|의|에|로|와|과|도)$'), '');
    if (text.length > 20) {
      final cut = text.substring(0, 20);
      final space = cut.lastIndexOf(' ');
      text = space > 10 ? '${cut.substring(0, space)}…' : '$cut…';
    }
    return text.isEmpty ? c.projectLabel : text;
  }

  String _todayText() {
    final now = DateTime.now();
    final y = now.year.toString().padLeft(4, '0');
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    final hh = now.hour.toString().padLeft(2, '0');
    final mm = now.minute.toString().padLeft(2, '0');
    return '$y-$m-$d $hh:$mm';
  }

  String _dueTextFrom(String? isoDate) {
    if (isoDate == null || isoDate.isEmpty) return '-';
    try {
      final parts = isoDate.split('-');
      if (parts.length < 3) return '-';
      final due = DateTime(
        int.parse(parts[0]),
        int.parse(parts[1]),
        int.parse(parts[2].substring(0, 2)),
      );
      final today = DateTime.now();
      final t = DateTime(today.year, today.month, today.day);
      final diff = due.difference(t).inDays;
      if (diff == 0) return 'D-day';
      if (diff > 0) return 'D-$diff';
      return 'D+${-diff}';
    } catch (_) {
      return '-';
    }
  }

  ImmediatePriority _immPriorityOf(String status, String dueText) {
    final s = status.toUpperCase();
    if (s == 'RED' && (dueText == 'D-day' || dueText == 'D-1')) {
      return ImmediatePriority.high;
    }
    return ImmediatePriority.mid;
  }

  _DivisionData _computeData(List<DashboardCard> allCards) {
    final divisionCards =
        allCards.where((c) => c.divisionId == widget.division.id).toList();

    // 프로젝트별 최악 상태 (지연 > 주의 > 정상) — 현황 카운트는 프로젝트 단위
    final worstStatusByKey = <String, String>{};
    int rank(String s) {
      switch (s.toUpperCase()) {
        case 'RED':
          return 3;
        case 'YELLOW':
        case 'ORANGE':
          return 2;
        default:
          return 1;
      }
    }
    for (final c in divisionCards) {
      if (c.projectKey.isEmpty) continue;
      final cur = worstStatusByKey[c.projectKey];
      if (cur == null || rank(c.status) > rank(cur)) {
        worstStatusByKey[c.projectKey] = c.status;
      }
    }

    // 즉시 확인: RED/ORANGE 카드 중 마감 임박 상위 3건
    final immCandidates = divisionCards
        .where((c) => c.status.toUpperCase() == 'RED' ||
            c.status.toUpperCase() == 'ORANGE')
        .toList();

    immCandidates.sort((a, b) {
      final da = a.dueDateMin ?? '9999-99-99';
      final db = b.dueDateMin ?? '9999-99-99';
      return da.compareTo(db);
    });

    final immediate = <DivisionImmediateItem>[];
    for (final c in immCandidates) {
      final due = _dueTextFrom(c.dueDateMin);
      final headline = _headlineOf(c);
      immediate.add(DivisionImmediateItem(
        priority: _immPriorityOf(c.status, due),
        dueText: due,
        headline: '${c.projectLabel} · $headline',
        status: _statusLabel(c.status),
      ));
    }

    // 프로젝트 카드 매핑
    // - Division 모델의 projects 리스트를 기준으로 하되,
    //   해당 project_key에 대응하는 dashboard 카드가 있으면 상태/진행률 반영
    final cardsByKey = <String, List<DashboardCard>>{};
    for (final c in divisionCards) {
      if (c.projectKey.isNotEmpty) {
        cardsByKey.putIfAbsent(c.projectKey, () => []).add(c);
      }
    }
    // 진행률은 모델 실데이터(/projects-progress-summary) 기준.
    // 데이터가 없으면 null → 카드에 '-' 표시하고 평균에서도 제외.
    int? avgProgressOf(String key) => _progress.of(key)?.progress;
    final cardByKey = <String, DashboardCard>{};
    for (final e in cardsByKey.entries) {
      cardByKey[e.key] = e.value.first;
    }

    // 매출/출하는 /overview 응답을 프로젝트 키로 붙인다.
    final revByKey = <String, OverviewProject>{
      for (final o in _overview.items) o.key: o,
    };

    final projects = <_ProjectItem>[];
    for (final p in widget.division.projects) {
      final card = cardByKey[p.id];
      final int? percent = avgProgressOf(p.id);
      // '데이터 있음' = 진행률이 산출되는 프로젝트 (모델만 있고 입력이 없으면 미등록)
      final hasData = _progress.of(p.id)?.hasData ?? false;
      final status = hasData && card != null ? _statusLabel(card.status) : '';
      final rev = revByKey[p.id];
      projects.add(_ProjectItem(
        id: p.id,
        englishName: _englishOf(p.id),
        koreanName: p.label,
        status: status,
        progressPercent: percent,
        hasData: hasData,
        modelsTotal: _progress.of(p.id)?.modelsTotal ?? 0,
        revenue: rev?.revenue ?? 0,
        planRevenue: rev?.planRevenue ?? 0,
        qtyPlan: rev?.qtyPlan ?? 0,
        qtyActual: rev?.qtyActual ?? 0,
      ));
    }

    // 백엔드 카드에는 있지만 division.projects에는 없는 경우 보강
    for (final c in divisionCards) {
      if (c.projectKey.isEmpty) continue;
      final exists = projects.any((p) => p.id == c.projectKey);
      if (exists) continue;
      final rev = revByKey[c.projectKey];
      projects.add(_ProjectItem(
        id: c.projectKey,
        englishName: _englishOf(c.projectKey),
        koreanName: c.projectLabel,
        status: _statusLabel(c.status),
        progressPercent: avgProgressOf(c.projectKey),
        hasData: _progress.of(c.projectKey)?.hasData ?? false,
        modelsTotal: _progress.of(c.projectKey)?.modelsTotal ?? 0,
        revenue: rev?.revenue ?? 0,
        planRevenue: rev?.planRevenue ?? 0,
        qtyPlan: rev?.qtyPlan ?? 0,
        qtyActual: rev?.qtyActual ?? 0,
      ));
    }

    // ── 보여주기용 매출 예시 (버릴 코드) ──────────────────────────
    //
    // 자동차는 월 매출이 /overview 에 안 들어와서 모든 줄이 '매출 미등록'
    // 으로 떨어지고, 그러면 목록이 통째로 접힌 그룹으로 내려가 첫 화면이
    // 빈다. 보고용으로 숫자를 채운다 — 서버에 0 만 있을 때만.
    //
    // 버릴 때: app_config 의 kDemoBoardData 를 false 로. (demo_board.dart)
    _demoRevenue = false;
    _demoRev = 0;
    _demoPlan = 0;
    if (kDemoBoardData &&
        DemoBoard.hasRevenue(widget.division.id) &&
        !projects.any((p) => p.revenue > 0 || p.planRevenue > 0)) {
      for (var i = 0; i < projects.length; i++) {
        final d = DemoBoard.of(widget.division.id, projects[i].id);
        if (d == null || d.planRevenue <= 0) continue;
        projects[i] = projects[i].withRevenue(d.revenue, d.planRevenue);
        _demoRev += d.revenue;
        _demoPlan += d.planRevenue;
        _demoRevenue = true;
      }
    }

    // ── 사업부 전체 진행률: 집계 대상 '모델' 가중 평균
    final keys = projects.map((p) => p.id);
    final scoredModels = _progress.scoredModelsFor(keys);
    final int? progress = _progress.weightedFor(keys);

    // ── 현황 카운트: 프로젝트 단위 (지연 + 주의 + 정상 + 미등록 = 전체)
    int red = 0, orange = 0, green = 0, noData = 0;
    for (final p in projects) {
      if (!p.hasData) {
        noData++;
        continue;
      }
      switch ((worstStatusByKey[p.id] ?? 'GREEN').toUpperCase()) {
        case 'RED':
          red++;
          break;
        case 'YELLOW':
        case 'ORANGE':
          orange++;
          break;
        default:
          green++;
      }
    }

    return _DivisionData(
      progressPercent: progress,
      progressDeltaPp: null, // 전월 데이터가 없으므로 표시하지 않음
      delayed: red,
      warning: orange,
      normal: green,
      noData: noData,
      scoredModels: scoredModels,
      updatedAt: _todayText(),
      immediate: immediate,
      projects: projects,
    );
  }

  // project_key → 영문 라벨.
  // 자동 변환이 어색한 특수 케이스는 명시적 매핑을 우선 사용.
  static const Map<String, String> _englishOverrides = {
    'tolon': 'Torlon',
    'eos_chamber': 'EOS Chamber',
    'faraday_4t': 'Faraday 4T',
    'hrva_plate': 'Hrva Plate',
    'plating_cell': 'Plating Cell',
    'major_module': 'Major Module',
    'powerbox': 'Powerbox',
    'chamber': 'Chamber',
    'spacex': 'CURIE (Space X)',
    'enclosure': 'Enclosure',
    'frame': 'Frame',
    'cup': 'CUP',
  };

  String _englishOf(String key) {
    if (key.isEmpty) return '';
    final override = _englishOverrides[key];
    if (override != null) return override;
    return key
        .split('_')
        .map((w) => w.isEmpty ? '' : (w[0].toUpperCase() + w.substring(1)))
        .join(' ');
  }

  List<_ProjectItem> _sortProjects(List<_ProjectItem> input) {
    final list = [...input];
    list.sort((a, b) {
      // 즐겨찾기 먼저, 그다음 데이터 있는 프로젝트, 그 안에서 선택한 정렬
      final aFav = _favoriteProjects.contains(a.id);
      final bFav = _favoriteProjects.contains(b.id);
      if (aFav != bFav) return aFav ? -1 : 1;
      // 자동차는 월 매출이 없다. /overview 값으로 줄을 세우면 순서가 무작위가 된다.
      // 2026-10-23 — 틀을 하나로 모으면서 줄 세우는 법도 같이 쓴다.
      if (_autoFrame) {
        final ar = _autoOf(a.id).revenue;
        final br = _autoOf(b.id).revenue;
        if (ar != br) return br.compareTo(ar);
        return a.koreanName.compareTo(b.koreanName);
      }
      // 국내 / 해외로 묶는 사업부는 매출 · 자료 유무로 앞세우지 않는다 —
      // 이름순으로 두면 찾는 고객사가 늘 같은 자리에 있다 (2026-11-04).
      if (!_grouped) {
        if (a.hasRevenue != b.hasRevenue) return a.hasRevenue ? -1 : 1;
        if (a.hasData != b.hasData) return a.hasData ? -1 : 1;
      }

      final ap = a.progressPercent;
      final bp = b.progressPercent;
      switch (_sort) {
        case _ProjectSort.revenueDesc:
          // 매출 기여는 '실적'이 아니라 '이 달에 걸린 금액'(계획)이 기준이다.
          // 실적순으로 두면 아직 안 나간 큰 건이 맨 아래로 밀린다.
          if (a.planRevenue != b.planRevenue) {
            return b.planRevenue.compareTo(a.planRevenue);
          }
          if (a.revenue != b.revenue) return b.revenue.compareTo(a.revenue);
          break;
        case _ProjectSort.achievementAsc:
          final ar = a.planRevenue <= 0 ? 1000.0 : a.revenue * 100 / a.planRevenue;
          final br = b.planRevenue <= 0 ? 1000.0 : b.revenue * 100 / b.planRevenue;
          if (ar != br) return ar.compareTo(br);
          break;
        case _ProjectSort.progressDesc:
          if (ap != bp) return (bp ?? -1).compareTo(ap ?? -1);
          break;
        case _ProjectSort.progressAsc:
          if (ap != bp) return (ap ?? 999).compareTo(bp ?? 999);
          break;
        case _ProjectSort.name:
          break;
      }
      return a.koreanName.compareTo(b.koreanName);
    });
    return list;
  }

  bool _matchesStatusFilter(_ProjectItem p) {
    switch (_statusFilter) {
      case _ProjectStatusFilter.all:
        return true;
      case _ProjectStatusFilter.normal:
        return p.hasData && p.status == '정상';
      case _ProjectStatusFilter.warning:
        return p.hasData && p.status == '주의';
      case _ProjectStatusFilter.delayed:
        return p.hasData && p.status == '지연';
      case _ProjectStatusFilter.noData:
        return !p.hasData;
    }
  }

  /// 고객사 한 줄 — 아래 '한 목록' 과 같은 모양 (매출 있으면 금액 줄)
  Widget _projectRow(_ProjectItem p) {
    if (p.hasRevenue) {
      return ProjectRevenueRow(
        koreanName: p.koreanName,
        status: p.status,
        revenue: p.revenue,
        planRevenue: p.planRevenue,
        qtyPlan: p.qtyPlan,
        qtyActual: p.qtyActual,
        modelsTotal: p.modelsTotal,
        progressPercent: p.progressPercent,
        isFavorite: _favoriteProjects.contains(p.id),
        isSelected: _selectedProjectId == p.id,
        onTap: () => _tapProject(p.id, p.koreanName),
        onToggleFavorite: () => _toggleFavorite(p.id),
      );
    }
    return ProjectPlainRow(
      koreanName: p.koreanName,
      modelsTotal: p.modelsTotal,
      progressPercent: p.progressPercent,
      isFavorite: _favoriteProjects.contains(p.id),
      onTap: () => _tapProject(p.id, p.koreanName),
      onToggleFavorite: () => _toggleFavorite(p.id),
    );
  }

  /// 국내 → 해외(Lam · 아리스타 · 기타). 묶음 안은 고른 정렬 그대로.
  /// 빈 묶음은 안 그린다.
  List<Widget> _groupedRows(List<_ProjectItem> list) {
    final by = <String, List<_ProjectItem>>{};
    for (final p in list) {
      final g = _groupOf(p.id);
      by.putIfAbsent('${g[0]}|${g[1]}', () => []).add(p);
    }
    final out = <Widget>[];
    // ── 바로 가기 버튼 (2026-11-04)
    // Min: "국내, 해외 위에 버튼으로 바로 이동 할 수 있게끔 해줘"
    final jumps = <Widget>[];
    for (final g in _groupOrder) {
      final n = by['${g[0]}|${g[1]}']?.length ?? 0;
      if (n == 0) continue;
      final gk = '${g[0]}|${g[1]}';
      jumps.add(_jumpChip(g[1].isEmpty ? g[0] : '${g[0]} · ${g[1]}', n, () => _jumpTo(gk)));
    }
    if (jumps.length > 1) {
      out.add(Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Wrap(spacing: 6, runSpacing: 6, children: jumps),
      ));
    }
    String? lastBig;
    for (final g in _groupOrder) {
      final items = by['${g[0]}|${g[1]}'] ?? const <_ProjectItem>[];
      if (items.isEmpty) continue;
      final gk = '${g[0]}|${g[1]}';
      final key = _groupKeys.putIfAbsent(gk, () => GlobalKey());
      if (g[0] != lastBig) {
        final n = _groupOrder
            .where((x) => x[0] == g[0])
            .fold<int>(0, (a, x) => a + (by['${x[0]}|${x[1]}']?.length ?? 0));
        // 작은 묶음이 없는 큰 묶음(국내)은 큰 머리글이 곧 버튼이 내려갈 자리다
        final head = _groupHead(g[0], n, big: true, first: lastBig == null);
        out.add(g[1].isEmpty ? KeyedSubtree(key: key, child: head) : head);
        lastBig = g[0];
      }
      if (g[1].isNotEmpty) {
        out.add(KeyedSubtree(key: key, child: _groupHead(g[1], items.length)));
      }
      for (final p in items) {
        out.add(_projectRow(p));
        out.add(const SizedBox(height: 8));
      }
    }
    return out;
  }

  Widget _jumpChip(String label, int n, VoidCallback onTap) {
    return Material(
      color: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Color(0xFFDDE3EA)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF1F2937))),
            const SizedBox(width: 5),
            Text('$n',
                style: const TextStyle(
                    fontSize: 11.5, fontWeight: FontWeight.w700, color: Color(0xFF94A3B8))),
            const SizedBox(width: 2),
            const Icon(Icons.south_rounded, size: 12, color: Color(0xFF94A3B8)),
          ]),
        ),
      ),
    );
  }

  Widget _groupHead(String label, int n, {bool big = false, bool first = false}) {
    return Padding(
      padding: EdgeInsets.fromLTRB(big ? 2 : 6, big ? (first ? 2 : 14) : 4, 2, 6),
      child: Row(children: [
        if (!big)
          Container(
            width: 3,
            height: 12,
            margin: const EdgeInsets.only(right: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF94A3B8),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        Text(label,
            style: TextStyle(
              fontSize: big ? 13.5 : 12,
              fontWeight: FontWeight.w800,
              color: big ? AppColors.headerNavy : const Color(0xFF475569),
            )),
        const SizedBox(width: 6),
        Text('$n',
            style: TextStyle(
              fontSize: big ? 12 : 11,
              fontWeight: FontWeight.w700,
              color: AppColors.textHint,
            )),
      ]),
    );
  }

  List<_ProjectItem> _visibleProjects(List<_ProjectItem> sorted) {
    final q = _projectQuery.trim().toLowerCase();
    final trimmed = _projectQuery.trim();
    return sorted.where((p) {
      if (!_matchesStatusFilter(p)) return false;
      if (_favoritesOnly && !_favoriteProjects.contains(p.id)) return false;
      if (q.isEmpty) return true;
      return p.englishName.toLowerCase().contains(q) ||
          p.koreanName.contains(trimmed) ||
          p.status.contains(trimmed);
    }).toList();
  }

  // 프로젝트 목록 필터 시트 (상태 / 정렬 / 즐겨찾기)
  Future<void> _openFilterSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            void update(VoidCallback fn) {
              setSheetState(fn);
              setState(fn);
            }

            Widget chip(String label, bool selected, VoidCallback onTap) {
              return GestureDetector(
                onTap: onTap,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: selected ? AppColors.headerNavy : Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: selected
                          ? AppColors.headerNavy
                          : const Color(0xFFD1D5DB),
                    ),
                  ),
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: selected ? Colors.white : AppColors.reportBody,
                    ),
                  ),
                ),
              );
            }

            Widget section(String title, List<Widget> children) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: AppText.bodyStrong.copyWith(
                          fontSize: 13, color: AppColors.headerNavy)),
                  const SizedBox(height: 8),
                  Wrap(spacing: 6, runSpacing: 6, children: children),
                  const SizedBox(height: 16),
                ],
              );
            }

            return Padding(
              padding: EdgeInsets.fromLTRB(
                16,
                16,
                16,
                16 + MediaQuery.of(sheetContext).padding.bottom,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text('프로젝트 필터',
                          style: AppText.bodyStrong
                              .copyWith(fontSize: 15, color: AppColors.headerNavy)),
                      const Spacer(),
                      TextButton(
                        onPressed: () => update(() {
                          _statusFilter = _ProjectStatusFilter.all;
                          _sort = _ProjectSort.progressDesc;
                          _favoritesOnly = false;
                        }),
                        child: const Text('초기화',
                            style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  section('상태', [
                    for (final f in _ProjectStatusFilter.values)
                      chip(f.label, _statusFilter == f,
                          () => update(() => _statusFilter = f)),
                  ]),
                  section('정렬', [
                    for (final v in _ProjectSort.values)
                      chip(v.label, _sort == v, () => update(() => _sort = v)),
                  ]),
                  section('보기', [
                    chip('즐겨찾기만', _favoritesOnly,
                        () => update(() => _favoritesOnly = !_favoritesOnly)),
                  ]),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                          backgroundColor: AppColors.headerNavy),
                      onPressed: () => Navigator.of(sheetContext).pop(),
                      child: const Text('적용'),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _toggleFavorite(String id) async {
    final nowFav = await FavoritesService.toggle(id);
    if (!mounted) return;
    setState(() {
      if (nowFav) {
        _favoriteProjects = {..._favoriteProjects, id};
      } else {
        _favoriteProjects = {..._favoriteProjects}..remove(id);
      }
    });
  }

  /// 행 탭 → 선택 표시 → 상세 진입 → 복귀 시 선택 해제.
  Future<void> _tapProject(String projectKey, String projectName) async {
    setState(() => _selectedProjectId = projectKey);
    await _openProject(projectKey, projectName);
    if (!mounted) return;
    setState(() => _selectedProjectId = null);
  }

  Future<void> _openProject(String projectKey, String projectName) async {
    // 모델 데이터 로드
    // 모델 데이터 로드 (사용하지 않음)

    // 모델 있든 없든 프로젝트 현황 화면으로 이동
    if (!mounted) return;

    // 모델 있든 없든 프로젝트 현황 화면으로 이동
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ProjectOverviewScreen(
          projectKey: projectKey,
          projectName: projectName,
        ),
      ),
    );
    // 상세에서 돌아오면 즐겨찾기 상태 재로드
    await _loadFavorites();
  }

  void _handleBottomNav(AppNavTab tab) {
    switch (tab) {
      case AppNavTab.home:
        Navigator.of(context).popUntil((route) => route.isFirst);
        break;
      case AppNavTab.list:
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => const DivisionSelectScreen(),
          ),
        );
        break;
      case AppNavTab.calendar:
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => const CalendarScreen(),
          ),
        );
        break;
      case AppNavTab.settings:
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('설정 화면은 준비 중입니다.')),
        );
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.reportPageBg,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: AppColors.headerNavy,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleSpacing: 0,
        leading: IconButton(
          icon: const Icon(Icons.chevron_left_rounded, size: 28),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              widget.division.label,
              style: const TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: 17,
              ),
            ),
            const SizedBox(width: 6),
            GestureDetector(
              onTap: _toggleDivisionFavorite,
              child: Icon(
                _isDivisionFavorite ? Icons.star_rounded : Icons.star_border_rounded,
                color: _isDivisionFavorite ? const Color(0xFFF4B63D) : const Color(0xFFB0B0B0),
                size: 20,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _refresh,
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(28),
          child: Container(
            width: double.infinity,
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(
              '목록 > ${widget.division.label}',
              style: AppText.caption.copyWith(
                fontSize: 11,
                color: const Color(0xFF7C8594),
              ),
            ),
          ),
        ),
      ),
      body: FutureBuilder<List<DashboardCard>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError || snap.data == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  '데이터를 불러오지 못했어요.\n${snap.error ?? ''}',
                  textAlign: TextAlign.center,
                  style: AppText.caption.copyWith(color: AppColors.reportBody),
                ),
              ),
            );
          }

          final data = _computeData(snap.data!);
          final sortedProjects = _sortProjects(data.projects);
          final visibleProjects = _visibleProjects(sortedProjects);

          return SafeArea(
            top: false,
            child: RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                // 묶음 버튼으로 내려가려면 아래 줄까지 미리 그려져 있어야 한다.
                // 고객사가 서른 줄 남짓이라 다 그려도 가볍다.
                cacheExtent: _grouped ? 20000 : null,
                children: [
                  // 2026-10-23 — 사업부 전용 카드는 안 그린다.
                  // 반도체사업부 화면에 없는 것은 어느 사업부에도 없다.
                  // (블룸 일일 보드 · 매입 현황 · 자동차 계약 카드)
                  if (_bloomFrame && _bloom.hasBoard) ...[
                    BloomPlanActualCard(board: _bloom),
                    const SizedBox(height: 12),
                    BloomTodayCard(board: _bloom),
                    const SizedBox(height: 12),
                  ],
                  if (_purchaseFrame) ...[
                    PurchaseStatusCard(status: _purchase),
                    const SizedBox(height: 12),
                  ],
                  if (_autoFrame)
                    _autoHero()
                  // 블룸은 '계획 대비 실적' 카드에 매출이 이미 있다. 매출 계획이
                  // 따로 등록된 적도 없어서 '계획이 없습니다' 만 떴다 — 뺀다.
                  // (보드가 없고 매출이 등록돼 있을 때만 보여준다)
                  else if (!_purchaseFrame &&
                      (!_bloomFrame ||
                          (!_bloom.hasBoard &&
                              (_overview.planRevenue > 0 ||
                                  _overview.revenue > 0))))
                    DivisionRevenueHero(
                    month: _useSheet ? _rev.month : _overview.month,
                    // 반도체는 주간보고 실적과 사람이 넣은 타겟을 쓴다.
                    //
                    // 예시 매출을 띄우는 사업부(자동차)는 히어로도 그 합으로
                    // 바꾼다. /overview 는 사업부를 안 가려 회사 전체 값을
                    // 돌려주는데, 아래 목록은 예시 숫자라 둘이 안 맞으면
                    // 보여줄 때 더 헷갈린다. 딱지는 '예시 ·' 로 붙인다.
                    revenue: _demoRevenue
                        ? _demoRev
                        : (_useSheet ? _rev.actual : _overview.revenue),
                    planRevenue: _demoRevenue
                        ? _demoPlan
                        : (_useSheet ? _rev.target : _overview.planRevenue),
                    pairLabel: _demoRevenue
                        ? '예시 · 실적 / 계획'
                        : (_useSheet
                            ? (_rev.hasTarget ? '실적 / 타겟' : '실적')
                            : '실적 / 계획'),
                    qtyPlan: _overview.qtyPlan,
                    qtyActual: _overview.qtyActual,
                    weekLabel: _weekLabel(),
                    businessDaysLeft: _businessDaysLeft(),
                    loading: _overviewLoading && !_overview.loaded,
                    loaded: _overview.loaded,
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => RevenueDetailScreen(
                            divisionId: widget.division.id,
                            divisionLabel: widget.division.label,
                          ),
                        ),
                      );
                    },
                  ),
                  if (!_autoFrame && !_purchaseFrame &&
                      data.delayed + data.warning > 0) ...[
                    const SizedBox(height: 10),
                    DivisionAttentionBanner(
                      count: data.delayed + data.warning,
                      severe: data.delayed > 0,
                      headline: data.immediate.isEmpty
                          ? null
                          : data.immediate.first.headline,
                      onTap: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => ImmediateCheckScreen(
                              divisionFilterLabel: widget.division.label,
                            ),
                          ),
                        );
                      },
                    ),
                  ],
                  // ── 일 보고 보드 (ESS · 블룸) ──────────────────
                  // 날마다 들어오는 자료라 가장 최근 소식이다. 그래서
                  // 주차 보드보다 위에 둔다.
                  if (_dailyBoard) ...[
                    const SizedBox(height: 14),
                    DailyBoardCard(
                      key: ValueKey('daily-${widget.division.id}'),
                      divisionId: widget.division.id,
                    ),
                  ],
                  // ── 사업부 주차 현황 보드 (블룸 · 자동차) ────────
                  // 프로젝트 화면과 같은 표인데 '구분' 열이 프로젝트다.
                  // (YFP · Corva KPE · 외 N종 · 합계)
                  // 어느 프로젝트를 이름으로 세울지는 kDivisionBoardPicks.
                  if (_divisionBoard && data.projects.isNotEmpty) ...[
                    const SizedBox(height: 14),
                    WeeklyBoardCard(
                      key: ValueKey('division-board-${widget.division.id}'),
                      // 보드 머리글에서 고른 달을 그대로 넘긴다 (2026-11-04)
                      loader: (month) => DivisionBoardService.fetch(
                        divisionId: widget.division.id,
                        month: month,
                        projects: [
                          for (final p in data.projects)
                            BoardProject(
                              p.id,
                              p.koreanName.isEmpty ? p.englishName : p.koreanName,
                            ),
                        ],
                        picked: kDivisionBoardPicks[widget.division.id] ??
                            const <String>[],
                      ),
                    ),
                  ],
                  // 프로젝트 목록은 어느 사업부에나 있다. 전에는 블룸과
                  // 매입 사업부에서 통째로 빠져 있었다.
                  if (!_bloomFrame && !_purchaseFrame) ...[
                  const SizedBox(height: 18),

                  // ── 프로젝트 (매출 기여순)
                  Row(
                    children: [
                      Text(
                        ownerLabelOf(widget.division.id),
                        style: AppText.bodyStrong.copyWith(
                          fontSize: 14,
                          color: AppColors.headerNavy,
                        ),
                      ),
                      const SizedBox(width: 8),
                      // 지어낸 매출로 그린 목록이라는 걸 붙여 둔다. 이 딱지가
                      // 없으면 회의실에서 진짜 매출로 읽힌다 — 떼면 안 된다.
                      if (_demoRevenue) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 7, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF7ED),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: const Color(0xFFFDBA74)),
                          ),
                          child: const Text('예시',
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w800,
                                  color: Color(0xFF9A3412))),
                        ),
                        const SizedBox(width: 8),
                      ],
                      Text(
                        _grouped
                            ? '${widget.division.groupTitle.isNotEmpty ? widget.division.groupTitle : (_groupOrder.any((g) => g[0] == '국내') ? '국내 / 해외' : '종류별')}${_sort == _ProjectSort.name ? '' : ' · ${_sort.label}'} · ${visibleProjects.length}건'
                            : '${_autoFrame ? '계약 매출순' : _sort.label} · ${visibleProjects.length}건',
                        style: AppText.caption.copyWith(
                          fontSize: 11.5,
                          color: AppColors.textHint,
                        ),
                      ),
                      const Spacer(),
                      GestureDetector(
                        onTap: _openFilterSheet,
                        behavior: HitTestBehavior.opaque,
                        child: Row(
                          children: [
                            Text(
                              '정렬',
                              style: AppText.caption.copyWith(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w700,
                                color: AppColors.todayBlue,
                              ),
                            ),
                            const SizedBox(width: 2),
                            const Icon(Icons.keyboard_arrow_down_rounded,
                                size: 16, color: AppColors.todayBlue),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  SearchFilterRow(
                    value: _projectQuery,
                    onChanged: (v) {
                      setState(() {
                        _projectQuery = v;
                      });
                    },
                    onTapFilter: _openFilterSheet,
                    hintText: '${ownerLabelOf(widget.division.id)} 검색',
                  ),
                  const SizedBox(height: 12),

                  if (visibleProjects.isEmpty)
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      alignment: Alignment.center,
                      child: Text(
                        _projectQuery.trim().isEmpty
                            ? '이 사업부에 프로젝트가 없어요'
                            : '검색 결과가 없어요',
                        style: AppText.caption.copyWith(
                          fontSize: 12,
                          color: const Color(0xFF7C8594),
                        ),
                      ),
                    )
                  else if (_autoFrame) ...[
                    for (final p in visibleProjects) ...[
                      _autoRow(p),
                      const SizedBox(height: 8),
                    ],
                  ]
                  // ── 국내 / 해외 묶음 (PCB, 2026-11-04) ─────────────────
                  else if (_grouped) ..._groupedRows(visibleProjects)
                  // ── 한 목록으로 (2026-11-02) ──────────────────────────
                  // Min: "매출 계획 없는 프로젝트 구분 빼줘"
                  //
                  // 전에는 매출이 걸린 것만 본문에 두고 나머지를 접힌 그룹으로
                  // 내렸다. 줄 수는 줄었지만, 프로젝트가 어느 쪽에 있는지 먼저
                  // 알아야 찾을 수 있게 됐다. 이제 정렬 순서대로 한 줄씩 선다.
                  //
                  // 줄 모양만 다르다 — 매출이 없는 줄에 ProjectRevenueRow 를
                  // 쓰면 금액 칸에 0 / 0 이 그대로 박힌다.
                  else ...[
                    for (final p in visibleProjects) ...[
                      if (p.hasRevenue)
                        ProjectRevenueRow(
                          koreanName: p.koreanName,
                          status: p.status,
                          revenue: p.revenue,
                          planRevenue: p.planRevenue,
                          qtyPlan: p.qtyPlan,
                          qtyActual: p.qtyActual,
                          modelsTotal: p.modelsTotal,
                          progressPercent: p.progressPercent,
                          isFavorite: _favoriteProjects.contains(p.id),
                          isSelected: _selectedProjectId == p.id,
                          onTap: () => _tapProject(p.id, p.koreanName),
                          onToggleFavorite: () => _toggleFavorite(p.id),
                        )
                      else
                        ProjectPlainRow(
                          koreanName: p.koreanName,
                          modelsTotal: p.modelsTotal,
                          progressPercent: p.progressPercent,
                          isFavorite: _favoriteProjects.contains(p.id),
                          onTap: () => _tapProject(p.id, p.koreanName),
                          onToggleFavorite: () => _toggleFavorite(p.id),
                        ),
                      const SizedBox(height: 8),
                    ],
                  ],
                  ],

                ],
              ),
            ),
          );
        },
      ),
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          BottomPromptBar(
              onSubmit: (text) async {
                await Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => ChatScreen(initialQuestion: text),
                  ),
                );
              },
            ),
          AppBottomNav(
            current: AppNavTab.list,
            onChanged: _handleBottomNav,
          ),
        ],
      ),
    );
  }
}

class _DivisionData {
  final int? progressPercent;
  final int? progressDeltaPp;
  final int delayed;
  final int warning;
  final int normal;
  final int noData;
  final int scoredModels;
  final String updatedAt;
  final List<DivisionImmediateItem> immediate;
  final List<_ProjectItem> projects;

  _DivisionData({
    required this.progressPercent,
    required this.progressDeltaPp,
    required this.delayed,
    required this.warning,
    required this.normal,
    required this.noData,
    required this.scoredModels,
    required this.updatedAt,
    required this.immediate,
    required this.projects,
  });
}

enum _ProjectStatusFilter {
  all('전체'),
  normal('정상'),
  warning('주의'),
  delayed('지연'),
  noData('미등록');

  final String label;
  const _ProjectStatusFilter(this.label);
}

enum _ProjectSort {
  revenueDesc('매출 기여순'),
  achievementAsc('달성률 낮은순'),
  progressDesc('진행률 높은순'),
  progressAsc('진행률 낮은순'),
  name('이름순');

  final String label;
  const _ProjectSort(this.label);
}

class _ProjectItem {
  final String id;
  final String englishName;
  final String koreanName;
  final String status;
  final int? progressPercent;
  final bool hasData;
  final int modelsTotal;
  final int revenue;
  final int planRevenue;
  final int qtyPlan;
  final int qtyActual;

  const _ProjectItem({
    required this.id,
    required this.englishName,
    required this.koreanName,
    required this.status,
    required this.progressPercent,
    required this.hasData,
    this.modelsTotal = 0,
    this.revenue = 0,
    this.planRevenue = 0,
    this.qtyPlan = 0,
    this.qtyActual = 0,
  });

  /// 이번 달 매출 계획이나 실적이 잡혀 있는가.
  /// 없으면 리스트 본문이 아니라 접힌 그룹으로 내린다.
  bool get hasRevenue => planRevenue > 0 || revenue > 0;

  /// 매출만 갈아 끼운 사본. 보여주기용 예시에서만 쓴다 — 버릴 코드.
  _ProjectItem withRevenue(int rev, int plan) => _ProjectItem(
        id: id,
        englishName: englishName,
        koreanName: koreanName,
        status: status,
        progressPercent: progressPercent,
        hasData: hasData,
        modelsTotal: modelsTotal,
        revenue: rev,
        planRevenue: plan,
        qtyPlan: qtyPlan,
        qtyActual: qtyActual,
      );
}
