# -*- coding: utf-8 -*-
"""사업부를 바꾸면 '보고 있던 화면'이 다시 그려져야 한다.

예전에는 어느 화면에 있든 renderModelsPage() 를 불렀다. 매입 관리에서
사업부를 바꾸면 왼쪽 메뉴와 빵부스러기는 '매입 관리' 인데 본문만 모델
관리로 바뀌었다. 쓰는 사람 눈에는 '화면이 안 따라온다 · 느리다' 로
보인다. 실제로 그렇게 보고가 들어왔다.

지금은 window._v2Page 에 지금 화면을 적어 두고 그 화면을 다시 그린다.
"""
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
SRC = (BACK / "admin_v2.html").read_text(encoding="utf-8")

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


ok("window._v2Page = pg;" in SRC, "메뉴를 눌러도 지금 화면을 적어 두지 않는다")
ok("window._v2Page = 'models';" in SRC, "모델 관리로 들어올 때 화면을 적어 두지 않는다")
ok("window._v2RenderPage" in SRC, "라우터를 밖에서 부를 수 없다")

# 사업부 change 핸들러 안을 본다
i = SRC.find("sidebarSel.addEventListener('change'")
ok(i > 0, "사업부 변경 처리가 없어졌다")
blk = SRC[i:i + 1200]
ok("window._v2Page" in blk, "사업부를 바꿀 때 지금 화면을 보지 않는다")
ok("window._v2RenderPage" in blk,
   "모델 관리가 아닌 화면을 다시 그리지 않는다 — 또 본문만 모델 관리로 바뀐다")

# 옛 방식(무조건 모델 관리)으로 돌아가지 않았는지
head = blk[:blk.find("var _pg")] if "var _pg" in blk else blk
ok("renderModelsPage()" not in head,
   "사업부를 바꾸자마자 무조건 모델 관리를 그리고 있다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 사업부를 바꿔도 보던 화면이 유지된다")
