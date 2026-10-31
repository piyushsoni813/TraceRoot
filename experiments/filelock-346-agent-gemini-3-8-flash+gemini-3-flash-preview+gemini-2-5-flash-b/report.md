# Investigation report: filelock-346

Model: gemini-3.8-flash,gemini-3-flash-preview,gemini-2.5-flash. Tool calls: 28. Time: 520.4 s. Tokens: 287622.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/filelock/_api.py`
- Function: `FileLockMeta.__call__`
- Breaking commit: `3a79343711eef57b864670dc2cafd352ed749d9b`

The `FileLockMeta.__call__` method, introduced in commit 3a79343, attempts to dynamically determine the `__init__` parameters of `BaseFileLock` subclasses. It assumes that the `lock_file` parameter will always be named `lock_file` or that the subclass will accept `**kwargs`. However, if a subclass renames the first positional argument (e.g., `file_path` instead of `lock_file`) and does not accept `**kwargs`, the metaclass explicitly tries to pass `lock_file` as a keyword argument, leading to a `TypeError`.

## Hypotheses

### H1 (supported)

The metaclass `FileLockMeta.__call__` incorrectly assumes that the first argument of `__init__` is always named `lock_file`. If a subclass uses a different name (like `file_path`), it filters out the argument but then explicitly adds `lock_file` back, which the subclass doesn't accept.

- Predicts: The reproduction script will fail with the same TypeError.
- Evidence: The experiment confirms that if the subclass __init__ doesn't have a 'lock_file' parameter, it won't be in present_params, and forcing it into init_params will cause a TypeError when calling the subclass __init__. (tool calls 14)

### H2 (rejected)

The `inspect.signature(cls.__init__).parameters` might not be correctly identifying the parameters if there's some other wrapping or if it's not looking at the right class in the hierarchy.

- Predicts: The reproduction script will fail with the same TypeError.
- Evidence: inspect.signature works as expected, identifying 'file_path' instead of 'lock_file'. (tool calls 14)

## Patch

```diff
diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index 7db0e01..40a47f0 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -129,10 +129,34 @@ class FileLockMeta(ABCMeta):
             **kwargs,
         }
 
-        present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
-        init_params = {key: value for key, value in all_params.items() if key in present_params}
-        # The `lock_file` parameter is required
-        init_params["lock_file"] = lock_file
+        present_params = inspect.signature(cls.__init__).parameters
+        init_params = {}
+        remaining_all_params = all_params.copy()
+
+        # Determine the name of the parameter that should receive the lock file path
+        lock_file_arg_name = "lock_file"  # Default to 'lock_file'
+        for name, param in present_params.items():
+            if name == "self":
+                continue
+            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY):
+                lock_file_arg_name = name
+                break
+
+        # Map the 'lock_file' value from all_params to the determined lock_file_arg_name
+        if lock_file_arg_name in present_params or present_params.get("kwargs"):
+            init_params[lock_file_arg_name] = remaining_all_params.pop("lock_file")
+
+        # Add other parameters that are present in the subclass's __init__
+        for key, value in remaining_all_params.items():
+            if key in present_params:
+                init_params[key] = value
+            elif present_params.get("kwargs"):
+                init_params.setdefault("kwargs", {})[key] = value
+
+        # If 'kwargs' is in init_params, unpack it before passing to super().__call__
+        if "kwargs" in init_params:
+            kwargs_to_pass = init_params.pop("kwargs")
+            init_params.update(kwargs_to_pass)
 
         instance = super().__call__(**init_params)
```

## Verification

- Call 19: `run_python`: Success: True
- Call 27: `run_tests(selection = ["tests/test_filelock.py", "tests/test_async_filelock.py", "tests/test_error.py"])`: 90 passed, 63 skipped, 5 warnings in 9.21s

## Evidence

### Call 14: run_python

Arguments: `{"code": "import inspect\nimport os\n\nclass Base:\n    def __init__(self, lock_file, timeout=-1):\n        pass\n\nclass Sub(Base):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nprint(f\"Sub parameters: {list(inspect.signature(Sub.__init__).parameters.keys(`

```
[exit 0]
Sub parameters: ['self', 'file_path']
init_params before forcing: {}
init_params after forcing: {'lock_file': 'foo.lock'}

```

### Call 19: run_python

Arguments: `{"code": "import tempfile\nimport os\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDirectory() as d:\n    path = os.path.join(d, \"a\")\n    try:\n        lock = FilePathL`

```
[exit 0]
Success: True

```

### Call 27: run_tests

Arguments: `{"selection": ["tests/test_filelock.py", "tests/test_async_filelock.py", "tests/test_error.py"]}`

```
[exit 0]
............................ssssssssssssssssssss........................ [ 47%]
..................................ssssssssssssssssssssssssssssssssssssss [ 94%]
sssss....                                                                [100%]
=============================== warnings summary ===============================
tests/test_async_filelock.py:14
  /work/tests/test_async_filelock.py:1
```

## Limitations

- The `test_virtualenv.py` test file could not be run due to a missing `virtualenv` module. This was not addressed as it was outside the scope of the reported bug and the core functionality was verified with other tests.
