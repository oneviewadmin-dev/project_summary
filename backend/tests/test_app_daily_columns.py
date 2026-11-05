# -*- coding: utf-8 -*-
"""앱의 블룸 보드 — 주차 칸과 '품목 전부' (2026-10-26).

앱은 날짜 칩만 있었고, 그날 숫자가 적힌 품목만 줄로 섰다. 그래서
  · 한 달치를 보려면 칩을 서른 번 눌러야 했고
  · 어제는 보이던 품목이 오늘은 사라져서 '빠진 건가' 를 매번 물었다

이제 가로 칸은 **서버가 접어서** 내려준다(daily_view.py → columns).
지난 주는 '41주차' 한 칸, 이번 주는 날짜. 앱은 받은 날짜만 더한다 —
앱이 따로 접으면 admin 과 숫자가 갈린다.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
MOB = os.path.join(os.path.dirname(BACK), "mobile", "lib")
sys.path.insert(0, BACK)

FAIL = []


def ok(c, why):
    if not c:
        FAIL.append(why)


def read(p):
    return io.open(os.path.join(MOB, p), encoding="utf-8").read()


MODEL = read("models/bloom_daily.dart")
CARD = read("widgets/bloom_plan_actual_card.dart")
MAIN = io.open(os.path.join(BACK, "main.py"), encoding="utf-8").read()

# ── 서버가 칸을 내려준다
ok('out["columns"] = cols' in MAIN, "서버가 접은 칸을 안 내려준다")

# ── 앱이 그 칸을 받는다
ok("class BloomColumn" in MODEL, "앱에 칸 모델이 없다")
ok("j['columns']" in MODEL, "앱이 columns 를 안 읽는다")
ok("BloomCell? over(List<String> dates)" in MODEL,
   "여러 날을 한 칸으로 더하는 자리가 없다")
# 안 적은 칸과 0 은 다르다
ok("return any ? BloomCell(plan: p, actual: a) : null;" in MODEL,
   "적힌 날이 하나도 없는 칸을 0 으로 만든다 — 안 적음과 0 이 같아진다")

# ── 앱이 접는 규칙을 또 들고 있으면 안 된다
ok("isoWeek" not in MODEL and "주차'" not in MODEL.replace("'41주차'", ""),
   "앱이 주차를 스스로 세고 있다 — 서버와 어긋난다")

# ── 품목은 전부 세운다
ok("for (var i = 0; i < b.items.length; i++)" in CARD,
   "품목을 걸러서 세운다 — 숫자가 없는 품목이 사라진다")
ok("(s, s.over(dates) ?? const BloomCell())" in CARD,
   "공정을 걸러서 세운다 — 안 적은 공정이 사라진다")
ok("dates: col.dates" in CARD, "고른 칸의 날짜를 줄에 안 넘긴다")

# ── 옛 서버면 날짜 칸으로 돌아간다 (되돌릴 자리)
ok("if (b.columns.isNotEmpty) return b.columns;" in CARD,
   "서버가 칸을 안 줄 때 날짜로 돌아갈 길이 없다")

# ── 탭 이름이 무엇을 보여주는지 말하는가
ok("주차 · 일별" in CARD, "탭이 아직 '일별' 이라고만 적혀 있다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 앱 블룸 보드 주차 칸")
