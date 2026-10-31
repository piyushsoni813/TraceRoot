# Investigation report: packaging-638

Model: gemini-3.1-flash-live-preview. Tool calls: 22. Time: 25.9 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/packaging/markers.py`
- Function: `_normalize`
- Breaking commit: `53dbb257e5fef150d32ef85c7427133d71651989`

The _normalize function was introduced to normalize 'extra' marker values using canonicalize_name. However, it did not account for the case where 'extra' is passed as None in the environment, causing canonicalize_name to raise a TypeError because it expects a string.

## Hypotheses

### H1 (supported)

The bug is caused by `_normalize` calling `canonicalize_name` on `None` when `extra` is `None` in the environment. This was introduced by commit 53dbb25 which added normalization for `extra`.

- Predicts: The reproduction script will fail with TypeError. Modifying `src/packaging/markers.py` to handle `None` in `_normalize` will fix the issue.
- Evidence: The reproduction script confirms the TypeError. Git history shows that commit 53dbb25 introduced _normalize which calls canonicalize_name. When extra is None, canonicalize_name fails. (tool calls 5, 13)

### H2 (rejected)

The bug is caused by `canonicalize_name` not handling `None` input. Although `_normalize` passes the value, `canonicalize_name` should be robust.

- Predicts: The reproduction script will fail with TypeError. Modifying `src/packaging/utils.py` to handle `None` in `canonicalize_name` will fix the issue.
- Evidence: canonicalize_name is defined to take a str, so passing None is incorrect usage by the caller. Fixing it in markers.py is more appropriate. (tool calls 5, 4)

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

- Call 5: `run_python reproduction script`: TypeError: expected string or bytes-like object, got 'NoneType'
- Call 20: `run_python reproduction script after fix`: False
- Call 21: `run_tests tests/test_markers.py`: 2221 passed

## Evidence

### Call 4: read_file

Arguments: `{"path": "src/packaging/utils.py"}`

```
1	# This file is dual licensed under the terms of the Apache License, Version
2	# 2.0, and the BSD License. See the LICENSE file in the root of this repository
3	# for complete details.
4	
5	import re
6	from typing import FrozenSet, NewType, Tuple, Union, cast
7	
8	from .tags import Tag, parse_tag
9	from .version import InvalidVersion, Version
10	
11	BuildTag = Union[Tuple[()], Tuple[int, str]]
12
```

### Call 5: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\ntry:\n    marker = Marker('extra == \"opt-feature\"')\n    print(marker.evaluate({\"extra\": None}))\nexcept Exception as e:\n    print(e)\n"}`

```
[exit 0]
expected string or bytes-like object, got 'NoneType'

```

### Call 13: git_show

Arguments: `{"rev": "53dbb25"}`

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

### Call 20: run_python

Arguments: `{"code": "from packaging.markers import Marker\n\ntry:\n    marker = Marker('extra == \"opt-feature\"')\n    print(marker.evaluate({\"extra\": None}))\nexcept Exception as e:\n    print(e)\n"}`

```
[exit 0]
False

```

### Call 21: run_tests

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

