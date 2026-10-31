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

# 8c. LocalClient: Gemini-shaped history becomes OpenAI messages, and the reply comes back Gemini-shaped
hist = [{"role": "user", "parts": [{"text": "bug"}]},
        {"role": "model", "parts": [{"functionCall": {"id": "c1", "name": "list_dir", "args": {"path": "."}}}]},
        {"role": "user", "parts": [{"functionResponse": {"id": "c1", "name": "list_dir", "response": {"result": "a.py"}}}]},
        {"role": "user", "parts": [{"text": "go on"}]}]
msgs = agent.LocalClient._messages("SYS", hist)
check("local messages: roles in order", [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "user"], [m["role"] for m in msgs])
check("local messages: tool call and result share an id", msgs[2]["tool_calls"][0]["id"] == msgs[3]["tool_call_id"] == "c1")
check("local messages: arguments are a JSON string", json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"]) == {"path": "."})
sent = {}
def local_ok(req, timeout=0):
    sent["body"] = json.loads(req.data)
    return Resp(json.dumps({"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "x9", "type": "function", "function": {"name": "read_file", "arguments": "{\"path\": \"src/a.py\"}"}},
        {"id": "x10", "type": "function", "function": {"name": "search", "arguments": "not json"}}]}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 321, "total_tokens": 400}}).encode())
agent.urllib.request.urlopen = local_ok
lc = agent.make_client("local-qwen3-8b", lambda e, **kw: None)
check("model names starting with local pick LocalClient", isinstance(lc, agent.LocalClient))
r, _ = lc.generate("SYS", hist)
parts = r["candidates"][0]["content"]["parts"]
check("local reply parsed into functionCall parts", [p["functionCall"]["name"] for p in parts] == ["read_file", "search"] and parts[0]["functionCall"]["args"] == {"path": "src/a.py"})
check("local reply keeps call ids and survives bad arguments", parts[0]["functionCall"]["id"] == "x9" and parts[1]["functionCall"]["args"] == {})
check("local usage is mapped", r["usageMetadata"] == {"promptTokenCount": 321, "totalTokenCount": 400})
check("local request forces a tool call and sends every tool", sent["body"]["tool_choice"] == "required" and len(sent["body"]["tools"]) == len(agent.SPECS))
check("gemini model names pick GeminiClient", isinstance(agent.make_client("gemini-3.5-flash", lambda e, **kw: None), agent.GeminiClient))

# 8d. model chain: a daily quota on one model moves the same conversation to the next
class Clock:
    def __init__(self): self.now = 1000.0; self.slept = []
    def time(self): return self.now
    def sleep(self, s): self.slept.append(s); self.now += s

clock = Clock()
real_time, real_sleep = agent.time.time, agent.time.sleep
agent.time.time, agent.time.sleep = clock.time, clock.sleep
seen_urls, seen_bodies = [], []
def chain_open(req, timeout=0):
    seen_urls.append(req.full_url.split("/models/")[1].split(":")[0])
    seen_bodies.append(req.data.decode())
    if seen_urls[-1] == "model-a":
        raise urllib.error.HTTPError(req.full_url, 429, "quota", {}, io.BytesIO(b'{"error":{"message":"requests per day limit exceeded"}}'))
    return Resp(json.dumps(response([fc("list_dir")])).encode())
