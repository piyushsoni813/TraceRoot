# Investigation report: flask-5160

Model: gemini-3.1-flash-lite. Tool calls: 24. Time: 121.3 s. Tokens: 116144.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/scaffold.py`
- Function: `_find_package_path`
- Breaking commit: `not identified`

The function `_find_package_path` calls `importlib.util.find_spec` twice. The second call was not wrapped in a try-except block, causing a `ValueError` when `__main__.__spec__` is `None` (which occurs in direct script execution). The fix wraps the second call in a try-except block to handle this case.

## Hypotheses

### H1 (rejected)

The `importlib.util.find_spec("__main__")` call raises a `ValueError` when `__main__.__spec__` is `None`, which happens in a direct script execution. The current code catches `ValueError` but it seems it might be failing to handle it correctly or the `ValueError` is being raised in a way that isn't caught as expected, or it's being re-raised. Wait, the stack trace says it's raised at `importlib.util.find_spec(root_mod_name)`. The `try...except` block in `_find_package_path` *does* catch `ValueError`. Let me re-read the stack trace.

- Predicts: If I change the code to handle `ValueError` from `importlib.util.find_spec` by returning `os.getcwd()`, the error will be resolved.
- Evidence: The first call is wrapped, but the second one is not, and the second one is where the crash happens. H1 is rejected because the `ValueError` *is* caught in the first block, but the code proceeds to a second call that is *not* caught. Wait, H1 said "If I change the code to handle `ValueError` from `importlib.util.find_spec` by returning `os.getcwd()`, the error will be resolved." This is technically true, but the *reason* it fails is because the second call is not wrapped. So H1 is partially correct but H2 is more precise. I will mark H1 as rejected because it misidentified *where* the handling was missing. Actually, I'll just mark it rejected. (tool calls 14)

### H2 (supported)

The second call to `importlib.util.find_spec(root_mod_name)` at line 858 is not wrapped in a try-except block, and it raises a `ValueError` when `root_mod_name` is `__main__`. This is why it fails. The first call is wrapped, but the second one is not.

- Predicts: If I wrap the second `importlib.util.find_spec` call in a try-except block, the error will be resolved.
- Evidence: The second call to `importlib.util.find_spec` at line 858 is indeed not wrapped in a try-except block, and it raises the `ValueError` as observed in the stack trace and confirmed by the reproduction script. (tool calls 14)

## Patch

```diff
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..cd4a7882 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -855,7 +855,10 @@ def _find_package_path(import_name):
             return os.path.dirname(root_spec.origin)
 
     # we were unable to find the `package_path` using PEP 451 loaders
-    spec = importlib.util.find_spec(root_mod_name)
+    try:
+        spec = importlib.util.find_spec(root_mod_name)
+    except ValueError:
+        spec = None
     loader = spec.loader if spec is not None else None
 
     if loader is None or root_mod_name == "__main__":
```

## Verification

- Call 19: `run_python with a reproduction script that mocks `__main__.__spec__ = None``: Path: /work
- Call 22: `run_tests tests/test_basic.py`: 127 passed in 3.02s
- Call 23: `run_tests tests/test_regression.py`: 1 passed in 0.76s

## Evidence

### Call 14: run_python

Arguments: `{"code": "import importlib.util\nimport os\n\ndef _find_package_path(import_name):\n    root_mod_name, _, _ = import_name.partition(\".\")\n    try:\n        root_spec = importlib.util.find_spec(root_mod_name)\n        if root_spec is None:\n            raise ValueError(\"not found\")\n    except (I`

```
[exit 1]
Caught expected exception
Calling find_spec again
Traceback (most recent call last):
  File "<string>", line 23, in <module>
    _find_package_path("__main__")
    ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
  File "<string>", line 19, in _find_package_path
    spec = importlib.util.find_spec(root_mod_name)
  File "<frozen importlib.util>", line 111, in find_spec
ValueError: __main__.__spec__ is None

```

### Call 19: run_python

Arguments: `{"code": "import importlib.util\nimport os\nimport sys\n\n# Mocking the environment\nsys.modules['__main__'].__spec__ = None\n\n# Import the function from the modified file\nimport flask.scaffold\ntry:\n    path = flask.scaffold._find_package_path(\"__main__\")\n    print(f\"Path: {path}\")\nexcept `

```
[exit 0]
Path: /work

```

### Call 22: run_tests

Arguments: `{"selection": ["tests/test_basic.py"]}`

```
[exit 0]
........................................................................ [ 56%]
.......................................................                  [100%]
127 passed in 3.02s

```

### Call 23: run_tests

Arguments: `{"selection": ["tests/test_regression.py"]}`

```
[exit 0]
.                                                                        [100%]
1 passed in 0.76s

```

## Limitations

- I have not run the full test suite, only a few relevant files. Given the nature of the fix, it is unlikely to affect other parts of the system, but it's a limitation.
