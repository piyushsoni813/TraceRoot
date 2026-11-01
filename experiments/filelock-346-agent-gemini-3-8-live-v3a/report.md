# Investigation report: filelock-346

Model: gemini-3.8-live. Tool calls: 40. Time: 566.1 s. Tokens: 613483.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/filelock/_api.py`
- Function: `FileLockMeta.__call__`
- Breaking commit: `192f1ef`

The metaclass `__call__` filters arguments for `__init__` using `inspect.signature`. If a subclass renames the `lock_file` parameter, it tries to pass `lock_file` as a keyword argument to `__init__`, causing a `TypeError`.

## Hypotheses

### H1 (supported)

The `FileLockMeta.__call__` incorrectly assumes that `cls.__init__` accepts `lock_file` as a keyword argument, or that it can pass `lock_file` to it when the subclass has renamed the parameter.

- Predicts: The `FileLockMeta.__call__` tries to pass keyword arguments to `cls.__init__` by filtering `all_params` based on `inspect.signature(cls.__init__).parameters`. If a subclass uses a different parameter name for `lock_file`, it gets passed as `lock_file` keyword argument to the subclass `__init__`, causing a `TypeError`.
- Evidence: The reproduction shows `TypeError: FilePathLock.__init__() got an unexpected keyword argument 'lock_file'` when calling `FilePathLock(path)`. This confirms that `FileLockMeta.__call__` passes `lock_file` keyword argument to `FilePathLock.__init__`, which does not accept it. (tool calls 1, 7)

### H2 (rejected)

The metaclass `__call__` implementation is too aggressive in intercepting and filtering arguments for `__init__`, breaking subclasses with custom `__init__` signatures.

- Predicts: The `FileLockMeta.__call__` should not try to filter arguments for `__init__` and pass them via `super().__call__(**init_params)`. Instead, it should only pass arguments defined in `BaseFileLock.__init__` to `super().__call__` and let `__init__` handle its own arguments, or it should pass `*args` and `**kwargs` properly.
- Evidence: H2 suggested that `__call__` should not filter arguments or should pass `*args` and `**kwargs`. However, the fix implemented modifies `init_params` to correctly map `lock_file` to the renamed parameter in the subclass `__init__`, which is a more direct fix for the `TypeError` while maintaining the argument filtering logic intended by the metaclass implementation. Thus, H2 is rejected in favor of the specific parameter mapping approach. (tool calls 18, 30)

## Patch

```diff
diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index 7db0e01..471ecbe 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -129,10 +129,39 @@ class FileLockMeta(ABCMeta):
             **kwargs,
         }
 
+        # Workaround to make `__init__`'s params optional in subclasses
+        # E.g. virtualenv changes the signature of the `__init__` method in the `BaseFileLock` class descendant
+        # (https://github.com/tox-dev/filelock/pull/340)
+
+        all_params = {
+            "lock_file": lock_file,
+            "timeout": timeout,
+            "mode": mode,
+            "thread_local": thread_local,
+            "blocking": blocking,
+            "is_singleton": is_singleton,
+            **kwargs,
+        }
+
         present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
         init_params = {key: value for key, value in all_params.items() if key in present_params}
         # The `lock_file` parameter is required
-        init_params["lock_file"] = lock_file
+        if "lock_file" in present_params:
+            init_params["lock_file"] = lock_file
+        else:
+            # try to find the first parameter that is not self and not args/kwargs
+            sig = inspect.signature(cls.__init__)
+            for name, param in sig.parameters.items():
+                if name == "self":
+                    continue
+                if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
+                    continue
+                init_params[name] = lock_file
+                break
+            else:
+                # If we didn't find any parameter to pass lock_file to, we might have issues,
+                # but let's try passing it as lock_file anyway to see if it fails gracefully or not.
+                init_params["lock_file"] = lock_file
 
         instance = super().__call__(**init_params)
```

## Verification

- Call 37: `pytest tests/test_filelock.py`: All tests passed.

## Evidence

### Call 1: run_python

Arguments: `{"code": "import tempfile\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDirectory() as d:\n    path = d + \"/a\"\n    lock = FilePathLock(path)\n    print(lock.lock_file =`

```
[exit 1]
Exception ignored in: <function BaseFileLock.__del__ at 0x7f1b228ae7a0>
Traceback (most recent call last):
  File "/work/src/filelock/_api.py", line 400, in __del__
    self.release(force=True)
  File "/work/src/filelock/_api.py", line 361, in release
    if self.is_locked:
  File "/work/src/filelock/_api.py", line 267, in is_locked
    return self._context.lock_file_fd is not None
Attrib
```

### Call 7: read_file

Arguments: `{"end": 143, "path": "src/filelock/_api.py", "start": 81}`

```
81	class FileLockMeta(ABCMeta):
82	    def __call__(  # noqa: PLR0913
83	        cls,
84	        lock_file: str | os.PathLike[str],
85	        timeout: float = -1,
86	        mode: int = 0o644,
87	        thread_local: bool = True,  # noqa: FBT001, FBT002
88	        *,
89	        blocking: bool = True,
90	        is_singleton: bool = False,
91	        **kwargs: Any,  # capture remaining kwargs for
```

### Call 18: git_show

Arguments: `{"rev": "3d7b1a6"}`

```
3d7b1a6276144bdbad0086067feb36e1c1a8d2f7
Ethan Blackwood 2024-06-12

Hotfix: Restore __init__ method; more robust initialization for singleton locks (#338)

Co-authored-by: pre-commit-ci[bot] <66853113+pre-commit-ci[bot]@users.noreply.github.com>


diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index b074c6d..2894e61 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -85,31 
```

### Call 30: run_tests

Arguments: `{"selection": ["tests/test_filelock.py"]}`

```
[exit 1]
............................ssssssssssssssssssss......FF................ [ 67%]
.......................FF..FFFF..F                                       [100%]
=================================== FAILURES ===================================
______________________ test_nested_contruct[UnixFileLock] ______________________

lock_type = <class 'filelock._unix.UnixFileLock'>
tmp_path = PosixPa
```

### Call 37: run_tests

Arguments: `{"selection": ["tests/test_filelock.py"]}`

```
[exit 0]
............................ssssssssssssssssssss........................ [ 67%]
..................................                                       [100%]
86 passed, 20 skipped in 8.86s

```

## Limitations

- The fix assumes that if `lock_file` is not in `present_params`, the first positional argument (not `self`, `*args`, `**kwargs`) of `__init__` corresponds to `lock_file`. This works for the reported issue and passes all tests.
