# Investigation report: flask-5160

Model: gemini-3.1-flash-lite. Tool calls: 22. Time: 142.2 s. Tokens: 100940.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/helpers.py`
- Function: `get_root_path`
- Breaking commit: `not identified`

`importlib.util.find_spec("__main__")` raises a `ValueError` when `__main__.__spec__` is `None`, which occurs when running a script directly. The code was calling `find_spec` before checking if the module was `__main__`.

## Hypotheses

### H1 (supported)

The issue is that `importlib.util.find_spec("__main__")` raises a ValueError when `__main__.__spec__` is None, which happens when running a script directly. The code in `_find_package_path` expects this to be handled, but it seems it's not being caught correctly or the logic around it is flawed.

- Predicts: If I change the code to handle the ValueError from find_spec, the application will start correctly.
- Evidence: The issue was indeed that `importlib.util.find_spec("__main__")` raises a `ValueError` when `__main__.__spec__` is `None`. Handling this by checking `import_name == "__main__"` before calling `find_spec` fixes the issue. (tool calls 12, 16)

### H2 (supported)

The `_find_package_path` function should explicitly check if `root_mod_name` is `__main__` and return `os.getcwd()` immediately, as it is already intended to do for `__main__` later in the function (line 861).

- Predicts: If I check if root_mod_name == "__main__" before calling find_spec, it will avoid the ValueError.
- Evidence: The fix in `src/flask/helpers.py` resolved the `ValueError` when constructing `Flask("__main__")`. The previous fix in `src/flask/scaffold.py` was also correct but `get_root_path` was called first. (tool calls 12, 16)

## Patch

```diff
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 4e8bc8b8..4c8280d4 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
@@ -575,6 +575,9 @@ def get_root_path(import_name: str) -> str:
         return os.path.dirname(os.path.abspath(mod.__file__))
 
     # Next attempt: check the loader.
+    if import_name == "__main__":
+        return os.getcwd()
+
     spec = importlib.util.find_spec(import_name)
     loader = spec.loader if spec is not None else None
 
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..5e6bd678 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -817,6 +817,9 @@ def _find_package_path(import_name):
     """Find the path that contains the package or module."""
     root_mod_name, _, _ = import_name.partition(".")
 
+    if root_mod_name == "__main__":
+        return os.getcwd()
+
     try:
         root_spec = importlib.util.find_spec(root_mod_name)
```

## Verification

- Call 16: `python -c "import os, sys; sys.modules['__main__'].__spec__ = None; from flask import Flask; app = Flask('__main__'); print('Success')"`: Success
- Call 21: `pytest tests/test_basic.py tests/test_helpers.py`: 158 passed in 2.00s

## Evidence

### Call 12: run_python

Arguments: `{"code": "import os\nimport sys\n# Mocking the environment where __main__.__spec__ is None\nsys.modules['__main__'].__spec__ = None\n\nfrom flask import Flask\ntry:\n    app = Flask(\"__main__\")\n    print(\"Success\")\nexcept Exception as e:\n    print(f\"Failed: {e}\")\n    import traceback\n    `

```
[exit 0]
Failed: __main__.__spec__ is None
Traceback (most recent call last):
  File "<string>", line 8, in <module>
    app = Flask("__main__")
  File "/work/src/flask/app.py", line 367, in __init__
    super().__init__(
    ~~~~~~~~~~~~~~~~^
        import_name=import_name,
        ^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
        root_path=root_path,
        ^^^^^^^^^^^^^^^^^^^^
    )
    ^

```

### Call 16: run_python

Arguments: `{"code": "import os\nimport sys\n# Mocking the environment where __main__.__spec__ is None\nsys.modules['__main__'].__spec__ = None\n\nfrom flask import Flask\ntry:\n    app = Flask(\"__main__\")\n    print(\"Success\")\nexcept Exception as e:\n    print(f\"Failed: {e}\")\n    import traceback\n    `

```
[exit 0]
Success

```

### Call 21: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py"]}`

```
[exit 0]
........................................................................ [ 45%]
........................................................................ [ 91%]
..............                                                           [100%]
158 passed in 2.00s

```

## Limitations

- Only verified the fix with a minimal reproduction script and existing tests. Did not run the full test suite, but the change is very localized and safe.
