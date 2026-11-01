# TraceRoot progress snapshot (2026-10-24)

## End goal (from the project owner)
Given a Python regression (a change broke a working feature and a test fails), TraceRoot should
investigate with repo, traces, tests and Git history; find the root cause through competing
hypotheses and diagnostic checks; apply the smallest justified fix; verify in isolation and reject
patches that break behavior; and deliver an auditable report (patch, root cause, evidence, test
results, limitations) for human review. No automatic merge or deploy.

## Done
1. Baseline protocol with frozen inputs, SHA-256 hashes, hidden reference fix, independent checker.
2. Five admitted regression cases in `cases/`: flask-5160, attrs-1416, packaging-638,
   filelock-346, click-3449. Each validated on the faulty and fixed revisions with a reproducer
   and targeted tests; breaking commits found with `git bisect run` for the four newer cases.
3. Two output protocols, kept separate:
   - Diff format (original): all four runs failed at `git apply` (Qwen3-8B v2, v3; Gemini 3.5 Flash a, b).
     v1 is invalid (response lost before saving).
   - Edit format (`experiments/PROTOCOL_EDIT_FORMAT.md`): results table in `README.md`.
     Qwen3-8B 0 successes; Gemini 3.5 Flash 4 successes of 9 valid runs (3 of 4 with source excerpt, 1 of 5 without).
4. Runner self-tested: the real fix converted to edit format scores `success` on all four newer cases.
5. Design draft for the investigator agent: `docs/investigator-design.md` (not built).
6. Cleanup: deleted `.tmp` contents, `.downloads`, `.pip-cache`. Nothing else removed.

## Key files
- `README.md`: layout, rules, results tables.
- `docs/benchmark-candidate-research.md`: candidate screening, admission evidence.
- `docs/investigator-design.md`: agent design awaiting decisions.
- `experiments/<case>-edit-<model>-<a|b>[-cap64k]/`: prompt, inputs, raw output, `evaluation.json`, `run.json`.
- `tools/scripts/`: `run_edit_experiment.py`, `make_case_runs.py`, `admit_case.py`.
- `cases/<id>/`: `metadata.json`, `report.md`, `stacktrace.txt`, `reference/`, `upstream/`.

## How to resume
- Local model: `tools/llama.cpp/llama-server.exe -m "D:\New folder\Qwen3-8B-Q4_K_M.gguf" -ngl 99 -c 8192 --host 127.0.0.1 --port 8091 --jinja --reasoning-budget 0`
- Gemini: key is stored as the user environment variable `GEMINI_API_KEY` (set with `setx`; a shell started before it was set may not see it). Model used: `gemini-3.5-flash` (Pro had no quota on this key). Groq key was mentioned but never set or used.
- Run one experiment: `.venv\Scripts\python.exe -I tools\scripts\run_edit_experiment.py <run_dir> <local|gemini> [model]`
- `.tmp/` must exist (empty is fine). The runner recreates its checkouts there.
- Python 3.13.7 venv in `.venv` (pytest 7.3.1 pinned; hypothesis, pretend, pytest-mock, pytest-timeout, pyparsing added).

## Decisions (confirmed 2026-10-31)
1. Driver model: Gemini 3.5 Flash.
2. Sandbox: Docker.
3. Per-run budget: 40 tool calls, 15 minutes, 200k tokens.
   - Guideline split: understand 6, investigate 12, hypothesis checks 10, fix 5, verify 5, margin 2.
   - Hard limit is the total of 40. Verify calls are reserved, so no patch ships untested.
   - Tools: read_file, search, run_tests, run_cmd, git, apply_edit.

## Agent build status
- Step 1 done: Docker image `traceroot-sandbox:1` (`tools/sandbox/`). Python 3.13.7, pinned deps, git, non-root user.
  Run with `--network none`, workspace mounted at `/work`, `PYTHONPATH=/work/src:/work`, pytest `-W ignore::DeprecationWarning`.
  On Windows Git Bash set `MSYS_NO_PATHCONV=1`. Checked on flask-5160: git works, no network, reproducer exits 1 at the faulty revision.
- Step 2 done: `tools/scripts/build_sandbox_repo.py <case_id> <dest>` builds the workspace at the faulty revision.
  Leaves only branch `main`, no remote, tags, reflogs or unreachable objects. Self-checks that the fix is absent from
  `git log --all` and the object store, and that the breaking commit stays visible. Passes on all five cases.
