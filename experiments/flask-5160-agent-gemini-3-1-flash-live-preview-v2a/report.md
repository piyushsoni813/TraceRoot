# Investigation report: flask-5160

Model: gemini-3.1-flash-live-preview. Tool calls: 38. Time: 61.0 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/scaffold.py, src/flask/helpers.py`
- Function: `_find_package_path, get_root_path`
- Breaking commit: `84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`

The commit replaced `pkgutil.get_loader` with `importlib.util.find_spec`. When running a script directly, `__name__` is `"__main__"`. If `sys.modules["__main__"].__spec__` is `None` (which is common when running scripts directly), `importlib.util.find_spec("__main__")` raises `ValueError: __main__.__spec__ is None`. This caused `Flask(__name__)` to fail during initialization.

## Hypotheses

### H1 (rejected)

The recent change replaced `pkgutil.get_loader(root_mod_name)` with `importlib.util.find_spec(root_mod_name)`. When `root_mod_name` is `"__main__"`, `find_spec` raises `ValueError` if `sys.modules["__main__"].__spec__` is `None`. This happens when running a script directly. Previously `pkgutil.get_loader("__main__")` did not raise this error.

- Predicts: Running a script that calls `Flask(__name__)` will fail with `ValueError: __main__.__spec__ is None` when `__spec__` is not set on `__main__`.
- Evidence: H2 is supported, which is essentially the same as H1 but more precise about the location. (tool calls 11)

### H2 (supported)

The recent change introduced a call to `importlib.util.find_spec(root_mod_name)` at line 858. When `root_mod_name` is `"__main__"`, `find_spec` raises `ValueError` if `sys.modules["__main__"].__spec__` is `None`. This happens when running a script directly. The previous code using `pkgutil.get_loader` did not have this issue.

- Predicts: Running a script that calls `Flask(__name__)` will fail with `ValueError: __main__.__spec__ is None` when `__spec__` is not set on `__main__`.
- Evidence: Running Flask('__main__') with sys.modules['__main__'].__spec__ = None reproduced the ValueError. (tool calls 11)

## Patch

```diff
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 4e8bc8b8..f370e61e 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
@@ -575,7 +575,15 @@ def get_root_path(import_name: str) -> str:
         return os.path.dirname(os.path.abspath(mod.__file__))
 
     # Next attempt: check the loader.
-    spec = importlib.util.find_spec(import_name)
+    if import_name == "__main__":
+        spec = None
+    else:
+        try:
+            spec = importlib.util.find_spec(import_name)
+        except ValueError:
+            # __main__.__spec__ is None
+            spec = None
+
     loader = spec.loader if spec is not None else None
 
     # Loader does not exist or we're referring to an unloaded main
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..4343827f 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -817,15 +817,21 @@ def _find_package_path(import_name):
     """Find the path that contains the package or module."""
     root_mod_name, _, _ = import_name.partition(".")
 
-    try:
-        root_spec = importlib.util.find_spec(root_mod_name)
+    if root_mod_name == "__main__":
+        root_spec = None
+    else:
+        try:
+            root_spec = importlib.util.find_spec(root_mod_name)
+        except ValueError:
+            # __main__.__spec__ is None
+            root_spec = None
 
+    try:
         if root_spec is None:
             raise ValueError("not found")
     # ImportError: the machinery told us it does not exist
     # ValueError:
     #    - the module name was invalid
-    #    - the module name is __main__
     #    - *we* raised `ValueError` due to `root_spec` being `None`
     except (ImportError, ValueError):
         pass  # handled below
@@ -855,7 +861,15 @@ def _find_package_path(import_name):
             return os.path.dirname(root_spec.origin)
 
     # we were unable to find the `package_path` using PEP 451 loaders
-    spec = importlib.util.find_spec(root_mod_name)
+    if root_mod_name == "__main__":
+        spec = None
+    else:
+        try:
+            spec = importlib.util.find_spec(root_mod_name)
+        except ValueError:
+            # __main__.__spec__ is None
+            spec = None
+
     loader = spec.loader if spec is not None else None
 
     if loader is None or root_mod_name == "__main__":
```

## Verification

- Call 30: `run_python reproduction script`: Caught ValueError: __main__.__spec__ is None
Traceback (most recent call last):
...
  File "/work/src/flask/scaffold.py", line 98, in __init__
    root_path = get_root_path(self.import_name)
  File "/work/src/flask/helpers.py", line 578, in get_root_path
    spec = importlib.util.find_spec(import_name)
  File "<frozen importlib.util>", line 111, in find_spec
ValueError: __main__.__spec__ is None
- Call 34: `run_python reproduction script after fix`: Success
Instance path: /work/instance
- Call 37: `run_tests tests/test_basic.py tests/test_helpers.py`: 158 passed

## Evidence

### Call 11: run_python

Arguments: `{"code": "import sys\nfrom flask import Flask\n\n# Simulate running as a script\nsys.modules['__main__'].__spec__ = None\n\ntry:\n    app = Flask('__main__')\n    print(\"Success\")\nexcept ValueError as e:\n    print(f\"Caught expected ValueError: {e}\")\nexcept Exception as e:\n    print(f\"Caught`

```
[exit 0]
Caught expected ValueError: __main__.__spec__ is None

```

### Call 30: run_python

Arguments: `{"code": "import sys\nimport os\n\n# Add src to sys.path so we can import flask\nsys.path.insert(0, os.path.abspath('src'))\n\nfrom flask import Flask\n\n# Simulate running as a script\nsys.modules['__main__'].__spec__ = None\n\ntry:\n    app = Flask('__main__')\n    print(\"Success\")\n    print(f\`

```
[exit 0]
Caught ValueError: __main__.__spec__ is None
Traceback (most recent call last):
  File "<string>", line 13, in <module>
    app = Flask('__main__')
  File "/work/src/flask/app.py", line 367, in __init__
    super().__init__(
    ~~~~~~~~~~~~~~~~^
        import_name=import_name,
        ^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
        root_path=root_path,
        ^^^^^^^^^^^^^^^^^^^^

```

### Call 34: run_python

Arguments: `{"code": "import sys\nimport os\n\n# Add src to sys.path so we can import flask\nsys.path.insert(0, os.path.abspath('src'))\n\nfrom flask import Flask\n\n# Simulate running as a script\nsys.modules['__main__'].__spec__ = None\n\ntry:\n    app = Flask('__main__')\n    print(\"Success\")\n    print(f\`

```
[exit 0]
Success
Instance path: /work/instance

```

### Call 37: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py"]}`

```
[exit 0]
........................................................................ [ 45%]
........................................................................ [ 91%]
..............                                                           [100%]
158 passed in 1.89s

```

## Limitations

