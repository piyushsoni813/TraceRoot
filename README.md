# TraceRoot

TraceRoot is an evidence-driven project for evaluating AI-assisted software incident investigation. The initial experiment is a single-LLM baseline that receives a bug report and stack trace; evaluation uses an independently verified regression case.

## Architecture

![TraceRoot architecture and workflow](docs/architecture.png)

Regenerate with `python tools/scripts/draw_architecture.py` (needs matplotlib).

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

Agent: `tools/agent/agent.py` (tools, hypotheses, budgets and report checks as in `docs/investigator-design.md`):
40 tool calls, 15 minutes of active time (rate-limit waits excluded and recorded), 200k context tokens. All runs on the
Gemini free tier, 2026-10-31. One model per driver, except the labelled Flash chain, which moves to the next model when one
model's daily quota ends. "Success" is the same independent evaluator as the baseline: the submitted edits replayed on a
fresh checkout, reproducer exits 0, held-out upstream tests pass. Root cause: `match` = breaking commit named; `likely` = same
file and function as the real fix (a person should confirm the mechanism); `partial` = file or function only; `miss`.
Evidence = items in the report backed by the transcript / all items checked (`tools/agent/evidence_check.py`, checker a7f25b9).

| Driver | filelock-346 | packaging-638 | attrs-1416 | click-3449 | flask-5160 | Solved |
| --- | --- | --- | --- | --- | --- | --- |
| Gemini 3.1 Flash Live (preview) | **success**, root cause likely, evidence 14/16 | **success**, root cause partial, evidence 12/16 | no submit (40 calls used) | **success**, root cause partial, evidence 19/21 | **success**, root cause match, evidence 10/13 | 4/5 |
| Gemini 3.5 Flash Lite | no submit (40 calls used) | **success**, root cause partial, evidence 7/11 | **success**, root cause likely, evidence 4/6 | no submit (40 calls used) | **success**, root cause miss, evidence 7/10 | 3/5 |
| Gemini 3.1 Flash Lite | no submit (40 calls used) (b) | **success** (b), root cause partial, evidence 9/9 | stopped: HTTP 503 (busy) (b) | no submit (40 calls used) | **success**, root cause likely, evidence 19/20 | 2/5 |
| Gemini 3.8 Live | no submit (40 calls used) (c) | **success** (c), root cause partial, evidence 11/11 | no submit (40 calls used) (c) | no submit (40 calls used) (c) | **success** (c), root cause match, evidence 8/10 | 2/5 |
| Flash chain (3.8 Flash, 3 Flash, 2.5 Flash) | **success** (b), root cause likely, evidence 10/13 | **success** (b), root cause partial, evidence 17/17 | stopped: daily quota (b) | stopped: harness bug (signature) | stopped: harness bug (signature) | 2/5 |

Cases solved by at least one driver: 5 of 5. Baseline for comparison (single prompt, edit format): Gemini 3.5 Flash 4 of 9 runs.

Reruns and exclusions (every attempt is kept in `experiments/`; the table shows the last attempt, letter in brackets):
- Gemini 3.8 Live `a` and `b` failed because of harness bugs in the Live client (an empty turn-closing message was read as an
  empty answer, so the agent was nudged out after about 4 calls). Fixed in c21045a and f44b893, then `c` ran.
- Gemini 3.1 Flash Lite `a` lost filelock, packaging and attrs to HTTP 503 (Google "high demand") before 503 patience was added;
  `b` reran those three. attrs `b` again stopped on 503 after 12 retries.
- Flash chain `a` lost every case to HTTP 503 or to a harness bug (missing thought signature after a model switch). `b` reran with
  the fixes; it stopped at attrs when the last model's daily quota ended. click and flask wait for the next quota reset.
- Gemini 3.8 Live Extended Thinking was dropped: it answered in speech and made no tool calls (all five `a` runs).
- The very first run (filelock, Gemini 3.5 Flash) stopped on the 20 request daily quota after 22 calls, before any edit.

Limits of these results:
- Five public bugs, one counted attempt per cell. Indicative only; the models may have seen these fixes in training.
- `likely` and `partial` root causes have not yet been reviewed by a person.
- The free tier may use prompts to improve Google products; the cases are public repositories.
