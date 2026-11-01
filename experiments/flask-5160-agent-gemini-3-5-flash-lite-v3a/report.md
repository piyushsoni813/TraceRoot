# Investigation report: flask-5160

Model: gemini-3.5-flash-lite. Tool calls: 33. Time: 134.8 s. Tokens: 334925.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/helpers.py and src/flask/scaffold.py`
- Function: `get_root_path and _find_package_path`
- Breaking commit: `not identified`

When importing or inspecting __main__ (or modules where __spec__ is None), calling importlib.util.find_spec raises a ValueError (__main__.__spec__ is None). Recent changes in Flask replaced pkgutil.get_loader with importlib.util.find_spec without wrapping all find_spec calls in try...except (ImportError, ValueError). Wrapping find_spec calls in try...except (ImportError, ValueError) correctly handles missing specs/ValueError and falls back to loading/cwd logic.

## Hypotheses

### H1 (supported)

importlib.util.find_spec("__main__") raises ValueError: __main__.__spec__ is None when __main__ has no __spec__ (e.g. running python -c or direct script execution in some python versions/setups where __spec__ is None), but find_spec expects a valid module name or raises ValueError for __main__ if spec is None.

- Predicts: Running a python script that instantiates Flask(__name__) when __name__ == '__main__' will succeed if we handle or check for __main__.__spec__ being None or pass when root_mod_name == "__main__" before calling importlib.util.find_spec(__main__)
- Evidence: importlib.util.find_spec('__main__') raises ValueError: __main__.__spec__ is None at line 858 just like line 821, but line 858 does NOT have a try...except block around importlib.util.find_spec(root_mod_name)! (tool calls 17, 18, 19, 20)

### H2 (supported)

The try...except (ImportError, ValueError) block around find_spec in _find_package_path handles __main__ or other ValueError-raising modules, but maybe something else calls find_spec or line 821 doesn't catch it properly, or something else? Let's check line 821 in scaffold.py.

- Predicts: Wrapping importlib.util.find_spec in try...except (ImportError, ValueError) correctly catches ValueError when __main__.__spec__ is None or module name is invalid, falling back to the loader/cwd path logic.
- Evidence: Line 821 has try...except (ImportError, ValueError), but line 858 does not have try...except (ImportError, ValueError). When line 821 hits ValueError, it falls through to line 858 which calls importlib.util.find_spec(root_mod_name) without try...except, raising ValueError: __main__.__spec__ is None. (tool calls 17, 18, 19, 20)

## Patch

```diff
diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 4e8bc8b8..44fee353 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
@@ -575,7 +575,11 @@ def get_root_path(import_name: str) -> str:
         return os.path.dirname(os.path.abspath(mod.__file__))
 
     # Next attempt: check the loader.
-    spec = importlib.util.find_spec(import_name)
+    try:
+        spec = importlib.util.find_spec(import_name)
+    except (ImportError, ValueError):
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     # Loader does not exist or we're referring to an unloaded main
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 3c23ef97..d5b96b0b 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -855,7 +855,11 @@ def _find_package_path(import_name):
             return os.path.dirname(root_spec.origin)
 
     # we were unable to find the `package_path` using PEP 451 loaders
-    spec = importlib.util.find_spec(root_mod_name)
+    try:
+        spec = importlib.util.find_spec(root_mod_name)
+    except (ImportError, ValueError):
+        spec = None
+
     loader = spec.loader if spec is not None else None
 
     if loader is None or root_mod_name == "__main__":
```

## Verification

- Call 29: `python -c "import sys; from flask import Flask; sys.modules['__main__'].__spec__ = None; app = Flask('__main__'); print(app.instance_path)"`: App instance path: /work/instance
- Call 32: `pytest tests/test_basic.py tests/test_helpers.py`: 158 passed in 2.20s

## Evidence

### Call 17: run_python

Arguments: `{"code": "import importlib.util, sys\nsys.modules['__main__'].__spec__ = None\ntry:\n    importlib.util.find_spec('__main__')\nexcept Exception as e:\n    print(type(e), e)\n"}`

```
[exit 0]
<class 'ValueError'> __main__.__spec__ is None

```

### Call 18: run_python

Arguments: `{"code": "import importlib.util, sys\nsys.modules['__main__'].__spec__ = None\nspec = importlib.util.find_spec('__main__')\n"}`

```
[exit 1]
Traceback (most recent call last):
  File "<string>", line 3, in <module>
    spec = importlib.util.find_spec('__main__')
  File "<frozen importlib.util>", line 111, in find_spec
ValueError: __main__.__spec__ is None

```

### Call 19: run_python

Arguments: `{"code": "import importlib.util, sys\nsys.modules['__main__'].__spec__ = None\ntry:\n    spec = importlib.util.find_spec('__main__')\nexcept ValueError as e:\n    print(\"Caught ValueError:\", e)\n    spec = None\nprint(\"spec:\", spec)\n"}`

```
[exit 0]
Caught ValueError: __main__.__spec__ is None
spec: None

```

### Call 20: run_python

Arguments: `{"code": "import importlib.util, sys\nsys.modules['__main__'].__spec__ = None\nroot_mod_name = \"__main__\"\ntry:\n    spec = importlib.util.find_spec(root_mod_name)\n    loader = spec.loader if spec is not None else None\nexcept (ImportError, ValueError):\n    loader = None\n\nprint(\"loader:\", lo`

```
[exit 0]
loader: None

```

### Call 29: run_python

Arguments: `{"code": "import sys\nfrom flask import Flask\nsys.modules['__main__'].__spec__ = None\napp = Flask(\"__main__\")\nprint(\"App instance path:\", app.instance_path)\n"}`

```
[exit 0]
App instance path: /work/instance

```

### Call 32: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py"]}`

```
[exit 0]
........................................................................ [ 45%]
........................................................................ [ 91%]
..............                                                           [100%]
158 passed in 2.20s

```

## Limitations

- Some unrelated click/click-runner version incompatibility tests in test_cli.py failed due to click version installed in the test environment (mix_stderr argument on CliRunner).
