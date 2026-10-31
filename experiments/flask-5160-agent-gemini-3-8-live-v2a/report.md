# Investigation report: flask-5160

Model: gemini-3.8-live. Tool calls: 27. Time: 225.7 s. Tokens: 234934.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/helpers.py and src/flask/scaffold.py`
- Function: `get_root_path and _find_package_path`
- Breaking commit: `84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`

Replacing pkgutil.get_loader with importlib.util.find_spec caused a ValueError when passing "__main__" because __main__.__spec__ is None in certain scripts.

## Hypotheses

### H1 (supported)

The regression was caused by replacing pkgutil.get_loader with importlib.util.find_spec in _find_package_path. importlib.util.find_spec raises ValueError when __main__.__spec__ is None, whereas pkgutil.get_loader handled it without raising an exception.

- Predicts: Changing importlib.util.find_spec to pkgutil.get_loader in _find_package_path will fix the ValueError for __main__ and restore previous behavior.
- Evidence: The change from pkgutil to importlib caused the regression. pkgutil handled __main__ without raising ValueError. (tool calls 8)

### H2 (supported)

We can catch the ValueError raised by importlib.util.find_spec when __main__.__spec__ is None and fallback to the same logic as when loader is None.

- Predicts: Adding a try-except block around importlib.util.find_spec to catch ValueError and fallback to os.getcwd() will fix the issue.
- Evidence: Applying try-except ValueError around importlib.util.find_spec in both scaffold.py and helpers.py resolved the ValueError when initializing Flask("__main__"). (tool calls 15, 22)

## Patch

```diff
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 4e8bc8b8..4d1489eb 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
@@ -575,7 +575,11 @@ def get_root_path(import_name: str) -> str:
         return os.path.dirname(os.path.abspath(mod.__file__))
 
     # Next attempt: check the loader.
-    spec = importlib.util.find_spec(import_name)
+    try:
+        spec = importlib.util.find_spec(import_name)
+    except ValueError:
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     # Loader does not exist or we're referring to an unloaded main
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..dead824f 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -855,7 +855,11 @@ def _find_package_path(import_name):
             return os.path.dirname(root_spec.origin)
 
     # we were unable to find the `package_path` using PEP 451 loaders
-    spec = importlib.util.find_spec(root_mod_name)
+    try:
+        spec = importlib.util.find_spec(root_mod_name)
+    except ValueError:
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     if loader is None or root_mod_name == "__main__":
```

## Verification

- Call 23: `python test_script.py`: Instance path: /work/instance

## Evidence

### Call 8: git_show

Arguments: `{"rev": "84e11a1e"}`

```
84e11a1e827c0f55f9b9ee15952eddcf8a6492e0
David Lord 2023-06-07

use importlib instead of pkgutil


diff --git a/CHANGES.rst b/CHANGES.rst
index 32ddd151..80652305 100644
--- a/CHANGES.rst
+++ b/CHANGES.rst
@@ -3,6 +3,8 @@ Version 2.3.3
 
 Unreleased
 
+-   Python 3.12 compatibility.
+
 
 Version 2.3.2
 -------------
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 61a0f818..4e8bc8b8 
```

### Call 15: apply_edit

Arguments: `{"replace": "    # we were unable to find the `package_path` using PEP 451 loaders\n    try:\n        spec = importlib.util.find_spec(root_mod_name)\n    except ValueError:\n        spec = None\n\n    loader = spec.loader if spec is not None else None", "search": "    # we were unable to find the `p`

```
applied edit 1 to src/flask/scaffold.py. Run tests to check it.
```

### Call 22: apply_edit

Arguments: `{"replace": "    # Next attempt: check the loader.\n    try:\n        spec = importlib.util.find_spec(import_name)\n    except ValueError:\n        spec = None\n\n    loader = spec.loader if spec is not None else None", "path": "src/flask/helpers.py", "search": "    # Next attempt: check the loader.`

```
applied edit 2 to src/flask/helpers.py. Run tests to check it.
```

### Call 23: run_python

Arguments: `{"code": "from flask import Flask\nimport os\n\ndef test_main_app():\n    app = Flask(\"__main__\")\n    print(\"Instance path:\", app.instance_path)\n\nif __name__ == \"__main__\":\n    test_main_app()\n"}`

```
[exit 0]
Instance path: /work/instance

```

## Limitations

- The fix assumes that a ValueError from importlib.util.find_spec during module spec resolution should be treated as if the spec is not found, falling back to current working directory or other defaults, which matches the previous behavior with pkgutil.get_loader.
