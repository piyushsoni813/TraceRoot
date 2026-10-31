# Protocol v2: search/replace edit output

Why: in the diff-format runs (v2, v3, gemini-a, gemini-b) every output failed at
`git apply`, including one whose idea matched the upstream repair. Models write
wrong hunk line counts and numbers. Protocol v2 changes ONLY the output format,
so that the experiment measures finding the fix, not formatting a diff.

## What changes
- The model returns one fenced block with info string `edit`, holding one or
  more edits in this exact form:

      FILE: src/flask/scaffold.py
      <<<<<<< SEARCH
      exact original lines
      =======
      replacement lines
      >>>>>>> REPLACE

- A fixed script (`tools/scripts/run_edit_experiment.py`) applies the edits to a clean checkout
  at the faulty revision. No human edits anything.

## What stays the same
Faulty revision, evaluator (`cases/flask-5160/reference/reproduce.py`), test
selection, inputs (report, stack trace, optional source excerpt), scope limit
(`src/flask/` only), and the rule that outputs are saved unedited.

## Admission rules
1. Exactly one `edit` block and no prose outside it, else `invalid_output_contract`.
2. Every FILE path must be under `src/flask/`, else `disallowed_patch_scope`.
3. Every SEARCH text must match the original file exactly once, else
   `patch_does_not_apply`. No fuzzy matching and no manual repair.
4. Then: evaluator must exit 0 (else `evaluator_still_fails`) and the upstream
   tests must pass (else `upstream_regression_check_fails`). Otherwise `success`.

Results from protocol v1 (diff format) and v2 (edit format) are reported
separately and are not mixed.
