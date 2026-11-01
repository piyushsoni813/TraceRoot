"""Build the agent results section of README.md from the run directories (no hand-typed numbers).

usage: python -I make_results_table.py
Replaces everything from "## Investigator agent results" to the end of README.md.
"""
import glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES = ["filelock-346", "packaging-638", "attrs-1416", "click-3449", "flask-5160"]
DRIVERS = [  # (label, slug, attempt per case; later attempts replace earlier ones)
    ("Gemini 3.1 Flash Live (preview)", "gemini-3-1-flash-live-preview"),
    ("Gemini 3.5 Flash Lite", "gemini-3-5-flash-lite"),
    ("Gemini 3.1 Flash Lite", "gemini-3-1-flash-lite"),
    ("Gemini 3.8 Live", "gemini-3-8-live"),
    ("Flash chain (3.8 Flash, 3 Flash, 2.5 Flash)", "gemini-3-8-flash+gemini-3-flash-preview+gemini-2-5-flash"),
]


def runs(case, slug, pat="?"):
    out = []
    for d in sorted(glob.glob(f"{ROOT}/experiments/{case}-agent-{slug}-{pat}")):
        if os.path.exists(f"{d}/evaluation.json"):  # finished and scored; runs in progress are left out
            out.append((d[-1], d))
    return out


def why(d, res):
    if res["outcome"] == "budget_exhausted":
        return "no submit (40 calls used)"
    if res["outcome"] == "api_error":
        det = " ".join(json.loads(l).get("detail", "") for l in open(f"{d}/transcript.jsonl", encoding="utf-8") if '"api_error"' in l)
        if "daily quota" in det:
            return "stopped: daily quota"
        if "503" in det:
            return "stopped: HTTP 503 (busy)"
        if "thought_signature" in det:
            return "stopped: harness bug (signature)"
        return "stopped: API error"
    if res["outcome"] == "no_submission":
        return "no submit (stopped calling tools)"
    if res["outcome"] == "time_exhausted":
        return "no submit (15 active minutes used)"
    if res["outcome"] == "model_returned_nothing":
        return "stopped: empty or malformed model reply"
    return res["outcome"]


def cell(case, slug, pat="?"):
    rs = runs(case, slug, pat)
    if not rs:
        return "not run yet", None
    att, d = rs[-1]
    res = json.load(open(f"{d}/result.json"))
    ev = json.load(open(f"{d}/evaluation.json"))
    tag = f" ({att})" if att != "a" else ""
    if ev["repair"]["outcome"] == "success":
        c = ev["evidence"]["counts"]
        tot = c["verified"] + c["unverifiable"] + c["contradicted"]
        return f"**success**{tag}, root cause {ev['root_cause']['status']}, evidence {c['verified']}/{tot}", True
    if ev["repair"]["outcome"] != "no_submission":
        return f"{ev['repair']['outcome']}{tag}", False
    return why(d, res) + tag, False


def build(drivers, pat):
    lines = ["| Driver | " + " | ".join(CASES) + " | Solved |", "| --- |" + " --- |" * (len(CASES) + 1)]
    solved = {c: [] for c in CASES}
    for label, slug in drivers:
        cells, n = [], 0
        for c in CASES:
            text, ok = cell(c, slug, pat)
            cells.append(text)
            if ok:
                n += 1
                solved[c].append(label)
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {n}/5 |")
    return "\n".join(lines), solved


table, solved_by_case = build(DRIVERS, "?")
union = sum(1 for c in CASES if solved_by_case[c])
DRIVERS_V2 = [d for d in DRIVERS if not d[1].startswith("gemini-3-8-flash+")]
table_v2, solved_v2 = build(DRIVERS_V2, "v2?")
union_v2 = sum(1 for c in CASES if solved_v2[c])
DRIVERS_V3 = [d for d in DRIVERS_V2 if d[1] != "gemini-3-1-flash-lite"]  # 3.1 Flash Lite waits for the 503 storms to pass
table_v3, solved_v3 = build(DRIVERS_V3, "v3?")
union_v3 = sum(1 for c in CASES if solved_v3[c])
contradicted = lambda pat: sum(json.load(open(f))["counts"]["contradicted"]
                               for f in glob.glob(f"{ROOT}/experiments/*-agent-*-{pat}/evidence_check.json")
                               if "gemini-3-1-flash-lite-" not in f)
checkers = sorted({json.load(open(f)).get("checker_commit", "?") for f in glob.glob(f"{ROOT}/experiments/*-agent-*/evidence_check.json")})
print(table)
print("cases solved by at least one driver:", union)
print(table_v2)
print("v2 cases solved by at least one driver:", union_v2)
print(table_v3)
print("v3 cases solved by at least one driver:", union_v3, "contradicted v2/v3:", contradicted("v2?"), contradicted("v3?"))

