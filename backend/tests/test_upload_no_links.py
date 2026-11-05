# 엑셀을 열 때 외부 링크를 읽지 않는다 (2026-11-04)
#   python3 backend/tests/test_upload_no_links.py
#
# PCB사업부 품목별 개발 일정 20261104 점검.xlsx 를 올리자
#   "읽지 못했습니다. Failed to execute 'json' on 'Response': Unexpected end of JSON input"
#
# 파일은 6.5MB 인데, 안에 다른 엑셀을 가리키는 외부 링크 캐시
# (xl/externalLinks/externalLink1.xml)가 51MB 나 들어 있었다. openpyxl 은
# 기본으로 그걸 다 읽는다 — 메모리 1.26GB, 11초. 서버가 메모리 부족으로
# 죽어서 빈 응답이 갔다. keep_links=False 면 34MB, 0.1초.
#
# 우리는 칸에 적힌 값만 읽는다. 외부 링크는 필요 없다.
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
bad = []
for f in sorted(ROOT.glob("*.py")):
    src = f.read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"\bload_workbook\(", line) and "keep_links=False" not in line \
                and not line.lstrip().startswith("#"):
            bad.append("%s:%d  %s" % (f.name, i, line.strip()))
assert not bad, "외부 링크까지 읽는 load_workbook 이 있다 (keep_links=False):\n  " + "\n  ".join(bad)
print("ok — 엑셀은 외부 링크 없이 연다")
