# 반도체사업부 양식 (2026-10-26 확정판) 을 지킨다.
#
# Min: "반도체사업부는 이 파일 양식으로만 진행이 될거야"
# 올려 주신 네 장 — CUP · HRVA · 챔버 · 엔클로저 — 이 기준이다.
#
# 이 양식에서 처음 드러난 문제가 하나 있었다. 주차 칸이 **W40 부터**
# 다섯이다. 달력 규칙상 W40 은 9월 것이고 W41~W44 는 10월 것인데,
# 파서는 '첫 주차가 속한 달' 하나로 양식 전체의 달을 정했다. 그래서
# 10월 양식이 '2026-09' 로 읽혔고, W41~W44 에 적힌 숫자가 9월 자리에
# 쌓였다. 9월 보드는 W36~W40 만, 10월 보드는 W41~W44 만 보기 때문에
# 양쪽 어디에도 안 나오고 조용히 사라졌다 — HRVA 한 장에서 65칸 중
# 57칸이 그랬다.
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import openpyxl                      # noqa: E402
import division_form_import as dfi    # noqa: E402
import week_calendar as wcal          # noqa: E402

FORMS = os.path.join(HERE, "forms", "v2")
FILES = {
    "CUP": "반도체_CUP_실제_1023.xlsx",
    "HRVA": "반도체_HRVA_실제_1023.xlsx",
    "챔버": "반도체_챔버_실제_1023.xlsx",
    "엔클로저": "반도체_엔클로저_실제_1023.xlsx",
}

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


def load(name):
    p = os.path.join(FORMS, FILES[name])
    wb = openpyxl.load_workbook(p, data_only=True)
    return dfi.parse_workbook(wb, division_id="semiconductor")


got = {}
for nm in FILES:
    p = os.path.join(FORMS, FILES[nm])
    if not os.path.exists(p):
        bad.append("양식 파일이 없다: %s" % FILES[nm])
        continue
    got[nm] = load(nm)

if not bad:
    # ── 1. 네 장 모두 같은 양식으로 읽힌다
    for nm, g in got.items():
        ok(g["sheet"] == "프로젝트별 품목정보",
           "%s: 품목정보 시트를 못 찾았다 (%s)" % (nm, g["sheet"]))
        ok(g["weeks"] == ["W40", "W41", "W42", "W43", "W44"],
           "%s: 주차 칸이 W40~W44 가 아니다 (%s)" % (nm, g["weeks"]))
        # 머리글에 '10월 주차별 계획 · 실적' 이라고 적혀 있다.
        ok(g["month"] == "2026-10",
           "%s: 10월 양식인데 %r 로 읽혔다" % (nm, g["month"]))
        ok(not g["warnings"], "%s: 경고가 떴다 — %s" % (nm, g["warnings"]))

    # ── 2. 품목이 통째로 사라지지 않는다 (올려 주신 장의 실제 줄 수)
    for nm, n in [("CUP", 30), ("HRVA", 231), ("챔버", 27), ("엔클로저", 12)]:
        if nm in got:
            ok(len(got[nm]["items"]) == n,
               "%s: 품목이 %d건이어야 하는데 %d건" % (nm, n, len(got[nm]["items"])))

    # ── 3. 프로젝트 이름은 파일마다 하나다 (E열 '프로젝트')
    for nm, owner in [("CUP", "CUP"), ("HRVA", "HRVA"),
                      ("챔버", "Chamber"), ("엔클로저", "Enclosure")]:
        if nm in got:
            owners = sorted({it["owner"] for it in got[nm]["items"]})
            ok(owners == [owner],
               "%s: 프로젝트가 %s 하나여야 하는데 %s" % (nm, owner, owners))

    # ── 4. 반도체형에만 있는 칸 — 연간수량 · 분류(HVM/RPM)
    if "HRVA" in got:
        dts = {it["dev_type"] for it in got["HRVA"]["items"]}
        ok(dts & {"HVM", "RPM"}, "HRVA: 분류(HVM/RPM) 를 안 읽었다")
    if "CUP" in got:
        ok(any(it["year_qty"] for it in got["CUP"]["items"]),
           "CUP: 연간수량을 안 읽었다")
        # 이슈사항 시트도 같은 파일에 들어온다
        ok(len(got["CUP"]["issues"]) == 1,
           "CUP: 이슈 1건을 못 읽었다 (%d건)" % len(got["CUP"]["issues"]))

    # ── 5. 모델명 칸에 줄바꿈이 남지 않는다
    #      하바플레이트는 이 칸에 소재를 적는데 231줄 중 227줄이
    #      'PC\n(Dynex)' 처럼 두 줄이었다. 그대로 두면 표 행 높이가
    #      들쭉날쭉해지고 같은 소재가 두 이름으로 갈라진다.
    if "HRVA" in got:
        nl = [it for it in got["HRVA"]["items"] if "\n" in (it["name"] or "")]
        ok(not nl, "모델명에 줄바꿈이 남아 있다 (%d줄)" % len(nl))
        ok(any(it["name"] == "PC (Dynex)" for it in got["HRVA"]["items"]),
           "'PC\\n(Dynex)' 가 'PC (Dynex)' 한 줄로 이어지지 않았다")

    # ── 6. 주차는 '그 주차가 속한 달' 칸으로 들어간다
    #      W40 은 9월, W41~W44 는 10월. 한 달로 몰아넣으면 숫자가 샌다.
    if "HRVA" in got:
        buck = {}
        for it in got["HRVA"]["items"]:
            for w in (it["weeks"] or {}):
                mon = wcal.month_of_week(w) or got["HRVA"]["month"]
                buck.setdefault(mon, set()).add(w)
        ok(buck.get("2026-09") == {"W40"},
           "W40 이 9월 칸으로 안 간다 (%s)" % buck.get("2026-09"))
        ok(buck.get("2026-10") == {"W41", "W42", "W43", "W44"},
           "W41~W44 가 10월 칸으로 안 간다 (%s)" % buck.get("2026-10"))
        # 적힌 칸이 하나도 안 사라졌는가
        wrote = sum(len(it["weeks"] or {}) for it in got["HRVA"]["items"])
        ok(wrote == 71, "HRVA 주차 칸이 71개여야 하는데 %d개" % wrote)

# ── 7. 반영하는 쪽(main.py)도 주차마다 달을 따로 묻는다
#      파서가 맞게 읽어도 여기서 한 달로 몰아넣으면 똑같이 샌다.
src = io.open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
ok("_mon = _wcal.month_of_week(_wk) or month" in src,
   "main.py 가 주차마다 달을 묻지 않는다 — 한 달로 몰아넣으면 숫자가 샌다")
ok('wp.setdefault(month, {}).update(it["weeks"])' not in src,
   "main.py 에 양식 달 하나로 몰아넣는 옛 코드가 남아 있다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_semi_form_v2")
