"""Investigator agent loop: Gemini function calling over the sandbox tools.

usage: python -I agent.py <case_id> <run_dir> [model] [--max-calls=N] [--max-seconds=N]

model may be a comma separated chain (m1,m2,m3): when one model's daily quota ends the run continues on the next.
A model name containing '-live' uses the Live API (WebSocket, audio-only models; only tool calls are used).

A model name starting with 'local' uses llama-server on 127.0.0.1:8091 (free, for harness dry runs).

Writes to <run_dir>: transcript.jsonl (every model response and tool result, unedited),
run.json (frozen configuration and hashes), submission.json (if the agent submitted) and
result.json (outcome and cost). The API key is read from .env (GEMINI_API_KEY, or the variable named by
--key-env=NAME) and never logged; run.json records only the variable name.
"""
import hashlib, json, os, subprocess, sys, time, urllib.error, urllib.request, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sandbox import Sandbox, ROOT
from tools import Toolset, SPECS, TOOLS_HASH
import report as report_mod
import evidence_check

KEY_ENV = "GEMINI_API_KEY"  # which variable holds the key; change with --key-env=NAME


def load_env(path=None):
    """Read KEY=VALUE lines from the repo's .env into os.environ (the file wins over the shell).
    Returns the names it set. The file is gitignored and is not inside any sandbox mount."""
    path = path or os.path.join(ROOT, ".env")
    names = []
    if not os.path.exists(path):
        return names
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().removeprefix("export ").strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k:
            os.environ[k] = v
            names.append(k)
    return names


MAX_CALLS = 40
MAX_SECONDS = 15 * 60
MAX_CONTEXT_TOKENS = 200_000
MAX_NUDGES = 3
MAX_API_ATTEMPTS = 7
MAX_BUSY_ATTEMPTS = 12  # HTTP 503 'high demand': back off up to about 12 minutes, outside the agent's time
RETRY_CODES = {429, 500, 502, 503, 504}
GEN_CONFIG = {"temperature": 0, "topP": 1, "topK": 1, "maxOutputTokens": 16384}

SYSTEM_PROMPT = f"""You are a debugging agent. A Python project had a working feature that now fails: a recent change broke it. Find the root cause and make the smallest justified fix. A human will review your work, so be accurate and honest.

You work in a sandboxed copy of the repository at the faulty revision, with its git history. You cannot see anything after that revision and have no network. You can read code, search, use git history, run Python and run tests. Source files are under src/. You may edit only files under src/ and you must not edit tests.

Method:
1. Investigate: read the stack trace frames, the code around them and the recent history of those files (git_log, git_show, git_blame). Find which change introduced the problem if you can.
2. Hypothesize: use record_hypothesis for at least two competing explanations. For each, say what observation would confirm or rule it out.
3. Test: run a targeted check (run_python, run_tests, a read of the code) and then update_hypothesis with the result. Cite the numbers of the tool calls that gave the evidence. Do not mark a hypothesis supported without evidence from a tool call.
4. Repair: use apply_edit for the smallest change that fixes the cause, not the symptom. Do not add workarounds that hide the failure.
5. Verify: run the failing scenario and the related existing tests with run_tests after your last edit. If something fails, revise.
6. submit with your report.

Budget: at most {MAX_CALLS} tool calls in total (every call counts, including hypothesis and submit calls), {MAX_SECONDS // 60} minutes, and each tool output is cut at 20 KB. Each tool result ends with a line showing your remaining budget. If you run out before submitting, the run fails with no result, so leave enough calls to verify and submit. If you could not fully verify something, say so under limitations instead of claiming it.

Efficiency: each reply you send uses one request from a small daily allowance, so do not spend a reply on a single call when several are independent. Send independent calls together in one reply (for example read two files, or record both hypotheses). Calls that depend on an earlier result must wait for it. Every call still counts toward the {MAX_CALLS} call budget, and they run in the order you list them.

Always answer with a tool call."""

NUDGE = "Continue by calling a tool. When you are done, call submit."
MALFORMED_NUDGE = ("Your last function call could not be parsed ({reason}: {detail}). "
                   "Call the tool again with valid JSON arguments that match its declaration.")
RECOVERABLE_FINISH = {"MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL"}


