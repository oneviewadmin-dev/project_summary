# 자동차사업부도 다른 사업부와 같은 표 (2026-11-02)
#   python3 backend/tests/test_auto_table_unified.py
#
# Min: "옆에 수정 기능이 있으면 안돼 삭제 기능도 있으면 안되고
#      그리고 왜 자돝ㅇ차사업부는 이상해? 왜 양산, 판가, 재료비, 재료비율
#      다른 사업부랑 왜 다른거야 통일 되어야 하는데"
#
# 자동차만 열여섯 칸짜리 다른 표를 썼다 — 제품명 · 최종고객사 · 차종 ·
# 납품 위치 · 공법 · SOP · 중량 · 톤수 · 불량률 · 원가 합계 · 원가율 ·
# 계약 물량 · 매출 · 원가 비중, 그리고 줄마다 ✏️ · 🗑.
#
# 그 표는 '원가' 자료를 보려고 만든 것인데, 지금 올라오는 자동차 양식
# (고객사별 품목정보)에는 원가 칸이 없다. 그래서 화면이 전부 '-' 였다.
# 양식은 이미 다른 사업부와 같은 모양이다 — 고객사 · 품목 · 파트넘버 ·
# 구분 · 판가 · 재료비 · PO수량 · 실적수량 · 주차별 계획/실적.
# 표도 같게 두면 양식과 화면이 맞아떨어진다.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
APP = (ROOT.parent / 'mobile' / 'lib' / 'config' / 'app_config.dart').read_text(encoding='utf-8')
ok = 0

# ── 1. 스위치가 꺼져 있다 ─────────────────────────────────────────
assert 'var AUTO_TABLE_ON = false;' in HTML, '자동차 전용 표가 아직 켜져 있다'
ok += 1
# 함수 안에 두면 표를 그리는 다른 함수에서 안 보인다 (STATUS_NOTE_CARD_ON 때 겪음)
_line = [l for l in HTML.splitlines() if 'var AUTO_TABLE_ON' in l][0]
assert len(_line) - len(_line.lstrip()) <= 2, \
    '스위치가 함수 안에 들어가 있다 (들여쓰기 %d칸)' % (len(_line) - len(_line.lstrip()))
ok += 1

# ── 2. 세 자리가 다 스위치를 본다 ─────────────────────────────────
# 한 군데만 고치면 표는 바뀌는데 단추나 고르는 표가 안 따라온다.
assert 'if (AUTO_TABLE_ON && window._projIsAuto && window._autoRenderTable) {' in HTML, \
    '표 고르는 자리가 스위치를 안 본다'
assert 'var _autoUI = AUTO_TABLE_ON && window._projIsAuto;' in HTML, \
    '엑셀 단추가 스위치를 안 본다'
assert "var _isAuto = AUTO_TABLE_ON && currentDiv === 'automotive';" in HTML, \
    '프로젝트 고르는 표가 스위치를 안 본다'
ok += 1

# ── 3. 지우지 않고 끈다 ───────────────────────────────────────────
# 원가 자료(auto)는 그대로 남아 있고, true 로 되돌리면 옛 표가 선다.
assert 'window._autoRenderTable = function' in HTML, '옛 표를 통째로 지웠다'
assert '원가 비중' in HTML, '되살릴 자리가 없다'
ok += 1

# ── 4. 공용 표에는 수정 · 삭제 단추가 없다 ────────────────────────
assert 'var MDL_ROW_ACTIONS = false;' in HTML, '공용 표에 줄별 단추가 켜져 있다'
# 그 단추들은 전부 MDL_ROW_ACTIONS 안에 있어야 한다
_v2 = HTML[HTML.index('var MDL_ROW_ACTIONS = false;'):]
_v2 = _v2[:_v2.index('window.renderTable') if 'window.renderTable' in _v2 else len(_v2)]
_act = _v2[_v2.index('(MDL_ROW_ACTIONS'):] if '(MDL_ROW_ACTIONS' in _v2 else ''
assert 'mdl-row-del' in _act, '삭제 단추가 스위치 밖에 있다'
ok += 1
# ✏️ · 🗑 는 자동차 전용 표에만 있고, 그 표는 꺼져 있다
_auto = HTML[HTML.index('window._autoRenderTable = function'):]
_auto = _auto[:_auto.index('// ── 편집 모달')]
assert 'auto-edit' in _auto and 'mdl-row-del' in _auto, '이 검사의 전제가 깨졌다'
ok += 1

# ── 5. 앱은 이미 같은 틀이다 ──────────────────────────────────────
# 여기가 false 로 돌아가면 앱만 또 자동차 전용 화면으로 갈라진다.
assert 'const bool kSameFrameForAll = true;' in APP, \
    '앱이 사업부마다 다른 틀로 갈라져 있다'
ok += 1

print('ok %d' % ok)
