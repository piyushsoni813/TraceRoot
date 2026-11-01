# Investigation report: packaging-638

Model: gemini-3.8-live. Tool calls: 21. Time: 108.5 s. Tokens: 107388.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

The _normalize function attempted to canonicalize the 'extra' marker value using canonicalize_name without checking if the value was None. When a user evaluated a marker with 'extra' set to None, a TypeError was raised.

## Hypotheses

### H1 (supported)

The function _normalize attempts to canonicalize values without checking if they are None. When extra is None, it passes None to canonicalize_name, causing a TypeError.

- Predicts: If we modify _normalize to return None (or handle it gracefully) when the value is None, the TypeError will be resolved and the marker evaluation will correctly return False.
- Evidence: canonicalize_name(None) raises TypeError, which causes evaluate() to fail when extra is None. (tool calls 7, 11)

### H2 (rejected)

The evaluation logic in _evaluate_markers should not normalize values if they are None, as None indicates the absence of an extra.

- Predicts: If we modify _evaluate_markers to skip normalization or handle None before calling _normalize, the TypeError will be avoided.
- Evidence: The TypeError is raised inside _normalize because it calls canonicalize_name with None. (tool calls 11)

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

- Call 17: `python -c "..."`: Result: False
- Call 20: `pytest tests/test_markers.py`: 2221 passed in 4.09s

## Evidence

### Call 7: run_python

Arguments: `{"code": "from packaging.utils import canonicalize_name\ntry:\n    canonicalize_name(None)\nexcept Exception as e:\n    print(f\"canonicalize_name(None) raises {type(e).__name__}\")\n"}`

```
[exit 0]
canonicalize_name(None) raises TypeError

```

### Call 11: run_python

Arguments: `{"code": "from packaging.markers import Marker\nmarker = Marker('extra == \"opt-feature\"')\ntry:\n    marker.evaluate({\"extra\": None})\n    print(\"No error\")\nexcept Exception as e:\n    print(f\"Error: {type(e).__name__}: {e}\")\n"}`

```
[exit 0]
Error: TypeError: expected string or bytes-like object, got 'NoneType'

```

### Call 17: run_python

Arguments: `{"code": "from packaging.markers import Marker\nmarker = Marker('extra == \"opt-feature\"')\ntry:\n    print(f\"Result: {marker.evaluate({'extra': None})}\")\nexcept Exception as e:\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Result: False

```

### Call 20: run_tests

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