def merge_roles(contents):
    """Join neighbouring turns of the same role; the REST API expects user and model turns to alternate."""
    out = []
    for c in contents:
        if out and out[-1].get("role") == c.get("role"):
            out[-1] = {"role": c.get("role"), "parts": out[-1].get("parts", []) + c.get("parts", [])}
        else:
            out.append(c)
    return out


class ApiError(Exception):
    pass


class DailyQuotaError(ApiError):
    pass


class ModelBusyError(ApiError):
    pass


# free-tier requests per minute (from https://ai.dev/rate-limit on 2026-10-31)
RPM = {"gemini-3.5-flash": 5, "gemini-3.6-flash": 5, "gemini-3.8-flash": 5, "gemini-3-flash-preview": 5,
       "gemini-2.5-flash": 5, "gemini-2.5-flash-lite": 10, "gemini-3.5-flash-lite": 15, "gemini-3.1-flash-lite": 15}
DEFAULT_RPM = 5
TPM = 250_000  # free-tier input tokens per minute, same for every text model listed
MAX_WALL_SECONDS = 60 * 60


DUMMY_SIGNATURE = "skip_thought_signature_validator"  # accepted by Gemini 3 for calls written by another model


def strip_signatures(contents):
    """Thought signatures belong to the model that wrote them. When another model takes over, function
    calls get the documented dummy signature (Gemini 3 rejects calls without one) and others lose theirs."""
    out = json.loads(json.dumps(contents))
    for c in out:
        for p in c.get("parts", []):
            if "functionCall" in p:
                p["thoughtSignature"] = DUMMY_SIGNATURE
            else:
                p.pop("thoughtSignature", None)
    return out


