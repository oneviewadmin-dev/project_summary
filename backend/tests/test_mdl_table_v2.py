# -*- coding: utf-8 -*-
"""프로젝트 안 모델 목록 표 — 시안(admin_redesign)대로 새로 짠 V2.

여기서 지키는 것은 셋이다.

  1. 열 구성은 서버 division_columns.py 가 정한다 (화면이 목록을 품지 않는다).
  2. 머리줄 두 단과 본문의 열 수가 어긋나지 않는다 — 어긋나면 표가 밀려
     보이기만 하고 아무 오류도 안 난다.
  3. 옛 표는 지우지 않고 MDL_TABLE_V2 하나로 되돌릴 수 있게 둔다.
"""
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

HTML = io.open(HERE.parent / "admin_v2.html", encoding="utf-8").read()
MAIN = io.open(HERE.parent / "main.py", encoding="utf-8").read()

fail = []


def ck(cond, why):
    if not cond:
        fail.append(why)


# ── 1. 열 구성을 내려주는 자리가 있다
ck('@app.get("/admin/division-columns")' in MAIN,
   "/admin/division-columns 엔드포인트가 없습니다")
ck("import division_columns as _dcol" in MAIN,
   "main.py 가 division_columns 를 들이지 않았습니다")
ck("_dcol.columns_for" in MAIN, "columns_for 를 쓰지 않습니다")

# ── 2. 화면은 그 자리에서 받아 쓴다
ck("/admin/division-columns" in HTML, "화면이 열 구성을 받아 오지 않습니다")
ck("window._mdlColSpecLoad" in HTML, "열 구성 로더가 없습니다")
ck("function _mdlBuildV2()" in HTML, "V2 builder 가 없습니다")

# 화면이 사업부 목록을 스스로 품으면 안 된다 (기준이 둘이 된다)
_i = HTML.find("function _mdlBuildV2()")
body = HTML[_i:HTML.find("let html = ''", _i)]
assert len(body) > 4000, "V2 builder 를 못 떼어 냈습니다"

for word in ("반도체형", "고객사형", "프로젝트형"):
    # sp.shape 와 견주는 한 자리만 허용한다
    ck(body.count("'" + word + "'") + body.count('"' + word + '"') <= 1,
       "V2 builder 안에 양식 모양('%s')을 두 번 넘게 적었습니다" % word)

# ── 3. 되돌릴 수 있다 — 옛 builder 가 else 안에 산다
ck("var MDL_TABLE_V2 = true;" in HTML, "MDL_TABLE_V2 스위치가 없습니다")
ck("if (MDL_TABLE_V2) { html = _mdlBuildV2(); } else {" in HTML,
   "옛 builder 를 else 로 감싸 두지 않았습니다")
ck('class="mdl-guide"' in HTML, "옛 표(mdl-guide)가 지워졌습니다 — 되돌릴 자리가 없습니다")

# ── 4. 시안의 모양새
for need in ('class="mdl-tbl2"', 'class="pn1"', 'class="pn2"',
             'class="loz ', 'class="n po"', 'class="mdl-tfade"'):
    ck(need in HTML, "시안 조각이 없습니다: %s" % need)
# 숫자 칸 CSS (오른쪽 정렬 · 자리수 맞춤)
ck("'.mdl-tbl2 th.n, .mdl-tbl2 td.n { text-align:right;" in HTML,
   "숫자 칸 오른쪽 정렬 CSS 가 없습니다")
# .mdl-table 규칙과 섞이면 인라인 !important 가 이긴다 — 이름을 갈라 둔다
ck(".mdl-tbl2 " in HTML and "'.mdl-table thead th{" not in
   HTML[HTML.find(".mdl-tbl2 "):], "표 CSS 이름이 옛 표와 섞였습니다")

# ── 5. 모델 목록은 비고로 끝난다 (주차 계획은 '주차별 계획' 탭 몫)
ck("'<th class=\"n\">잔여수량</th>' +" in body, "잔여수량 칸이 없습니다")
ck(body.rstrip().find("'<th>비고</th>'") > body.find("잔여수량"),
   "비고가 잔여수량 뒤에 오지 않습니다")
ck("weekly_plan" not in body, "모델 목록에 주차 계획을 또 세웠습니다")
ck("wkc" not in body, "모델 목록에 주차 칸이 남아 있습니다")
ck("m.due_text" not in body, "납기 칸이 남아 있습니다")
ck("m.issues" not in body, "이슈사항 칸이 남아 있습니다")

# ── 6. 줄마다 붙던 관리 단추는 숨긴다 — 지우지는 않는다
ck("var MDL_ROW_ACTIONS = false;" in HTML, "관리 단추 스위치가 없습니다")
for need in ("mdl-row-process", "mdl-row-phase", "mdl-row-del"):
    ck(need in body, "%s 를 지웠습니다 — 되살릴 자리가 없습니다" % need)
# 고르기(체크박스)도 숨긴다 — 지우지는 않는다
ck("var MDL_ROW_CHECK = false;" in HTML, "체크박스 스위치가 없습니다")
for need in ("mdl-row-chk", 'id="mdl-check-all"'):
    ck(need in body, "%s 를 지웠습니다 — 되살릴 자리가 없습니다" % need)

# ── 7. 빈 칸과 0 을 섞지 않는다
ck("v === undefined || v === null || v === ''" in body,
   "빈 칸과 0 을 가르는 자리가 없습니다")

if fail:
    print("실패 %d건" % len(fail))
    for f in fail:
        print(" -", f)
    raise SystemExit(1)
print("ok — 모델 목록 표 V2")
