# ============================================================
#  주차 ↔ 월 소유 규칙 단일 진입점
# ============================================================

from __future__ import annotations

import datetime as _dt


# ============================================================
#  그 달이 '일단' 가져가는 주차 목록을 만든다.
# ============================================================
# 규칙 (1)+(2) 만 적용한 주차 목록.
def month_weeks_base(y: int, m: int) -> list:
    first = _dt.date(y, m, 1)
    last = (_dt.date(y + 1, 1, 1) if m == 12 else _dt.date(y, m + 1, 1)) - _dt.timedelta(days=1)
    # 규칙 (1) — 그 달의 날짜를 하루씩 보면서, 목요일이 있으면 그 주차를 담는다
    weeks = []
    seen = set()
    cur = first
    while cur <= last:
        if cur.weekday() == 3:  # 목요일
            _, iso_week, _ = cur.isocalendar()
            key = f"W{iso_week:02d}"
            if key not in seen:
                seen.add(key)
                weeks.append(key)
        cur += _dt.timedelta(days=1)

    # 규칙 (2) — 말일이 낀 주가 아직 안 담겼으면, 그 주의 7일 중 이 달에 속한 날이 3일 이상일 때만 이 달이 가져간다
    _, w_last, _ = last.isocalendar()
    key_last = f"W{w_last:02d}"
    if key_last not in seen:
        mon = last - _dt.timedelta(days=last.weekday())
        days = sum(1 for i in range(7) if first <= mon + _dt.timedelta(days=i) <= last)
        if days >= 3:
            weeks.append(key_last)
    return weeks


# ============================================================
#  바깥에서 제일 많이 쓰는 입구.
# ============================================================
# '2026-09' → ['W36','W37','W38','W39','W40'].
def get_month_weeks(month: str) -> list:
    y, m = map(int, str(month).split("-"))
    weeks = month_weeks_base(y, m)
    # 규칙 (3) — 앞 달이 이미 가져간 주차는 앞에서부터 떼어낸다
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    prev = set(month_weeks_base(py, pm))
    while weeks and weeks[0] in prev:
        weeks = weeks[1:]
    return weeks


# ============================================================
#  반대 방향. 주차 하나를 주면 그게 어느 달 것인지 돌려준다.
# ============================================================
# 'W40' → 그 주차를 소유한 'YYYY-MM'.
def month_of_week(week_label, year=None):
    # ----------------------------------------------------------------------------
    #  'W40' · 'w40' · '40' 을 모두 숫자 40 으로 받는다. 이상하면 None
    # ----------------------------------------------------------------------------
    if week_label in (None, ""):
        return None
    try:
        n = int(str(week_label).upper().lstrip("W"))
    except Exception:
        return None
    if not (1 <= n <= 53):
        return None
    if year is None:
        year = _dt.date.today().year

    # 그 주차의 목요일이 몇 월인지 본다
    for _y in (year, year - 1):
        try:
            thu = _dt.date.fromisocalendar(_y, n, 4)      # 4 = 목요일
        except Exception:
            continue
        key = f"W{n:02d}"
        iso_month = f"{thu.year}-{thu.month:02d}"
        # 앞 달이 이 주차를 가져갔으면(2026년 9월의 W40 처럼) 그 달을 돌려준다
        py, pm = (thu.year - 1, 12) if thu.month == 1 else (thu.year, thu.month - 1)
        prev_month = f"{py}-{pm:02d}"
        try:
            if key in get_month_weeks(prev_month):
                return prev_month
        except Exception:
            pass
        return iso_month
    return None


# ============================================================
#  위와 같은 일을 하되 숫자로 받는다 (month_of_week_no(40, 2026)).
# ============================================================
# 주차 '번호'로 받는 형태. 임포터들이 쓰던 시그니처와 맞춘다
def month_of_week_no(week_no, year):
    return month_of_week(f"W{int(week_no):02d}", year)
