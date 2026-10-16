# -*- coding: utf-8 -*-
"""엑셀로 모델을 등록하는 길이 화면에 있어야 한다.

/admin/projects/{키}/models/import 과 그걸 부르는 bindModelExcel() 은
멀쩡히 살아 있는데, 그 함수가 찾는 버튼 두 개가 화면에서 빠져 있었다.

    var upBtn = document.getElementById('mdl-excel-btn');
    if (!upBtn || !input) return;          ← 여기서 조용히 끝났다

그래서 엑셀로 모델을 새로 등록할 방법이 아예 없었다. 주차별 계획 탭에
올리면 '68줄 인식' 같은 숫자만 떠서 된 줄 알게 된다 — 주차 양식은 판가·
재료비 칸이 없어서 등록을 못 한다. 실제로 81줄을 올리고 0줄이 들어갔다.

버튼이 또 빠지면 같은 일이 반복되니 여기서 잡는다.
"""
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
SRC = (BACK / "admin_v2.html").read_text(encoding="utf-8")

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# 함수가 찾는 id 와 화면에 있는 id 가 같아야 한다
for bid, what in [("mdl-excel-btn", "모델 등록 올리기"),
                  ("mdl-excel-tpl-btn", "모델 등록 양식 받기"),
                  ("mdl-excel-input", "파일 고르는 칸")]:
    ok(('id="%s"' % bid) in SRC, "%s(%s) 가 화면에 없다" % (what, bid))
    ok(("getElementById('%s')" % bid) in SRC, "%s 를 찾는 코드가 없다" % bid)

# 메뉴 안에 있어야 한다 (툴바 어딘가가 아니라)
i = SRC.find('id="mdl-import-menu"')
ok(i > 0, "엑셀 메뉴가 없어졌다")
menu = SRC[i:i + 2200]
ok('id="mdl-excel-btn"' in menu, "올리기 버튼이 엑셀 메뉴 안에 없다")
ok('id="mdl-excel-tpl-btn"' in menu, "양식 받기 버튼이 엑셀 메뉴 안에 없다")

# 붙이는 함수가 실제로 불려야 한다
ok("bindModelExcel()" in SRC, "bindModelExcel() 을 아무도 부르지 않는다")

# 올리는 주소
ok("/models/import" in SRC, "모델 등록 주소를 부르지 않는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 엑셀로 모델을 등록하는 길이 화면에 있다")