class GeminiClient:
    """Gemini over REST.

    `model` may be a comma separated chain. When a model's daily quota is used up the same
    conversation continues on the next one. Requests are paced to each model's per-minute limit.
    Time spent waiting (pacing and retry back-off) is added to `waited`, so the loop can keep
    it out of the agent's time budget.
    """
    def __init__(self, model, log):
        self.models = [m.strip() for m in model.split(",") if m.strip()]
        self.log = log
        self.idx, self.waited, self.strip = 0, 0.0, False
        self.last_model = self.models[0]
        self._last_request, self._last_tokens = {}, {}
        self.key = os.environ.get(KEY_ENV)
        if not self.key:
            raise SystemExit(f"{KEY_ENV} is not set (put it in .env)")

    def _sleep(self, seconds):
        if seconds > 0:
            time.sleep(seconds)
            self.waited += seconds

    def _pace(self, model):
        last = self._last_request.get(model)
        if last is not None:
            # wait for whichever is stricter: requests per minute, or tokens per minute for a prompt this size
            gap = max(60.0 / RPM.get(model, DEFAULT_RPM), 60.0 * self._last_tokens.get(model, 0) / TPM)
            self._sleep(last + gap + 0.5 - time.time())
        self._last_request[model] = time.time()

    def generate(self, system, contents):
        while True:
            model = self.models[self.idx]
            try:
                resp, attempt = self._request(model, system, strip_signatures(contents) if self.strip else contents)
                self.last_model = model
                return resp, attempt
            except (DailyQuotaError, ModelBusyError) as e:
                if self.idx + 1 >= len(self.models):
                    raise
                why = "daily quota" if isinstance(e, DailyQuotaError) else "busy (HTTP 503 after all retries)"
                self.log("model_switch", from_model=model, to_model=self.models[self.idx + 1], reason=why)
                self.idx += 1
                self.strip = True

    def _request(self, model, system, contents):
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": merge_roles(contents),
            "tools": [{"functionDeclarations": SPECS}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
            "generationConfig": GEN_CONFIG,
        }).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        attempt, busy = 0, 0
        while True:
            attempt += 1
            self._pace(model)
            req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": self.key})
            try:
                raw = urllib.request.urlopen(req, timeout=300).read()
                d = json.loads(raw)
                self._last_tokens[model] = (d.get("usageMetadata") or {}).get("promptTokenCount", 0)
                return d, attempt
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                if e.code == 429 and "per day" in detail:  # a daily quota will not clear by waiting
                    raise DailyQuotaError(f"HTTP 429 (daily quota, {model}): {detail}")
                if e.code == 503:
                    busy += 1
                    if busy >= MAX_BUSY_ATTEMPTS:
                        raise ModelBusyError(f"HTTP 503 ({model}) {busy} times: {detail}")
                    self.log("api_retry", attempt=attempt, status=e.code, model=model, detail=detail)
                    self._sleep(min(120, 2 ** busy))
                    continue
                if e.code in RETRY_CODES and attempt < MAX_API_ATTEMPTS:
                    self.log("api_retry", attempt=attempt, status=e.code, model=model, detail=detail)
                    self._sleep(min(60, 2 ** attempt))
                    continue
                raise ApiError(f"HTTP {e.code} ({model}): {detail}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < MAX_API_ATTEMPTS:
                    self.log("api_retry", attempt=attempt, status="network", model=model, detail=str(e)[:300])
                    self._sleep(min(60, 2 ** attempt))
                    continue
                raise ApiError(f"network: {e}")


class LocalClient:
    """llama-server (OpenAI-compatible) behind the same interface as GeminiClient.

    Takes and returns Gemini-shaped messages so the loop does not change. Used to exercise the
    whole harness for free; a small local model is not a meaningful driver for results.
    """
    URL = "http://127.0.0.1:8091/v1/chat/completions"
    ATTEMPTS = 3

    def __init__(self, model, log):
        self.model, self.log = model, log

    @staticmethod
    def _messages(system, contents):
        msgs = [{"role": "system", "content": system}]
        for c in contents:
            parts = c.get("parts", [])
            if c["role"] == "user":
                for p in parts:
                    if "functionResponse" in p:
                        fr = p["functionResponse"]
                        msgs.append({"role": "tool", "tool_call_id": fr["id"], "content": fr["response"]["result"]})
                text = "\n".join(p["text"] for p in parts if "text" in p)
                if text:
                    msgs.append({"role": "user", "content": text})
            else:
                calls = [p["functionCall"] for p in parts if "functionCall" in p]
                m = {"role": "assistant", "content": "".join(p.get("text", "") for p in parts if "text" in p) or None}
                if calls:
                    m["tool_calls"] = [{"id": fc["id"], "type": "function",
                                        "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args") or {})}} for fc in calls]
                msgs.append(m)
        return msgs

    def generate(self, system, contents):
        body = json.dumps({
            "messages": self._messages(system, contents), "temperature": 0, "top_k": 1, "max_tokens": 2048, "stream": False,
            "tools": [{"type": "function", "function": s} for s in SPECS], "tool_choice": "required"}).encode()
        for attempt in range(1, self.ATTEMPTS + 1):
            req = urllib.request.Request(self.URL, body, {"Content-Type": "application/json"})
            try:
                d = json.loads(urllib.request.urlopen(req, timeout=900).read())
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                if e.code in RETRY_CODES and attempt < self.ATTEMPTS:
                    self.log("api_retry", attempt=attempt, status=e.code, detail=detail)
                    time.sleep(2 * attempt)
                    continue
                raise ApiError(f"HTTP {e.code}: {detail}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < self.ATTEMPTS:
                    self.log("api_retry", attempt=attempt, status="network", detail=str(e)[:300])
                    time.sleep(2 * attempt)
                    continue
                raise ApiError(f"network: {e}")
        ch = (d.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        parts = [{"text": msg["content"]}] if msg.get("content") else []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            parts.append({"functionCall": {"id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}", "name": fn.get("name", ""), "args": args}})
        u = d.get("usage", {})
        return ({"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": ch.get("finish_reason")}] if parts else [],
                 "usageMetadata": {"promptTokenCount": u.get("prompt_tokens", 0), "totalTokenCount": u.get("total_tokens", 0)}}, attempt)


