"""Self-test of the agent loop with a scripted fake model (no API calls). usage: python -I selftest_agent.py"""
import io, json, os, shutil, stat, subprocess, sys, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent
import report as report_mod
from sandbox import ROOT

CASE = "click-3449"
meta = json.load(open(f"{ROOT}/cases/{CASE}/metadata.json"))
src = subprocess.run(["git", "-C", f"{ROOT}/cases/{CASE}/upstream", "show", f"{meta['faulty_revision']}:src/click/__init__.py"],
                     capture_output=True, text=True, encoding="utf-8").stdout
lines = src.split("\n")
UNIQ = next(l for l in lines if l.strip() and lines.count(l) == 1)
TEST = "tests/test_testing.py"
RUNS = f"{ROOT}/.tmp/agent-selftest"
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {str(detail)[:300]!r}"))
    if not cond:
        fails.append(name)


def rm(p):
    shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)), ignore_errors=False) if os.path.exists(p) else None


def fc(name, **args):
    return {"functionCall": {"name": name, "args": args}}


def response(parts, sig=None, ctx=1000):
    if sig:
        parts = [dict(p, thoughtSignature=sig) for p in parts]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": ctx, "totalTokenCount": ctx + 50}}


class Scripted:
    """Returns the next scripted response; records what it was sent."""
    def __init__(self, steps):
        self.steps, self.sent = list(steps), []

    def __call__(self, model, log):
        return self

    def generate(self, system, contents):
        self.sent.append(json.loads(json.dumps(contents)))
        step = self.steps.pop(0) if self.steps else response([fc("list_dir", path=".")])
        return (step() if callable(step) else step), 1


def go(name, client, **kw):
    d = f"{RUNS}/{name}"
    rm(d)
    rm(f"{ROOT}/.tmp/agent-{name}")
    res = agent.run(CASE, d, "fake-model", client_factory=client, **kw)
    events = [json.loads(l) for l in open(f"{d}/transcript.jsonl", encoding="utf-8")]
    return d, res, events


os.makedirs(RUNS, exist_ok=True)

# 1. happy path, with a thought signature that must be passed back untouched
H = lambda i, st: fc("update_hypothesis", id=i, status=st, evidence="seen", calls=[1])
happy = Scripted([
    response([fc("list_dir", path="src")], sig="SIG-1"),
    response([fc("record_hypothesis", text="A", predicts="x"), fc("record_hypothesis", text="B", predicts="y")]),
    response([H("H1", "rejected"), H("H2", "supported")]),
    response([fc("apply_edit", path="src/click/__init__.py", search=UNIQ, replace=UNIQ + "  # edited")]),
    response([fc("run_tests", selection=[TEST])]),
    response([fc("submit", report={"root_cause": {"file": "src/click/__init__.py", "function": "g", "mechanism": "a long enough explanation of the mechanism"}, "verification": [{"command": "run_tests", "result": "passed", "call": 1}], "limitations": ["not checked on other versions"]})]),
])
d, res, ev = go("happy", happy)
d_happy, res_happy = d, res
check("happy outcome submitted", res["outcome"] == "submitted", res)
check("happy tool calls counted", res["tool_calls"] == 8, res)
sub = json.load(open(f"{d}/submission.json"))
check("submission has edit, hypotheses, decision", len(sub["edits"]) == 1 and len(sub["hypotheses"]) == 2 and sub["decision"] == "ready for human review")
check("workspace.patch holds the edit", "# edited" in open(f"{d}/workspace.patch", encoding="utf-8").read())
check("thought signature echoed back", any("SIG-1" in json.dumps(c) for c in happy.sent[1]))
check("tool results carry budget notice", "tool call 1 of 40 used" in json.dumps(happy.sent[1]))
check("transcript events", [e["event"] for e in ev][0] == "run_start" and ev[-1]["event"] == "run_end" and sum(e["event"] == "tool_call" for e in ev) == 8)
check("tool_call numbers are 1..8", [e["n"] for e in ev if e["event"] == "tool_call"] == list(range(1, 9)))
check("run.json has hashes", set(json.load(open(f"{d}/run.json"))) >= {"tools_hash", "system_prompt_sha256", "user_prompt_sha256", "limits"})
check("refuses to overwrite a run", subprocess.run([sys.executable, "-I", f"{ROOT}/tools/agent/agent.py", CASE, d], capture_output=True).returncode != 0)

