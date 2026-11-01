# Investigation report: filelock-346

Model: gemini-3.5-flash-lite. Tool calls: 29. Time: 147.9 s. Tokens: 312081.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/filelock/_api.py`
- Function: `FileLockMeta.__call__`
- Breaking commit: `not identified`

FileLockMeta.__call__ filtered initialization parameters based on explicit presence of exact parameter name keys (such as `lock_file`) in `cls.__init__`. When subclasses of `FileLock` defined their `__init__` with a differently named first parameter (e.g. `file_path`), `lock_file` was dropped from `init_params` and passed as an unexpected keyword argument `lock_file` to `FilePathLock.__init__`. We updated `FileLockMeta.__call__` to inspect `cls.__init__` signature and correctly map `lock_file` to the first parameter of `cls.__init__` if that parameter is not named `lock_file`.

## Hypotheses

### H1 (supported)

Subclassing FileLock with a differently named first parameter (e.g. `file_path` instead of `lock_file`) fails because FileLockMeta filters out `lock_file` if `cls.__init__` does not have a parameter named `lock_file`, and passes `lock_file` as a keyword argument to `super().__call__` which goes to `FilePathLock.__init__`, which doesn't accept `lock_file`.

- Predicts: If we check class parameter names or use signature binding instead of filtering `all_params` by `present_params` matching key names, subclasses with differently named first parameters (like `file_path`) can accept the passed argument correctly.
- Evidence: Running reproduction snippet produces TypeError: FilePathLock.__init__() got an unexpected keyword argument 'lock_file', confirming H1. (tool calls 9)

### H2 (supported)

Using `inspect.signature(cls.__init__).bind` to forward arguments correctly to `cls.__init__` (or `super().__call__`) will support custom signatures and custom parameter names.

- Predicts: If we inspect the signature of `cls.__init__` using `inspect.signature(cls.__init__).bind` or mapping positional/keyword arguments, or if we do not enforce strict keyword argument filtering based on parameter names matching `all_params` keys, it will work.
- Evidence: Reproduction snippet fails due to mismatch between `lock_file` argument passed by metaclass and `file_path` expected by `FilePathLock.__init__`. (tool calls 9)

## Patch

```diff
diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index 7db0e01..785e1aa 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -129,10 +129,26 @@ class FileLockMeta(ABCMeta):
             **kwargs,
         }
 
-        present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
-        init_params = {key: value for key, value in all_params.items() if key in present_params}
-        # The `lock_file` parameter is required
-        init_params["lock_file"] = lock_file
+        sig = inspect.signature(cls.__init__)  # type: ignore[misc]
+        params = sig.parameters
+        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
+        if has_var_keyword:
+            init_params = all_params
+        else:
+            init_params = {key: value for key, value in all_params.items() if key in params}
+            param_names = [
+                name
+                for name, p in params.items()
+                if name != "self"
+                and p.kind
+                in (
+                    inspect.Parameter.POSITIONAL_ONLY,
+                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
+                    inspect.Parameter.KEYWORD_ONLY,
+                )
+            ]
+            if param_names and param_names[0] not in init_params and "lock_file" in all_params:
+                init_params[param_names[0]] = all_params["lock_file"]
 
         instance = super().__call__(**init_params)
```

## Verification

- Call 27: `python -c '...'`: True
- Call 28: `pytest tests/test_filelock.py`: 86 passed, 20 skipped in 8.19s

## Evidence

### Call 9: run_python

Arguments: `{"code": "import tempfile\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDirectory() as d:\n    path = d + \"/a\"\n    lock = FilePathLock(path)\n    print(lock.lock_file =`

```
[exit 1]
Exception ignored in: <function BaseFileLock.__del__ at 0x7821ea3a67a0>
Traceback (most recent call last):
  File "/work/src/filelock/_api.py", line 400, in __del__
    self.release(force=True)
  File "/work/src/filelock/_api.py", line 361, in release
    if self.is_locked:
  File "/work/src/filelock/_api.py", line 267, in is_locked
    return self._context.lock_file_fd is not None
Attrib
```

### Call 27: run_python

Arguments: `{"code": "import tempfile\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDirectory() as d:\n    path = d + \"/a\"\n    lock = FilePathLock(path)\n    print(lock.lock_file =`

```
[exit 0]
True

```

### Call 28: run_tests

Arguments: `{"selection": ["tests/test_filelock.py"]}`

```
[exit 0]
............................ssssssssssssssssssss........................ [ 67%]
..................................                                       [100%]
86 passed, 20 skipped in 8.19s

```

## Limitations

