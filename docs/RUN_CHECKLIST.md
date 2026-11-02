# Checklist for a real agent run (Gemini free tier)

Free tier limits differ by model (2026-11): Flash 5 RPM / 20 RPD, Flash Lite 15 RPM / 500 RPD, Live models no daily
limit. A run stops with `api_error` if the quota ends.
Daily quotas usually reset at midnight Pacific time. Confirm the remaining quota at https://ai.dev/rate-limit before starting.

## A. Decide once, before the first run (then freeze)

- [ ] Prompt: keep the current system prompt, or add the line that asks the model to send independent calls together.
      Decide now. Do not change it after seeing any result. Record the choice in `docs/PROGRESS.md`.
- [ ] Model name: `gemini-3.5-flash`. Use the same name for all five cases.
- [ ] Limits stay at 40 tool calls, 15 minutes, 200k context tokens.
- [ ] One attempt per case. A run that fails on quota, network or a model error is kept and reported, not silently repeated.

## B. Ready check (all verified on 2026-10-31)

- [x] The key is in the gitignored `.env` (`GEMINI_API_KEY`, second key `GEMINI_API_KEY_2`; choose with `--key-env=NAME`).
- [x] Docker is running and image `traceroot-sandbox:1` exists.
- [x] Working tree is clean and pushed.
- [x] Offline tests pass: `selftest_tools.py`, `selftest_agent.py`, `selftest_evidence.py`, `selftest_score.py`, `selftest_e2e.py`.
- [ ] Re-run `selftest_agent.py` and `selftest_e2e.py filelock-346` on the day (no API cost) to be sure nothing drifted.
- [ ] Remaining Gemini quota for the model is at least 20 requests.

## C. Run

```
.venv\Scripts\python.exe -I tools\agent\agent.py <case> experiments\<case>-agent-gemini-3-5-flash-a gemini-3.5-flash
.venv\Scripts\python.exe -I tools\agent\score.py experiments\<case>-agent-gemini-3-5-flash-a
```

First case: `filelock-346` (small repository). The run directory must not exist; the loop refuses to overwrite.

Several cases with one model (runs and scores each, stops on daily quota):

```
.venv\Scripts\python.exe -I tools\agent\run_batch.py <model> <variant> [case ...] --protocol=v3 [--key-env=NAME]
```

Variant names: `a`, `b`, ... for v1; `v2a`, `v2b`, ... for v2; `v3a`, ... for v3. A rerun gets the next letter.

### When the model answers HTTP 503 ("high demand")

503 is Google's servers being busy, not our quota (that is 429) and not our code. Another key does not help: it is
the same model on the same servers. The agent retries a 503 up to 12 times and counts that time as waiting, not active
time, but a long storm still ends the run with `api_error`. If a batch keeps hitting 503:

1. Stop the batch, remove any leftover `tr-*` container (`docker rm -f`), and delete the run folders of runs that the
   storm cut short, so the rerun can use the same variant name. Record in `docs/PROGRESS.md` that this was done.
2. Let `run_when_ready.py` wait, probe the model with one tiny request, and start the batches only once it answers 200:

```
.venv\Scripts\python.exe -I tools\agent\run_when_ready.py gemini-3.1-flash-lite v2b:v2:filelock-346,packaging-638,attrs-1416 v3a:v3 --wait-hours=2 --key-env=GEMINI_API_KEY_2
```

   Defaults: no initial wait, then up to 8 probes 30 minutes apart (`--probes=N`, `--gap-min=M`). If every probe fails,
   no run starts. Keep the PC and Docker running. Used on 2026-11-01/02: first probe after 2 hours answered 200, and all
   eight runs finished without a 503 storm.

## D. After the run

- [ ] Read `result.json`: outcome, tool calls, model calls, tokens, seconds, retries in `transcript.jsonl`.
- [ ] Read `evaluation.json`: repair outcome, root cause status (`match`, `likely`, `partial`, `miss`), evidence check, cost.
- [ ] If root cause is `likely` or `partial`, a person reads `report.md` and decides about the mechanism.
- [ ] Open `report.md` and spot-check two evidence entries against `transcript.jsonl`.
- [ ] Check that no secret is in the run directory: `grep -r "AQ\." experiments/<run>` finds nothing.
- [ ] Add one row to the agent results table in `README.md` (separate from the baseline tables) and update `docs/PROGRESS.md`.
- [ ] Commit the run directory and push. Never edit saved outputs.

## E. Rules that keep the result honest

- Baseline and agent results stay in separate tables.
- Report failures the same as successes, including quota stops and `no_submission`.
- Five public cases and one attempt each are indicative only; models may have seen these bugs in training.
- The free tier may use prompts to improve Google products. The cases are public repositories, so this is acceptable here.
