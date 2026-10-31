# Investigation report: filelock-346

Model: gemini-3.1-flash-live-preview. Tool calls: 30. Time: 59.6 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/filelock/_api.py`
- Function: `FileLockMeta.__call__`
- Breaking commit: `192f1efcb95924010d785c3f726433273f6ed114`

The metaclass `FileLockMeta` was introduced to handle singleton locks. It filters arguments passed to `__init__` based on the subclass signature. However, it was forcing the `lock_file` argument to be passed as a keyword argument named 'lock_file', even if the subclass `__init__` method named its first parameter differently (e.g., 'file_path'). This caused a `TypeError` in subclasses with differently named parameters.

## Hypotheses

### H1 (supported)

The metaclass `FileLockMeta` incorrectly assumes that the first argument to `__init__` is always named `lock_file`. When a subclass uses a different name, forcing `lock_file` into the arguments causes a `TypeError`.

- Predicts: The reproduction script will fail with TypeError. Inspecting `src/filelock/_api.py` will show that `FileLockMeta.__call__` filters arguments based on `cls.__init__` signature and then forces `lock_file` into `init_params`.
- Evidence: Reading src/filelock/_api.py confirms that FileLockMeta.__call__ filters parameters based on inspect.signature(cls.__init__) but then explicitly adds "lock_file" to init_params, even if it's not in present_params. This matches the observed TypeError. (tool calls 5, 13)

### H2 (rejected)

The metaclass `FileLockMeta` passes all arguments, including `lock_file`, to `super().__call__`, which calls `FilePathLock.__init__`. Since `FilePathLock.__init__` does not accept `lock_file` as a keyword argument, it fails.

- Predicts: The reproduction script will fail with TypeError. Inspecting `src/filelock/_api.py` will show that `FileLockMeta.__call__` passes all arguments to `super().__call__` without filtering, and `FilePathLock.__init__` does not accept `lock_file`.
- Evidence: Reading src/filelock/_api.py shows that filtering IS performed, but "lock_file" is forced back in. So it's not passing ALL arguments blindly. (tool calls 5, 13)

## Patch

```diff
diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index 7db0e01..14a34a2 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -132,7 +132,18 @@ class FileLockMeta(ABCMeta):
         present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
         init_params = {key: value for key, value in all_params.items() if key in present_params}
         # The `lock_file` parameter is required
-        init_params["lock_file"] = lock_file
+        if "lock_file" not in present_params:
+            params = [
+                p
+                for p in inspect.signature(cls.__init__).parameters.values()
+                if p.name != "self" and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
+            ]
+            if params:
+                init_params[params[0].name] = lock_file
+            else:
+                init_params["lock_file"] = lock_file
+        else:
+            init_params["lock_file"] = lock_file
 
         instance = super().__call__(**init_params)
```

## Verification

- Call 27: `run_python reproduction script`: Lock file: /tmp/tmpa5dgpcxr/a.lock
Expected: /tmp/tmpa5dgpcxr/a.lock
True
- Call 26: `run_tests tests/test_filelock.py`: 86 passed, 20 skipped in 8.41s

## Evidence

### Call 5: read_file

Arguments: `{"end": 150, "path": "src/filelock/_api.py", "start": 100}`

```
100	                    "blocking": (blocking, instance.blocking),
101	                }
102	
103	                non_matching_params = {
104	                    name: (passed_param, set_param)
105	                    for name, (passed_param, set_param) in params_to_check.items()
106	                    if passed_param != set_param
107	                }
108	                if not non_matching_para
```

### Call 13: git_show

Arguments: `{"rev": "3a79343"}`

```
3a79343711eef57b864670dc2cafd352ed749d9b
Vitaliy Yelnik 2024-06-19

Fix `TypeError: _CountedFileLock.__init__() got an unexpected keyword argument 'timeout'` (#345)

* Fix TypeError: _CountedFileLock.__init__() got an unexpected keyword argument 'timeout'

* fix

* fix type check

* ignore Skipping analyzing "virtualenv": module is installed, but missing library stubs or py.typed marker  [import-u
```

### Call 26: apply_edit

Arguments: `{"search": "        present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]\n        init_params = {key: value for key, value in all_params.items() if key in present_params}\n        # The `lock_file` parameter is required\n        if \"lock_file\" not in present_param`

```
applied edit 3 to src/filelock/_api.py. Run tests to check it.
```

### Call 27: run_tests

Arguments: `{"selection": ["tests/test_filelock.py"]}`

```
[exit 0]
............................ssssssssssssssssssss........................ [ 67%]
..................................                                       [100%]
86 passed, 20 skipped in 8.41s

```

## Limitations

