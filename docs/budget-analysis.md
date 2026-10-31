# Where the 40 tool calls go (round 1)

Question: 8 of the round 1 runs ended with all 40 tool calls used and no submission. Where did the calls go, and what
would help? Data: every agent run's `transcript.jsonl`, summarised by `tools/scripts/analyze_budget.py`.

## Findings

1. **Late hypotheses.** Runs that submitted recorded their first hypothesis at call 10 (median) and made their first edit
   at call 18. Runs that ran out recorded their first hypothesis at call 27 (median); four of the eight never made an edit.
2. **Too many diagnostic runs and reads.** Runs that ran out used a median of 16.5 `run_python`/`run_tests` calls and 12.5
   reads, against 7 and 8 in runs that submitted. They kept exploring instead of committing to an explanation.
   Typical cases: attrs on 3.1 Flash Live (24 reads, 16 runs, no hypothesis at all) and click on 3.8 Live (35 reads).
3. **Edit thrashing.** Two filelock runs (3.1 Flash Lite `b`, 3.8 Live `c`) found the right place early (edit at call 10
   and 11) but then made 9 and 12 edits, re-running the same failing tests between them. The failure output was visible
   every time (18 of 18 failing test results were complete, none cut at 20 KB), so this is the model guessing, not
   missing information.
4. **Not the cause:** repeated identical calls (median 0; the repeat note works), tool errors (median 0.5) and
   refused submits (3 in total).

## Proposed changes for protocol v2 (not applied yet)

Keep the 40-call budget so v1 and v2 stay comparable. Change only the guidance the loop gives:

| Change | Trigger | Message to the model |
| --- | --- | --- |
| Hypothesis checkpoint | call 15 with no hypothesis recorded | record your competing hypotheses now; the median successful run did so by call 10 |
| Repair checkpoint | call 25 with no successful edit | choose the best-supported hypothesis and make the smallest fix now |
| Thrash guard | 3 edits in a row each followed by a failing test run | stop editing; read the failing test output and update your hypotheses first |

How to test: run v2 on the same five cases with the drivers that have enough free quota (both Flash Lite models and both
Live models), compare with v1 cell by cell, and report both. The v1 results stay as they are.

## Data


### budget_exhausted: 8 runs

| run | calls | read | git | exec | hyp | edit | submit | repeats | errors | rejected_submits | read_kchars | big_reads | first_hyp | first_edit | test_after_edit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| attrs-1416 3-1-flash-live-preview-a | 40 | 24 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 42 | 0 | None | None | None |
| attrs-1416 3-8-live-c | 40 | 13 | 2 | 22 | 2 | 1 | 0 | 1 | 0 | 0 | 16 | 0 | 36 | 39 | None |
| click-3449 3-1-flash-lite-a | 40 | 26 | 2 | 8 | 3 | 1 | 0 | 0 | 1 | 0 | 60 | 1 | 27 | None | None |
| click-3449 3-5-flash-lite-a | 40 | 12 | 4 | 19 | 4 | 1 | 0 | 0 | 1 | 0 | 44 | 1 | 34 | 39 | 40 |
| click-3449 3-8-live-c | 40 | 35 | 0 | 1 | 3 | 1 | 0 | 0 | 1 | 0 | 30 | 0 | 36 | None | None |
| filelock-346 3-1-flash-lite-b | 40 | 9 | 0 | 17 | 4 | 10 | 0 | 0 | 1 | 0 | 23 | 1 | 4 | 10 | 17 |
| filelock-346 3-5-flash-lite-a | 40 | 8 | 5 | 23 | 4 | 0 | 0 | 0 | 0 | 0 | 23 | 0 | 8 | None | None |
| filelock-346 3-8-live-c | 40 | 5 | 4 | 16 | 2 | 12 | 1 | 0 | 0 | 1 | 29 | 0 | 7 | 11 | 25 |

