# Investigation report: flask-5160

Model: gemini-3.8-flash,gemini-3-flash-preview,gemini-2.5-flash. Tool calls: 30. Time: 800.2 s. Tokens: 180848.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/flask/helpers.py, src/flask/scaffold.py`
- Function: `get_root_path, _find_package_path`
- Breaking commit: `84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`

The replacement of `pkgutil.get_loader(name)` with `importlib.util.find_spec(name)` introduced a regression because `find_spec` raises `ValueError` if the module exists in `sys.modules` but has its `__spec__` attribute set to `None`. This happens for the `__main__` module when running a script directly. The previous `pkgutil.get_loader` implementation handled this gracefully.

## Hypotheses

### H1 (supported)

Commit 84e11a1e replaced pkgutil.get_loader with importlib.util.find_spec without handling ValueError (such as when sys.modules[name].__spec__ is None or invalid name), causing unhandled exceptions in get_root_path and _find_package_path.

- Predicts: Catching (ImportError, ValueError) around importlib.util.find_spec in helpers.py and scaffold.py (where pkgutil.get_loader was replaced) will allow find_spec to gracefully return None/catch the error, making Flask("__main__") and direct script execution succeed.
- Evidence: find_spec raises ValueError when a module exists in sys.modules but has __spec__=None. This is the case for __main__ when run as a script. The previous code used pkgutil.get_loader which didn't have this behavior. (tool calls 4, 9, 15, 16)

### H2 (rejected)

The bug is caused specifically by __main__ missing __spec__ when run as a script, so find_spec should only be avoided when import_name == '__main__'.

- Predicts: Bypassing find_spec exclusively when root_mod_name == '__main__' is sufficient and other modules never trigger find_spec failure in sys.modules.
- Evidence: Any module in sys.modules with __spec__=None will trigger this, not just __main__. (tool calls 15, 16)

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

- Call 4: `run_python (reproduction script)`: ValueError: __main__.__spec__ is None
- Call 21: `run_python (verification script)`: Instance path: /work/instance (Success)
- Call 24: `run_tests (relevant tests)`: 168 passed (Success)

## Evidence

### Call 4: run_python

Arguments: `{"code": "from flask import Flask\napp = Flask(\"__main__\")\nprint(app.instance_path)\n"}`

```
[exit 1]
Traceback (most recent call last):
  File "<string>", line 2, in <module>
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
  File "/work/src/flask/scaffold.p
```

### Call 9: run_python

Arguments: `{"code": "import importlib.util, sys\nprint(\"sys.modules['__main__']:\", sys.modules.get(\"__main__\"))\nprint(\"__spec__:\", getattr(sys.modules.get(\"__main__\"), \"__spec__\", None))\ntry:\n    importlib.util.find_spec(\"__main__\")\nexcept Exception as e:\n    print(\"find_spec('__main__') rais`

```
[exit 0]
sys.modules['__main__']: <module '__main__' (<class '_frozen_importlib.BuiltinImporter'>)>
__spec__: None
find_spec('__main__') raised: <class 'ValueError'> __main__.__spec__ is None

```

### Call 15: run_python

Arguments: `{"code": "import importlib.util\ntry:\n    importlib.util.find_spec(\".relative\")\nexcept Exception as e:\n    print(f\"find_spec('.relative') raised: {type(e)} {e}\")\n"}`

```
[exit 0]
find_spec('.relative') raised: <class 'ImportError'> no package specified for '.relative' (required for relative module names)

```

### Call 16: run_python

Arguments: `{"code": "import importlib.util, sys\nfrom types import ModuleType\nm = ModuleType(\"bad_mod\")\nm.__spec__ = None\nsys.modules[\"bad_mod\"] = m\ntry:\n    importlib.util.find_spec(\"bad_mod\")\nexcept Exception as e:\n    print(f\"find_spec('bad_mod') raised: {type(e)} {e}\")\n"}`

```
[exit 0]
find_spec('bad_mod') raised: <class 'ValueError'> bad_mod.__spec__ is None

```

### Call 21: run_python

Arguments: `{"code": "from flask import Flask\nimport os\napp = Flask(\"__main__\")\nprint(f\"Instance path: {app.instance_path}\")\nassert app.instance_path == os.path.join(os.getcwd(), \"instance\")\n"}`

```
[exit 0]
Instance path: /work/instance

```

### Call 24: run_tests

Arguments: `{"selection": ["tests/test_basic.py", "tests/test_helpers.py", "tests/test_instance_config.py"]}`

```
[exit 0]
........................................................................ [ 42%]
........................................................................ [ 85%]
........................                                                 [100%]
168 passed in 1.92s

```

## Limitations

- The test suite has some pre-existing failures in `tests/test_cli.py` due to an apparent incompatibility with the installed version of `click` (CliRunner does not accept `mix_stderr`). These failures are unrelated to the reported bug and my fix.
