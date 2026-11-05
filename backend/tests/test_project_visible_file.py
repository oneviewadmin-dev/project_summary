# 프로젝트를 끄는 일이 파일에 제대로 남는가 (2026-10-28)
#   python3 backend/tests/test_project_visible_file.py
#
# Min: "양식 엑셀에 있는 프로젝트만 떠야 되는데 왜 없는것도 그대로 있는거야.."
#
# 양식에 없는 프로젝트는 화면에서 내린다. 지우지 않고 끈다 — 쌓인 주차
# 계획·실적이 그대로 남아야 이름이 돌아왔을 때 숫자가 살아 있다.
#
# 여기서는 '정말 파일에 남는가' 만 본다. 켜고 끄는 **규칙**은
# test_project_sync.py 가 본다.
import json, os, pathlib, shutil, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = tempfile.mkdtemp(prefix="cfgvis_")
# config_loader 는 들어오자마자 DATA_DIR 을 읽는다 — 먼저 세운다
os.environ["DATA_DIR"] = TMP
sys.path.insert(0, str(ROOT))
for _m in ("config_loader",):
    sys.modules.pop(_m, None)
import config_loader as cl              # noqa: E402

ok = 0
try:
    assert str(cl.EXTRA_PROJECTS_FILE).startswith(TMP), \
        "시험용 폴더를 안 쓴다 (%s) — 운영 파일을 건드릴 뻔했다" % cl.EXTRA_PROJECTS_FILE
    ok += 1

    cl.add_project({"id": "t_a", "division_id": "t", "label": "가",
                    "created_by": "division_form", "visible": True})
    cl.add_project({"id": "t_b", "division_id": "t", "label": "나",
                    "created_by": "division_form", "visible": True})

    # ── 끄면 목록에서 빠지고, visible_only=False 로는 그대로 보인다
    assert cl.set_project_visible("t_a", False, "division_form") is True
    ids = [p["id"] for p in cl.get_projects(division_id="t")]
    assert ids == ["t_b"], "끈 프로젝트가 아직 보인다: %r" % ids
    ok += 1
    allids = sorted(p["id"] for p in cl.get_projects(division_id="t", visible_only=False))
    assert allids == ["t_a", "t_b"], "끈 프로젝트가 사라졌다 — 지우면 안 된다: %r" % allids
    ok += 1

    # ── 파일에 남는가. 서버가 다시 떠도 꺼진 채여야 한다.
    saved = json.loads(cl.EXTRA_PROJECTS_FILE.read_text(encoding="utf-8"))
    row = [p for p in saved["projects"] if p["id"] == "t_a"][0]
    assert row["visible"] is False, "파일에는 켜진 채로 남았다: %r" % row
    assert row.get("hidden_by") == "division_form", "왜 껐는지 안 적었다: %r" % row
    assert row.get("hidden_at"), "언제 껐는지 안 적었다: %r" % row
    ok += 1

    # ── 두 번 꺼도 '바꾼 것 없음'. 화면에 같은 줄이 두 번 뜨면 안 된다.
    assert cl.set_project_visible("t_a", False) is False, "이미 꺼진 것을 또 껐다고 한다"
    ok += 1

    # ── 다시 켜면 '왜 껐는지' 자국을 지운다
    assert cl.set_project_visible("t_a", True) is True
    row = [p for p in json.loads(cl.EXTRA_PROJECTS_FILE.read_text(encoding="utf-8"))["projects"]
           if p["id"] == "t_a"][0]
    assert row["visible"] is True and "hidden_by" not in row and "hidden_at" not in row, \
        "다시 켰는데 꺼진 자국이 남아 있다: %r" % row
    ok += 1

    # ── '양식이 만든 것인가' 는 어디에 적혀 있는가로 가른다
    # created_by 표시로 가르려다 실패했다 — 그 표시를 넣기 전에 생긴
    # 프로젝트가 이미 서버에 쌓여 있어서 옛것이 하나도 안 걸렸다.
    assert cl.is_runtime_project("t_a") is True, "/data 에 있는데 아니라고 한다"
    assert cl.is_runtime_project("없는거") is False, "없는 것을 양식이 만들었다고 한다"
    assert cl.is_runtime_project("") is False
    ok += 1

    # ── 모르는 id 는 조용히 False. 양식 한 번 잘못 올린 게 서버를 세우면 안 된다.
    assert cl.set_project_visible("없는거", False) is False
    assert cl.set_project_visible("", False) is False
    ok += 1
finally:
    shutil.rmtree(TMP, ignore_errors=True)
    os.environ.pop("DATA_DIR", None)

print("ok %d" % ok)
