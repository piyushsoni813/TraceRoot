# Investigation report: packaging-638

Model: gemini-3.5-flash-lite. Tool calls: 34. Time: 160.0 s. Tokens: 428353.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `not identified`

When evaluating markers where `key == "extra"` and the environment provides `extra` as `None`, `_normalize()` called `canonicalize_name(v)` directly on `None`, which raised a `TypeError` because `canonicalize_name` expects a string. Treating `None` as an empty string (`""`) in `_normalize` when normalizing extra values allows evaluation to proceed successfully and return `False`, matching expectations and behavior when no extra is specified.

## Hypotheses

### H1 (supported)

When `extra` is `None` in the environment dictionary passed to `Marker.evaluate()`, `_normalize()` attempts to call `canonicalize_name(v)` on `None`, which raises a `TypeError`. Instead, `None` (or falsy / missing / None extra) should be handled or treated appropriately (e.g. as empty string or non-matching or handled gracefully so it evaluates to False without raising TypeError).

- Predicts: If environment has extra as None, or if we handle None in _normalize or when evaluating environment values, what happens? Let's check how other values in environment are treated or what callers expect.
- Evidence: Running python snippet with marker.evaluate({"extra": None}) raised TypeError: expected string or bytes-like object, got 'NoneType' in canonicalize_name. (tool calls 9)

### H2 (supported)

The bug report states: 'Evaluating a marker that mentions `extra` raises a TypeError when the environment passes `extra` as `None`. This used to return `False`.' If `extra` is `None`, evaluating `extra == "opt-feature"` should evaluate to `False` instead of raising TypeError.

- Predicts: If `environment["extra"]` can be `None`, should `None` be normalized to `""` or should `None` be treated as not matching / empty string or handled in `_normalize` / environment population / comparison? Wait, what did packaging do previously or what does the bug report say?
- Evidence: The bug report and reproduction confirm that passing {"extra": None} raises TypeError because canonicalize_name expects a string/bytes object. (tool calls 9)

### H3 (supported)

If `environment` passes `extra` as `None`, handling `None` in `_normalize` (or when setting up environment / normalizing extra values) so that `None` is treated as `""` (empty string) or not raising TypeError and returning `False` for `extra == ...` will fix the issue and match existing expectations (where no extra is being evaluated).

- Predicts: If `v` is `None` (or not a string) when `key == "extra"`, what should `_normalize` or `canonicalize_name` do? Or should `_normalize` handle `None` (or convert `None` to `""` or something, or should `canonicalize_name` or `_normalize` accept `None` / handle `None`? Wait, let's check what `environment` values can be, or what `None` means for `extra`). If `extra` is `None`, what should it be normalized to? Or should `None` remain `None` or become `""` or what? Wait, what does `extra` equal when `extra` is `None`? If `extra` is `None`, can it match `"opt-feature"`? No, it should return `False` (which means it should not equal `"opt-feature"`). If `None` is normalized to `""` (or if `None` is handled), `"" == "opt-feature"` is `False`. Wait, what if the comparison is `extra != "opt-feature"`? If `extra` is `None`, `extra != "opt-feature"` should be `True` (since no extra is being evaluated, so it's not `"opt-feature"`). If `extra` is `None`, treating `None` as `""` (empty string) means `extra` is treated as empty extra (no extra), which is what `Marker.evaluate()` does when no environment is passed (`current_environment["extra"] = ""`).
Wait, let's check if `None` in `environment` for `extra` should be treated as `""` or if `_normalize` (or environment setup) should convert `None` to `""` or handle `None`.
Wait! What if other environment keys are passed as `None` or what does PEP / packaging expect?
Let's check `tests/test_markers.py` to see how environment and `extra` are tested.
- Evidence: `_normalize` is where `key == "extra"` is checked and `canonicalize_name` is called on values. If `v` is `None` (or if `environment["extra"]` is `None`), what should `_normalize` do? If `v` is `None`, should it be treated as `""` or handled? Wait, what if someone passes `{"extra": None}` or `extra` evaluates to `None`? If `v` is `None`, what should `canonicalize_name(v)` do or how should `_normalize` handle `None`? Wait, if `v` is `None`, can an extra be `None`? If `extra` is `None`, does that mean no extra, or should `v` be converted to `""` or `"" if v is None else canonicalize_name(v)`? Wait, what if `v` is not a string (e.g. `None`)? Let's check what `_normalize` receives: `values` can come from environment (`lhs_value` or `rhs_value`) or parsed marker (`rhs.value` or `lhs.value`).
In `extra == "opt-feature"`, `lhs` is Variable("extra") (so `environment_key = "extra"`, `lhs_value = environment["extra"]`), and `rhs` is Value("opt-feature") (`rhs_value = "opt-feature"`).
If `environment["extra"]` is `None`, `lhs_value` is `None`. `rhs_value` is `"opt-feature"`.
`_normalize(None, "opt-feature", key="extra")` is called.
If `key == "extra"`, `v` could be `None` or a string.
If `v is None`, what should `canonicalize_name` or `_normalize` do?
If `_normalize` maps `None` to `""` (or `v if v is not None else ""` or similar, or `v or ""`? Wait, is `""` falsy? What if an extra name is `""`? Well, empty string `""` is the default extra when no extra is specified. If `v` is `None`, it also represents no extra, so treating `None` as `""` (or normalizing `None` to `""`) means `None` behaves like `""`).
Wait, what if `v` is `None` vs `""`? If `v is None`, `canonicalize_name(v)` fails. If `v` is `None`, should `_normalize` return `""` or should `canonicalize_name` handle `None` or should `_normalize` do:
```python
    if key == "extra":
        return tuple(canonicalize_name(v) if v is not None else "" for v in values)
```
Wait, what if `v` is `None` in `environment` for other keys? Other keys don't use `_normalize` (or `_normalize` just returns `values` if `key != "extra"`). But wait, what if someone passes `{"os_name": None}`? Does environment expect strings? Type annotation of environment is `Dict[str, str]`, but users might pass `None` for `extra` (as explicitly noted in the bug report: "Existing callers pass `None` for `extra` when no extra is being evaluated").
Let's re-read the bug report:
"Evaluating a marker that mentions `extra` raises a TypeError when the environment passes `extra` as `None`. This used to return `False`.
...
Expected behavior: `False` is printed. Existing callers pass `None` for `extra` when no extra is being evaluated."
 (tool calls 19)

