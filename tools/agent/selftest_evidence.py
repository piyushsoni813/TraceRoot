"""Self-test of evidence_check.py on hand-built transcripts (no API, no Docker).
usage: python -I selftest_evidence.py"""
import copy, json, os, shutil, stat, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_check
from sandbox import ROOT

BASE = f"{ROOT}/.tmp/evidence-selftest"
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {str(detail)[:300]!r}"))
    if not cond:
        fails.append(name)


def rm(p):
    if os.path.exists(p):
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def call(n, name, args, result):
    return {"t": n, "event": "tool_call", "n": n, "name": name, "args": args, "result": result, "notice": "", "seconds": 0.1}


EDIT = {"path": "src/pkg/mod.py", "search": "return x + 1", "replace": "return x + 2"}
DIFF = "--- a/src/pkg/mod.py\n+++ b/src/pkg/mod.py\n@@ -3 +3 @@\n-    return x + 1\n+    return x + 2\n"


def good():
    calls = [
        call(1, "read_file", {"path": "src/pkg/mod.py", "start": 1, "end": 3}, "1\timport os\n2\tdef foo(x):\n3\t    return x + 1\n"),
        call(2, "git_log", {"n": 5}, "abc1234 2024-01-01 Dev change foo\n"),
        call(3, "git_show", {"rev": "abc1234"}, "abc1234def0000000000000000000000000000ff\nDev 2024-01-01\n\nchange foo\n\ndiff --git a/src/pkg/mod.py b/src/pkg/mod.py\n"),
        call(4, "record_hypothesis", {"text": "A", "predicts": "x"}, "recorded H1"),
        call(5, "record_hypothesis", {"text": "B", "predicts": "y"}, "recorded H2"),
        call(6, "run_python", {"code": "from pkg.mod import foo\nprint(foo(1))"}, "[exit 0]\n2\n"),
        call(7, "update_hypothesis", {"id": "H1", "status": "rejected", "evidence": "e", "calls": [6]}, "H1 is now rejected"),
        call(8, "update_hypothesis", {"id": "H2", "status": "supported", "evidence": "e", "calls": [1, 3]}, "H2 is now supported"),
        call(9, "apply_edit", EDIT, "applied edit 1 to src/pkg/mod.py. Run tests to check it."),
        call(10, "run_tests", {"selection": ["tests/test_mod.py"]}, "[exit 0]\n............\n12 passed in 0.50s\n"),
        call(11, "submit", {"report": {}}, "submitted"),
    ]
    report = {
        "root_cause": {"file": "src/pkg/mod.py", "function": "foo", "breaking_commit": "abc1234",
                       "mechanism": "`return x + 1` at src/pkg/mod.py:3 returns the wrong value since commit abc1234."},
        "hypotheses": [
            {"id": "H1", "text": "the caller passes the wrong value", "predicts": "p", "status": "rejected", "evidence": "foo(1) printed 2 in isolation", "calls": [6]},
            {"id": "H2", "text": "foo changed in a recent commit", "predicts": "p", "status": "supported", "evidence": "see src/pkg/mod.py:3 and commit abc1234", "calls": [1, 3]}],
        "verification": [{"command": "run_tests tests/test_mod.py", "result": "12 passed", "call": 10}],
        "patch": {"edits": [EDIT], "diff": DIFF},
    }
    sub = {"edits": [EDIT], "hypotheses": [
        {"id": "H1", "calls": [6], "updated_at_call": 7}, {"id": "H2", "calls": [1, 3], "updated_at_call": 8}]}
    return {"calls": calls, "report": report, "sub": sub, "diff": DIFF, "prompt": "Bug: foo is wrong. Trace: File \"/work/src/pkg/mod.py\", line 3, in foo"}


def run(name, mut=None):
    d = good()
    if mut:
        mut(d)
    path = f"{BASE}/{name}"
    rm(path)
    os.makedirs(path)
    ev = [{"t": 0, "event": "run_start", "user_prompt": d["prompt"]}] + d["calls"] + [{"t": 9, "event": "run_end"}]
    open(f"{path}/transcript.jsonl", "w", encoding="utf-8").write("\n".join(json.dumps(e) for e in ev) + "\n")
    json.dump(d["report"], open(f"{path}/report.json", "w"))
    json.dump(d["sub"], open(f"{path}/submission.json", "w"))
    open(f"{path}/workspace.patch", "w", encoding="utf-8").write(d["diff"])
    return evidence_check.check(path)


def has(r, kind, status, text=""):
    return any(i["kind"] == kind and i["status"] == status and text in i["detail"] for i in r["items"])


os.makedirs(BASE, exist_ok=True)
r = run("good")
check("honest report passes", r["passed"] and r["counts"]["unverifiable"] == 0 and r["counts"]["contradicted"] == 0, r["counts"])
check("good report has items of every kind", {i["kind"] for i in r["items"]} >= {"hypothesis_call", "verification", "line_citation", "commit", "quote", "root_cause_file", "patch"}, {i["kind"] for i in r["items"]})
check("evidence_check.json is written", os.path.exists(f"{BASE}/good/evidence_check.json"))

# hypothesis citations
r = run("future", lambda d: d["report"]["hypotheses"][1].update(calls=[11]) or d["sub"]["hypotheses"][1].update(calls=[11]))
check("citing a call after the update is contradicted", has(r, "hypothesis_call", "contradicted", "at or after") and not r["passed"], r["items"])
r = run("missing", lambda d: d["sub"]["hypotheses"][0].update(calls=[40]))
check("citing a call that does not exist is contradicted", has(r, "hypothesis_call", "contradicted", "does not exist"))
r = run("bookkeeping", lambda d: d["sub"]["hypotheses"][0].update(calls=[4]))
check("citing record_hypothesis as evidence is unverifiable", has(r, "hypothesis_call", "unverifiable", "no evidence"))
r = run("errcall", lambda d: d["calls"][5].update(result="error: boom"))
check("citing a call that errored is unverifiable", has(r, "hypothesis_call", "unverifiable", "error"))

