# 서버에서도 막는다 — 화면만 잠그면 반쪽이다
#   python3 backend/tests/test_admin_write_off.py
#
# 2026-10-22 — 모델 정보와 프로젝트 현황을 엑셀 기준으로만 바꾸기로 했다.
# 화면(admin_v2.html)만 잠그면 브라우저 콘솔 한 줄, 열어 둔 옛 탭,
# 북마크해 둔 주소로 같은 요청이 그대로 나간다. 그렇게 들어온 저장은
# 엑셀이 들고 온 값을 조용히 덮어쓴다 — 아무도 못 본다.
#
# 이 시험이 막는 것
#   들어오는 자리의 가드가 빠지는 것.
#   가드가 함수 중간으로 내려가 이미 고친 뒤에 막는 것.
#   엑셀로 올리는 길(plan-file · import)까지 같이 막아 버리는 것.
#   함수를 통째로 지워 되살릴 자리를 잃는 것.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
HTML = (ROOT / "admin_v2.html").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
ok = 0


def fn(name):
    # async def 도 같이 본다 — 엑셀 업로드 쪽이 async 다
    for n in ast.walk(TREE):
        if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name):
            return n
    return None


# ── 1. 스위치와 가드가 있다 ──────────────────────────────────
assert "ADMIN_WRITE_OFF = True" in SRC, "ADMIN_WRITE_OFF 스위치가 없다"
assert fn("_write_off"), "_write_off 가드가 없다"
assert "403" in ast.get_source_segment(SRC, fn("_write_off")), \
    "403 으로 돌려보내지 않는다"
ok += 1
print("1. 스위치 · 403 가드 ✓")

# ── 2. 두 자리에서 **맨 먼저** 부른다 ────────────────────────
#   중간에서 막으면 이미 고친 뒤라 반쯤 바뀐 자료가 남는다.
for name, what in (("admin_put_project_models", "models"),
                   ("put_project_status_note", "status-note")):
    f = fn(name)
    assert f, "%s 가 없다 — 지우지 말고 막아 둔다" % name
    body = [b for b in f.body if not (isinstance(b, ast.Expr)
                                      and isinstance(b.value, ast.Constant))]
    first = body[0]
    assert (isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and getattr(first.value.func, "id", "") == "_write_off"
            and first.value.args[0].value == what), \
        "%s 의 첫 줄이 _write_off('%s') 가 아니다" % (name, what)
ok += 1
print("2. 모델 저장 · 현황 저장 둘 다 첫 줄에서 막는다 ✓")

# ── 3. 엑셀로 올리는 길은 안 막혔다 ──────────────────────────
#   여기까지 막으면 고칠 길이 아예 없어진다.
for name in ("admin_models_import",):
    f = fn(name)
    assert f, "%s 가 없다" % name
    assert "_write_off" not in ast.get_source_segment(SRC, f), \
        "%s 까지 막혔다 — 엑셀로 올릴 길이 없어진다" % name
assert "_write_off" not in SRC[SRC.find("plan-file/apply"):][:400], \
    "주차별 계획 올리는 길이 막혔다"
ok += 1
print("3. 엑셀로 올리는 길은 열려 있다 ✓")

# ── 4. 화면 쪽 현황 카드도 잠겼다 ────────────────────────────
assert "function lockStatusNote()" in HTML, "현황 카드 잠그는 자리가 없다"
assert "lockStatusNote();" in HTML, "현황 카드를 안 잠근다"
assert "mdl-note-save" in HTML, "현황 저장 버튼이 사라졌다"
guard = HTML[HTML.find("noteSaveBtn.addEventListener"):][:400]
assert "MODELS_READONLY" in guard, "현황 저장 요청이 안 막혔다"
ok += 1
print("4. 화면의 현황 카드(글 · 진행/보류 · 저장)도 잠겼다 ✓")

# ── 5. 되돌릴 자리가 한 줄로 남아 있다 ───────────────────────
assert SRC.count("ADMIN_WRITE_OFF") >= 2, "스위치를 안 쓰고 박아 넣었다"
assert "if not ADMIN_WRITE_OFF:" in SRC, "스위치를 끄면 풀리게 되어 있지 않다"
ok += 1
print("5. 스위치 한 줄로 되돌릴 수 있다 ✓")

print("전부 통과 · %d 가지" % ok)
