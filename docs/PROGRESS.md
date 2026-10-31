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
- Next: step 10, real runs on the free tier (20 requests/day per model). Plan: one case per day, filelock-346 first. Optional prompt
  tweak to batch independent calls (not done; it changes behaviour, so decide before the first real run).

## Not yet done / known gaps
- Git repository has no commits; nothing is under version control.
- The investigator agent, sandbox, hypothesis tracking and the auditable report are not built.
- One attempt per cell on five public bugs: results are indicative only; training-data exposure is possible.
- Prompt example path `src/example/module.py` may have misled Qwen once; reword before the next round.
- Cleanup done: deleted `hii.py`, `cases/flask-5160/reference-fixed/`, `.logs/`.