# verification
r = run("stale", lambda d: d["report"]["verification"][0].update(call=6))
check("verification before the last edit is unverifiable", has(r, "verification", "unverifiable", "before the last edit"))
r = run("notest", lambda d: d["report"]["verification"][0].update(call=2))
check("verification citing git_log is unverifiable", has(r, "verification", "unverifiable", "not a test"))
r = run("nocall", lambda d: d["report"]["verification"][0].update(call=77))
check("verification citing a missing call is contradicted", has(r, "verification", "contradicted"))
r = run("count", lambda d: d["report"]["verification"][0].update(result="13 passed"))
check("wrong pass count is contradicted", has(r, "verification", "contradicted", "13 passed"))
def failing(d):
    d["calls"][9]["result"] = "[exit 1]\nFAILED tests/test_mod.py::t\n1 failed, 11 passed in 0.5s\n"
    d["report"]["verification"][0]["result"] = "all tests pass"
r = run("claimpass", failing)
check("claiming a pass on a failing run is contradicted", has(r, "verification", "contradicted", "exited 1"))
r = run("honestfail", lambda d: (d["calls"][9].update(result="[exit 1]\n1 failed, 11 passed in 0.5s\n"), d["report"]["verification"][0].update(result="1 failed, 11 passed")))
check("honestly reporting a failure is verified", has(r, "verification", "verified"), r["items"])
r = run("othertests", lambda d: d["report"]["verification"][0].update(command="pytest tests/other.py"))
check("command naming other tests is unverifiable", has(r, "verification", "unverifiable", "does not name"))
r = run("twospans", lambda d: d["report"]["root_cause"].update(mechanism="The `foo` call and the `bar` call disagree, which breaks `return x + 1` here."))
check("text between two short spans is not taken as a quote", not any(i["kind"] == "quote" and "call and the" in i["detail"] for i in r["items"]), r["items"])
check("a real long span next to short ones is still checked", has(r, "quote", "verified", "return x + 1"))
r = run("python-label", lambda d: (d["calls"][9].update(name="run_python", args={"code": "import pkg; assert pkg.mod.foo(1) == 3"}, result="[exit 0]\n"),
                                   d["report"]["verification"][0].update(command="ran the reproducer", result="exit 0, no error")))
check("a run_python verification is not judged by its command label", has(r, "verification", "verified"), r["items"])
check("the checker commit is recorded", "checker_commit" in r)
r = run("python-ok", lambda d: (d["calls"][9].update(name="run_python", args={"code": "print('ok check')"}, result="[exit 0]\nok check\n"),
                                d["report"]["verification"][0].update(command="python -c \"print('ok check')\"", result="printed ok check")))
check("run_python verification matched by its code", has(r, "verification", "verified"), r["items"])

# citations in the text
r = run("badline", lambda d: d["report"]["root_cause"].update(mechanism="`return x + 1` at src/pkg/mod.py:99 is wrong because of the change."))
check("a line that was never shown is unverifiable", has(r, "line_citation", "unverifiable", "mod.py:99"))
r = run("lineword", lambda d: d["report"]["root_cause"].update(mechanism="In src/pkg/mod.py, line 3 the code `return x + 1` is wrong for sure."))
check("'file, line N' form is recognised and verified", has(r, "line_citation", "verified", "mod.py:3"))
r = run("badcommit", lambda d: d["report"]["root_cause"].update(breaking_commit="deadbee1"))
check("a commit hash seen in no git output is unverifiable", has(r, "commit", "unverifiable", "deadbee1"))
r = run("shortcommit", lambda d: d["report"]["root_cause"].update(breaking_commit="abc1234def"))
check("a longer prefix of a seen hash is verified", has(r, "commit", "verified", "abc1234def"))
r = run("badquote", lambda d: d["report"]["root_cause"].update(mechanism="The code `def bar(y): return y * 3` never handles the case."))
check("a quote that appears nowhere is unverifiable", has(r, "quote", "unverifiable", "def bar"))
r = run("promptquote", lambda d: d["report"]["root_cause"].update(mechanism="The trace shows `Bug: foo is wrong.` as the report, so look there."))
check("a quote from the bug report is verified", has(r, "quote", "verified", "Bug: foo is wrong"), r["items"])
r = run("unopened", lambda d: d["report"]["root_cause"].update(file="src/pkg/other.py"))
check("a root cause file that was never opened is unverifiable", has(r, "root_cause_file", "unverifiable", "other.py"))

# patch consistency
r = run("editsdiffer", lambda d: d["report"]["patch"].update(edits=[dict(EDIT, replace="return x + 9")]))
check("report edits that differ from apply_edit calls are contradicted", has(r, "patch", "contradicted", "differ from the apply_edit"))
r = run("diffdiffers", lambda d: d["report"]["patch"].update(diff="something else"))
check("a report diff that differs from workspace.patch is contradicted", has(r, "patch", "contradicted", "workspace.patch"))
r = run("failededit", lambda d: d["calls"][8].update(result="error: search text matches 0 times"))
check("an edit that failed is not counted as applied", has(r, "patch", "contradicted"))

# the same input twice gives the same answer
a, b = run("same1"), run("same2")
check("deterministic", a["items"] == b["items"])

rm(BASE)
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
