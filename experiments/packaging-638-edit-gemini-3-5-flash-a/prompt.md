You are repairing a Python regression. You have only the bug report, stack
trace below. Do not assume access to the rest of the repository, tests, Git history, or any
other tools.

Return your fix as edits inside exactly one fenced code block whose info string
is `edit`. Each edit has this exact form:

```edit
FILE: src/example/module.py
<<<<<<< SEARCH
exact original lines, copied character for character including indentation
=======
the replacement lines
>>>>>>> REPLACE
```

The SEARCH text must match the original code exactly and occur exactly once in
that file. You may put several edits inside the one block. Edits may modify only
files under `src/`. Do not modify, add, or delete tests, dependency files,
configuration, or generated files. Do not include prose outside the code block.

## Bug report

Evaluating a marker that mentions `extra` raises a TypeError when the environment
passes `extra` as `None`. This used to return `False`.

```python
from packaging.markers import Marker

marker = Marker('extra == "opt-feature"')
print(marker.evaluate({"extra": None}))
```

Expected behavior: `False` is printed. Existing callers pass `None` for `extra`
when no extra is being evaluated.

## Stack trace

```text
Traceback (most recent call last):
  File "reproduce.py", line 5, in <module>
    result = marker.evaluate({"extra": None})
  File "src/packaging/markers.py", line 241, in evaluate
    return _evaluate_markers(self._markers, current_environment)
  File "src/packaging/markers.py", line 150, in _evaluate_markers
    lhs_value, rhs_value = _normalize(lhs_value, rhs_value, key=environment_key)
  File "src/packaging/markers.py", line 124, in _normalize
    return tuple(canonicalize_name(v) for v in values)
  File "src/packaging/markers.py", line 124, in <genexpr>
    return tuple(canonicalize_name(v) for v in values)
  File "src/packaging/utils.py", line 34, in canonicalize_name
    value = _canonicalize_regex.sub("-", name).lower()
TypeError: expected string or bytes-like object, got 'NoneType'
```
