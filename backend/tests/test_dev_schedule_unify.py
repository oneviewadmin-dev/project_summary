# 개발 일정 — 품목마다 조금씩 다르게 적힌 단계 이름을 맞춘다 (2026-11-04)
#   python3 backend/tests/test_dev_schedule_unify.py
#
# Min: "03 PO 접수 가 왜 있냐..."
#   41개는 '03 PO 접수', 하나만 '03 PO 접수/등록' → 화면 표에 '03 PO 접수'
#   열이 맨 끝에 하나 더 섰다. '08 생산투입' 자리에 '투입 대기' 도 있었다.
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dev_schedule_import as d   # noqa: E402

A = ["01 Stack Up", "02 Stack Up 승인", "03 PO 접수", "04 자재 발주"]
B = ["01 사양 검토", "02 DFM", "03 Stack Up", "04 승인", "05 PO 접수"]


def item(row, names, pn="P"):
    return {"row": row, "part_number": pn, "project": "X",
            "steps": [{"name": n, "expected": None, "actual": None,
                       "expected_note": None, "actual_note": None} for n in names]}


items = [item(6, ["01 Stack Up", "02 Stack Up 승인", "03 PO 접수/등록", "04 자재 발주"], "AR00129")]
items += [item(10 + i, A) for i in range(5)]
items += [item(40 + i, B) for i in range(3)]
items += [item(60, ["01 사양 검토", "02 DFM", "03 Stack Up", "투입 대기", "05 PO 접수"], "LV00004")]
items += [item(70, ["가", "나", "다", "라"], "OTHER")]          # 아예 다른 틀은 건드리지 않는다
warn = []
d._unify_steps(items, warn)

names = lambda it: [s["name"] for s in it["steps"]]
assert names(items[0]) == A, names(items[0])
assert names(items[9]) == B, names(items[9])
assert items[9]["steps"][3]["actual_note"] == "투입 대기", "이름 칸의 상태 글자를 버렸다"
assert names(items[10]) == ["가", "나", "다", "라"], "다른 틀까지 바꿨다"
assert all(names(it) == A for it in items[1:6]) and all(names(it) == B for it in items[6:9]), "멀쩡한 줄이 바뀌었다"
assert len(warn) == 2 and "03 PO 접수/등록" in warn[0], warn
print("ok — 개발 일정 단계 이름 맞춤 (변형만 · 상태 글자는 메모로)")
