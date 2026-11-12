# ============================================================
#  코드 설명 규칙 점검 — 파일 머리 · 함수 위 설명 · 구분선
# ============================================================
# docs/코드_주석_규칙.md 의 '모든 파일에 있어야 하는 세 가지' 를 기계로 센다.
#
#   1. 파일 머리 설명   맨 위에 '# ====' 줄 · 제목 줄 · '# ====' 줄
#                      (dart · js 는 '// ====', html 은 '<!-- ====')
#   2. 함수 위 설명     모든 함수 · 클래스 바로 위에 주석, 또는 docstring
#   3. 구분선          함수가 3개 이상인 파일은 머리 말고도 구분선이 있고,
#                      구분선 하나 아래에 함수가 8개를 넘지 않는다
#
# 쓰는 법
#   python3 backend/tests/test_comment_rules.py            저장소 전체
#   python3 backend/tests/test_comment_rules.py 파일 ...   몇 개만
#   python3 backend/tests/test_comment_rules.py --list     빠진 곳 전부 출력
#
# 저장소 맨 위(project_summary)를 기준으로 파일을 찾는다. 하나라도 빠지면
# 종료 코드 1 — 다른 tests/test_*.py 와 같이 돌릴 수 있다.
from __future__ import annotations

import ast
import os
import re
import sys

# 저장소 맨 위 — 이 파일은 backend/tests/ 안에 있다
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 구분선 하나 아래에 둘 수 있는 함수 수. 이보다 많으면 묶음을 나눈다.
# 8 인 이유: 화면 한 장(40~60줄)에 함수 머리가 다 안 들어오면 묶음 제목을
# 다시 찾으러 올라가야 한다. 지금 코드에서 잘 읽히는 묶음이 대개 3~7개다.
MAX_PER_SECTION = 8

# 구분선으로 치는 줄. '='·'-' 4개 이상, 또는 '─'·'━' 6개 이상.
# '# ── 1. 하는 일' 같은 함수 안 단계 표시(─ 2개)는 구분선이 아니다.
_DIV_BODY = r"(={4,}|-{4,}|─{6,}|━{6,})"
PY_DIV = re.compile(r"^\s*#\s*" + _DIV_BODY)
SL_DIV = re.compile(r"^\s*(//+|/\*+|\*)\s*" + _DIV_BODY)
HTML_DIV = re.compile(r"^\s*<!--\s*" + _DIV_BODY)


# ============================================================
#  공통
# ============================================================
# 파일 머리: 맨 위(빈 줄 · #! 줄은 건너뜀) 세 줄이 '구분선 · 제목 · 구분선' 인가.
def _has_header(lines: list, div_re, title_re) -> bool:
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or lines[i].startswith("#!")
                              or lines[i].startswith("# -*-")):
        i += 1
    if i + 2 >= len(lines):
        return False
    if not div_re.match(lines[i]):
        return False
    # 제목 줄은 한 줄 이상일 수 있다 — 다음 구분선까지 4줄 안에서 찾는다
    for j in range(i + 1, min(len(lines), i + 6)):
        if div_re.match(lines[j]):
            return j > i + 1 and all(title_re.match(lines[k]) for k in range(i + 1, j))
    return False


# 구분선 사이에 함수가 몇 개씩 있는지. top 은 맨 바깥 함수들의 줄 번호(1부터).
def _section_problems(lines: list, top: list, div_re, header_end: int) -> list:
    out = []
    if len(top) < 3:
        return out
    divs = [i + 1 for i, l in enumerate(lines) if div_re.match(l) and i + 1 > header_end]
    if not divs:
        out.append((1, "구분선이 머리 말고는 하나도 없음 (함수 %d개)" % len(top)))
        return out
    # 구분선마다 그 아래 함수 수를 센다
    bounds = divs + [10 ** 9]
    before = [n for n in top if n < divs[0]]
    if len(before) > MAX_PER_SECTION:
        out.append((before[0], "첫 구분선 전에 함수 %d개" % len(before)))
    for a, b in zip(bounds, bounds[1:]):
        inside = [n for n in top if a < n < b]
        if len(inside) > MAX_PER_SECTION:
            out.append((a, "구분선 하나 아래 함수 %d개 (최대 %d)" % (len(inside), MAX_PER_SECTION)))
    return out


# 머리 블록이 끝나는 줄 번호 (머리 안의 구분선은 묶음 구분선으로 안 센다).
def _header_end(lines: list, div_re) -> int:
    seen = 0
    for i, l in enumerate(lines[:8]):
        if div_re.match(l):
            seen += 1
            if seen == 2:
                return i + 1
    return 0


