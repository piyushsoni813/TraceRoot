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
    # submit validation
    check("submit outside scope", "rejected" in t.call("submit", {"edits": [{"path": "tests/test_utils.py", "search": "a", "replace": "b"}], "report": {}}))
    check("submit no match", "matches 0 times" in t.call("submit", {"edits": [{"path": path, "search": "zzz_not_there_zzz", "replace": "b"}], "report": {}}))
    check("submit multi match", "matches" in t.call("submit", {"edits": [{"path": path, "search": "import", "replace": "b"}], "report": {}}) and t.submission is None)
    line = open(f"{sb.workdir}/{path}", encoding="utf-8").read().splitlines()[0]
    check("submit valid", t.call("submit", {"edits": [{"path": path, "search": line + "\n", "replace": line + "\n"}], "report": {"x": 1}}) == "submitted" and t.submission is not None)
    check("specs complete", {s["name"] for s in SPECS} == {n[2:] for n in dir(Toolset) if n.startswith("t_")})

print("tools hash", TOOLS_HASH[:16])
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
