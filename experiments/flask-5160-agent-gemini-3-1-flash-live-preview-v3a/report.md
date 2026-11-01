# Investigation report: flask-5160

Model: gemini-3.1-flash-live-preview. Tool calls: 20. Time: 28.5 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/scaffold.py`
- Function: `_find_package_path`
- Breaking commit: `84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`

The commit replaced `pkgutil.get_loader(root_mod_name)` with `importlib.util.find_spec(root_mod_name)`. When running a script directly, `root_mod_name` is `"__main__"`. If `__main__.__spec__` is `None` (which is common when running scripts), `importlib.util.find_spec("__main__")` raises a `ValueError`, whereas `pkgutil.get_loader` did not.

## Hypotheses

### H1 (supported)

The recent change replaced pkgutil.get_loader with importlib.util.find_spec. When running as a script, __name__ is "__main__". importlib.util.find_spec("__main__") raises ValueError if __main__.__spec__ is None, which happens when running a script directly. pkgutil.get_loader("__main__") likely handled this gracefully or returned None.

- Predicts: Running a script that creates Flask(__name__) will fail with ValueError: __main__.__spec__ is None.
- Evidence: pkgutil.get_loader('__main__') returns a loader, while importlib.util.find_spec('__main__') raises ValueError when __main__.__spec__ is None. (tool calls 11, 12)

### H2 (rejected)

The issue is specific to Python 3.11+ where __main__.__spec__ behavior might have changed, and the new importlib code in Flask interacts poorly with it.

- Predicts: Running a script that creates Flask(__name__) will fail with ValueError: __main__.__spec__ is None, but only on Python 3.11+.
- Evidence: The issue is reproduced in the current environment, confirming that the change in implementation is the cause, regardless of specific Python version behavior changes (though it might be relevant why __spec__ is None). H1 provides a sufficient explanation. (tool calls 11, 12)

## Patch

```diff
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..b3e834d0 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -855,7 +855,12 @@ def _find_package_path(import_name):
             return os.path.dirname(root_spec.origin)
 
     # we were unable to find the `package_path` using PEP 451 loaders
-    spec = importlib.util.find_spec(root_mod_name)
+    try:
+        spec = importlib.util.find_spec(root_mod_name)
+    except ValueError:
+        # __main__.__spec__ is None
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     if loader is None or root_mod_name == "__main__":
```

## Verification

- Call 16: `run_python reproduction script`: App created successfully
Reproduction script passed.
- Call 19: `run_tests tests/test_basic.py tests/test_helpers.py tests/test_instance_config.py`: 168 passed

## Evidence

### Call 11: run_python

Arguments: `{"code": "import pkgutil\nimport sys\n\n# Simulate running as a script\nsys.modules['__main__'].__spec__ = None\n\ntry:\n    loader = pkgutil.get_loader(\"__main__\")\n    print(f\"pkgutil.get_loader('__main__') returned: {loader}\")\nexcept Exception as e:\n    print(f\"pkgutil.get_loader('__main__`

```
[exit 0]
pkgutil.get_loader('__main__') returned: <class '_frozen_importlib.BuiltinImporter'>

```

### Call 12: run_python

Arguments: `{"code": "import importlib.util\nimport sys\n\n# Simulate running as a script\nsys.modules['__main__'].__spec__ = None\n\ntry:\n    spec = importlib.util.find_spec(\"__main__\")\n    print(f\"importlib.util.find_spec('__main__') returned: {spec}\")\nexcept Exception as e:\n    print(f\"importlib.uti`

```
[exit 0]
importlib.util.find_spec('__main__') raised: __main__.__spec__ is None

```

### Call 16: run_python

Arguments: `{"code": "import os\n\n# Create app.py\nwith open(\"app.py\", \"w\") as f:\n    f.write(\"from flask import Flask\\n\")\n    f.write(\"app = Flask(__name__)\\n\")\n    f.write(\"print('App created successfully')\\n\")\n\n# Run app.py\nexit_code = os.system(\"python3 app.py\")\nif exit_code == 0:\n  `

```
[exit 0]
App created successfully
Reproduction script passed.

```

### Call 19: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py", "tests/test_instance_config.py"]}`

```
[exit 0]
........................................................................ [ 42%]
........................................................................ [ 85%]
........................                                                 [100%]
168 passed in 2.11s

```

## Limitations

- I only ran a subset of tests that seemed relevant to application construction and path finding. I did not run the full test suite.