agent.urllib.request.urlopen = chain_open
chain_log = []
chain = agent.GeminiClient("model-a, model-b", lambda e, **kw: chain_log.append((e, kw)))
signed = [{"role": "user", "parts": [{"text": "hi"}]}, {"role": "model", "parts": [{"functionCall": {"name": "list_dir", "args": {}}, "thoughtSignature": "SIG-A"}]}]
r, _ = chain.generate("sys", signed)
check("daily quota on the first model moves on to the second", seen_urls == ["model-a", "model-b"] and chain.last_model == "model-b", seen_urls)
check("the switch is logged with both model names", [(k["from_model"], k["to_model"]) for e, k in chain_log if e == "model_switch"] == [("model-a", "model-b")])
check("thought signatures are not sent to the next model", "SIG-A" in seen_bodies[0] and "SIG-A" not in seen_bodies[1])
check("the caller's history keeps its signatures", signed[1]["parts"][0]["thoughtSignature"] == "SIG-A")
chain.generate("sys", signed)
check("later requests stay on the new model", seen_urls[-1] == "model-b" and "model-a" not in seen_urls[2:])
# pacing: five requests per minute means at least 12 s between two requests to the same model
clock.slept.clear(); before = chain.waited
chain.generate("sys", signed)
check("requests to one model are paced to its per-minute limit", clock.slept and 12.0 <= sum(clock.slept) <= 13.5, clock.slept)
check("pacing time is counted as waiting", abs(chain.waited - before - sum(clock.slept)) < 1e-6)
fast = agent.GeminiClient("gemini-3.5-flash-lite", lambda e, **kw: None)
fast.generate("sys", signed); clock.slept.clear(); fast.generate("sys", signed)
check("a model with a higher limit waits less", clock.slept and 4.0 <= sum(clock.slept) <= 5.0, clock.slept)
# a large prompt is paced by tokens per minute: 125k tokens at 250k TPM means about 30 s
fast._last_tokens["gemini-3.5-flash-lite"] = 125_000
clock.slept.clear(); fast.generate("sys", signed)
check("a large prompt is paced by tokens per minute", clock.slept and 29.5 <= sum(clock.slept) <= 31.0, clock.slept)
check("prompt size is read from each response", fast._last_tokens["gemini-3.5-flash-lite"] == 1000)
# every model out of quota raises
agent.urllib.request.urlopen = lambda req, timeout=0: (_ for _ in ()).throw(urllib.error.HTTPError(req.full_url, 429, "q", {}, io.BytesIO(b'{"error":{"message":"requests per day limit exceeded"}}')))
allout = agent.GeminiClient("m1,m2", lambda e, **kw: None)
try:
    allout.generate("sys", signed)
    check("all models out of quota raises", False)
except agent.DailyQuotaError:
    check("all models out of quota raises", True)
agent.time.time, agent.time.sleep = real_time, real_sleep

# 8e. waiting on rate limits is not the agent's time, and the answering model is recorded
class Slow(Scripted):
    waited = 0.0
    last_model = "m-x"
    def generate(self, system, contents):
        self.waited += 1000.0       # pretend a long rate-limit wait happened before this answer
        return super().generate(system, contents)
d, res, ev = go("waited", Slow([response([fc("list_dir", path=".")])] * 2), max_calls=2, max_seconds=900)
check("a long rate-limit wait does not use up the time budget", res["outcome"] == "budget_exhausted", res)
check("result separates active and waited time", res["waited_seconds"] == 2000.0 and res["active_seconds"] < res["seconds"], res)
check("model_response records the answering model and result counts them", all(e["model"] == "m-x" for e in ev if e["event"] == "model_response") and res["models_used"] == {"m-x": 2}, res)

# 8f. LiveClient over a fake socket
class FakeWS:
    def __init__(self, replies):
        self.sent, self.replies, self.closed = [], list(replies), False
    def send(self, m): self.sent.append(json.loads(m))
    def recv(self, timeout=None):
        if not self.replies:
            raise TimeoutError("no reply")
        return json.dumps(self.replies.pop(0))
    def close(self): self.closed = True

tool_msg = lambda *calls: {"toolCall": {"functionCalls": [{"id": i, "name": n, "args": a} for i, n, a in calls]}, "usageMetadata": {"promptTokenCount": 1200, "totalTokenCount": 1300}}
ws1 = FakeWS([{"setupComplete": {}},
              {"serverContent": {"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm", "data": "AAAA"}}]}}},
              {"sessionResumptionUpdate": {"newHandle": "H-1", "resumable": True}},
              tool_msg(("i1", "list_dir", {"path": "."}), ("i2", "read_file", {"path": "src/a.py"})),
              {"serverContent": {"outputTranscription": {"text": "I will check."}}},
              {"goAway": {"timeLeft": "5s"}},
              {"serverContent": {"turnComplete": True}}])
