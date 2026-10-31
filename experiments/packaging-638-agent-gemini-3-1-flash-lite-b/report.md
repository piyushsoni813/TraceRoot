# Investigation report: packaging-638

Model: gemini-3.1-flash-lite. Tool calls: 15. Time: 220.4 s. Tokens: 59002.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

The _normalize function was unconditionally calling canonicalize_name on values when the key was 'extra'. When 'extra' was None, canonicalize_name raised a TypeError because it expects a string. The fix is to check if the value is None before calling canonicalize_name.

## Hypotheses

### H1 (supported)

The _normalize function blindly calls canonicalize_name on values when key is 'extra', but it doesn't check if the value is None. If it's None, it should probably be treated as not matching or handled gracefully.

- Predicts: If I change _normalize to handle None by returning it as is (or converting to empty string), the TypeError will be gone and it will return False.
- Evidence: The code fails when 'extra' is None, but works when it is a string. The failure is in _normalize which calls canonicalize_name on the value. If the value is None, it should probably not be canonicalized, or it should be handled. If I change _normalize to handle None, it should fix the issue. (tool calls 1, 6, 7)

### H2 (rejected)

The environment dictionary contains None values which are not expected by the marker evaluation logic. Filtering them out might be the correct approach.

- Predicts: If I change _evaluate_markers to filter out None values from the environment before passing them to _normalize, it might fix the issue.
- Evidence: Filtering out None from the environment in _evaluate_markers might be tricky because the environment is used for other markers too. If I filter it out, I might break other things. H1 seems more direct. (tool calls 5)

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

- Call 11: `python reproduction script`: Result: False
- Call 14: `pytest tests/test_markers.py`: 2221 passed in 4.26s

## Evidence

### Call 1: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\ntry:\n    marker = Marker('extra == \"opt-feature\"')\n    print(marker.evaluate({\"extra\": None}))\nexcept Exception as e:\n    print(e)\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
expected string or bytes-like object, got 'NoneType'
Traceback (most recent call last):
  File "<string>", line 5, in <module>
    print(marker.evaluate({"extra": None}))
          ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
  File "/work/src/packaging/markers.py", line 241, in evaluate
    return _evaluate_markers(self._markers, current_environment)
  File "/work/src/packaging/markers.py", line 150
```

### Call 5: read_file

Arguments: `{"end": 160, "path": "src/packaging/markers.py", "start": 130}`

```
130	def _evaluate_markers(markers: MarkerList, environment: Dict[str, str]) -> bool:
131	    groups: List[List[bool]] = [[]]
132	
133	    for marker in markers:
134	        assert isinstance(marker, (list, tuple, str))
135	
136	        if isinstance(marker, list):
137	            groups[-1].append(_evaluate_markers(marker, environment))
138	        elif isinstance(marker, tuple):
139	            l
```

### Call 6: run_python

Arguments: `{"code": "from packaging.markers import Marker\n# Check what happens if we pass a string instead of None\nmarker = Marker('extra == \"opt-feature\"')\nprint(f\"None: {marker.evaluate({'extra': None})}\")\n"}`

```
[exit 1]
Traceback (most recent call last):
  File "<string>", line 4, in <module>
    print(f"None: {marker.evaluate({'extra': None})}")
                   ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
  File "/work/src/packaging/markers.py", line 241, in evaluate
    return _evaluate_markers(self._markers, current_environment)
  File "/work/src/packaging/markers.py", line 150, in _evaluate_markers
    lhs_va
```

### Call 7: run_python

Arguments: `{"code": "from packaging.markers import Marker\n# Check what happens if we pass a string instead of None\nmarker = Marker('extra == \"opt-feature\"')\ntry:\n    print(f\"String: {marker.evaluate({'extra': 'opt-feature'})}\")\nexcept Exception as e:\n    print(f\"String failed: {e}\")\n"}`

```
[exit 0]
String: True

```

### Call 11: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\nmarker = Marker('extra == \"opt-feature\"')\ntry:\n    result = marker.evaluate({\"extra\": None})\n    print(f\"Result: {result}\")\nexcept Exception as e:\n    print(f\"Failed: {e}\")\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Result: False

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

- None identified. The fix is simple and verified by the reproduction script and existing tests.