# 1b. the report for the happy run is built, valid and readable
rep = json.load(open(f"{d_happy}/report.json"))
check("report is valid", res_happy.get("report_valid") is True, res_happy.get("report_errors"))
check("evidence check ran with the report", "evidence_passed" in res_happy and os.path.exists(f"{d_happy}/evidence_check.json"), res_happy)
check("evidence check flags the weak verification call", res_happy.get("evidence_passed") is False and res_happy["evidence_counts"]["unverifiable"] >= 1, res_happy.get("evidence_counts"))
check("report has evidence entries for cited calls", [e["call"] for e in rep["evidence"]] == [1])
check("evidence excerpt comes from the transcript", "src" in rep["evidence"][0]["excerpt"] or rep["evidence"][0]["excerpt"] != "")
check("report patch has the diff", "# edited" in rep["patch"]["diff"] and rep["decision"] == "ready for human review")
md = open(f"{d_happy}/report.md", encoding="utf-8").read()
check("report.md has the sections", all(h in md for h in ("## Root cause", "## Hypotheses", "## Patch", "## Verification", "## Evidence", "## Limitations")))
# validator rejects bad reports
def bad(mut):
    r = json.loads(json.dumps(rep)); mut(r); return report_mod.validate(r, report_mod.SCHEMA)
check("rejects missing root cause field", any("root_cause.mechanism" in e for e in bad(lambda r: r["root_cause"].pop("mechanism"))))
check("rejects one hypothesis", any("at least 2" in e for e in bad(lambda r: r["hypotheses"].pop())))
check("rejects open status", any("not one of" in e for e in bad(lambda r: r["hypotheses"][0].update(status="open"))))
check("rejects wrong decision", any("decision" in e for e in bad(lambda r: r.update(decision="merged"))))
check("rejects empty patch", any("patch" in e for e in bad(lambda r: r["patch"].update(edits=[]))))
check("rejects extra top-level field", any("not allowed" in e for e in bad(lambda r: r.update(extra=1))))
check("rejects bool as integer", any("expected integer" in e for e in bad(lambda r: r["verification"][0].update(call=True))))

# 2. budget exhausted
d, res, ev = go("budget", Scripted([response([fc("list_dir", path=".")])] * 10), max_calls=3)
check("budget outcome", res["outcome"] == "budget_exhausted" and res["tool_calls"] == 3, res)
# a parallel batch larger than the budget must not run extra calls
d, res, ev = go("budget-batch", Scripted([response([fc("list_dir", path=".")] * 6)]), max_calls=3)
check("batch capped at budget", res["tool_calls"] == 3 and res["outcome"] == "budget_exhausted", res)

# 3. time exhausted before any model call
d, res, ev = go("time", Scripted([]), max_seconds=0)
check("time outcome", res["outcome"] == "time_exhausted" and res["model_calls"] == 0, res)

# 4. text-only answers are nudged, then the run ends
text_only = {"candidates": [{"content": {"role": "model", "parts": [{"text": "thinking"}]}, "finishReason": "STOP"}], "usageMetadata": {}}
d, res, ev = go("nudge", Scripted([text_only] * 6))
check("nudged then no_submission", res["outcome"] == "no_submission" and sum(e["event"] == "nudge" for e in ev) == 4, res)

# 5. empty candidate (blocked)
d, res, ev = go("empty", Scripted([{"candidates": [], "usageMetadata": {}}]))
check("empty candidate outcome", res["outcome"] == "model_returned_nothing", res)

