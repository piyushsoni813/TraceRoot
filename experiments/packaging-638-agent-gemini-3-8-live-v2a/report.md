# Investigation report: packaging-638

Model: gemini-3.8-live. Tool calls: 17. Time: 90.1 s. Tokens: 90757.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

The `_normalize` function attempted to unconditionally canonicalize the `extra` environment marker value using `canonicalize_name`. When `extra` was passed as `None` (which occurs when no extra is evaluated), `canonicalize_name` raised a `TypeError` because it expected a string. The fix checks if the value is `None` before canonicalizing.

## Hypotheses

### H1 (supported)

The `TypeError` occurs because `canonicalize_name` does not accept `None`. We can fix this by handling `None` in `_normalize` or by ensuring `None` is not passed to `canonicalize_name`.

- Predicts: If we modify `_normalize` to skip `canonicalize_name` when the value is `None`, the `TypeError` will be avoided and the marker evaluation will correctly return `False`.
- Evidence: The fix in `_normalize` handles `None` values for `extra` by skipping `canonicalize_name`. The reproduction script now evaluates to `False` without raising `TypeError`. Existing tests pass. (tool calls 12, 13)

### H2 (rejected)

The `TypeError` occurs because `None` is passed to `_normalize` which then passes it to `canonicalize_name`. We can fix this by checking for `None` in `_evaluate_markers` before calling `_normalize`.

- Predicts: If we modify `_evaluate_markers` to handle `None` values before calling `_normalize`, the `TypeError` will be avoided.
- Evidence: H1 was successfully implemented and verified. H2 is no longer needed. (tool calls 12, 13)

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

- Call 13: `python -c 'from packaging.markers import Marker; marker = Marker("extra == \"opt-feature\""); print(marker.evaluate({"extra": None}))'`: False
- Call 14: `pytest tests/test_markers.py`:         [exit 0]
........................................................................ [  3%]
...
2221 passed in 4.23s

## Evidence

### Call 12: apply_edit

Arguments: `{"search": "    if key == \"extra\":\n        return tuple(canonicalize_name(v) for v in values)", "replace": "    if key == \"extra\":\n        return tuple(canonicalize_name(v) if v is not None else v for v in values)", "path": "src/packaging/markers.py"}`

```
applied edit 1 to src/packaging/markers.py. Run tests to check it.
```

### Call 13: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\nmarker = Marker('extra == \"opt-feature\"')\nprint(marker.evaluate({\"extra\": None}))\n"}`

```
[exit 0]
False

```

### Call 14: run_tests

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

