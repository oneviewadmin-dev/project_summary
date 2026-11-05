import '../services/offline_store.dart';
import 'dart:convert';
import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../design/typography.dart';

class DevProcessScreen extends StatefulWidget {
  final String projectKey;
  final String modelId;
  final String modelName;
  const DevProcessScreen({
    super.key,
    required this.projectKey,
    required this.modelId,
    required this.modelName,
  });

  @override
  State<DevProcessScreen> createState() => _DevProcessScreenState();
}

class _DevProcessScreenState extends State<DevProcessScreen> {
  late Future<Map<String, dynamic>> _future;

  // 반도체 13단계가 쓰는 묶음. 색만 여기서 가져온다.
  static const _groups = [
    ['발주', Color(0xFFDBEAFE), Color(0xFF1D4ED8)],
    ['제작·검사', Color(0xFFFEF3C7), Color(0xFFB45309)],
    ['승인', Color(0xFFEDE9FE), Color(0xFF7C3AED)],
  ];
  static const _plain = ['개발 단계', Color(0xFFF1F5F9), Color(0xFF475569)];

  /// 단계를 **서버가 준 그대로** 묶는다 (2026-11-02).
  ///
  /// Min: "자동차 개발은 고객사별로 개발 일정 양식이 맞춰져야돼"
  ///
  /// 전에는 위 세 묶음만 훑어서 `group` 이 그 셋 중 하나인 단계만 그렸다.
  /// 그런데 개발 일정 양식으로 들어온 단계는 group 이 빈 값이다 — 묶음은
  /// 반도체 13단계에만 붙어 있는 값이라서다. 그래서 자동차
  /// (01 T-car … 06 SOP) 와 블룸 (PO 발주 → PRP → 최종 승인) 은
  /// 진행률과 초록 체크는 맞게 나오는데 **단계 목록이 통째로 비어** 보였다.
  ///
  /// 이제 묶음이 있으면 그 묶음으로, 없으면 '개발 단계' 한 덩이로 그린다.
  /// 순서는 서버가 준 차례를 지킨다 — 고객사마다 단계가 달라서, 화면이
  /// 멋대로 재정렬하면 그 고객사의 일하는 차례가 깨진다.
  static List<List<dynamic>> _sections(List<Map<String, dynamic>> steps) {
    final out = <List<dynamic>>[];
    final seen = <String>{};
    for (final s in steps) {
      final g = (s['group'] ?? '').toString().trim();
      final key = g.isEmpty ? _plain[0] as String : g;
      if (seen.contains(key)) continue;
      seen.add(key);
      final known = _groups.firstWhere((x) => x[0] == key,
          orElse: () => _plain);
      out.add([key, known[1], known[2]]);
    }
    return out;
  }

  @override
  void initState() {
    super.initState();
    _future = _fetch();
  }