ws2 = FakeWS([{"setupComplete": {}}, tool_msg(("i3", "search", {"regex": "x"}))])
sockets = [ws1, ws2]
agent.LiveClient.connect = lambda: sockets.pop(0)
clock2 = Clock()
agent.time.time, agent.time.sleep = clock2.time, clock2.sleep
live_log = []
lv = agent.make_client("gemini-3.8-live", lambda e, **kw: live_log.append(e))
check("model names with -live pick LiveClient", isinstance(lv, agent.LiveClient))
hist = [{"role": "user", "parts": [{"text": "bug report"}]}]
r1, _ = lv.generate("SYS", hist)
setup = ws1.sent[0]["setup"]
check("live setup asks for audio, transcription, our tools and the system prompt",
      setup["generationConfig"]["responseModalities"] == ["AUDIO"] and "outputAudioTranscription" in setup
      and len(setup["tools"][0]["functionDeclarations"]) == len(agent.SPECS) and setup["systemInstruction"]["parts"][0]["text"] == "SYS")
check("first turn is sent as client content", ws1.sent[1] == {"clientContent": {"turns": [{"role": "user", "parts": [{"text": "bug report"}]}], "turnComplete": True}})
p1 = r1["candidates"][0]["content"]["parts"]
check("live tool calls come back as functionCall parts with ids", [(x["functionCall"]["id"], x["functionCall"]["name"]) for x in p1] == [("i1", "list_dir"), ("i2", "read_file")], p1)
check("audio data is dropped", "AAAA" not in json.dumps(r1))
check("live usage is mapped", r1["usageMetadata"]["promptTokenCount"] == 1200)
check("resumption handle is kept", lv.handle == "H-1")
# loop appends the model turn and the tool results; only the results go out, matched by id
hist += [r1["candidates"][0]["content"], {"role": "user", "parts": [
    {"functionResponse": {"id": "i1", "name": "list_dir", "response": {"result": "a"}}},
    {"functionResponse": {"id": "i2", "name": "read_file", "response": {"result": "b"}}}]}]
clock2.slept.clear()
r2, _ = lv.generate("SYS", hist)
check("tool results go out as one toolResponse with the same ids",
      ws1.sent[2] == {"toolResponse": {"functionResponses": [{"id": "i1", "name": "list_dir", "response": {"result": "a"}},
                                                              {"id": "i2", "name": "read_file", "response": {"result": "b"}}]}}, ws1.sent[2:])
check("the model's own turn is not sent back", len(ws1.sent) == 3)
check("live sends are paced by tokens per minute", clock2.slept and 1.0 <= sum(clock2.slept) <= 2.0, clock2.slept)
check("a spoken answer becomes a text part with no calls", r2["candidates"][0]["content"]["parts"] == [{"text": "I will check."}])
# after goAway the next turn reconnects with the handle, then sends the nudge
hist += [r2["candidates"][0]["content"], {"role": "user", "parts": [{"text": agent.NUDGE}]}]
r3, _ = lv.generate("SYS", hist)
check("after goAway the session is resumed with the handle", ws1.closed and ws2.sent[0]["setup"]["sessionResumption"] == {"handle": "H-1"} and "live_resume" in live_log)
check("the nudge goes out as client content on the new socket", ws2.sent[1]["clientContent"]["turns"][0]["parts"][0]["text"] == agent.NUDGE)
check("calls after resume are returned", r3["candidates"][0]["content"]["parts"][0]["functionCall"]["id"] == "i3")
# a socket error ends the run as an API error, and a refused setup too
try:
    lv.generate("SYS", hist + [{"role": "user", "parts": [{"text": "more"}]}])
    check("socket errors become ApiError", False)
except agent.ApiError as e:
    check("socket errors become ApiError", "TimeoutError" in str(e))
agent.LiveClient.connect = lambda: FakeWS([{"error": "bad model"}])
try:
    agent.LiveClient("gemini-x-live", lambda e, **kw: None).generate("SYS", [{"role": "user", "parts": [{"text": "x"}]}])
    check("refused setup becomes ApiError", False)
except agent.ApiError as e:
    check("refused setup becomes ApiError", "setup failed" in str(e))
agent.LiveClient.connect = None
agent.time.time, agent.time.sleep = real_time, real_sleep

# 9. the key never reaches the saved files
key = os.environ["GEMINI_API_KEY"]
leak = [os.path.join(dp, f) for dp, _, fs in os.walk(RUNS) for f in fs if key.encode() in open(os.path.join(dp, f), "rb").read()]
check("api key not in any run file", not leak, leak)

for name in os.listdir(RUNS):
    rm(f"{ROOT}/.tmp/agent-{name}")
rm(RUNS)
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
