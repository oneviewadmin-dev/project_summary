# 양식 받기 — 두 가지 양식 · 기준 달 고르기 (2026-11-02)
#   python3 backend/tests/test_form_get_menu.py
#
# Min: "양식 받기에 양식 올리기 양식이랑 개발 일정 양식 두 개 다운 받을
#      수 있게 해야되는데 ... 지금 주차별 계획이 들어있는 양식들을 보면
#      10월 기준으로 되어 있는데 11월 뭐 선택하거나 12월 선택할 수
#      있도록도 할 수 있을까?"
#
# 전에는 단추 하나가 '오늘이 속한 달' 사업부 양식만 받았다. 11월 계획을
# 짜려고 받으면 10월 주차가 깔려 나와서 담당자가 열을 손으로 만들었고,
# 개발 일정 양식은 아예 받을 길이 없어서 내가 손으로 만들어 보냈다.
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 받을 양식이 둘인가 ────────────────────────────────────────
ok('id="mdl-form-get-menu"' in HTML, '양식 받기 메뉴가 없다')
ok('id="fg-div"' in HTML, '사업부 양식을 받을 자리가 없다')
ok('id="fg-dev"' in HTML, '개발 일정 양식을 받을 자리가 없다')
ok("'/form/download'" in HTML or "/form/download" in HTML,
   '사업부 양식 주소가 없다')
ok('/dev-schedule/download' in HTML, '개발 일정 양식 주소가 없다')
# 서버에 두 길이 다 있어야 한다
ok('/admin/divisions/{division_id}/form/download' in SRC, '서버에 사업부 양식 길이 없다')
ok('/admin/divisions/{division_id}/dev-schedule/download' in SRC,
   '서버에 개발 일정 양식 길이 없다')

# ── 2. 기준 달을 고르는가 ────────────────────────────────────────
ok('id="fg-month"' in HTML, '기준 달 고르는 칸이 없다')
ok('id="fg-span"' in HTML, '몇 달치를 고르는 칸이 없다')
# 달을 박아 두면 안 된다 — 전에는 오늘 날짜로 month 를 만들어 붙였다
_i = HTML.find('window._divFormGetBind')
_body = HTML[_i:HTML.find('window._divFormBind')]
ok('msel.value' in _body, '고른 달을 안 쓴다 — 또 오늘 달로 받는다')
ok("getElementById('fg-span')" in _body, '고른 달 수를 안 쓴다')
# 지난 달도 받을 수 있어야 한다 (빠진 실적을 채워 올릴 때가 있다)
_m = re.search(r'for \(var k = (-?\d+); k <= (-?\d+); k\+\+\)', _body)
ok(_m is not None, '달 목록을 안 만든다')
if _m:
    ok(int(_m.group(1)) < 0, '지난 달을 못 고른다')
    ok(int(_m.group(2)) >= 2, '두 달 뒤를 못 고른다 — 11월 · 12월을 고르려던 것이다')

# ── 2-b. 일 보고 사업부는 달 · 주차를 안 고른다 ─────────────────
# Min: "양식 받기에서 주차달?인가랑 주차 블록이 필요없지
#      일일은 어차피 다른 양식 쓰니까"
#
# ESS · 블룸은 주차별 계획·실적을 일 보고 파일로 받는다. 고르는 칸을
# 띄워 두면 '여기서 고른 달이 일 보고에도 걸리나' 를 한 번 생각하게 된다.
ok('id="fg-when"' in HTML, '달 · 주차 줄을 묶어 두지 않았다 — 따로 숨기면 어긋난다')
ok('#fg-when[hidden] { display:none !important; }' in HTML,
   'hidden 이 클래스에 져서 줄이 그대로 보인다')
ok('_isDaily' in _body, '일 보고 사업부인지 안 본다')
ok('window._DAILY_DIVISIONS' in _body, '일 보고 사업부 목록을 안 읽는다')
# 열 때마다 다시 봐야 한다. 사업부는 메뉴를 만든 뒤에도 바뀐다.
_click = _body[_body.find("b.addEventListener('click'"):]
_click = _click[:_click.find('menu.addEventListener')]
ok('when.hidden = _isDaily(div())' in _click,
   '열 때 다시 안 본다 — 반도체에서 열었던 모양이 블룸에 남는다')
# 숨겼어도 양식은 받아져야 한다 (주차 칸 자체는 양식에 그대로 있다)
ok("_isDaily(d)" in _body and "now.getMonth() + 1" in _body,
   '달을 안 고른 사업부에 기본 달을 안 넣는다 — 주소에 month 가 빈다')

# ── 3. 새 창을 열지 않는가 ───────────────────────────────────────
# 관리자 쿠키가 같은 창에서만 붙는다. window.open 으로 열면 403 이 온다.
ok('window.open' not in _body, '새 창으로 연다 — 관리자 쿠키가 안 붙는다')
ok('window.location.href' in _body, '내려받기를 시작하지 않는다')

