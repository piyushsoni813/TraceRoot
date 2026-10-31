# Investigation report: filelock-346

Model: gemini-3.1-flash-live-preview. Tool calls: 31. Time: 67.1 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/filelock/_api.py`
- Function: `FileLockMeta.__call__`
- Breaking commit: `3a79343711eef57b864670dc2cafd352ed749d9b`

The metaclass `FileLockMeta` was introduced to handle singleton locks and argument filtering for `__init__`. It explicitly added `lock_file` to the arguments passed to `cls.__init__`, even if the subclass `__init__` did not accept a parameter named `lock_file`, leading to a `TypeError`. Subclasses that take the lock file path as a positional argument or under a different keyword name were broken.

## Hypotheses

### H1 (supported)

The metaclass `FileLockMeta` incorrectly filters arguments passed to `__init__`. It assumes that if `cls.__init__` does not have a parameter named `lock_file`, it should still pass it, leading to a `TypeError` when the subclass `__init__` has a differently named first parameter (like `file_path`).

- Predicts: The reproduction script will fail with the reported TypeError.
- Evidence: The reproduction script fails with TypeError: FilePathLock.__init__() got an unexpected keyword argument 'lock_file'. Tool call 15 confirms that inspect.signature(cls.__init__) returns parameters of the subclass __init__, which does not include 'lock_file' in the reproduction case. However, line 135 explicitly adds 'lock_file' to init_params, causing the TypeError. (tool calls 4, 15)

### H2 (supported)

The metaclass `FileLockMeta` fails to pass the positional argument `lock_file` correctly to the subclass `__init__`. By forcing it as a keyword argument `lock_file=...` when calling `super().__call__(**init_params)`, it clashes with subclasses that expect the lock file path as a positional argument or under a different keyword name.

- Predicts: The reproduction script will fail with the reported TypeError.
- Evidence: The error is indeed about 'lock_file' being passed as an unexpected keyword argument. H1 provides a more detailed explanation of why this happens (explicit addition in line 135). (tool calls 4)

## Patch

```diff
diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index 7db0e01..11c0408 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -132,7 +132,15 @@ class FileLockMeta(ABCMeta):
         present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
         init_params = {key: value for key, value in all_params.items() if key in present_params}
         # The `lock_file` parameter is required
-        init_params["lock_file"] = lock_file
+        if "lock_file" in present_params:
+            init_params["lock_file"] = lock_file
+        else:
+            params = list(inspect.signature(cls.__init__).parameters.values())
+            if len(params) > 1:  # params[0] is self
+                if params[1].kind == inspect.Parameter.VAR_POSITIONAL:
+                    init_params["lock_file"] = lock_file
+                else:
+                    init_params[params[1].name] = lock_file
 
         instance = super().__call__(**init_params)
```

## Verification

- Call 23: `run_python reproduction script`: True
- Call 30: `run_tests tests/test_filelock.py tests/test_error.py tests/test_async_filelock.py`: 90 passed, 63 skipped

## Evidence

### Call 4: run_python

Arguments: `{"code": "import tempfile\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDirectory() as d:\n    path = d + \"/a\"\n    try:\n        lock = FilePathLock(path)\n        prin`

```
[exit 0]
FilePathLock.__init__() got an unexpected keyword argument 'lock_file'
Exception ignored in: <function BaseFileLock.__del__ at 0x7dbc7a3ca7a0>
Traceback (most recent call last):
  File "/work/src/filelock/_api.py", line 400, in __del__
    self.release(force=True)
  File "/work/src/filelock/_api.py", line 361, in release
    if self.is_locked:
  File "/work/src/filelock/_api.py", line 267
```

### Call 15: run_python

Arguments: `{"code": "import inspect\n\nclass Base:\n    def __init__(self, a, b=1):\n        pass\n\nclass Sub(Base):\n    def __init__(self, c):\n        super().__init__(c + 1)\n\nsig = inspect.signature(Sub.__init__)\nprint(f\"Sub parameters: {sig.parameters}\")\nprint(f\"'c' in Sub parameters: {'c' in sig.`

```
[exit 0]
Sub parameters: OrderedDict({'self': <Parameter "self">, 'c': <Parameter "c">})
'c' in Sub parameters: True
'a' in Sub parameters: False

```

### Call 23: run_python

Arguments: `{"code": "import tempfile\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDirectory() as d:\n    path = d + \"/a\"\n    try:\n        lock = FilePathLock(path)\n        prin`

```
[exit 0]
True

```

### Call 30: run_tests

Arguments: `{"selection": ["tests/test_filelock.py", "tests/test_error.py", "tests/test_async_filelock.py"]}`

```
[exit 0]
............................ssssssssssssssssssss........................ [ 47%]
......................................ssssssssssssssssssssssssssssssssss [ 94%]
sssssssss                                                                [100%]
=============================== warnings summary ===============================
tests/test_async_filelock.py:14
  /work/tests/test_async_filelock.py:1
```

## Limitations

- Could not run tests/test_virtualenv.py due to missing 'virtualenv' module in the environment.
