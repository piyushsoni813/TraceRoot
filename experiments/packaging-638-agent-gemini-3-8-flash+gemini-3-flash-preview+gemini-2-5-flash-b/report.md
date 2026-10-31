# Investigation report: packaging-638

Model: gemini-3.8-flash,gemini-3-flash-preview,gemini-2.5-flash. Tool calls: 17. Time: 96.0 s. Tokens: 53302.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `1aa82a856a1d6fbc7b111b4896a2fd28c7cdccc5`

The `_normalize` function, introduced in commit 53dbb257, calls `canonicalize_name` on values when the key is "extra". Commit 1aa82a85 removed the `_get_env` function, which previously handled `None` values by raising an `UndefinedEnvironmentName` exception. This change allowed `None` to be passed directly to `_normalize` for the "extra" key, which then passed `None` to `canonicalize_name`. `canonicalize_name` expects a string or bytes-like object, but received `NoneType`, leading to a TypeError.

## Hypotheses

### H1 (supported)

The _normalize function was recently changed to call canonicalize_name without checking for None values.

- Predicts: git_blame on src/packaging/markers.py lines 118-127 will show a recent commit that introduced the call to canonicalize_name or removed a None check.
- Evidence: git_blame (call 7) shows commit 53dbb257 introduced _normalize and the call to canonicalize_name. git_show (call 9) confirms that _normalize does not check for None. (tool calls 7, 9)

### H2 (supported)

The _evaluate_markers function was recently changed to pass None to _normalize for the "extra" key.

- Predicts: git_blame on src/packaging/markers.py lines 143-150 will show a recent commit that changed how lhs_value or rhs_value are assigned, allowing None for "extra".
- Evidence: git_blame (call 8) shows commit 1aa82a85 changed how environment variables are accessed. git_show (call 10) confirms that _get_env was removed, allowing None to be passed directly to _normalize. (tool calls 8, 10)

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

- Call 16: `run_tests(selection = ["tests/test_markers.py"])`: 2221 passed in 3.99s

## Evidence

### Call 7: git_blame

Arguments: `{"end": 127, "path": "src/packaging/markers.py", "start": 118}`

```
53dbb257 packaging/markers.py (Miro Hrončok    2022-05-12 08:34:23 +0200 118) def _normalize(*values: str, key: str) -> Tuple[str, ...]:
53dbb257 packaging/markers.py (Miro Hrončok    2022-05-12 08:34:23 +0200 119)     # PEP 685 – Comparison of extra names for optional distribution dependencies
53dbb257 packaging/markers.py (Miro Hrončok    2022-05-12 08:34:23 +0200 120)     # https://peps.python.
```

### Call 8: git_blame

Arguments: `{"end": 150, "path": "src/packaging/markers.py", "start": 143}`

```
1aa82a85 packaging/markers.py (Blazej Michalik 2022-06-02 17:04:32 +0200 143)                 lhs_value = environment[environment_key]
6b67f7fd packaging/markers.py (Donald Stufft   2016-01-19 09:42:16 -0500 144)                 rhs_value = rhs.value
821690a7 packaging/markers.py (Donald Stufft   2015-11-09 21:55:38 -0500 145)             else:
6b67f7fd packaging/markers.py (Donald Stufft   2016-0
```

### Call 9: git_show

Arguments: `{"rev": "53dbb257"}`

```
53dbb257e5fef150d32ef85c7427133d71651989
Miro Hrončok 2022-05-12

Adhere to PEP 685 when evaluating markers with extras (#545)

PEP: https://peps.python.org/pep-0685/
Original problem: https://discuss.python.org/t/7614

diff --git a/packaging/markers.py b/packaging/markers.py
index 3990514..03d8cde 100644
--- a/packaging/markers.py
+++ b/packaging/markers.py
@@ -21,6 +21,7 @@ from pyparsing import
```

### Call 10: git_show

Arguments: `{"rev": "1aa82a85"}`

```
1aa82a856a1d6fbc7b111b4896a2fd28c7cdccc5
Blazej Michalik 2022-06-02

Evaluate markers under environment with empty "extra" (#550)

Co-authored-by: Pradyun Gedam <pradyunsg@gmail.com>

diff --git a/CHANGELOG.rst b/CHANGELOG.rst
index 214326e..23b85d1 100644
--- a/CHANGELOG.rst
+++ b/CHANGELOG.rst
@@ -4,7 +4,9 @@ Changelog
 *unreleased*
 ~~~~~~~~~~~~
 
-No unreleased changes.
+* ``Marker.evaluate`` 
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