# 6. context budget
d, res, ev = go("context", Scripted([response([fc("list_dir", path=".")], ctx=250_000)] * 3))
check("context outcome", res["outcome"] == "context_exhausted", res)

# 7. unknown tool and bad args do not crash
d, res, ev = go("badcalls", Scripted([response([fc("rm_rf"), fc("read_file", nope=1)])] + [response([fc("list_dir", path=".")])] * 5), max_calls=4)
check("bad calls survive", res["tool_calls"] == 4, res)
check("bad call errors are logged", any("unknown tool" in e.get("result", "") for e in ev) and any("bad arguments" in e.get("result", "") for e in ev))

# 8. retry logic of the real client with a faked network
class Resp:
    def __init__(self, b): self.b = b
    def read(self): return self.b

calls = {"n": 0}
def fake_urlopen(req, timeout=0):
    calls["n"] += 1
    if calls["n"] <= 2:
        raise urllib.error.HTTPError(req.full_url, 503, "unavailable", {}, io.BytesIO(b'{"error":"busy"}'))
    return Resp(json.dumps(response([fc("list_dir")])).encode())

logged = []
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
real = agent.GeminiClient("m", lambda e, **kw: logged.append((e, kw)))
agent.urllib.request.urlopen, agent.time.sleep = fake_urlopen, lambda s: None
r, attempt = real.generate("sys", [{"role": "user", "parts": [{"text": "hi"}]}])
check("retried 503 twice then succeeded", attempt == 3 and len([e for e, _ in logged if e == "api_retry"]) == 2, logged)
calls["n"] = -100  # always fail
try:
    real.generate("sys", [])
    check("gives up after max attempts", False)
except agent.ApiError as e:
    check("gives up after max attempts", "503" in str(e) and len([1 for e, _ in logged if e == "api_retry"]) == 2 + agent.MAX_API_ATTEMPTS - 1)
def bad_request(req, timeout=0):
    raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":"bad schema"}'))
agent.urllib.request.urlopen = bad_request
n_before = len(logged)
try:
    real.generate("sys", [])
    check("400 is not retried", False)
except agent.ApiError:
    check("400 is not retried", len(logged) == n_before)

# 8b. a daily quota fails fast, and an API error mid-run still leaves the artifacts
def daily(req, timeout=0):
    raise urllib.error.HTTPError(req.full_url, 429, "quota", {}, io.BytesIO(b'{"error":{"message":"Generate content requests per day limit exceeded"}}'))
agent.urllib.request.urlopen = daily
n_before = len([1 for e, _ in logged if e == "api_retry"])
try:
    real.generate("sys", [])
    check("daily quota not retried", False)
except agent.ApiError as e:
    check("daily quota not retried", len([1 for e2, _ in logged if e2 == "api_retry"]) == n_before and "daily quota" in str(e))

class FailsAfterTwo(Scripted):
    def generate(self, system, contents):
        if len(self.sent) >= 2:
            raise agent.ApiError("HTTP 429 (daily quota): test")
        return super().generate(system, contents)

d, res, ev = go("apierr", FailsAfterTwo([response([fc("list_dir", path=".")])] * 3))
check("api_error outcome keeps the tool count", res["outcome"] == "api_error" and res["tool_calls"] == 2, res)
check("api_error still writes workspace.patch and result.json", os.path.exists(f"{d}/workspace.patch") and os.path.exists(f"{d}/result.json"))
check("api_error is in the transcript", ev[-2]["event"] == "api_error" and ev[-1]["event"] == "run_end")

# 9. the key never reaches the saved files
key = os.environ["GEMINI_API_KEY"]
leak = [os.path.join(dp, f) for dp, _, fs in os.walk(RUNS) for f in fs if key.encode() in open(os.path.join(dp, f), "rb").read()]
check("api key not in any run file", not leak, leak)

for name in os.listdir(RUNS):
    rm(f"{ROOT}/.tmp/agent-{name}")
rm(RUNS)
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
