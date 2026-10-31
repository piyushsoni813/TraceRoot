"""Self-test of the agent tools against a real sandbox. usage: python -I selftest_tools.py [case_id]"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sandbox import Sandbox, ROOT
from tools import Toolset, MAX_OUT, SPECS, TOOLS_HASH

case = sys.argv[1] if len(sys.argv) > 1 else "click-3449"
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail[:200]!r}"))
    if not cond:
        fails.append(name)


_meta = json.load(open(f"{ROOT}/cases/{case}/metadata.json"))
test_file = (_meta.get("targeted_tests") or ["tests/test_helpers.py"])[0]

with Sandbox(case, f"{ROOT}/.tmp/tools-{case}") as sb:
    t = Toolset(sb)
    out = t.call("list_dir", {"path": "src"})
    check("list_dir src", out.strip() != "" and not out.startswith("error"), out)
    pkg = out.split()[0].rstrip("/")
    main = next((f for f in t.call("list_dir", {"path": f"src/{pkg}"}).split() if f.endswith(".py") and not f.startswith("_")), "__init__.py")
    path = f"src/{pkg}/{main}"
    out = t.call("read_file", {"path": path, "start": 3, "end": 5})
    check("read_file numbered range", [l.split("\t")[0] for l in out.splitlines()] == ["3", "4", "5"], out)
    check("read_file past end", "nothing in that range" in t.call("read_file", {"path": path, "start": 10**6}))
    check("read_file missing", t.call("read_file", {"path": "src/nope.py"}).startswith("error"))
    out = t.call("search", {"regex": "^import "})
    check("search finds", ":" in out and "no matches" not in out, out)
    check("search none", t.call("search", {"regex": "zzz_not_there_zzz"}) == "no matches")
    check("git_log", len(t.call("git_log", {"n": 3}).splitlines()) == 3)
    h = t.call("git_log", {"n": 1}).split()[0]
    check("git_show", h in t.call("git_show", {"rev": h}) or "diff" in t.call("git_show", {"rev": h}))
    check("git_blame", t.call("git_blame", {"path": path, "start": 1, "end": 2}).count("\n") == 2)
    check("git_show rejects option", t.call("git_show", {"rev": "--output=x"}).startswith("invalid"))
    check("git_show rejects branch name", t.call("git_show", {"rev": "main"}).startswith("invalid"))
    out = t.call("run_python", {"code": "import " + pkg + "; print('imported', " + pkg + ".__file__)"})
    check("run_python imports workspace", "/work/src/" in out and "[exit 0]" in out, out)
    out = t.call("run_python", {"code": "import urllib.request as u; u.urlopen('http://1.1.1.1', timeout=3)"})
    check("network blocked", "unreachable" in out.lower() or "URLError" in out, out)
    out = t.call("run_python", {"code": "print('x' * 50000)"})
    check("output truncated", len(out) < MAX_OUT + 200 and "truncated" in out, str(len(out)))
    out = t.call("run_python", {"code": "import time; time.sleep(100)"} if False else {"code": "print(1)"})
    check("run_python ok", "[exit 0]" in out, out)
    out = t.call("run_tests", {"selection": [test_file]})
    check("run_tests runs", "[exit" in out and "passed" in out, out[-200:])
    check("run_tests rejects flag", t.call("run_tests", {"selection": ["--co"]}).startswith("error"))
    for bad in ["../x", "/etc/passwd", "-rf", "src/../../x", "~/x"]:
        check(f"path rejected {bad}", "invalid path" in t.call("read_file", {"path": bad}))
    check("unknown tool", t.call("rm_rf", {}).startswith("error: unknown"))
    check("bad args", t.call("read_file", {"nope": 1}).startswith("error: bad arguments"))
    # hypotheses and submit gates
    t2 = Toolset(sb)
    rec = lambda i, st: t2.call("update_hypothesis", {"id": i, "status": st, "evidence": "e", "calls": [1]})
    check("submit needs hypotheses", "at least two" in t2.call("submit", {"report": {}}))
    check("record H1", t2.call("record_hypothesis", {"text": "a", "predicts": "x"}) == "recorded H1")
    check("record H2", t2.call("record_hypothesis", {"text": "b", "predicts": "y"}) == "recorded H2")
    check("record rejects empty", t2.call("record_hypothesis", {"text": " ", "predicts": "x"}).startswith("error"))
    check("update unknown id", "unknown hypothesis" in t2.call("update_hypothesis", {"id": "H9", "status": "rejected", "evidence": "e", "calls": [1]}))
    check("update bad status", t2.call("update_hypothesis", {"id": "H1", "status": "maybe", "evidence": "e", "calls": [1]}).startswith("error"))
    check("update needs calls", "calls must be" in t2.call("update_hypothesis", {"id": "H1", "status": "rejected", "evidence": "e", "calls": []}))
    check("update rejects future call", "calls must be" in t2.call("update_hypothesis", {"id": "H1", "status": "rejected", "evidence": "e", "calls": [99]}))
    check("update rejects own call", "calls must be" in t2.call("update_hypothesis", {"id": "H1", "status": "rejected", "evidence": "e", "calls": [t2.n_calls + 1]}))
    check("submit blocks open", "still open" in t2.call("submit", {"report": {}}))
    check("H1 rejected", rec("H1", "rejected") == "H1 is now rejected")
    check("H2 rejected", rec("H2", "rejected") == "H2 is now rejected")
    check("submit needs a supported one", "no hypothesis is supported" in t2.call("submit", {"report": {}}))
    check("H2 supported", rec("H2", "supported") == "H2 is now supported")
    check("submit needs an edit", "no fix applied" in t2.call("submit", {"report": {}}))
    # apply_edit
    check("edit outside scope", t2.call("apply_edit", {"path": "tests/x.py", "search": "a", "replace": "b"}).startswith("error: path"))
    check("edit traversal", t2.call("apply_edit", {"path": "src/../setup.py", "search": "a", "replace": "b"}).startswith("error: path"))
    check("edit missing file", "file not found" in t2.call("apply_edit", {"path": "src/nope.py", "search": "a", "replace": "b"}))
    check("edit no match", "matches 0 times" in t2.call("apply_edit", {"path": path, "search": "zzz_not_there_zzz", "replace": "b"}))
    check("edit multi match", "matches" in t2.call("apply_edit", {"path": path, "search": "e", "replace": "b"}) and not t2.edits)
    lines = open(f"{sb.workdir}/{path}", encoding="utf-8", newline="").read().split("\n")
    uniq = next(l for l in lines if l.strip() and sum(1 for m in lines if m == l) == 1)
    check("edit valid", t2.call("apply_edit", {"path": path, "search": uniq, "replace": uniq + "  # edited"}).startswith("applied edit 1"))
    check("workspace changed", "# edited" in open(f"{sb.workdir}/{path}", encoding="utf-8").read())
    check("submit needs tests after edit", "since your last apply_edit" in t2.call("submit", {"report": {}}))
    check("tests run", "[exit" in t2.call("run_tests", {"selection": [test_file]}))
    # a stray change made outside apply_edit must be caught
    other = next(f for f in t.call("list_dir", {"path": f"src/{pkg}"}).split() if f.endswith(".py") and f != main)
    t2.call("run_python", {"code": f"open('src/{pkg}/{other}', 'a').write('\\n# stray\\n')"})
    t2.call("run_tests", {"selection": [test_file]})
    check("submit catches stray change", "without apply_edit" in t2.call("submit", {"report": {}}), t2.call("submit", {"report": {}}))
    t2.call("run_python", {"code": f"import subprocess; subprocess.run(['git', 'checkout', '--', 'src/{pkg}/{other}'])"})
    t2.call("run_tests", {"selection": [test_file]})
    out = t2.call("submit", {"report": {"root_cause": {}}})
    check("submit valid", out == "submitted" and t2.submission is not None, out)
    check("submission has edits and hypotheses", len(t2.submission["edits"]) == 1 and [h["id"] for h in t2.submission["hypotheses"]] == ["H1", "H2"])
    check("calls are counted", t2.n_calls > 20 and t2.submission["hypotheses"][1]["calls"] == [1])
    check("specs complete", {s["name"] for s in SPECS} == {n[2:] for n in dir(Toolset) if n.startswith("t_")})

print("tools hash", TOOLS_HASH[:16])
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
