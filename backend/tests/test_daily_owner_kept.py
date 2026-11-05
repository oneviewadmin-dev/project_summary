# 일 보고의 고객사(owner)를 저장까지 끌고 간다 (2026-11-03)
#   python3 backend/tests/test_daily_owner_kept.py
#
# Min: "엑셀 올렸는데 왜 반영을 못 하는거야"
#      (ESS 프로젝트 화면 — "이 프로젝트는 일 보고 자료에 없습니다")
#
# ESS 일 보고에는 품목 왼쪽에 **고객사** 열이 따로 있다
# (SDI · 플루언스 · EPC POWER). 프로젝트 화면은 그 고객사로 제 몫을
# 골라 낸다 (_daily_slice_by_project 가 owner 를 먼저 본다).
#
# 그런데 파서는 owner 를 읽어 놓고 **저장할 때 버렸다** — 담기는 건
# code · wait_ship · wait_part 뿐이었다. 그래서 품목 이름
# ('SBB 1.5 UL (한국 함안)') 으로만 고르게 됐고, 거기엔 'SDI' 가 없으니
# 한 줄도 못 골랐다. 블룸은 고객사 열이 없어서 이 구멍이 안 드러났다.
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 파서는 고객사를 읽는가 ───────────────────────────────────
import openpyxl
import bloom_daily_import as _bd

FX = ROOT / 'tests' / 'forms' / 'v2' / 'ESS_일보고_1028.xlsx'
if FX.exists():
    g = _bd.parse_daily(openpyxl.load_workbook(FX, data_only=True))
    items = g.get('items') or []
    ok(len(items) == 15, '품목이 %d개다 (15개)' % len(items))
    owners = {str(i.get('owner') or '') for i in items}
    ok('SDI' in owners, '고객사 SDI 를 못 읽는다: %r' % owners)
    ok('플루언스' in owners, '고객사 플루언스를 못 읽는다')
    ok('EPC POWER' in owners, '고객사 EPC POWER 를 못 읽는다')
    # 품목 이름에는 고객사가 안 들어 있다 — 그래서 owner 가 필요하다
    ok(all('SDI' not in str(i.get('item') or '') for i in items),
       '품목 이름에 고객사가 들어 있다 — 그러면 owner 없이도 골라진다')
else:
    print('(ESS 일 보고 없음 — 파일 검사는 건너뜀)')

# ── 2. 저장할 때 안 버리는가 ────────────────────────────────────
ok('for f in ("code", "owner", "wait_ship", "wait_part"):' in SRC,
   '저장할 때 고객사를 버린다 — 프로젝트가 제 몫을 못 고른다')

# ── 3. 고를 때 고객사를 먼저 보는가 ────────────────────────────
_i = SRC.find('def _daily_slice_by_project')
_fn = SRC[_i:SRC.find('\ndef ', _i + 10)]
ok('own = _norm_label(str((it or {}).get("owner") or ""))' in _fn,
   '고르는 쪽이 고객사를 안 본다')
ok('hay = own or nm' in _fn, '고객사가 있어도 품목 이름으로만 고른다')
# 한 줄도 못 고르면 빈 보드다 — 남의 자료를 보여 주느니 비운다
ok('out["items"] = picked' in _fn, '못 골랐을 때 남의 품목이 그대로 뜬다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 일 보고 고객사 유지')