- Step 3 done: `tools/agent/sandbox.py` (one container per run, `docker exec`, no shell) and `tools/agent/tools.py`
  (list_dir, read_file, search, git_log/show/blame, run_python, run_tests, submit; 20 KB output cap; paths relative, no `..`;
  submit only under `src/`, each search must match once). `tools/agent/selftest_tools.py <case>` passes on all five cases.
  The builder now also writes `shim_files` from `env.json` (filelock needs a generated version.py).
  Image has a `less` stub (cat): a missing pager killed pytest silently on click's pager tests.
- Step 4 done: `record_hypothesis` and `update_hypothesis` in `tools/agent/tools.py`. Tool calls are numbered from 1;
  evidence must cite earlier call numbers (not the current or a future one). `submit` is refused until there are at least
  two hypotheses, none left open, and at least one supported. The submission carries the hypotheses. Tools hash is now `ffeb20f0...`.
- Step 5 and 6 done: `tools/agent/agent.py <case> <run_dir> [model]`. Gemini function calling (mode ANY), raw model content
  (thought signatures) echoed back, budgets 40 calls / 15 min / 200k context tokens, each tool result ends with a budget line,
  retry with identical request on 429/5xx/network (every retry logged), daily-quota 429 fails fast. Writes `transcript.jsonl`
  (every model response and tool result), `run.json` (hashes), `submission.json`, `workspace.patch`, `result.json`.
  Added tool `apply_edit` (edits the workspace so the fix can be tested); `submit(report)` now needs: 2+ hypotheses resolved with one
  supported, an edit, a run_tests after the last edit, and a workspace that equals HEAD plus the recorded edits only.
  Self-tests: `tools/agent/selftest_tools.py <case>` and `selftest_agent.py` (scripted fake model, no API), both pass.
- Real smoke run (filelock-346): API accepted the tool schema and the agent ran 18 calls, then stopped on HTTP 429.
  Cause: Gemini FREE TIER allows 20 requests per day per model. A run needs up to ~40 requests, so free tier is not enough.
  Smoke run output was deleted (incomplete). **Blocker: need a paid key or billing on the project before real runs.**
- Step 7 done: `tools/agent/report.schema.json` (JSON Schema subset) and `tools/agent/report.py`. After a submitted run the loop writes
  `report.json`, `report.md` and `report_validation.json`. Fields: root_cause, hypotheses (each with prediction, status, evidence,
  cited calls), evidence (cited calls resolved to tool, args and a 400 char excerpt from the transcript), patch (edits and diff),
  verification, limitations, decision (always "ready for human review"). Structure only: it checks every cited call exists.
  Whether the output supports the claim is step 8.
- Step 9 done: `tools/agent/score.py <run_dir>` writes `evaluation.json`. Repair uses the same evaluator and outcome names as the
  baseline (replays the submitted edits on a fresh checkout, reproducer must exit 0, held-out upstream tests at the fixed revision).
  Root cause is compared with the real fix by script: `match` (breaking commit), `likely` (file and function, needs a person),
  `partial`, `miss`. Evidence slot stays null until step 8. Cost is copied from result.json. `selftest_score.py` (76 checks, no API):
  the real fix scores success on all five cases, no-op, wrong scope, traversal, bad search and a fix that breaks other behaviour fail correctly.
  Git clones now pin `core.autocrlf=false` so multi-line search text matches on Windows.
- Step 8 done: `tools/agent/evidence_check.py <run_dir>` writes `evidence_check.json` (runs automatically after a report is built;
  `score.py` carries it into `evaluation.json`). Items are verified / unverifiable / contradicted. Checks: hypothesis citations (call exists,
  came before the update, is an evidence tool, no error), verification steps (a run_tests/run_python after the last edit, command matches,
  claimed counts and pass/fail agree with the real output), file:line citations (the line was actually shown), commit hashes (seen in a git
  output), inline `code` quotes (seen in the transcript or bug report), root cause file opened, patch equals the apply_edit calls and the saved diff.
  A run passes only with zero unverifiable and zero contradicted items. It cannot judge whether an argument is sound.
  `selftest_evidence.py`: 26 checks on hand-built transcripts, no API.
- Decision (2026-10-31): stay on the Gemini FREE tier, no billing. Limit is 20 requests per day per model, so real runs
  must be planned around that (see the run plan in the next session note).

