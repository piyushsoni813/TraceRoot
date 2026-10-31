# Investigation report: packaging-638

Model: gemini-3.5-flash-lite. Tool calls: 40. Time: 181.9 s. Tokens: 387083.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

When evaluating markers mentioning `extra`, `_normalize` unconditionally called `canonicalize_name(v)` on all values. When `extra` was passed as `None` in the environment, `v` was `None`, causing `canonicalize_name` to raise a `TypeError` because it expects a string or bytes-like object.

## Hypotheses

### H1 (supported)

When environment passes extra as None, _normalize calls canonicalize_name on None (or on a value that is None), which expects str or bytes-like object and raises TypeError.

- Predicts: If environment["extra"] is None, normalizing it or comparing it without checking for None or handling None causes a TypeError. If we handle None by treating it or converting it, or if canonicalize_name / _normalize handles None (or if values can be None), it won't raise TypeError and will evaluate to False (or handle comparison properly).
- Evidence: Running python code with Marker('extra == "opt-feature"').evaluate({"extra": None}) raises TypeError: expected string or bytes-like object, got 'NoneType' in _normalize / canonicalize_name. (tool calls 12, 13)

### H2 (supported)

Environment values in markers can be None (specifically extra can be None). _normalize assumes all values for key == "extra" are strings and passes them to canonicalize_name.

- Predicts: If we check for `v is None` in `_normalize` (or if `environment["extra"]` or any value being normalized for extra is None), we can return `None` (or handle it so comparison proceeds or evaluates to False).
- Evidence: _normalize calls canonicalize_name(v) on values when key == "extra", but when environment provides extra as None, v can be None. (tool calls 12, 13)

## Patch

```diff
diff --git a/src/packaging/markers.py b/src/packaging/markers.py
index a5bf35c..9731b32 100644
--- a/src/packaging/markers.py
+++ b/src/packaging/markers.py
@@ -115,13 +115,13 @@ def _eval_op(lhs: str, op: Op, rhs: str) -> bool:
     return oper(lhs, rhs)
 
 
-def _normalize(*values: str, key: str) -> Tuple[str, ...]:
+def _normalize(*values: Any, key: str) -> Tuple[Any, ...]:
     # PEP 685 – Comparison of extra names for optional distribution dependencies
     # https://peps.python.org/pep-0685/
     # > When comparing extra names, tools MUST normalize the names being
     # > compared using the semantics outlined in PEP 503 for names
     if key == "extra":
-        return tuple(canonicalize_name(v) for v in values)
+        return tuple(canonicalize_name(v) if v is not None else v for v in values)
 
     # other environment markers don't have such standards
     return values
```

## Verification

- Call 34: `run_python (Marker('extra == "opt-feature"').evaluate({"extra": None}))`: False
- Call 33: `run_tests (tests/test_markers.py)`: 2221 passed

## Evidence

### Call 12: record_hypothesis

Arguments: `{"text": "Environment values in markers can be None (specifically extra can be None). _normalize assumes all values for key == \"extra\" are strings and passes them to canonicalize_name.", "predicts": "If we check for `v is None` in `_normalize` (or if `environment[\"extra\"]` or any value being nor`

```
recorded H2
```

### Call 13: run_python

Arguments: `{"code": "from packaging.markers import Marker\nmarker = Marker('extra == \"opt-feature\"')\ntry:\n    print(marker.evaluate({\"extra\": None}))\nexcept Exception as e:\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Traceback (most recent call last):
  File "<string>", line 4, in <module>
    print(marker.evaluate({"extra": None}))
          ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
  File "/work/src/packaging/markers.py", line 241, in evaluate
    return _evaluate_markers(self._markers, current_environment)
  File "/work/src/packaging/markers.py", line 150, in _evaluate_markers
    lhs_value, rhs_value = _no
```

### Call 33: apply_edit

Arguments: `{"search": "def _normalize(*values: str, key: str) -> Tuple[str, ...]:\n    # PEP 685 \u2013 Comparison of extra names for optional distribution dependencies\n    # https://peps.python.org/pep-0685/\n    # > When comparing extra names, tools MUST normalize the names being\n    # > compared using the`

```
applied edit 1 to src/packaging/markers.py. Run tests to check it.
```

### Call 34: run_tests

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