# ============================================================
#  파이썬
# ============================================================
# 함수 · 클래스 바로 위(데코레이터 위)에 # 주석이 있나. 빈 줄 하나는 봐준다.
def _py_comment_above(lines: list, node) -> bool:
    start = node.lineno
    if getattr(node, "decorator_list", None):
        start = min(d.lineno for d in node.decorator_list)
    i = start - 2
    if i >= 0 and lines[i].strip() == "":
        i -= 1
    return i >= 0 and lines[i].lstrip().startswith("#")


# 파이썬 파일 하나를 보고 빠진 곳 목록을 돌려준다. [(줄, 무엇)]
def check_py(path: str) -> list:
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    out = []
    if not _has_header(lines, PY_DIV, re.compile(r"^#(\s|$)")):
        out.append((1, "파일 머리 설명 없음 (# ==== / # 제목 / # ====)"))
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return out + [(e.lineno or 1, "문법 오류: %s" % e.msg)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(node) is None and not _py_comment_above(lines, node):
                out.append((node.lineno, "함수 위 설명 없음: %s" % node.name))
    top = [n.lineno if not getattr(n, "decorator_list", None) else min(d.lineno for d in n.decorator_list)
           for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    out += _section_problems(lines, top, PY_DIV, _header_end(lines, PY_DIV))
    return out


# ============================================================
#  자바스크립트 (admin_v2.html 의 <script> 안)
# ============================================================
_JS_FN = re.compile(
    r"^(\s*)(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
    r"|^(\s*)(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")
_JS_COMMENT = re.compile(r"^\s*(//|/\*|\*)")


# html 파일 하나 — 머리는 <!-- ==== -->, <script> 마다 // ==== 머리, 함수마다 // 설명.
def check_html(path: str) -> list:
    lines = open(path, encoding="utf-8").read().split("\n")
    out = []
    if not _has_header(lines, HTML_DIV, re.compile(r"^\s*(\S|$)")) and not _has_header(
            [l for l in lines if l.strip() and not l.lower().startswith("<!doctype")], HTML_DIV,
            re.compile(r"^\s*(\S|$)")):
        out.append((1, "파일 머리 설명 없음 (<!-- ==== / 제목 / ==== -->)"))
    # <script> 블록을 찾는다 (src= 로 밖에서 불러오는 것은 뺀다)
    blocks = []
    start = None
    for i, l in enumerate(lines):
        low = l.lower()
        if start is None and "<script" in low and "src=" not in low and "</script>" not in low:
            start = i + 1
        elif start is not None and "</script>" in low:
            blocks.append((start, i))
            start = None
    for a, b in blocks:
        body = lines[a:b]
        if sum(1 for l in body if l.strip()) < 3:
            continue
        # 블록 머리 — 첫 줄들(빈 줄 · '(function () {' 건너뜀)이 // ==== 머리인가
        k = 0
        while k < len(body) and (body[k].strip() == "" or body[k].strip().startswith("(function")):
            k += 1
        if not _has_header(body[k:], SL_DIV, re.compile(r"^\s*//")):
            out.append((a + 1, "<script> 머리 설명 없음 (// ==== / // 제목 / // ====)"))
        top = []
        base = None
        for j, l in enumerate(body):
            m = _JS_FN.match(l)
            if not m:
                continue
            ind = len(m.group(1) if m.group(1) is not None else m.group(3))
            name = m.group(2) or m.group(4)
            p = j - 1
            if p >= 0 and body[p].strip() == "":
                p -= 1
            if not (p >= 0 and _JS_COMMENT.match(body[p])):
                out.append((a + j + 1, "함수 위 설명 없음: %s" % name))
            # 구분선 묶음은 블록에서 가장 바깥 들여쓰기의 함수로 센다
            if base is None or ind < base:
                base = ind
                top = [x for x in top if x[1] <= ind]
            if ind == base:
                top.append((a + j + 1, ind))
        out += [(a + n, msg) for n, msg in
                _section_problems(body, [t[0] - a for t in top], SL_DIV, k + _header_end(body[k:], SL_DIV))]
    return out


# ============================================================
#  다트 (앱)
# ============================================================
_DART_CLASS = re.compile(r"^(\s*)(?:abstract\s+|sealed\s+|final\s+|base\s+)*(class|enum|mixin|extension|typedef)\s+\w+")
# 반환형 + 이름 + ( … — 들여쓰기 0(맨 바깥) 또는 2(클래스 안)만 본다.
_DART_FN = re.compile(
    r"^( {0}| {2})(?:static\s+|external\s+)*"
    r"(?:Future<.*?>|Stream<.*?>|FutureOr<.*?>|void|dynamic|[A-Z]\w*(?:<.*?>)?\??|int|double|num|bool|String|List<.*?>|Map<.*?>|Set<.*?>|Iterable<.*?>)\s+"
    r"(?:get\s+)?(_?[a-zA-Z]\w*)\s*(\(|=>|\{)")
_DART_SKIP = {"if", "for", "while", "switch", "return", "catch", "new", "await", "else", "case"}


# 다트 파일 하나 — 머리 // ====, 클래스 · 함수마다 // 또는 /// 설명, 구분선.
def check_dart(path: str) -> list:
    lines = open(path, encoding="utf-8").read().split("\n")
    out = []
    if not _has_header(lines, SL_DIV, re.compile(r"^\s*//")):
        out.append((1, "파일 머리 설명 없음 (// ==== / // 제목 / // ====)"))
    top = []
    depth = 0          # 중괄호 깊이 — 문자열 안 괄호는 드물어서 대충 센다
    for i, l in enumerate(lines):
        code = re.sub(r"//.*$", "", l)
        m_c = _DART_CLASS.match(l)
        m_f = _DART_FN.match(l) if depth <= 1 else None
        hit = None
        if m_c and depth == 0:
            hit = l.split()[1] if l.split()[0] in ("abstract", "sealed", "final", "base") else l.split()[1]
        elif m_f and m_f.group(2) not in _DART_SKIP and (depth == 0 or (depth == 1 and m_f.group(1) == "  ")):
            hit = m_f.group(2)
        if hit:
            p = i - 1
            while p >= 0 and lines[p].strip().startswith("@"):
                p -= 1
            if p >= 0 and lines[p].strip() == "":
                p -= 1
            if not (p >= 0 and lines[p].lstrip().startswith(("//", "/*", "*"))):
                out.append((i + 1, "함수 위 설명 없음: %s" % hit))
            if depth == 0:
                top.append(i + 1)
        depth += code.count("{") - code.count("}")
        if depth < 0:
            depth = 0
    out += _section_problems(lines, top, SL_DIV, _header_end(lines, SL_DIV))
    return out


# ============================================================
#  셸
# ============================================================
# 셸 스크립트 — 머리만 본다 (함수가 거의 없다).
def check_sh(path: str) -> list:
    lines = open(path, encoding="utf-8").read().split("\n")
    if _has_header(lines, PY_DIV, re.compile(r"^#(\s|$)")):
        return []
    return [(1, "파일 머리 설명 없음 (# ==== / # 제목 / # ====)")]


# ============================================================
#  저장소 훑기
# ============================================================
# 점검할 파일 목록 — 자료(data) · 빌드 결과 · 외부 패키지는 뺀다.
def targets() -> list:
    out = []
    for rel in ("backend", "backend/tests"):
        d = os.path.join(ROOT, rel)
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") or f.endswith(".html"):
                out.append(os.path.join(d, f))
    for rel in ("mobile/lib", "mobile/test"):
        for dp, _, fs in os.walk(os.path.join(ROOT, rel)):
            for f in sorted(fs):
                if f.endswith(".dart") and not f.endswith((".g.dart", ".freezed.dart")):
                    out.append(os.path.join(dp, f))
    for f in ("release.sh", "backup.sh", "tools_changelog.py", "tools_pull_api.py", "tools_code_map.py"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            out.append(p)
    return [p for p in out if os.path.isfile(p)]


# 확장자에 맞는 점검을 고른다.
def check(path: str) -> list:
    if path.endswith(".py"):
        return check_py(path)
    if path.endswith(".dart"):
        return check_dart(path)
    if path.endswith(".html"):
        return check_html(path)
    if path.endswith(".sh"):
        return check_sh(path)
    return []


# 명령줄에서 부르면 — 파일별로 빠진 곳 수를 찍고, 하나라도 있으면 1 로 끝낸다.
def main(argv: list) -> int:
    show = "--list" in argv
    files = [a for a in argv if not a.startswith("--")] or targets()
    total = 0
    bad = 0
    for p in files:
        probs = check(p)
        if probs:
            bad += 1
            total += len(probs)
            rel = os.path.relpath(p, ROOT)
            print("%-60s %d곳" % (rel, len(probs)))
            if show:
                for n, msg in probs:
                    print("    %s:%d  %s" % (rel, n, msg))
    print("파일 %d개 중 %d개 · 빠진 곳 %d" % (len(files), bad, total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