- Free dry run done (2026-10-31): `agent.py` accepts a model name starting with `local` (llama-server on 127.0.0.1:8091, `LocalClient`
  converts to and from the Gemini-shaped messages). Started with `-ngl 22 -c 16384 -fa on -ctk q8_0 -ctv q8_0` (6 GB GPU).
  Qwen3-8B on filelock-346, 15 calls: tool calling works through the harness, budget stops correctly, all files written, scores `no_submission`.
  It repeated the same git_show three times, so read-only repeats now get a note (identical to call N). It never submitted; a small local model is for harness tests only.
- `selftest_e2e.py <case>` (no API): a scripted model makes the real fix in a real Docker sandbox, then report, evidence check and scoring run.
  19 checks per case, all pass on all five cases: success, root cause `match`, evidence all verified.
- `TOOLS_HASH` now covers the tool source code as well as the declarations.
- CLI options for short runs: `--max-calls=N --max-seconds=N`.
- FROZEN before the first real run (2026-10-31): the system prompt now has an Efficiency paragraph asking the model to send independent calls
  together in one reply (needed because the smoke run used one request per call and the free tier allows 20 requests/day). Not to be changed after results are seen.
- First real run (2026-10-31, filelock-346, `experiments/filelock-346-agent-gemini-3-5-flash-a`): ended `api_error` on the DAILY free-tier
  quota (20 requests) after 16 successful requests and 22 tool calls (batching worked: 1.4 calls per request), no edit made, `no_submission`.
  Conclusion: one run needs more than 20 requests (the agent was still investigating at request 16), so the free tier cannot finish a run in one day.
  Failed 503 attempts may also count against the quota. The run is kept and not repeated.
- Free-tier quotas seen on https://ai.dev/rate-limit (2026-10-31): Flash models (3.5/3.6, 3, 3.8, 2.5) 5 RPM and 20 RPD each;
  Flash Lite models (gemini-3.5-flash-lite, gemini-3.1-flash-lite) 15 RPM and 500 RPD; Pro models 0 on free tier.
- Agent client now supports a comma separated model chain (switches model on a daily quota, strips thought signatures on switch,
  logs `model_switch`), paces requests to each model's RPM, and keeps rate-limit waits out of the 15 minute budget
  (`active_seconds`; `seconds` is wall time; hard wall cap 60 min). `result.json` records `models_used`.
- Decision: real runs use ONE model for the whole run, `gemini-3.5-flash-lite` (500 RPD makes complete runs possible).
  The chain is available but mixes models inside a run, so it is not used for the main results.
- Live API models (no daily request limit, 65K tokens/min on free tier): `gemini-3.8-live`, `gemini-3.1-flash-live-preview`,
  `gemini-3.8-live-extended-thinking`. They only output AUDIO but emit tool calls as structured messages, which is all the agent needs.
  `LiveClient` (model name containing `-live`) keeps one WebSocket session per run, sends only new tool results, drops audio, keeps the
  transcription as text, paces by tokens per minute and resumes the session on goAway. Needs `websockets` in `.venv` (installed 17.4).
  Probe: 3.8-live and 3.1-flash-live-preview made parallel tool calls; extended-thinking spoke instead (nudges handle that).
- Drivers started 2026-10-31, each as its own column (one model per run, except the labelled Flash chain):
  gemini-3.5-flash-lite, gemini-3.1-flash-lite, Flash chain (3.8, 3, 2.5 Flash), gemini-3.8-live, gemini-3.1-flash-live-preview,
  gemini-3.8-live-extended-thinking.
- Step 10 runs done for today (2026-10-31). Results table is in README.md ("Investigator agent results"), generated from the
  run directories. Solved (independent evaluator): 3.1 Flash Live 4/5, 3.5 Flash Lite 3/5, 3.1 Flash Lite 2/5, 3.8 Live 2/5,
  Flash chain 2/5 (2 of 3 attempted). All five cases solved by at least one driver. flask root cause `match` for 3.1 Flash Live and 3.8 Live.
  All runs were re-scored with evidence checker a7f25b9 (two false positives fixed); raw outputs untouched.
- Open: Flash chain click and flask (and attrs) need the next daily quota; a person should review `likely`/`partial` root causes;
  3.1 Flash Lite attrs lost twice to HTTP 503.
- Round 1 finished (2026-10-31). Final solved counts: 3.1 Flash Live 4/5, 3.5 Flash Lite 3/5, 3.1 Flash Lite 3/5, Flash chain 3/5,
  3.8 Live 2/5; every case solved by at least one driver. Table generated by `tools/scripts/make_results_table.py`.
  Keys live in a gitignored `.env` (GEMINI_API_KEY, GEMINI_API_KEY_2); Flash chain click/flask `b` and attrs `c` used key 2.