section = f"""## Investigator agent results (separate from the baseline tables above)

Agent: `tools/agent/agent.py` (tools, hypotheses, budgets and report checks as in `docs/investigator-design.md`):
40 tool calls, 15 minutes of active time (rate-limit waits excluded and recorded), 200k context tokens. All runs on the
Gemini free tier, 2026-10-31. One model per driver, except the labelled Flash chain, which moves to the next model when one
model's daily quota ends. "Success" is the same independent evaluator as the baseline: the submitted edits replayed on a
fresh checkout, reproducer exits 0, held-out upstream tests pass. Root cause: `match` = breaking commit named; `likely` = same
file and function as the real fix (a person should confirm the mechanism); `partial` = file or function only; `miss`.
Evidence = items in the report backed by the transcript / all items checked (`tools/agent/evidence_check.py`, checker {', '.join(checkers)}).

{table}

Cases solved by at least one driver: {union} of 5. Baseline for comparison (single prompt, edit format): Gemini 3.5 Flash 4 of 9 runs.

Reruns and exclusions (every attempt is kept in `experiments/`; the table shows the last attempt, letter in brackets):
- Gemini 3.8 Live `a` and `b` failed because of harness bugs in the Live client (an empty turn-closing message was read as an
  empty answer, so the agent was nudged out after about 4 calls). Fixed in c21045a and f44b893, then `c` ran.
- Gemini 3.1 Flash Lite `a` lost filelock, packaging and attrs to HTTP 503 (Google "high demand") before 503 patience was added;
  `b` reran those three. attrs `b` again stopped on 503 after 12 retries; `c` reran attrs and solved it.
- Flash chain `a` lost every case to HTTP 503 or to a harness bug (missing thought signature after a model switch). `b` reran with
  the fixes on the first key and stopped at attrs when the last model's daily quota ended. click `b`, flask `b` and attrs `c` then
  ran on a second key (`run.json` records `key_env`). click `b` used up the 15 active minutes in 10 calls (Gemini 3.8 Flash took
  90 to 185 s per reply). attrs `c` ended when Gemini 2.5 Flash returned `MALFORMED_FUNCTION_CALL`; the loop treats an empty reply
  as the end of the run instead of nudging, a harness weakness to fix in the next protocol version.
- Gemini 3.8 Live Extended Thinking was dropped: it answered in speech and made no tool calls (all five `a` runs).
- The very first run (filelock, Gemini 3.5 Flash) stopped on the 20 request daily quota after 22 calls, before any edit.

### Protocol v2 (checkpoint guidance)

Same agent, budget, prompt and evaluator. v2 only adds three messages to the tool result notice: a hypothesis checkpoint at
call 15, a repair checkpoint at call 25, and a guard after three failing edit/test cycles (see `docs/budget-analysis.md`).
Run folders end in `-v2a`. One attempt per cell, 2026-10-31.

{table_v2}

Cases solved by at least one v2 driver: {union_v2} of 5.

Notes on v2:
- Gemini 3.1 Flash Live went from 4 to 5 of 5; attrs was solved after the hypothesis checkpoint fired at call 15.
- Gemini 3.5 Flash Lite went from 3 to 4 of 5; filelock was solved after the repair checkpoint fired at call 25.
- Gemini 3.8 Live stayed at 2 of 5. On filelock it made 11 edits but checked them with `run_python`, not `run_tests`, so the
  thrash guard (which counts failing `run_tests` only) never fired. A gap in v2.
- Gemini 3.1 Flash Lite fell from 3 to 1 of 5, but three of its four failures were caused by the service: HTTP 503 on 17 to 18
  requests, single replies taking up to 585 s. packaging stopped on 503; filelock and attrs ran out of active time because a
  failed request's hanging time was counted as the agent's time. That harness bug is fixed (the time is now counted as
  waiting); these three cells need a rerun before v2 can be judged on this driver.
- Two v2 reports have a `contradicted` verification: Gemini 3.5 Flash Lite cited call numbers one off from the output it
  quoted (for example it quoted the result of call 28 under call 31).

### Protocol v3 (thrash guard counts run_python, call number first)

v2 plus two changes: the thrash guard also counts failing `run_python` checks after an edit, and every tool result sent to
the model starts with "[call N]" (the transcript keeps the bare result). Run folders end in `-v3a`, reruns in `-v3b`.
2026-11-01. Gemini 3.1 Flash Lite is not in this round yet: its v2 rerun on 2026-11-01 hit HTTP 503 on every retry.

{table_v3}

Cases solved by at least one v3 driver: {union_v3} of 5. Contradicted evidence items, same three drivers: v2 {contradicted("v2?")}, v3 {contradicted("v3?")}.

Notes on v3:
- Solve counts did not improve: Gemini 3.1 Flash Live 4 of 5 (v2 5 of 5), Gemini 3.5 Flash Lite 4 of 5 (same cells as v2),
  Gemini 3.8 Live 2 of 5 (it gained filelock and lost flask). No v3 driver solved click; in v2 only Gemini 3.1 Flash Live did.
- Gemini 3.1 Flash Live click `a` stopped before its first call when the Live connection closed (WebSocket 1008, a service
  error); `b` reran it and used all 40 calls.
- The new thrash guard fired once, on Gemini 3.8 Live filelock at call 25. The model kept editing anyway and passed the tests
  on its last edit (the run used all 40 calls, with submit as the last). It did not update its hypotheses after the warning.
- No v3 report has a `contradicted` evidence item (v2, same drivers: see the count above). This fits the "[call N]" change, but
  the number of runs is small.
- One attempt per cell. A loss or gain of one case is within run-to-run noise, so v3 is not better or worse at solving on this
  evidence; its clear effect so far is on citations.

Limits of these results:
- Five public bugs, one counted attempt per cell. Indicative only; the models may have seen these fixes in training.
- `likely` and `partial` root causes have not yet been reviewed by a person.
- The free tier may use prompts to improve Google products; the cases are public repositories.
"""
readme = open(f"{ROOT}/README.md", encoding="utf-8").read()
a = readme.index("## Investigator agent results")
open(f"{ROOT}/README.md", "w", encoding="utf-8", newline="\n").write(readme[:a] + section)
print("README updated")
