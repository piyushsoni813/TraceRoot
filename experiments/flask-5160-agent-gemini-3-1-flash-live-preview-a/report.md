# Investigation report: flask-5160

Model: gemini-3.1-flash-live-preview. Tool calls: 20. Time: 36.0 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/helpers.py, src/flask/scaffold.py`
- Function: `get_root_path, _find_package_path`
- Breaking commit: `84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`

The commit replaced `pkgutil.get_loader(import_name)` with `importlib.util.find_spec(import_name)`. In Python 3.11+, `find_spec` raises `ValueError` if `import_name` is `"__main__"` and `sys.modules["__main__"].__spec__` is `None`, which is the case when running a script directly. Previously `pkgutil.get_loader` returned `None` in this case, which Flask handled correctly.

## Hypotheses

### H1 (supported)

The recent change replacing pkgutil.get_loader with importlib.util.find_spec broke Flask for scripts run directly, because find_spec raises ValueError when __main__.__spec__ is None, which is common in direct script execution.

- Predicts: Running the reproduction script will fail with ValueError: __main__.__spec__ is None.
- Evidence: The reproduction script failed with the predicted ValueError. (tool calls 4)

### H2 (rejected)

The issue is environment-specific and not reproducible in this sandbox.

- Predicts: Running the reproduction script will succeed.
- Evidence: The reproduction script failed, so it is reproducible. (tool calls 4)

## Patch

```diff
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 4e8bc8b8..47de4d4e 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
@@ -575,7 +575,12 @@ def get_root_path(import_name: str) -> str:
         return os.path.dirname(os.path.abspath(mod.__file__))
 
     # Next attempt: check the loader.
-    spec = importlib.util.find_spec(import_name)
+    try:
+        spec = importlib.util.find_spec(import_name)
+    except ValueError:
+        # Python 3.11+ raises ValueError if __main__.__spec__ is None.
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     # Loader does not exist or we're referring to an unloaded main
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..60c3351f 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -855,7 +855,12 @@ def _find_package_path(import_name):
             return os.path.dirname(root_spec.origin)
 
     # we were unable to find the `package_path` using PEP 451 loaders
-    spec = importlib.util.find_spec(root_mod_name)
+    try:
+        spec = importlib.util.find_spec(root_mod_name)
+    except ValueError:
+        # Python 3.11+ raises ValueError if __main__.__spec__ is None.
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     if loader is None or root_mod_name == "__main__":
```

## Verification

- Call 4: `run_python reproduction script`: ValueError: __main__.__spec__ is None
- Call 17: `run_python reproduction script after fix`: Flask app created successfully
- Call 19: `run_tests tests/test_basic.py tests/test_helpers.py tests/test_instance_config.py`: 168 passed

## Evidence

### Call 4: run_python

Arguments: `{"code": "from flask import Flask\ntry:\n    app = Flask(__name__)\n    print(\"Flask app created successfully\")\nexcept Exception as e:\n    print(f\"Caught exception: {e}\")\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Caught exception: __main__.__spec__ is None
Traceback (most recent call last):
  File "<string>", line 3, in <module>
    app = Flask(__name__)
  File "/work/src/flask/app.py", line 367, in __init__
    super().__init__(
    ~~~~~~~~~~~~~~~~^
        import_name=import_name,
        ^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
        root_path=root_path,
        ^^^^^^^^^^^^^^^^^^^^
    
```

### Call 17: run_python

Arguments: `{"code": "from flask import Flask\ntry:\n    app = Flask(__name__)\n    print(\"Flask app created successfully\")\nexcept Exception as e:\n    print(f\"Caught exception: {e}\")\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Flask app created successfully

```

### Call 19: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py", "tests/test_instance_config.py"]}`

```
[exit 0]
........................................................................ [ 42%]
........................................................................ [ 85%]
........................                                                 [100%]
168 passed in 3.19s

```

## Limitations