class LiveClient:
    """Gemini Live API (WebSocket) behind the same interface as GeminiClient.

    Live models only speak (AUDIO output), but they emit tool calls as structured messages, and
    the agent's work and its report all go through tool calls, so the audio is ignored and only
    its transcription is kept as text. One session per run: each generate() sends only what is
    new since the last call (tool results or a nudge). Free-tier limit is tokens per minute, so
    sends are paced by the size of the last prompt and the wait is counted in `waited`.
    The session is resumed with the latest handle when the server announces it will close.
    """
    URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    TPM = 65_000
    connect = None  # tests replace this with a factory returning a fake socket

    def __init__(self, model, log):
        self.model, self.log, self.last_model = model, log, model
        self.key = os.environ.get(KEY_ENV)
        if not self.key:
            raise SystemExit(f"{KEY_ENV} is not set (put it in .env)")
        self.ws, self.handle, self.reopen = None, None, False
        self.consumed, self.waited = 0, 0.0
        self._last_send, self._last_tokens = None, 0
        self._pending = []  # messages read early, handled first by the next _read
        self._turn_open = False  # a tool call was returned and its turn has not been closed yet
        self.system = ""

    def _socket(self):
        if LiveClient.connect:
            return LiveClient.connect()
        from websockets.sync.client import connect
        return connect(self.URL, additional_headers={"x-goog-api-key": self.key}, max_size=None, open_timeout=30)

    def _open(self):
        self.ws = self._socket()
        gen = {"responseModalities": ["AUDIO"], "temperature": 0, "topP": 1, "topK": 1}
        if "extended-thinking" in self.model:
            gen["thinkingConfig"] = {"thinkingLevel": "high"}
        self.ws.send(json.dumps({"setup": {
            "model": f"models/{self.model}", "generationConfig": gen, "outputAudioTranscription": {},
            "systemInstruction": {"parts": [{"text": self.system}]}, "tools": [{"functionDeclarations": SPECS}],
            "sessionResumption": {"handle": self.handle} if self.handle else {}}}))
        first = json.loads(self.ws.recv(timeout=60))
        if "setupComplete" not in first:
            raise ApiError(f"live setup failed ({self.model}): {json.dumps(first)[:300]}")

    def _send(self, msg):
        if self._last_send is not None:
            wait = self._last_send + 60.0 * self._last_tokens / self.TPM + 0.5 - time.time()
            if wait > 0:
                time.sleep(wait)
                self.waited += wait
        self.ws.send(json.dumps(msg))
        self._last_send = time.time()

    def _next(self, timeout):
        return self._pending.pop(0) if self._pending else json.loads(self.ws.recv(timeout=timeout))

    def _drain_turn_end(self, usage):
        """Some Live models close the tool-call turn with a separate, empty turnComplete. Read it now so the
        next turn does not mistake it for an empty answer; anything else is kept for the next turn."""
        try:
            m = json.loads(self.ws.recv(timeout=1.0))
        except TimeoutError:
            return usage
        sc = m.get("serverContent") or {}
        if sc.get("turnComplete") and not sc.get("modelTurn") and not sc.get("outputTranscription") and set(m) <= {"serverContent", "usageMetadata"}:
            return m.get("usageMetadata") or usage
        self._pending.append(m)
        return usage

    @staticmethod
    def _shape(m):
        """Message type summary for the transcript (no content, no audio)."""
        sc = m.get("serverContent") or {}
        return "+".join(sorted(k for k in m if k != "serverContent")) + ("|" + "+".join(sorted(sc)) if sc else "")

    def _read(self):
        texts, calls, usage, shapes = [], [], {}, []
        while True:
            m = self._next(300)
            shapes.append(self._shape(m))
            upd = m.get("sessionResumptionUpdate") or {}
            if upd.get("resumable") and upd.get("newHandle"):
                self.handle = upd["newHandle"]
            if "goAway" in m:
                self.reopen = True
            if m.get("usageMetadata"):
                usage = m["usageMetadata"]
            if "toolCall" in m:
                calls = m["toolCall"].get("functionCalls", [])
                self._turn_open = True
                break
            sc = m.get("serverContent") or {}
            if (sc.get("outputTranscription") or {}).get("text"):
                texts.append(sc["outputTranscription"]["text"])
            texts += [p["text"] for p in (sc.get("modelTurn") or {}).get("parts", []) if "text" in p]
            if sc.get("modelTurn") or texts:
                self._turn_open = False  # the model has started a new answer
            if sc.get("turnComplete"):
                if self._turn_open and not texts:
                    self._turn_open = False  # this closes the previous tool-call turn, not a new empty answer
                    continue
                break
        self.log("live_read", shapes=shapes)
        self._last_tokens = usage.get("promptTokenCount", 0)
        parts = ([{"text": "".join(texts)}] if texts else []) + [
            {"functionCall": {"id": c.get("id"), "name": c.get("name", ""), "args": c.get("args") or {}}} for c in calls]
        return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "TOOL_CALL" if calls else "STOP"}],
                "usageMetadata": {"promptTokenCount": usage.get("promptTokenCount", 0), "totalTokenCount": usage.get("totalTokenCount", 0)}}

    def generate(self, system, contents):
        self.system = system
        msgs = []
        for c in contents[self.consumed:]:
            if c.get("role") == "model":
                continue  # the model's own turn is already in the session
            parts = c.get("parts", [])
            frs = [p["functionResponse"] for p in parts if "functionResponse" in p]
            if frs:
                msgs.append({"toolResponse": {"functionResponses": [
                    {"id": f.get("id"), "name": f["name"], "response": f["response"]} for f in frs]}})
            text = "\n".join(p["text"] for p in parts if "text" in p)
            if text:
                msgs.append({"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}})
        self.consumed = len(contents)
        try:
            if self.reopen and self.ws is not None:
                self.log("live_resume", handle_present=bool(self.handle))
                self.close()
                self.reopen = False
            if self.ws is None:
                self._open()
            for m in msgs:
                self._send(m)
            return self._read(), 1
        except ApiError:
            raise
        except Exception as e:  # closed socket, timeout, bad frame: the run ends with api_error
            raise ApiError(f"live ({self.model}): {type(e).__name__}: {str(e)[:300]}")

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None


def make_client(model, log):
    if model.startswith("local"):
        return LocalClient(model, log)
    if "-live" in model:
        return LiveClient(model, log)
    return GeminiClient(model, log)


def code_commit():
    """The git commit of the harness, with '+dirty' if tools/agent has uncommitted changes."""
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", "tools/agent", "tools/sandbox"],
                           capture_output=True, text=True).stdout.strip()
    return head + ("+dirty" if dirty else "")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(case, run_dir, model, client_factory=make_client, max_calls=MAX_CALLS, max_seconds=MAX_SECONDS):
    os.makedirs(run_dir)  # refuses to overwrite an existing run
    case_dir = f"{ROOT}/cases/{case}"
    report_md = open(f"{case_dir}/report.md", encoding="utf-8").read()
    stack = open(f"{case_dir}/stacktrace.txt", encoding="utf-8").read()
    user_text = f"## Bug report\n\n{report_md}\n\n## Stack trace\n\n{stack}"
    t0 = time.time()
    tlog = open(f"{run_dir}/transcript.jsonl", "w", encoding="utf-8", newline="\n")

    def log(event, **kw):
        tlog.write(json.dumps({"t": round(time.time() - t0, 2), "event": event, **kw}, ensure_ascii=False) + "\n")
        tlog.flush()

    cfg = {"case_id": case, "model": model, "tools_hash": TOOLS_HASH, "system_prompt_sha256": sha(SYSTEM_PROMPT),
           "user_prompt_sha256": sha(user_text), "gen_config": GEN_CONFIG,
           "limits": {"tool_calls": max_calls, "active_seconds": max_seconds, "wall_seconds": MAX_WALL_SECONDS,
                      "context_tokens": MAX_CONTEXT_TOKENS, "note": "time spent waiting on rate limits is excluded from active_seconds"},
           "sandbox_image": "traceroot-sandbox:1", "code_commit": code_commit(), "key_env": KEY_ENV}
    json.dump(cfg, open(f"{run_dir}/run.json", "w"), indent=2)
    log("run_start", config=cfg, system_prompt=SYSTEM_PROMPT, user_prompt=user_text)

    client = client_factory(model, log)
    active = lambda: time.time() - t0 - getattr(client, "waited", 0.0)  # rate-limit waits are not the agent's time
    models_used = {}
    contents = [{"role": "user", "parts": [{"text": user_text}]}]
    outcome, nudges, total_tokens, last_ctx, model_calls = None, 0, 0, 0, 0
    workdir = f"{ROOT}/.tmp/agent-{os.path.basename(os.path.normpath(run_dir))}"
    with Sandbox(case, workdir) as sb:
        ts = Toolset(sb)
        try:
            while outcome is None:
                if active() > max_seconds or time.time() - t0 > MAX_WALL_SECONDS:
                    outcome = "time_exhausted"
                    break
                resp, attempt = client.generate(SYSTEM_PROMPT, contents)
                model_calls += 1
                usage = resp.get("usageMetadata", {})
                last_ctx = usage.get("promptTokenCount", 0)
                total_tokens += usage.get("totalTokenCount", 0)
                answered_by = getattr(client, "last_model", model)
                models_used[answered_by] = models_used.get(answered_by, 0) + 1
                log("model_response", attempt=attempt, model=answered_by, response=resp)
                cands = resp.get("candidates") or []
                if not cands or "content" not in cands[0]:
                    reason = cands[0].get("finishReason") if cands else None
                    if reason in RECOVERABLE_FINISH and nudges < MAX_NUDGES:
                        # a broken call is the model's slip, not the end of the run: say so and ask again
                        nudges += 1
                        detail = (cands[0].get("finishMessage") or "")[:300]
                        log("nudge", n=nudges, finish_reason=reason, detail=detail)
                        contents.append({"role": "user", "parts": [{"text": MALFORMED_NUDGE.format(reason=reason, detail=detail or "no detail")}]})
                        continue
                    outcome = "model_returned_nothing"
                    break
                content = cands[0]["content"]
                content.setdefault("role", "model")
                contents.append(content)  # kept as returned, including any thought signatures
                calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
                if not calls:
                    nudges += 1
                    log("nudge", n=nudges, finish_reason=cands[0].get("finishReason"))
                    if nudges > MAX_NUDGES:
                        outcome = "no_submission"
                        break
                    contents.append({"role": "user", "parts": [{"text": NUDGE}]})
                    continue
                replies = []
                for fc in calls:
                    if ts.n_calls >= max_calls:
                        replies.append({"functionResponse": dict({"name": fc["name"], "response": {"result": "error: tool call budget exhausted"}}, **({"id": fc["id"]} if fc.get("id") else {}))})
                        continue
                    t_call = time.time()
                    result = ts.call(fc["name"], fc.get("args"))
                    left = max_calls - ts.n_calls
                    mins = max(0, (max_seconds - active()) / 60)
                    notice = f"[tool call {ts.n_calls} of {max_calls} used, {left} left, {mins:.0f} min left]"
                    log("tool_call", n=ts.n_calls, name=fc["name"], args=fc.get("args"), result=result, notice=notice,
                        seconds=round(time.time() - t_call, 2))
                    fr = {"name": fc["name"], "response": {"result": f"{result}\n{notice}"}}
                    if fc.get("id"):
                        fr["id"] = fc["id"]
                    replies.append({"functionResponse": fr})
                    if ts.submission:
                        break
                contents.append({"role": "user", "parts": replies})
                if ts.submission:
                    outcome = "submitted"
                elif ts.n_calls >= max_calls:
                    outcome = "budget_exhausted"
                elif last_ctx > MAX_CONTEXT_TOKENS:
                    outcome = "context_exhausted"
        except ApiError as e:
            outcome = "api_error"
            log("api_error", detail=str(e))
        getattr(client, "close", lambda: None)()
        if ts.submission:
            sub = dict(ts.submission, decision="ready for human review")
            json.dump(sub, open(f"{run_dir}/submission.json", "w"), indent=2)
        # copy the final workspace diff for the reviewer
        diff = sb.exec(["git", "diff", "--", "src"])[1]
        open(f"{run_dir}/workspace.patch", "w", encoding="utf-8", newline="\n").write(diff)
        n_calls = ts.n_calls
    result = {"outcome": outcome, "tool_calls": n_calls, "model_calls": model_calls,
              "seconds": round(time.time() - t0, 1), "active_seconds": round(active(), 1),
              "waited_seconds": round(getattr(client, "waited", 0.0), 1), "models_used": models_used,
              "total_tokens": total_tokens, "last_context_tokens": last_ctx}
    json.dump(result, open(f"{run_dir}/result.json", "w"), indent=2)  # report.py reads this
    if outcome == "submitted":
        errors = report_mod.write(run_dir)
        result["report_valid"], result["report_errors"] = not errors, errors
        if os.path.exists(f"{run_dir}/report.json"):
            ec = evidence_check.check(run_dir)
            result["evidence_passed"], result["evidence_counts"] = ec["passed"], ec["counts"]
    log("run_end", **result)
    json.dump(result, open(f"{run_dir}/result.json", "w"), indent=2)
    tlog.close()
    return result


if __name__ == "__main__":
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    load_env()
    KEY_ENV = opts.get("key-env", KEY_ENV)
    case, run_dir = pos[0], pos[1]
    model = pos[2] if len(pos) > 2 else "gemini-3.5-flash"
    print(json.dumps(run(case, run_dir, model, max_calls=int(opts.get("max-calls", MAX_CALLS)),
                         max_seconds=int(opts.get("max-seconds", MAX_SECONDS))), indent=2))
