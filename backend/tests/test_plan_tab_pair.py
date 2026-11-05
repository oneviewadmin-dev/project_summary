# -*- coding: utf-8 -*-
"""주차별 계획 탭의 두 표가 '같은 숫자' 라는 걸 화면이 말하는가.

### 왜 이걸 세나

주차별 계획 탭에는 표가 둘이다.

    위  주차 현황 보드      구분(양산 · 개발 · 합계) 단위 — **앱에 그대로 뜨는 표**
    아래 모델별 주차별 계획  모델 한 줄씩 — 위 보드를 만든 숫자

둘이 무슨 사이인지 화면에 안 적혀 있으면, 보는 사람은 같은 숫자를 두 번
보는 줄 알고 한쪽만 고친다. 그러면 보고용 보드와 담당자 표가 어긋난다.
또 위 보드가 앱에 그대로 뜨는 표라는 걸 모르면, admin 과 앱을 따로
맞춰 보느라 같은 일을 두 번 한다.

여기서 보는 것은 **글자 한 줄**이지 계산이 아니다. 계산은
test_week_shortfall · test_weekly_roundtrip 이 본다.
"""
import io
import os

BACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(BACK, "admin_v2.html"), encoding="utf-8").read()

FAIL = []
def ok(c, m):
    if not c: FAIL.append(m)

# ── 1. 탭 안에 표가 둘 다 있다
pane_i = SRC.find('data-mpane="plan"')
ok(pane_i > 0, "주차별 계획 탭이 없다")
pane = SRC[pane_i:pane_i + 9000]
ok('id="wb-board"' in pane, "주차 현황 보드가 탭에 없다")
ok("모델별 주차별 계획" in pane, "모델별 주차별 계획 표가 탭에 없다")
# 보드가 **위**에 와야 한다 — 보고에서 먼저 읽는 표다
ok(pane.index('id="wb-board"') < pane.index("모델별 주차별 계획"),
   "모델별 표가 보드보다 위에 있다 — 보고에서 먼저 읽는 건 보드다")

# ── 2. 보드가 '앱에 뜨는 표' 라고 적혀 있다
ok("ov-app-tag" in pane, "보드에 '앱 화면' 딱지가 없다")
ok("앱에 그대로 뜹니다" in pane,
   "보드가 앱의 그 표라는 설명이 없다 — admin 과 앱을 따로 맞춰 보게 된다")

# ── 3. 아래 표가 위 보드의 재료라고 적혀 있다
ok("위 보드를 만든 숫자" in pane,
   "모델별 표가 보드의 재료라는 설명이 없다 — 같은 숫자를 두 번 보는 줄 안다")
ok("구분(양산 · 개발)으로 더한 값" in pane,
   "보드가 어떻게 만들어지는지(구분별 합) 안 적혀 있다")

# ── 4. 딱지와 설명에 쓸 모양이 CSS 에 있다
ok(".ov-app-tag{" in SRC, "ov-app-tag 모양이 없다")
ok(".wb-foot{" in SRC, "wb-foot 모양이 없다")

if FAIL:
    print("\n".join("· " + m for m in FAIL))
    raise SystemExit(1)
print("ok — 주차별 계획 탭: 보드(앱 화면) + 모델별, 둘 사이가 적혀 있다")