medians: calls=40.0, read=12.5, git=2.0, exec=16.5, hyp=3.0, edit=1.0, submit=0.0, repeats=0.0, errors=0.5, rejected_submits=0.0, read_kchars=29.5, big_reads=0.0
first_hyp: median 27, missing in 1 runs
first_edit: median 25.0, missing in 4 runs
submit refusals: {'resolve every hypothesis  first; still open': 1, 'no hypothesis is supported; the root cause must be one of th': 1, 'run_tests has not been run since your last apply_edit': 1}

### submitted: 15 runs

| run | calls | read | git | exec | hyp | edit | submit | repeats | errors | rejected_submits | read_kchars | big_reads | first_hyp | first_edit | test_after_edit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| attrs-1416 3-1-flash-lite-c | 38 | 18 | 2 | 12 | 4 | 1 | 1 | 0 | 0 | 0 | 41 | 1 | 14 | 33 | 35 |
| attrs-1416 3-5-flash-lite-a | 40 | 16 | 4 | 13 | 4 | 1 | 2 | 2 | 0 | 1 | 71 | 0 | 16 | 38 | 39 |
| click-3449 3-1-flash-live-preview-a | 35 | 25 | 0 | 4 | 4 | 1 | 1 | 1 | 0 | 0 | 54 | 2 | 27 | 29 | 33 |
| filelock-346 3-1-flash-live-preview-a | 31 | 8 | 3 | 13 | 4 | 2 | 1 | 0 | 0 | 0 | 20 | 0 | 11 | 22 | 24 |
| filelock-346 3-8-flash+3-flash-preview+2-5-flash | 28 | 9 | 3 | 8 | 4 | 3 | 1 | 0 | 1 | 0 | 20 | 0 | 12 | 18 | 20 |
| flask-5160 3-1-flash-lite-a | 24 | 10 | 0 | 8 | 4 | 1 | 1 | 0 | 0 | 0 | 6 | 0 | 10 | 18 | 20 |
| flask-5160 3-1-flash-live-preview-a | 20 | 7 | 2 | 4 | 4 | 2 | 1 | 0 | 0 | 0 | 56 | 3 | 9 | 13 | 19 |
| flask-5160 3-5-flash-lite-a | 25 | 9 | 2 | 7 | 4 | 2 | 1 | 0 | 0 | 0 | 15 | 0 | 8 | 17 | 20 |
| flask-5160 3-8-flash+3-flash-preview+2-5-flash-b | 30 | 5 | 2 | 16 | 4 | 2 | 1 | 0 | 0 | 0 | 9 | 0 | 10 | 19 | 22 |
| flask-5160 3-8-live-c | 20 | 5 | 2 | 7 | 4 | 1 | 1 | 0 | 0 | 0 | 8 | 0 | 9 | 12 | 13 |
| packaging-638 3-1-flash-lite-b | 15 | 3 | 0 | 6 | 4 | 1 | 1 | 0 | 0 | 0 | 2 | 0 | 3 | 10 | 14 |
| packaging-638 3-1-flash-live-preview-a | 17 | 3 | 5 | 3 | 4 | 1 | 1 | 0 | 0 | 0 | 17 | 1 | 10 | 12 | 16 |
| packaging-638 3-5-flash-lite-a | 40 | 13 | 5 | 16 | 4 | 1 | 1 | 0 | 0 | 0 | 27 | 0 | 11 | 33 | 34 |
| packaging-638 3-8-flash+3-flash-preview+2-5-flas | 17 | 2 | 6 | 3 | 4 | 1 | 1 | 0 | 0 | 0 | 10 | 0 | 5 | 14 | 15 |
| packaging-638 3-8-live-c | 17 | 3 | 2 | 5 | 5 | 1 | 1 | 0 | 1 | 0 | 3 | 0 | 4 | 10 | 16 |

medians: calls=25, read=8, git=2, exec=7, hyp=4, edit=1, submit=1, repeats=0, errors=0, rejected_submits=0, read_kchars=17, big_reads=0
first_hyp: median 10, missing in 0 runs
first_edit: median 18, missing in 0 runs
submit refusals: {'no fix applied; use apply_edit first': 1}
