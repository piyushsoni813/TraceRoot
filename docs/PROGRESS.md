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

## Not yet done / known gaps
- Git repository has no commits; nothing is under version control.
- The investigator agent, sandbox, hypothesis tracking and the auditable report are not built.
- One attempt per cell on five public bugs: results are indicative only; training-data exposure is possible.
- Prompt example path `src/example/module.py` may have misled Qwen once; reword before the next round.
- Cleanup done: deleted `hii.py`, `cases/flask-5160/reference-fixed/`, `.logs/`.
