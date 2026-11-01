# Investigation report: packaging-638

Model: gemini-3.1-flash-lite. Tool calls: 17. Time: 87.4 s. Tokens: 74756.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

The _normalize function was unconditionally calling canonicalize_name on values when the key was 'extra'. When 'extra' was None in the environment, this caused a TypeError because canonicalize_name expects a string.

## Hypotheses

### H1 (supported)

The issue is that _normalize assumes all values passed to it are strings, but when 'extra' is None in the environment, it passes None to canonicalize_name, which expects a string.

- Predicts: The fix will be to handle None in _normalize or before calling it. If I change _normalize to handle None, it should fix the issue.
- Evidence: canonicalize_name indeed fails with None. (tool calls 9)

### H2 (rejected)

The environment dictionary is being passed with 'extra': None, which is not a valid value for a marker evaluation if it's expected to be a string. The code should handle None as a non-existent extra.

- Predicts: The issue is that the environment dictionary should not contain None for 'extra' if it's not set, or the code should handle it. If I change the code to skip normalization if the value is None, it should fix the issue.
- Evidence: The environment dictionary is passed by the user, and the documentation/existing behavior suggests it should be handled. The code in _normalize is where the crash happens. (tool calls 9)

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

- Call 13: `python -c 'from packaging.markers import Marker; marker = Marker("extra == \"opt-feature\""); print(marker.evaluate({"extra": None}))'`: Result: False
- Call 14: `python -c 'from packaging.markers import Marker; marker = Marker("extra == \"opt-feature\""); print(marker.evaluate({"extra": "opt-feature"}))'`: Result: True
- Call 16: `pytest tests/test_markers.py`: 2221 passed in 3.95s

## Evidence

### Call 9: run_python

Arguments: `{"code": "from packaging.utils import canonicalize_name\ntry:\n    print(canonicalize_name(None))\nexcept Exception as e:\n    print(e)\n"}`

```
[exit 0]
expected string or bytes-like object, got 'NoneType'

```

### Call 13: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\ntry:\n    marker = Marker('extra == \"opt-feature\"')\n    result = marker.evaluate({\"extra\": None})\n    print(f\"Result: {result}\")\n    assert result is False\nexcept Exception as e:\n    print(e)\n    import traceback\n    traceback.print_exc(`

```
[exit 0]
Result: False

```

### Call 14: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\ntry:\n    marker = Marker('extra == \"opt-feature\"')\n    result = marker.evaluate({\"extra\": \"opt-feature\"})\n    print(f\"Result: {result}\")\n    assert result is True\nexcept Exception as e:\n    print(e)\n    import traceback\n    traceback.`

```
[exit 0]
Result: True

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

- None identified. The fix is simple and verified.
