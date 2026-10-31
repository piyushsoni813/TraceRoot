# Investigator design (draft for review)

Status: proposal only. Nothing in this document has been built or run.

## Goal

Replace the single-prompt baseline with an agent that investigates a failing Python
repository the way a developer would, and ends with a reviewable report. It must be scored on
the same five cases (flask-5160, attrs-1416, packaging-638, filelock-346, click-3449) with the
same independent evaluator, so the baseline and the agent are directly comparable.

## What the agent receives and what it must never see

Receives: the bug report, the stack trace, and a sandboxed copy of the repository at the
faulty revision with Git history up to that revision.

Never visible:
- Anything after the faulty revision. The sandbox repository is rebuilt so the fix commit,
  later commits, tags and other branches are not reachable (fresh clone, reset to the faulty
  revision, delete all other refs and reflogs, prune unreachable objects). Check: `git log --all`
  must not list the fix commit.
- `cases/<id>/reference/`, the evaluator tests at the fixed revision, the issue thread and the
  fix PR. There is no network access.

## Tools (all run inside the sandbox)

| Tool | Purpose |
| --- | --- |
| `list_dir`, `read_file(path, start, end)` | Inspect code. |
| `search(regex, path)` | Find definitions and call sites. |
| `git_log(path, n)`, `git_show(rev)`, `git_blame(path, start, end)` | Use history: what changed recently near the failure. |
| `run_python(code)` | Run a small diagnostic script against the checked-out code. |
| `run_tests(selection)` | Run the repository's tests (any selection the agent chooses). |
| `record_hypothesis(text, predicts)` and `update_hypothesis(id, status, evidence)` | Keep competing explanations and what each predicts. |
| `submit(edits, report)` | End the run. Edits use the existing search/replace edit format. |

Limits per run: 40 tool calls, 15 minutes, 200k tokens of model context, 20 KB per tool output.
Edits may touch only files under `src/`. The agent cannot edit tests.

## Workflow the agent is asked to follow

1. Investigate: read the trace frames, the code around them, the recent history of those files.
2. Hypothesize: at least two competing explanations, each with an observation that would
   distinguish it.
3. Test: run targeted diagnostics, then mark each hypothesis supported or rejected with evidence.
4. Repair: the smallest change that fixes the cause, not the symptom.
5. Verify: run the failing scenario and a regression selection of its choosing. If something
   fails, revise (counts against the call budget).
6. Report.

## Sandbox

Docker (installed here, version 29.6.1): Python 3.13 image with the pinned test dependencies,
`--network none`, CPU and memory limits, the repository mounted as a throwaway copy, tool
scripts mounted read-only. One container per run, deleted afterward. All paths and caches on D:.
Alternative if Docker causes trouble: run on the host in a temporary directory with no network
tools. This is weaker isolation and would be recorded as a deviation.

## Auditable report (required fields, validated by a schema)

- `root_cause`: mechanism, file, function, and the breaking commit if identified.
- `hypotheses`: each with prediction, check performed, status, evidence reference.
- `evidence`: items that point to a tool call in the saved transcript (file and line, command
  output, commit id).
- `patch`: the edits.
- `verification`: commands run and their results, copied from the transcript.
- `limitations`: what was not checked.
- `decision`: always "ready for human review". No merge or deploy.

## How it is scored

1. Repair (same as baseline): evaluator reproducer exits 0 and the held-out upstream tests pass.
2. Root cause: the report names the breaking commit, or the same file and mechanism as the real
   fix. Checked against `metadata.json` by a script first, then read by a person for the
   borderline ones.
3. Evidence validity: every cited command output or line number must match the transcript.
   Unverifiable citations count against the run. Automated.
4. Cost: tool calls, tokens, wall time.

## Experiment layout

`experiments/<case>-agent-<model>-<variant>/` holds the frozen tool configuration and its hash,
the full transcript (every model message and tool result, unedited), the submission, and
`evaluation.json`. Baseline and agent results are reported in separate tables.

Planned comparisons (five cases each): agent with all tools; agent without git tools; agent
without `run_python` and `run_tests`. The differences show which capabilities matter.

## Known risks

- The five bugs are public and may appear in model training data, so a success is not proof of
  investigation. The transcript and evidence checks are the defense; they do not remove the risk.
- Five cases cannot give reliable rates. Treat results as indicative.
- Gemini returns intermittent 503 errors; calls need retry with identical settings, and every
  retry is logged.
- Tool-calling quality of Qwen3-8B through llama.cpp is untested and may be poor; a failure there
  would partly measure the harness, not the model.

## Decisions needed

1. Which model drives the agent: Gemini 3.5 Flash (recommended, reliable function calling), with
   Qwen3-8B as an optional second.
2. Docker sandbox (recommended) or host-only.
3. The per-run budgets above.
