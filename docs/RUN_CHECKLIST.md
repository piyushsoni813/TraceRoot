# Checklist for a real agent run (step 10, Gemini free tier)

Free tier limit: 20 requests per day per model. A run stops with `api_error` if the quota ends.
Daily quotas usually reset at midnight Pacific time. Confirm the remaining quota at https://ai.dev/rate-limit before starting.

## A. Decide once, before the first run (then freeze)

- [ ] Prompt: keep the current system prompt, or add the line that asks the model to send independent calls together.
      Decide now. Do not change it after seeing any result. Record the choice in `docs/PROGRESS.md`.
- [ ] Model name: `gemini-3.5-flash`. Use the same name for all five cases.
- [ ] Limits stay at 40 tool calls, 15 minutes, 200k context tokens.
- [ ] One attempt per case. A run that fails on quota, network or a model error is kept and reported, not silently repeated.

## B. Ready check (all verified on 2026-10-31)

- [x] `GEMINI_API_KEY` is set as a user environment variable (start a new terminal to see it).
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
