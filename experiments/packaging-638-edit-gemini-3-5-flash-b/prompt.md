You are repairing a Python regression. You have only the bug report, stack
trace, and source excerpt below. Do not assume access to the rest of the repository, tests, Git history, or any
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

## Source excerpt

Unmodified code of the functions named in the stack trace:

```python
# src/packaging/markers.py (lines 227-241)
    def evaluate(self, environment: Optional[Dict[str, str]] = None) -> bool:
        """Evaluate a marker.

        Return the boolean from evaluating the given marker against the
        environment. environment is an optional argument to override all or
        part of the determined environment.

        The environment is determined from the current Python process.
        """
        current_environment = default_environment()
        current_environment["extra"] = ""
        if environment is not None:
            current_environment.update(environment)

        return _evaluate_markers(self._markers, current_environment)

# src/packaging/markers.py (lines 130-157)
def _evaluate_markers(markers: MarkerList, environment: Dict[str, str]) -> bool:
    groups: List[List[bool]] = [[]]

    for marker in markers:
        assert isinstance(marker, (list, tuple, str))

        if isinstance(marker, list):
            groups[-1].append(_evaluate_markers(marker, environment))
        elif isinstance(marker, tuple):
            lhs, op, rhs = marker

            if isinstance(lhs, Variable):
                environment_key = lhs.value
                lhs_value = environment[environment_key]
                rhs_value = rhs.value
            else:
                lhs_value = lhs.value
                environment_key = rhs.value
                rhs_value = environment[environment_key]

            lhs_value, rhs_value = _normalize(lhs_value, rhs_value, key=environment_key)
            groups[-1].append(_eval_op(lhs_value, op, rhs_value))
        else:
            assert marker in ["and", "or"]
            if marker == "or":
                groups.append([])

    return any(all(item) for item in groups)

# src/packaging/markers.py (lines 118-127)
def _normalize(*values: str, key: str) -> Tuple[str, ...]:
    # PEP 685 – Comparison of extra names for optional distribution dependencies
    # https://peps.python.org/pep-0685/
    # > When comparing extra names, tools MUST normalize the names being
    # > compared using the semantics outlined in PEP 503 for names
    if key == "extra":
        return tuple(canonicalize_name(v) for v in values)

    # other environment markers don't have such standards
    return values

# src/packaging/utils.py (lines 32-35)
def canonicalize_name(name: str) -> NormalizedName:
    # This is taken from PEP 503.
    value = _canonicalize_regex.sub("-", name).lower()
    return cast(NormalizedName, value)
```
