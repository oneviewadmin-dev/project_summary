import 'package:flutter/material.dart';

enum CalendarCategory { shipping, receiving, report, approval, milestone }

extension CalendarCategoryX on CalendarCategory {
  String get label {
    switch (this) {
      case CalendarCategory.shipping:
        return '출하';
      case CalendarCategory.receiving:
        return '입고';
      case CalendarCategory.report:
        return '보고';
      case CalendarCategory.approval:
        return '승인·검토';
      case CalendarCategory.milestone:
        return '마일스톤';
    }
  }

  Color get color {
    switch (this) {
      case CalendarCategory.shipping:
        return const Color(0xFFE53935);
      case CalendarCategory.receiving:
        return const Color(0xFF1E88E5);
      case CalendarCategory.report:
        return const Color(0xFF43A047);
      case CalendarCategory.approval:
        return const Color(0xFF8E24AA);
      case CalendarCategory.milestone:
        return const Color(0xFFFB8C00);
    }
  }
}

class CalendarEvent {
  final String id;
  final DateTime date;
  final CalendarCategory category;
  final String title;
  final String divisionLabel;
  final String projectLabel;
  final String? time;
  final bool isDone;
  final String projectKey;
  final String headline;

  /// 서버가 정한 상태 (2026-11-04) — 'done' · 'planned' · 'late' · 'soon'.
  /// 예전 방식(/dashboard 글자)으로 만든 일정은 빈 글자다.
  final String status;

  /// 지연이면 예정일에서 며칠 지났나
  final int? days;

  /// 날짜 없는 지연 — 달력 칸에는 안 놓고 마감 목록 맨 위에만 선다.
  final bool undated;

  const CalendarEvent({
    required this.id,
    required this.date,
    required this.category,
    required this.title,
    required this.divisionLabel,
    required this.projectLabel,
    this.time,
    this.isDone = false,
    this.projectKey = '',
    this.headline = '',
    this.status = '',
    this.days,
    this.undated = false,
  });

  bool get isLate => status == 'late';

  /// 줄 밑에 붙이는 한 마디. 홈과 같은 말을 쓴다 (utils/status_words.dart).
  String get statusLabel {
    switch (status) {
      case 'late':
        return days != null && days! > 0 ? '일정 지연 $days일' : '일정 지연';
      case 'soon':
        return '집중관리';
      case 'done':
        return '완료';
      case 'planned':
        return '예정';
      default:
        return '';
    }
  }

  static CalendarCategory _cat(String v) {
    switch (v) {
      case 'shipping':
        return CalendarCategory.shipping;
      case 'receiving':
        return CalendarCategory.receiving;
      case 'report':
        return CalendarCategory.report;
      case 'approval':
        return CalendarCategory.approval;
      default:
        return CalendarCategory.milestone;
    }
  }

  /// /calendar/events 한 줄 → 일정. 날짜가 이상하면 null (날짜 없는 지연은 오늘로).
  static CalendarEvent? fromServer(Map j) {
    final undated = (j['kind'] ?? '') == 'undated';
    DateTime? d = DateTime.tryParse((j['date'] ?? '').toString());
    if (d == null && undated) {
      final n = DateTime.now();
      d = DateTime(n.year, n.month, n.day);
    }
    if (d == null) return null;
    final st = (j['status'] ?? '').toString();
    return CalendarEvent(
      id: (j['id'] ?? '').toString(),
      date: d,
      category: _cat((j['category'] ?? '').toString()),
      title: (j['title'] ?? '').toString(),
      divisionLabel: (j['division'] ?? '').toString(),
      projectLabel: (j['project'] ?? '').toString(),
      projectKey: (j['project_key'] ?? '').toString(),
      headline: (j['note'] ?? '').toString(),
      isDone: st == 'done',
      status: st,
      days: (j['days'] as num?)?.toInt(),
      undated: undated,
    );
  }

  CalendarEvent copyWith({bool? isDone}) => CalendarEvent(
        id: id,
        date: date,
        category: category,
        title: title,
        divisionLabel: divisionLabel,
        projectLabel: projectLabel,
        time: time,
        isDone: isDone ?? this.isDone,
        projectKey: projectKey,
        headline: headline,
        status: status,
        days: days,
        undated: undated,
      );

  int diffDays(DateTime today) {
    final d0 = DateTime(today.year, today.month, today.day);
    final d1 = DateTime(date.year, date.month, date.day);
    return d1.difference(d0).inDays;
  }
}