### H4 (supported)

Checking usages of `canonicalize_name` across the codebase will reveal whether `canonicalize_name` expects strings or if handling `None` should be inside `_normalize` or `canonicalize_name`.

- Predicts: Alternatively, what if `_normalize` checks `if v is None:` or similar? Or what if `canonicalize_name` handles `None` or raises / converts? Wait, does `canonicalize_name` accept non-strings in other contexts or is `canonicalize_name` strictly for package/extra names? Let's check where `canonicalize_name` is used across the codebase.
- Evidence: `canonicalize_name` takes `name: str` and is used for package/wheel/sdist names and marker extra normalization. It expects a string. (tool calls 16)

## Patch

```diff
diff --git a/src/packaging/markers.py b/src/packaging/markers.py
index a5bf35c..fa2454e 100644
--- a/src/packaging/markers.py
+++ b/src/packaging/markers.py
@@ -121,7 +121,7 @@ def _normalize(*values: str, key: str) -> Tuple[str, ...]:
     # > When comparing extra names, tools MUST normalize the names being
     # > compared using the semantics outlined in PEP 503 for names
     if key == "extra":
-        return tuple(canonicalize_name(v) for v in values)
+        return tuple(canonicalize_name(v) if v is not None else "" for v in values)
 
     # other environment markers don't have such standards
     return values
```

## Verification

- Call 33: `python snippet evaluation with {"extra": None}`: False
- Call 29: `pytest tests/test_markers.py`: 2221 passed

## Evidence

### Call 9: run_python

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

### Call 16: search

Arguments: `{"regex": "canonicalize_name"}`

```
./CHANGELOG.rst:110:* Change type hint for ``canonicalize_name`` to return
./docs/utils.rst:17:.. function:: canonicalize_name(name)
./docs/utils.rst:30:        >>> from packaging.utils import canonicalize_name
./docs/utils.rst:31:        >>> canonicalize_name("Django")
./docs/utils.rst:33:        >>> canonicalize_name("oslo.concurrency")
./docs/utils.rst:35:        >>> canonicalize_name("requests
```

### Call 19: read_file

Arguments: `{"path": "tests/test_markers.py", "end": 300, "start": 250}`

```
250	        assert hash(marker1) != hash(marker2)
251	
252	    def test_compare_markers_to_other_objects(self):
253	        # Markers should not be comparable to other kinds of objects.
254	        assert Marker("os_name == 'nt'") != "os_name == 'nt'"
255	
256	    def test_environment_assumes_empty_extra(self):
257	        assert Marker('extra == "im_valid"').evaluate() is False
258	
259	    @pyte
```

### Call 29: run_tests

Arguments: `{"selection": ["tests/test_markers.py"]}`

```
[exit 0]
........................................................................ [  3%]
........................................................................ [  6%]
........................................................................ [  9%]
........................................................................ [ 12%]
.......................................................................
```

### Call 33: run_python

Arguments: `{"code": "from packaging.markers import Marker\nmarker = Marker('extra == \"opt-feature\"')\nprint(marker.evaluate({\"extra\": None}))\n"}`

```
[exit 0]
False

```

## Limitations

- None
