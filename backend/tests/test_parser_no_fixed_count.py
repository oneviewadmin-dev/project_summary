# 파서는 '몇 개인지' 를 외워 두지 않는다 (2026-10-27).
#
# 김민찬 박사: "프로세스 개수의 변화가 일어 날수도 있다는…전제"
#              "지금보다 30%만큼 더 등록 할수 있는 여유를 가져 갈 수 있을지요"
#
# 여유를 숫자로 잡아 두는 것은 답이 아니다. 오늘 13개면 20칸을 그려 두고,
# 내년에 21개가 되면 또 고쳐야 한다. 개수를 아예 안 정하면 그 일이 다시
# 오지 않는다 — 담당자가 열을 추가하는 순간 읽힌다.
#
# 자세한 까닭은 docs/엑셀_읽는_규칙.md 에 적어 두었다.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import openpyxl                      # noqa: E402
import division_form_import as dfi   # noqa: E402

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


def make(nweek, nitem=1):
    """주차 칸이 nweek 개인 반도체형 양식을 만든다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "프로젝트별 품목정보"
    ws["D2"] = "프로젝트별 품목정보"
    h = 4
    for c, v in [(4, "No."), (5, "프로젝트"), (6, "파트넘버"), (7, "모델명 (있을 시)"),
                 (8, "구분"), (9, "분류 (HVM/RPM)"), (10, "판가"), (12, "재료비"),
                 (14, "연간수량"), (15, "PO수량"), (16, "실적수량"), (17, "비고")]:
        ws.cell(h, c, v)
    ws.cell(h, 18, "10월 주차별 계획 · 실적")
    ws.cell(h + 1, 10, "통화"); ws.cell(h + 1, 11, "판가")
    ws.cell(h + 1, 12, "통화"); ws.cell(h + 1, 13, "재료비")
    c = 18
    for i in range(nweek):
        ws.cell(h + 1, c, "W%02d" % (40 + i))
        ws.cell(h + 2, c, "계획")
        ws.cell(h + 2, c + 1, "실적")
        c += 2
    for j in range(nitem):
        r = h + 3 + j
        ws.cell(r, 4, j + 1); ws.cell(r, 5, "CUP")
        ws.cell(r, 6, "PN-%d" % (j + 1)); ws.cell(r, 8, "양산")
        ws.cell(r, 10, "USD"); ws.cell(r, 11, 100)
        ws.cell(r, 15, 10); ws.cell(r, 16, 3)
        c = 18
        for i in range(nweek):
            ws.cell(r, c, i + 1)
            ws.cell(r, c + 1, i)
            c += 2
    return wb


# ── 1. 주차 칸을 늘려 가며 — 그만큼 읽히는가
#      4·5 는 지금 쓰는 수, 8 은 한 달에 다섯 주가 넘는 경우,
#      20·30 은 "설마 이만큼" 을 넘어서는 경우.
for n in (1, 4, 5, 8, 20, 30):
    got = dfi.parse_workbook(make(n), division_id="semiconductor")
    ok(len(got["weeks"]) == n,
       "주차 칸 %d개를 넣었는데 %d개만 읽었다 — 개수가 어딘가 박혀 있다"
       % (n, len(got["weeks"])))
    if got["items"]:
        wk = got["items"][0]["weeks"] or {}
        # 0 으로 적힌 칸은 안 담길 수 있으니 '하나도 안 빠졌나' 대신
        # '마지막 주차가 담겼나' 를 본다.
        last = "W%02d" % (40 + n - 1)
        ok(last in wk, "마지막 주차(%s)가 품목에 안 담겼다" % last)

# ── 2. 품목 줄 수도 외우지 않는다
for n in (1, 3, 231, 400):
    got = dfi.parse_workbook(make(4, nitem=n), division_id="semiconductor")
    ok(len(got["items"]) == n,
       "품목 %d줄을 넣었는데 %d줄만 읽었다" % (n, len(got["items"])))

# ── 3. week_count 를 '한계' 로 쓰면 안 된다
#      화면에 "보통 주차가 넷입니다" 를 알려 주려고 둔 값이지, 읽는 쪽이
#      지킬 약속이 아니다. 이 값보다 많은 주차가 와도 다 읽혀야 한다.
import division_columns as dcol      # noqa: E402

hint = dcol.columns_for("semiconductor")["week_count"]
got = dfi.parse_workbook(make(hint + 7), division_id="semiconductor")
ok(len(got["weeks"]) == hint + 7,
   "week_count(%d)를 넘는 주차가 잘렸다 — 힌트를 한계로 쓰고 있다" % hint)

# ── 4. 파서 안에 '읽을 열 개수' 를 박아 둔 자리가 없는가
#      ws.max_column 까지 훑어야 한다. 고정 숫자로 끊으면 그 뒤가
#      조용히 사라지고, 사라진 건 아무도 못 알아챈다.
import io                            # noqa: E402

src = io.open(os.path.join(HERE, "..", "division_form_import.py"),
              encoding="utf-8").read()
ok("_lastc(ws)" in src, "읽을 마지막 열을 ws 에서 구하지 않는다")
ok("ws.max_column" in src, "ws.max_column 을 안 본다")
ok("range(1, _lastc(ws) + 1)" in src,
   "머리글을 훑는 범위가 ws 의 실제 열 수에서 오지 않는다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_parser_no_fixed_count — 주차 1·4·5·8·20·30 / 품목 1·3·231·400")
