# Investigation report: packaging-638

Model: gemini-3.8-live. Tool calls: 17. Time: 76.6 s. Tokens: 74638.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

The `_normalize` function attempted to canonicalize the `extra` environment marker value even when it was `None`, leading to a `TypeError` in `canonicalize_name`.

## Hypotheses

### H1 (supported)

The `_normalize` function attempts to `canonicalize_name` for all values when `key == "extra"`, including `None`. We should handle `None` by not canonicalizing it, or by returning `None` directly.

- Predicts: If we modify `_normalize` to return `None` as is when `v is None`, the `TypeError` will be avoided and the comparison will evaluate to `False` as expected.
- Evidence: The TypeError is fixed and evaluate returns False. (tool calls 11)

### H2 (rejected)

The `canonicalize_name` function should handle `None` inputs gracefully.

- Predicts: If we modify `canonicalize_name` to accept `None` and return `None` (or handle it gracefully), it might fix the issue, but `_normalize` is specifically for environment markers and `extra` normalization is PEP 685.
- Evidence: H1 is supported and fixes the issue locally in markers.py without changing utils.py. (tool calls 11)

## Patch

```diff
diff --git a/src/packaging/markers.py b/src/packaging/markers.py
index a5bf35c..8c91548 100644
--- a/src/packaging/markers.py
+++ b/src/packaging/markers.py
@@ -121,7 +121,7 @@ def _normalize(*values: str, key: str) -> Tuple[str, ...]:
     # > When comparing extra names, tools MUST normalize the names being
     # > compared using the semantics outlined in PEP 503 for names
     if key == "extra":
-        return tuple(canonicalize_name(v) for v in values)
+        return tuple(canonicalize_name(v) if v is not None else v for v in values)
 
     # other environment markers don't have such standards
     return values
```

## Verification

- Call 11: `run_python code to evaluate marker with extra=None`: Result: False
- Call 16: `run_tests tests/test_markers.py`: 2221 passed in 4.64s

## Evidence

### Call 11: run_python

Arguments: `{"code": "from packaging.markers import Marker\nmarker = Marker('extra == \"opt-feature\"')\ntry:\n    result = marker.evaluate({\"extra\": None})\n    print(f\"Result: {result}\")\nexcept Exception as e:\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Result: False

```

### Call 16: run_tests

Arguments: `{"selection": ["tests/test_markers.py"]}`

```
[exit 0]
........................................................................ [  3%]
........................................................................ [  6%]
........................................................................ [  9%]
........................................................................ [ 12%]
.......................................................................
```

## Limitations

