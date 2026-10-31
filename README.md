# TraceRoot

TraceRoot is an evidence-driven project for evaluating AI-assisted software incident investigation. The initial experiment is a single-LLM baseline that receives a bug report and stack trace; evaluation uses an independently verified regression case.

## Workspace layout

- `cases/<case-id>/` holds case metadata, the bug report, and stack trace. Keep reference fixes in `reference/`, separate from all model inputs.
- `experiments/<run-id>/input/` stores the exact model prompt and supplied files.
- `experiments/<run-id>/output/` stores the unedited model response.
- `experiments/<run-id>/evaluation.json` records evaluation criteria and observed results.

Do not copy anything from a case's `reference/` directory into an experiment's `input/`. Record project revisions, environment details, and commands so results can be reproduced. Do not report outcomes until commands have actually been run.

## Current state

- Case: `flask-5160` (pallets/flask issue 5160, faulty revision `84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`).
- Model: Qwen3-8B Q4_K_M via local llama.cpp, greedy decoding, no thinking mode.
- `experiments/flask-5160-minimal-context-v1`: invalid (`environment_failure`). The response was lost before it could be saved; nothing was evaluated.
- `experiments/flask-5160-minimal-context-v2`: completed, outcome `patch_does_not_apply`. The response was captured intact through the llama.cpp API and met the output contract, but the diff's context lines do not exist in the faulty revision, so `git apply` failed. The evaluator and upstream tests were not run, and the patch was not repaired by hand.

This is a single run of one small model on one case, so it is a baseline data point, not a general result.

## Results so far (case flask-5160, one attempt per cell, greedy decoding)

Diff-format protocol (original): Qwen3-8B fails both inputs (v2, v3); Gemini 3.5 Flash fails both (gemini-a, gemini-b). All four were rejected at `git apply`.

Edit-format protocol (`experiments/PROTOCOL_EDIT_FORMAT.md`, edits applied by `tools/scripts/run_edit_experiment.py`):

| Model | Report + stack trace only | + source excerpt |
| --- | --- | --- |
| Qwen3-8B (local) | `patch_does_not_apply` | `evaluator_still_fails` |
| Gemini 3.5 Flash | `patch_does_not_apply` | `success` (evaluator exit 0, 41 upstream tests pass) |

The two protocols are reported separately. Gemini 3.1 Pro was planned but its quota was exceeded on the available key, so Gemini 3.5 Flash was used.

## Cases

`flask-5160` (baseline already run) plus four newly admitted regressions, each validated on both revisions with a reproducer and targeted tests: `attrs-1416`, `packaging-638`, `filelock-346`, `click-3449`. See `docs/benchmark-candidate-research.md`. The new cases have not been run against any model yet.

## Edit-format results across all five cases (2026-10-24)

One attempt per cell, greedy decoding. `a` = report + stack trace only; `b` = plus a source excerpt built from the stack trace. `n/a` = the trace has no project frames, so there is no `b` variant.

| Case | Qwen3-8B a | Qwen3-8B b | Gemini 3.5 Flash a | Gemini 3.5 Flash b |
| --- | --- | --- | --- | --- |
| flask-5160 | patch_does_not_apply | evaluator_still_fails | patch_does_not_apply | **success** |
| attrs-1416 | patch_does_not_apply | n/a | patch_does_not_apply | n/a |
| packaging-638 | patch_does_not_apply | evaluator_still_fails | **success** | **success** |
| filelock-346 | patch_does_not_apply | evaluator_still_fails | evaluator_still_fails (cap64k) | **success** (cap64k) |
| click-3449 | patch_does_not_apply | evaluator_still_fails | patch_does_not_apply (cap64k) | invalid_output_contract |

Totals over the 9 runs per model: Qwen3-8B 0 successes; Gemini 3.5 Flash 4 successes.

Notes:
- `cap64k` rows were rerun with the output cap raised to 65,536 tokens because the first run (cap 16,384) stopped at `MAX_TOKENS` after spending about 15.7k tokens thinking and produced no edit. Those first runs are recorded as `output_limit_reached` (invalid, not a model failure) in the sibling folders without the suffix.
- `click-3449` Gemini `b` wrote a plausible edit but added prose outside the code block, which the contract rejects; it was not scored on its merits.
- Qwen3-8B `attrs-1416 a` copied the prompt's placeholder path `src/example/module.py`, so the prompt's example path may have misled the small model. That prompt wording is shared by all runs.
- Evaluator tests for the new cases are the upstream versions at the fixed revision (see `experiments/PROTOCOL_EDIT_FORMAT.md`).
- Gemini runs hit HTTP 503 (service unavailable) several times; those requests returned no response and were repeated with identical settings.

## Investigator agent results (separate from the baseline tables above)

Agent: `tools/agent/agent.py` with the tools, budgets and report checks described in `docs/investigator-design.md`
(40 tool calls, 15 minutes, 200k context tokens). Driver model: Gemini 3.5 Flash on the free tier (20 requests per day,
5 per minute). Quota errors named the model `gemini-3.6-flash` although `gemini-3.5-flash` was requested; this looks like an alias.
One attempt per case. System prompt frozen on 2026-10-31 (commit d30bd84).

| Case | Run outcome | Repair | Root cause | Evidence | Tool calls | Model requests |
| --- | --- | --- | --- | --- | --- | --- |
| filelock-346 | `api_error` (daily quota) | `no_submission` | n/a | n/a | 22 | 16 |

Notes:
- filelock-346: the run stopped at 403 s with HTTP 429 (daily free-tier quota) after 22 tool calls. By then the agent had
  recorded two hypotheses and was running diagnostics, but had made no edit. This measures the free-tier limit, not the agent's ability.
  The run was not repeated. Retries are logged in `transcript.jsonl`: 5 times HTTP 503 and once HTTP 429 (per-minute limit).