# ── 4. 메뉴가 닫히는가 ───────────────────────────────────────────
# 한 번 열고 안 닫히면 아래 표를 가린다.
ok("e.key === 'Escape'" in _body, 'Esc 로 안 닫힌다')
ok('menu.hidden = true' in _body, '바깥을 눌러도 안 닫힌다')
ok("menu.addEventListener('click'" in _body,
   '메뉴 안을 눌러도 닫힌다 — 달을 고를 수가 없다')
# 두 번 그려도 핸들러가 겹쳐 붙으면 안 된다
ok('b.dataset.wired' in _body, '다시 그릴 때마다 핸들러가 겹쳐 붙는다')
ok('!msel.options.length' in _body, '다시 그릴 때마다 달 목록이 또 쌓인다')

# ── 5. 사업부를 안 골랐을 때 ─────────────────────────────────────
ok(_body.count('사업부를 먼저 고르세요') >= 2,
   '사업부 없이 눌러도 그냥 내려받기를 시작한다')

# ── 6. 받은 양식이 그대로 다시 올라가는가 ───────────────────────
# 받기와 올리기가 짝이 안 맞으면 제일 나쁘다 — 받아서 날짜만 적어
# 올렸는데 "읽을 품목이 없습니다" 가 뜬다. 한 바퀴 돌려 본다.
import sys
sys.path.insert(0, str(ROOT))
try:
    import openpyxl as _ox
    import dev_schedule_export as _E
    import dev_schedule_import as _I
except ImportError as _e:
    print('(모듈 없음 — 왕복은 건너뜀:', _e, ')')
else:
    _rows = [
        {"owner": "KEFICO KR", "name": "VCU Base", "part_number": "9109020119",
         "dev_owner": "김영아 차장",
         "process": [{"name": "01 T-car", "status": "완료",
                      "expected_note": "완료", "actual_note": "완료"},
                     {"name": "03 P1 [Pilot]", "expected": "2025-11-30",
                      "actual": "2025-11-30"},
                     {"name": "06 SOP", "expected": "2026-10-15"}]},
        # 아직 단계가 없는 새 개발 품목 — 양식에는 서야 한다
        {"owner": "신규", "name": "단계 없음", "part_number": "ZZZ-1",
         "dev_owner": "", "process": []},
    ]
    _steps = ['01 T-car', '02 Proto', '03 P1 [Pilot]', '04 P2 [Pilot]',
              '05 M [Pilot]', '06 SOP']
    _blob = _E.build('자동차사업부', _rows, _steps)
    import tempfile
    _tmp = pathlib.Path(tempfile.mkdtemp(prefix='fg_')) / 'rt.xlsx'
    _tmp.write_bytes(_blob)
    _g = _I.parse_workbook(_ox.load_workbook(_tmp, data_only=True))
    ok(len(_g['items']) == 2, '받은 양식에서 품목이 %d개 읽힌다' % len(_g['items']))
    ok(not _g['warnings'], '받은 양식을 올리면 경고가 난다: %r' % _g['warnings'])
    _by = {i['part_number']: {s['name']: s for s in i['steps']}
           for i in _g['items']}
    ok(_by.get('9109020119', {}).get('03 P1 [Pilot]', {}).get('expected')
       == '2025-11-30', '적혀 있던 계획일이 왕복에서 사라진다')
    ok(_by.get('9109020119', {}).get('01 T-car', {}).get('actual_note') == '완료',
       "'완료' 글자가 왕복에서 사라진다")
    ok(any(i['owner'] == '김영아 차장' for i in _g['items']),
       '담당이 왕복에서 사라진다')
    # 단계가 아직 없는 품목은 '그 사업부에서 제일 흔한 단계 묶음' 을
    # 받는다. 빈 줄로 내보내면 올릴 때 '단계 이름이 한 칸도 없습니다' 로
    # 튕겨서, 새 개발 품목은 영영 일정을 못 적는다.
    ok('ZZZ-1' in _by and len(_by['ZZZ-1']) == 3,
       '단계가 없던 품목이 단계 칸을 못 받았다: %r' % sorted(_by.get('ZZZ-1') or {}))
    ok(sorted(_by.get('ZZZ-1') or {}) == sorted(_by.get('9109020119') or {}),
       '새 품목이 다른 단계 묶음을 받았다')
    # 그 사업부에 단계가 하나도 없으면 넘겨준 기본값을 쓴다
    _only = [{"owner": "새", "name": "a", "part_number": "P1",
              "dev_owner": "", "process": []}]
    ok(_E.common_steps(_only, _steps) == _steps,
       '단계가 하나도 없을 때 기본 단계를 안 쓴다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 양식 받기 메뉴')
