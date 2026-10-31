# Frozen evaluation protocol

## Question

Can a single LLM, given only `input/report.md` and `input/stacktrace.txt`,
produce an applyable source patch that independently repairs the regression?

## Controlled variable

The model output is the only experimental variable. The prompt, faulty checkout,
Python environment, evaluator, accepted patch scope, and test commands are
fixed before invocation.

## Invocation record

Before the first invocation, record the model provider, model identifier,
sampling parameters, timestamp, and the SHA-256 hashes of `prompt.md` and both
input files in `run.json`. Store the raw response, unchanged, as `output/raw.md`.

## Patch extraction and admission

1. Extract the sole fenced `diff` block from `output/raw.md` without editing it.
2. Reject the output if it contains prose outside that block, more than one
   diff block, or no diff block.
3. Reject any patch that changes a path outside `src/flask/`.
4. Apply the patch with `git apply --whitespace=error` to a new clean checkout
   of case `flask-5160` at its recorded faulty revision.
5. Reject a malformed or non-applying patch. Do not repair it manually.

## Independent evaluation

Run the evaluator held outside the candidate checkout:

```powershell
$env:PYTHONPATH = '<candidate-checkout>\\src'
D:\TraceRoot\.venv\Scripts\python.exe D:\TraceRoot\cases\flask-5160\reference\reproduce.py
```

Then run:

```powershell
D:\TraceRoot\.venv\Scripts\python.exe -m pytest -q --basetemp <D-drive-temp> tests\test_helpers.py tests\test_instance_config.py
```

All temporary paths must be under `D:\TraceRoot`. Ask for permission before a
command uses `C:` storage.

## Success criterion

The run succeeds only if the patch applies, the external evaluator exits 0, and
the specified upstream test selection passes. A plausible explanation, a patch
that does not apply, or a green result obtained by changing tests is a failure.

## Failure labels

- `no_patch`
- `invalid_output_contract`
- `disallowed_patch_scope`
- `patch_does_not_apply`
- `evaluator_still_fails`
- `upstream_regression_check_fails`
- `environment_failure`
