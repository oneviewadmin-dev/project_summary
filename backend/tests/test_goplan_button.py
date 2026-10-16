# -*- coding: utf-8 -*-
"""'주차별 계획으로 →' 버튼은 표를 다시 그려도 계속 눌려야 한다.

이 버튼은 모델 표 HTML 안에 들어 있다. 표는 엑셀을 올리거나 자동 반영이
돌 때마다 통째로 다시 그려지고, 그때 버튼도 새 것으로 바뀐다. 버튼을
직접 찾아 리스너를 붙이면 그 순간 떨어져 나가, 눌러도 아무 일이 없다.
실제로 그래서 안 눌렸다.

그래서 document 에 한 번만 걸고 눌린 것이 그 버튼인지 보는 방식으로
바꿨다. 다시 그 방식에서 벗어나면 여기서 잡는다.
"""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
SRC = (BACK / "admin_v2.html").read_text(encoding="utf-8")

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


ok('id="mdl-goplan-btn"' in SRC, "버튼이 없어졌다")
ok('id="mdl-tab-plan"' in SRC, "보낼 곳인 '주차별 계획' 탭이 없어졌다")

ok("window._mdlGoPlanWired" in SRC,
   "한 번만 거는 표시(_mdlGoPlanWired)가 없다 — 위임 방식이 아니다")
ok("t.closest('#mdl-goplan-btn')" in SRC,
   "document 에 걸고 눌린 것을 확인하는 코드가 없다")

# 옛 방식으로 되돌아가지 않았는지
ok("getElementById('mdl-goplan-btn')" not in SRC,
   "버튼을 직접 찾아 붙이고 있다 — 표를 다시 그리면 또 안 눌린다")

# 눌렀을 때 실제로 탭을 누르는지
i = SRC.find("window._mdlGoPlanWired")
blk = SRC[i:i + 700]
ok("getElementById('mdl-tab-plan')" in blk, "탭을 찾지 않는다")
ok("tab.click()" in blk, "탭을 누르지 않는다")
ok("mdl-import-menu" in blk, "열려 있던 엑셀 메뉴를 닫지 않는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 주차별 계획 버튼은 표를 다시 그려도 눌린다")
