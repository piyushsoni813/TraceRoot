# Investigation report: flask-5160

Model: gemini-3.1-flash-lite. Tool calls: 24. Time: 381.8 s. Tokens: 121835.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/scaffold.py and src/flask/helpers.py`
- Function: `_find_package_path and get_root_path`
- Breaking commit: `not identified`

importlib.util.find_spec raises a ValueError when called with "__main__" if __main__.__spec__ is None, which happens when running a script directly. The code did not handle this exception, causing the application construction to fail.

## Hypotheses

### H1 (supported)

The issue is that importlib.util.find_spec("__main__") raises a ValueError when __main__.__spec__ is None, which is the case when running a script directly. The current code in _find_package_path catches ValueError but it seems it might be failing in a way that isn't caught or is re-raised. Wait, the traceback says it fails at line 858: spec = importlib.util.find_spec(root_mod_name). This is *outside* the try-except block that starts at line 820.

- Predicts: If I change the code to handle the ValueError from find_spec, it will fix the issue.
- Evidence: The traceback confirms the failure is at line 858, which is outside the try-except block. The first find_spec call at line 821 is protected, but the second one at line 858 is not. (tool calls 12)

### H2 (supported)

The code at line 858 is outside the try-except block that handles the initial find_spec. It should be inside or have its own try-except.

- Predicts: If I move the find_spec call inside the try-except block, it will be caught and handled correctly.
- Evidence: The code at line 858 is indeed outside the try-except block. The try-except block only covers the first find_spec call at line 821. If the first call fails, it goes to the else block (wait, no, it goes to the except block, then continues to line 857). Wait, if it goes to the except block, it passes, and then continues to line 857. So it *does* reach line 858. And line 858 is not protected by a try-except. So if line 858 raises a ValueError, it will propagate up. (tool calls 12)

## Patch

```diff
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 4e8bc8b8..d1bb9658 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
@@ -575,7 +575,10 @@ def get_root_path(import_name: str) -> str:
         return os.path.dirname(os.path.abspath(mod.__file__))
 
     # Next attempt: check the loader.
-    spec = importlib.util.find_spec(import_name)
+    try:
+        spec = importlib.util.find_spec(import_name)
+    except ValueError:
+        spec = None
     loader = spec.loader if spec is not None else None
 
     # Loader does not exist or we're referring to an unloaded main
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

- Call 19: `run_python with a script creating a Flask app with __main__`: Success
- Call 22: `run_tests tests/test_basic.py tests/test_helpers.py`: 158 passed in 2.40s
- Call 23: `run_tests tests/test_instance_config.py`: 10 passed in 0.49s

## Evidence

### Call 12: read_file

Arguments: `{"end": 865, "start": 816, "path": "src/flask/scaffold.py"}`

```
816	def _find_package_path(import_name):
817	    """Find the path that contains the package or module."""
818	    root_mod_name, _, _ = import_name.partition(".")
819	
820	    try:
821	        root_spec = importlib.util.find_spec(root_mod_name)
822	
823	        if root_spec is None:
824	            raise ValueError("not found")
825	    # ImportError: the machinery told us it does not exist
826	   
```

### Call 19: run_python

Arguments: `{"code": "import sys\nfrom flask import Flask\ntry:\n    app = Flask(\"__main__\")\n    print(\"Success\")\nexcept Exception as e:\n    print(f\"Failed: {e}\")\n    import traceback\n    traceback.print_exc()\n"}`

```
[exit 0]
Success

```

### Call 22: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py"]}`

```
[exit 0]
........................................................................ [ 45%]
........................................................................ [ 91%]
..............                                                           [100%]
158 passed in 2.40s

```

### Call 23: run_tests

Arguments: `{"selection": ["tests/test_instance_config.py"]}`

```
[exit 0]
..........                                                               [100%]
10 passed in 0.49s

```

## Limitations

- Only verified the fix with a simple script and existing tests. Did not run the full test suite, but ran relevant ones.