  Future<Map<String, dynamic>> _fetch() async {
    final res = await OfflineStore
        .httpGet(Uri.parse(
            '$kApiBaseUrl/projects/${widget.projectKey}/model-process?model_id=${Uri.encodeComponent(widget.modelId)}'))
        .timeout(const Duration(seconds: 8));
    if (res.statusCode != 200) throw Exception('HTTP ${res.statusCode}');
    return jsonDecode(utf8.decode(res.bodyBytes));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F6F8),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        title: Text(widget.modelName, style: AppText.bodyStrong.copyWith(fontSize: 17)),
        iconTheme: const IconThemeData(color: Color(0xFF111827)),
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(OfflineStore.errorText(snap.error), textAlign: TextAlign.center, style: const TextStyle(fontSize: 13.5, height: 1.5, color: Color(0xFF6B7280)))));
          }
          final d = snap.data ?? {};
          final steps = (d['steps'] as List? ?? []).cast<Map<String, dynamic>>();
          final done = (d['done'] as num?)?.toInt() ?? 0;
          final total = (d['total'] as num?)?.toInt() ?? 13;
          final progress = (d['progress'] as num?)?.toInt() ?? 0;
          final devType = (d['dev_type'] ?? 'HVM').toString();
          final currentStage = (d['current_stage'] ?? '').toString();
          final currentExpected = (d['current_expected'] ?? '').toString();
          final issueLines = (d['issues'] ?? '')
              .toString()
              .split('\n')
              .where((s) => s.trim().isNotEmpty)
              .toList();

          int num0 = 0;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // 요약 카드
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE5E7EB)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                        decoration: BoxDecoration(
                          color: devType == 'RPM' ? const Color(0xFFE0F2FE) : const Color(0xFFEDE9FE),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(devType,
                            style: TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w800,
                              color: devType == 'RPM' ? const Color(0xFF0284C7) : const Color(0xFF7C3AED),
                            )),
                      ),
                      const Spacer(),
                      Text('$progress%',
                          style: const TextStyle(
                              fontSize: 24, fontWeight: FontWeight.w800, color: Color(0xFF0F2C59))),
                    ]),
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: progress / 100,
                        minHeight: 8,
                        backgroundColor: const Color(0xFFF3F4F6),
                        valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF0F2C59)),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      currentStage.isEmpty
                          ? '진행률 $done / $total 단계 · 일정 미등록'
                          : '진행률 $done / $total 단계 · 다음 단계: $currentStage'
                              '${currentExpected.isNotEmpty ? ' (예상 $currentExpected)' : ''}',
                      style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
                    ),
                  ],
                ),
              ),
              // 이슈사항 카드 (이슈 있을 때만 표시)
              if (issueLines.isNotEmpty) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE5E7EB)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('이슈사항',
                          style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                      const SizedBox(height: 10),
                      for (final line in issueLines)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('• ',
                                  style: TextStyle(color: Color(0xFFD32F2F), fontSize: 13)),
                              Expanded(
                                child: Text(line,
                                    style: const TextStyle(fontSize: 13, height: 1.5)),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 12),
              // 단계 그룹
              ..._sections(steps).map((g) {
                final list = steps.where((s) {
                  final sg = (s['group'] ?? '').toString().trim();
                  return (sg.isEmpty ? _plain[0] : sg) == g[0];
                }).toList();
                if (list.isEmpty) return const SizedBox.shrink();
                return Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE5E7EB)),
                  ),
                  child: Column(
                    children: [
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: g[1] as Color,
                          borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                        ),
                        child: Row(children: [
                          Text(g[0] as String,
                              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: g[2] as Color)),
                          const Spacer(),
                          Text('${list.length}단계',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: g[2] as Color)),
                        ]),
                      ),
                      ...list.map((s) {
                        num0++;
                        final stepStatus = (s['status'] ?? '').toString().trim();
                        final isDone = (s['actual'] ?? '').toString().trim().isNotEmpty ||
                            stepStatus == '완료';
                        // 계획일·실적일·상태가 하나도 없으면 '진행중'으로 표시하지 않는다
                        final hasInput = (s['expected'] ?? '').toString().trim().isNotEmpty ||
                            (s['actual'] ?? '').toString().trim().isNotEmpty ||
                            stepStatus.isNotEmpty;
                        final isCurrent = !isDone &&
                            hasInput &&
                            (stepStatus == '진행중' ||
                                (currentStage.isNotEmpty && s['name'] == currentStage));
                        final expected = (s['expected'] ?? '').toString();
                        final actual = (s['actual'] ?? '').toString();
                        return Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: isCurrent ? const Color(0xFFFFFBEB) : Colors.white,
                            border: const Border(top: BorderSide(color: Color(0xFFF3F4F6))),
                          ),
                          child: Row(children: [
                            Container(
                              width: 24, height: 24,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: isDone
                                    ? const Color(0xFFD1FAE5)
                                    : (isCurrent ? const Color(0xFFDBEAFE) : const Color(0xFFF3F4F6)),
                              ),
                              alignment: Alignment.center,
                              child: Icon(
                                isDone ? Icons.check : (isCurrent ? Icons.play_arrow : Icons.circle),
                                size: 14,
                                color: isDone
                                    ? const Color(0xFF059669)
                                    : (isCurrent ? const Color(0xFF1D4ED8) : const Color(0xFF9CA3AF)),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                Text('${num0.toString().padLeft(2, '0')} ${s['name']}',
                                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                                const SizedBox(height: 2),
                                Text(
                                  '계획 ${expected.isNotEmpty ? expected : '-'} · 실제 ${actual.isNotEmpty ? actual : '미완료'}',
                                  style: const TextStyle(fontSize: 11, color: Color(0xFF9CA3AF)),
                                ),
                              ]),
                            ),
                            Text(
                              isDone ? '완료' : (isCurrent ? '진행중' : '대기'),
                              style: TextStyle(
                                fontSize: 11, fontWeight: FontWeight.w700,
                                color: isDone
                                    ? const Color(0xFF059669)
                                    : (isCurrent ? const Color(0xFF1D4ED8) : const Color(0xFF9CA3AF)),
                              ),
                            ),
                          ]),
                        );
                      }),
                    ],
                  ),
                );
              }),
            ],
          );
        },
      ),
    );
  }
}