- Fixed after round 1: an empty reply with finishReason MALFORMED_FUNCTION_CALL (or UNEXPECTED_TOOL_CALL) used to end the run
  (`model_returned_nothing`). It is now nudged with the reason, within the same 3-nudge limit, and the REST client merges
  neighbouring same-role turns. Round 1 runs were made before this change; runs after it record the newer `code_commit`.
- Root cause review (2026-10-31): `docs/root-cause-review.md` (generated) has the real fix next to each of the 15 successful runs.
  AI pre-review in `docs/root-cause-review-ai.json`: 10 correct, 5 partly, 0 wrong (filelock x2 and packaging chain name the wrong
  breaking commit; attrs 3.5 Flash Lite muddled; flask 3.1 Flash Lite covers only scaffold.py). Human verdicts still pending.
- Scorer fix: root cause fields listing several files or functions ("a.py and b.py", "f, g") are now split before matching;
  re-scoring changed only flask 3.5 Flash Lite from miss to likely.
- Evidence checker limit seen in review: it verifies that a cited commit appears in a git output, not that what is said about it is true.
- Budget analysis (step 3 of the plan): `docs/budget-analysis.md`. Runs that ran out of calls hypothesised late (median call 27
  vs 10) and explored more (16.5 diagnostic runs vs 7); two filelock runs thrashed with 9 and 12 edits. Proposed protocol v2:
  hypothesis checkpoint at call 15, repair checkpoint at call 25, thrash guard after 3 failing edit/test cycles.
  Implemented as `PROTOCOL = "v2"` (default; `--protocol=v1` restores round 1 behaviour). The system prompt is unchanged;
  guidance is appended to the tool result notice and logged as `guidance` events. run.json records `protocol`.
  v2 runs use the variant suffix `v2a` so they never mix with v1 folders.
- Protocol v2 round (2026-10-31, folders `-v2a`): 3.1 Flash Live 5/5 (v1 4/5), 3.5 Flash Lite 4/5 (v1 3/5), 3.8 Live 2/5 (same),
  3.1 Flash Lite 1/5 (v1 3/5, but 3 failures were HTTP 503 storms plus a harness timing bug). Table in README.
  Harness fix after v2: a failed request's hanging time now counts as waiting, not active time. Rerun 3.1 Flash Lite filelock,
  packaging, attrs under v2 before judging that driver.
- v2 gaps found: the thrash guard ignores failing `run_python` checks after edits (3.8 Live filelock made 11 edits unguarded);
  models sometimes cite call numbers one off, likely because the call number appears only at the end of each result.
  Candidate v3: count run_python failures in the thrash guard; put "[call N]" at the start of every tool result.
- 3.1 Flash Lite v2 rerun (2026-11-01, variant `v2b`): stopped after filelock hit 12 HTTP 503 replies in a row (27 min) and
  packaging did the same. The timing fix worked (24 s active of 1663 s). Folders removed; retry later with
  `--protocol=v2` (the default is now v3).
- Protocol v3 implemented (2026-11-01, default; variant suffix `v3a`): the thrash guard also counts failing `run_python`
  checks after an edit, and every tool result sent to the model starts with "[call N]". The transcript keeps the bare
  result, so the evidence checker is unchanged. v2 and v1 behave as before with `--protocol=v2|v1`.
- Parked for later: discussion of a multi-agent design (planner, reviewer) on top of the single investigator agent.
- Next, in order: (2) root cause review sheet for a person to confirm likely/partial, (3) analyse where the 40 calls go in
  budget_exhausted runs, (4) test improvements as protocol v2 against frozen v1, (5) new cases fixed after model training cutoffs. (20 requests/day per model). Plan: one case per day, filelock-346 first. Optional prompt
  tweak to batch independent calls (not done; it changes behaviour, so decide before the first real run).

## Not yet done / known gaps
- Git repository has no commits; nothing is under version control.
- The investigator agent, sandbox, hypothesis tracking and the auditable report are not built.
- One attempt per cell on five public bugs: results are indicative only; training-data exposure is possible.
- Prompt example path `src/example/module.py` may have misled Qwen once; reword before the next round.
- Cleanup done: deleted `hii.py`, `cases/flask-5160/reference-fixed/`, `.logs/`.
