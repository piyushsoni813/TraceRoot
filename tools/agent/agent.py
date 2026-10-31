"""Investigator agent loop: Gemini function calling over the sandbox tools.

usage: python -I agent.py <case_id> <run_dir> [model]

Writes to <run_dir>: transcript.jsonl (every model response and tool result, unedited),
run.json (frozen configuration and hashes), submission.json (if the agent submitted) and
result.json (outcome and cost). The API key is read from GEMINI_API_KEY and never logged.
"""
import hashlib, json, os, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sandbox import Sandbox, ROOT
from tools import Toolset, SPECS, TOOLS_HASH

MAX_CALLS = 40
MAX_SECONDS = 15 * 60
MAX_CONTEXT_TOKENS = 200_000
MAX_NUDGES = 3
MAX_API_ATTEMPTS = 7
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

Always answer with a tool call."""

NUDGE = "Continue by calling a tool. When you are done, call submit."


class ApiError(Exception):
    pass


class GeminiClient:
    def __init__(self, model, log):
        self.model, self.log = model, log
        self.key = os.environ.get("GEMINI_API_KEY")
        if not self.key:
            raise SystemExit("GEMINI_API_KEY is not set")

    def generate(self, system, contents):
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": SPECS}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
            "generationConfig": GEN_CONFIG,
        }).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        for attempt in range(1, MAX_API_ATTEMPTS + 1):
            req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": self.key})
            try:
                raw = urllib.request.urlopen(req, timeout=300).read()
                return json.loads(raw), attempt
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                if e.code == 429 and "per day" in detail:  # a daily quota will not clear by waiting
                    raise ApiError(f"HTTP 429 (daily quota): {detail}")
                if e.code in RETRY_CODES and attempt < MAX_API_ATTEMPTS:
                    self.log("api_retry", attempt=attempt, status=e.code, detail=detail)
                    time.sleep(min(60, 2 ** attempt))
                    continue
                raise ApiError(f"HTTP {e.code}: {detail}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < MAX_API_ATTEMPTS:
                    self.log("api_retry", attempt=attempt, status="network", detail=str(e)[:300])
                    time.sleep(min(60, 2 ** attempt))
                    continue
                raise ApiError(f"network: {e}")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(case, run_dir, model, client_factory=GeminiClient, max_calls=MAX_CALLS, max_seconds=MAX_SECONDS):
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
           "limits": {"tool_calls": max_calls, "seconds": max_seconds, "context_tokens": MAX_CONTEXT_TOKENS},
           "sandbox_image": "traceroot-sandbox:1"}
    json.dump(cfg, open(f"{run_dir}/run.json", "w"), indent=2)
    log("run_start", config=cfg, system_prompt=SYSTEM_PROMPT, user_prompt=user_text)

    client = client_factory(model, log)
    contents = [{"role": "user", "parts": [{"text": user_text}]}]
    outcome, nudges, total_tokens, last_ctx, model_calls = None, 0, 0, 0, 0
    workdir = f"{ROOT}/.tmp/agent-{os.path.basename(os.path.normpath(run_dir))}"
    with Sandbox(case, workdir) as sb:
        ts = Toolset(sb)
        try:
            while outcome is None:
                if time.time() - t0 > max_seconds:
                    outcome = "time_exhausted"
                    break
                resp, attempt = client.generate(SYSTEM_PROMPT, contents)
                model_calls += 1
                usage = resp.get("usageMetadata", {})
                last_ctx = usage.get("promptTokenCount", 0)
                total_tokens += usage.get("totalTokenCount", 0)
                log("model_response", attempt=attempt, response=resp)
                cands = resp.get("candidates") or []
                if not cands or "content" not in cands[0]:
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
                        replies.append({"functionResponse": {"name": fc["name"], "response": {"result": "error: tool call budget exhausted"}}})
                        continue
                    t_call = time.time()
                    result = ts.call(fc["name"], fc.get("args"))
                    left = max_calls - ts.n_calls
                    mins = max(0, (max_seconds - (time.time() - t0)) / 60)
                    notice = f"[tool call {ts.n_calls} of {max_calls} used, {left} left, {mins:.0f} min left]"
                    log("tool_call", n=ts.n_calls, name=fc["name"], args=fc.get("args"), result=result, notice=notice,
                        seconds=round(time.time() - t_call, 2))
                    replies.append({"functionResponse": {"name": fc["name"], "response": {"result": f"{result}\n{notice}"}}})
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
        if ts.submission:
            sub = dict(ts.submission, decision="ready for human review")
            json.dump(sub, open(f"{run_dir}/submission.json", "w"), indent=2)
        # copy the final workspace diff for the reviewer
        diff = sb.exec(["git", "diff", "--", "src"])[1]
        open(f"{run_dir}/workspace.patch", "w", encoding="utf-8", newline="\n").write(diff)
        n_calls = ts.n_calls
    result = {"outcome": outcome, "tool_calls": n_calls, "model_calls": model_calls,
              "seconds": round(time.time() - t0, 1), "total_tokens": total_tokens, "last_context_tokens": last_ctx}
    log("run_end", **result)
    json.dump(result, open(f"{run_dir}/result.json", "w"), indent=2)
    tlog.close()
    return result


if __name__ == "__main__":
    case, run_dir = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "gemini-3.5-flash"
    print(json.dumps(run(case, run_dir, model), indent=2))
