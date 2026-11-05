# 모델 목록 머리의 '＋ 모델 추가' · '📁 엑셀 ▾' 를 안 그린다 (2026-11-02)
#   python3 backend/tests/test_mdl_toolbar_tools.py
#
# Min: "빨간 박스에 있는것도 빼버려"
#
# 모델이 들어오는 문을 '양식 올리기' 하나로 모은다. 손으로 더하는 길과
# 따로 '모델 등록 양식' 을 올리는 길이 같이 열려 있으면, 화면과 엑셀이
# 서로 다른 목록을 들고 있게 된다 — 지난달 내내 났던 문제가 그거다.
#
# 지우지 않고 끈다. 그래서 검사가 둘이다 —
#   (1) 스위치가 꺼져 있나
#   (2) 스위치가 함수 밖(블록 맨 위)에 있나. 함수 안에 넣으면 머리글을
#       그리는 다른 함수에서 안 보여서, 조용히 true 처럼 동작한다.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
LINES = HTML.split('\n')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 스위치 ────────────────────────────────────────────────────
decl = [l for l in LINES if 'var MDL_TOOLBAR_TOOLS_ON' in l]
ok(len(decl) == 1, '스위치가 %d개다 — 하나여야 한다' % len(decl))
if decl:
    ok('= false' in decl[0], '스위치가 켜져 있다')
    indent = len(decl[0]) - len(decl[0].lstrip())
    ok(indent <= 2,
       '스위치가 함수 안에 있다 (들여쓰기 %d칸) — 머리글 그리는 데서 안 보인다'
       % indent)

# ── 2. 두 단추가 스위치에 걸려 있나 ──────────────────────────────
ok("(MDL_TOOLBAR_TOOLS_ON\n              ? '<button type=\"button\" class=\"ov-btn\" "
   "id=\"mdl-add-btn\">" in HTML,
   "'＋ 모델 추가' 가 스위치에 안 걸려 있다")
ok("'<div class=\"ov-menu-wrap\"' + (MDL_TOOLBAR_TOOLS_ON ? '' : ' hidden') + '>'"
   in HTML, "'📁 엑셀 ▾' 칸이 스위치에 안 걸려 있다")

# Min: "빨간 박스에 있는 저장 버튼 삭제 시켜줘"
# 표가 보기 전용이라 눌러도 할 일이 없는 단추였다. 그런 단추가
# 살아 있으면 "저장했는데 안 됐다" 가 된다.
ok('id=\"mdl-save-btn\">저장</button>' in HTML
   and HTML.count('id=\"mdl-save-btn\">저장') == 1, '저장 단추가 사라졌다 — 스위치로 꺼야 한다')
_i = HTML.find('id=\"mdl-save-btn\">저장')
ok('MDL_TOOLBAR_TOOLS_ON' in HTML[max(0, _i - 200):_i],
   "'저장' 단추가 스위치에 안 걸려 있다")

# hidden 은 display:block 이라 클래스가 display 를 정해 두면 진다
ok('.ov-menu-wrap[hidden] { display:none !important; }' in HTML,
   'hidden 이 클래스에 져서 칸이 그대로 보인다')

# ── 3. 다른 데서 다시 켜지 않나 ─────────────────────────────────
# 자동차 전용 분기가 '자동차가 아니면 보여라' 로 되어 있었다 — 머리글을
# 안 그려도 이 줄 하나가 되살려 놓는다.
ok('_mdlExcelWrap.parentElement.hidden = !MDL_TOOLBAR_TOOLS_ON || !!_autoUI;'
   in HTML, '자동차 분기가 엑셀 칸을 도로 켠다')

# ── 4. 없는 단추를 가리키지 않나 ────────────────────────────────
ok('＋ 모델 추가로 만들거나' not in HTML,
   '빈 목록 안내가 없는 단추를 가리킨다')

# ── 5. 핸들러는 단추가 없어도 안 터져야 한다 ────────────────────
# 처음 껐을 때 여기서 터졌다 —
#   Uncaught TypeError: Cannot read properties of null (reading 'addEventListener')
# 터진 자리가 renderModelsPage 중간이라, 그 아래가 통째로 안 돌아서
# 모델 화면이 빈 채로 멈췄다. 단추 하나가 화면 전체를 세운 것이다.
for name, guard in (
    ('mdl-add-btn', "if (addBtn) addBtn.addEventListener('click'"),
    ('mdl-save-btn', "if (saveBtn) saveBtn.addEventListener('click'"),
    ('mdl-excel-btn', 'if (!upBtn || !input) return;'),
    ('mdl-lead-btn', 'if (leadBtn && !leadBtn.dataset.wired)'),
    ('mdl-import-btn', 'if (importBtn && importMenu)'),
):
    ok(guard in HTML, '%s 핸들러에 없을 때 대비가 없다' % name)

# ── 6. 사라진 id 를 가드 없이 만지는 데가 또 있나 ───────────────
# 하나하나 적어 두면 다음에 단추를 더 뺄 때 또 터진다. 기계가 훑는다.
import re
_lines = LINES
_gone = ('mdl-add-btn', 'mdl-save-btn', 'mdl-import-btn', 'mdl-import-menu', 'mdl-excel-tpl-btn',
         'mdl-excel-btn', 'mdl-lead-btn', 'mdl-bloom-btn')
_touch = r'\.(addEventListener|onclick|click|hidden|disabled|title|dataset|'
_touch += r'setAttribute|querySelectorAll|textContent|style)'
for _i, _l in enumerate(_lines):
    if 'getElementById' not in _l and 'querySelector' not in _l:
        continue
    if not any(("'" + g + "'") in _l for g in _gone):
        continue
    _m = re.search(r'(?:var|const|let)\s+(\w+)\s*=', _l)
    if not _m:
        continue
    _v = _m.group(1)
    for _j in range(_i + 1, min(_i + 120, len(_lines))):
        if not re.search(r'\b' + _v + _touch, _lines[_j]):
            continue
        _seg = '\n'.join(_lines[_i:_j + 1])
        if not (('if (!' + _v) in _seg or ('if (' + _v) in _seg
                or ('&& ' + _v) in _seg or (_v + ' &&') in _seg):
            ok(False, '%d행 — 없을 수도 있는 %s 를 가드 없이 만진다' % (_j + 1, _v))
        break

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 모델 목록 머리 단추 끄기')
