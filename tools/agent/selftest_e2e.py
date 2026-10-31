"""End-to-end test with no API: a scripted model makes the real fix inside a real Docker sandbox,
then report, evidence check and scoring run on the saved files.
usage: python -I selftest_e2e.py [case_id]"""
import json, os, shutil, stat, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent, score
from sandbox import ROOT

case = sys.argv[1] if len(sys.argv) > 1 else "filelock-346"
info = score.case_info(case)
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {str(detail)[:400]!r}"))
    if not cond:
        fails.append(name)


def show(rev, path):
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=info["upstream"], capture_output=True).stdout.decode("utf-8")


names = subprocess.run(["git", "diff", "--name-only", info["faulty"], info["fixed"], "--", "src"],
                       cwd=info["upstream"], capture_output=True, text=True).stdout.split()
target = names[0]
fc = lambda n, **a: {"functionCall": {"name": n, "args": a}}
resp = lambda *calls: {"candidates": [{"content": {"role": "model", "parts": list(calls)}}], "usageMetadata": {"promptTokenCount": 500, "totalTokenCount": 600}}
steps = [
    resp(fc("read_file", path=target, start=1, end=40), fc("git_show", rev=info["breaking"][:10])),                    # calls 1, 2
    resp(fc("record_hypothesis", text="The change in the breaking commit altered behaviour of this module", predicts="the commit diff touches the failing path"),
         fc("record_hypothesis", text="The test itself is wrong", predicts="the test would fail on other code too")),  # 3, 4
    resp(fc("run_python", code="print('checking the failing scenario')")),                                             # 5
    resp(fc("update_hypothesis", id="H1", status="supported", evidence="The breaking commit diff shows the change", calls=[1, 2]),
         fc("update_hypothesis", id="H2", status="rejected", evidence="The scenario fails in the library code", calls=[5])),  # 6, 7
    resp(*[fc("apply_edit", path=n, search=show(info["faulty"], n), replace=show(info["fixed"], n)) for n in names]),  # 8..
]
n_edits = len(names)
verify_call = 7 + n_edits + 1
steps += [
    resp(fc("run_tests", selection=info["tests"])),
    resp(fc("submit", report={
        "root_cause": {"file": target, "function": "unknown", "breaking_commit": info["breaking"][:10],
                       "mechanism": "The breaking commit changed the behaviour of this module, so the failing scenario no longer works."},
        "verification": [{"command": "run_tests " + " ".join(info["tests"]), "result": "tests run after the edit", "call": verify_call}],
        "limitations": ["Only the targeted tests were run."]})),
]


class Scripted:
    def __init__(self, model, log): pass
    def generate(self, system, contents): return steps.pop(0), 1


def rm(p):
    if os.path.exists(p):
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


run_dir = f"{ROOT}/.tmp/e2e-{case}"
rm(run_dir)
rm(f"{ROOT}/.tmp/agent-e2e-{case}")
res = agent.run(case, run_dir, "scripted", client_factory=Scripted)
check("run submitted", res["outcome"] == "submitted", res)
check("expected number of tool calls", res["tool_calls"] == verify_call + 1, res)
check("report is valid", res.get("report_valid") is True, res.get("report_errors"))
ec = json.load(open(f"{run_dir}/evidence_check.json"))
check("evidence check ran", "items" in ec and ec["total"] > 0)
bad = [i for i in ec["items"] if i["status"] != "verified"]
check("every claim in the honest report is verified", ec["passed"] and not bad, bad)
ev = score.score(run_dir)
check("real fix scores success", ev["repair"]["outcome"] == "success", ev["repair"])
check("root cause matched by commit", ev["root_cause"]["status"] == "match", ev["root_cause"])
check("evidence result is in the evaluation", ev["evidence"]["passed"] is True)
check("cost is in the evaluation", ev["cost"]["tool_calls"] == res["tool_calls"])
for f in ("transcript.jsonl", "run.json", "submission.json", "workspace.patch", "result.json", "report.json", "report.md", "evidence_check.json", "evaluation.json"):
    check(f"artifact {f}", os.path.exists(f"{run_dir}/{f}"))
check("workspace.patch has the fix", len(open(f"{run_dir}/workspace.patch", encoding="utf-8").read()) > 20)
rm(run_dir)
rm(f"{ROOT}/.tmp/score-e2e-{case}")
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
