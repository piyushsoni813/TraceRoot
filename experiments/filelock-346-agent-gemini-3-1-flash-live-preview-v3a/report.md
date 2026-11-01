# Investigation report: filelock-346

Model: gemini-3.1-flash-live-preview. Tool calls: 22. Time: 57.8 s. Tokens: 0.

**Decision: ready for human review.** Nothing was merged or deployed.

## Root cause

- File: `src/filelock/_api.py`
- Function: `FileLockMeta.__call__`
- Breaking commit: `not identified`

The metaclass was filtering arguments passed to __init__ based on the subclass's signature, but then explicitly adding 'lock_file' as a keyword argument. If the subclass renamed the 'lock_file' parameter, this caused a TypeError.

## Hypotheses

### H1 (supported)

FileLockMeta.__call__ incorrectly passes 'lock_file' as a keyword argument to the subclass's __init__, even if the subclass has renamed that parameter. Passing it positionally should fix this.

- Predicts: If I modify `FileLockMeta.__call__` to not filter parameters, the `TypeError` will disappear, but `FilePathLock.__init__` might receive unexpected arguments if it doesn't accept `**kwargs`. In the reproduction case, it should work because `FilePathLock.__init__` only takes `file_path`, and `FileLockMeta` should pass `lock_file` as positional argument if it matches. Wait, `super().__call__(**init_params)` passes keyword arguments.

If `FilePathLock.__init__` is `def __init__(self, file_path):`, and `init_params` is `{'lock_file': '...'}`. `super().__call__(**init_params)` calls `FilePathLock.__init__(self, lock_file='...')`. This fails because `file_path` is not `lock_file`.

If I change `FileLockMeta.__call__` to pass positional arguments for `lock_file`, it might fix it.

Wait, `FileLockMeta.__call__` is trying to be smart about what arguments to pass to `__init__`.

If `FilePathLock.__init__` is `def __init__(self, file_path):`.
`inspect.signature(cls.__init__).parameters` will contain `file_path`.

`all_params` contains `lock_file`, `timeout`, etc.

`init_params` will be empty because `file_path` is not in `all_params`.

Then `init_params["lock_file"] = lock_file`.

So `init_params` is `{'lock_file': '...'}`.

And `super().__call__(**init_params)` calls `FilePathLock.__init__(self, lock_file='...')`.

This is indeed why it fails.

The hypothesis is that `FileLockMeta` incorrectly assumes that `cls.__init__` accepts `lock_file` as a keyword argument, or that it should filter arguments based on `cls.__init__` signature but then forces `lock_file`.

If I revert the logic to just pass all arguments, it should work as before, assuming `BaseFileLock.__init__` handles them.

`BaseFileLock.__init__` signature:
```python
155	    def __init__(  # noqa: PLR0913
156	        self,
157	        lock_file: str | os.PathLike[str],
158	        timeout: float = -1,
159	        mode: int = 0o644,
160	        thread_local: bool = True,  # noqa: FBT001, FBT002
161	        *,
162	        blocking: bool = True,
163	        is_singleton: bool = False,
164	    ) -> None:
```

In the reproduction:
```python
class FilePathLock(FileLock):
    def __init__(self, file_path):
        super().__init__(file_path + ".lock")
```
`FileLock` is likely an alias for `BaseFileLock` or a subclass. Let's check `src/filelock/__init__.py`.

If `FilePathLock` calls `super().__init__`, it calls `BaseFileLock.__init__`.

The issue is in `FileLockMeta.__call__`.

If I change `FileLockMeta.__call__` to pass `lock_file` as a positional argument, and other arguments as keyword arguments.

```python
137	        instance = super().__call__(**init_params)
```

If I change it to:
```python
        lock_file = init_params.pop("lock_file")
        instance = super().__call__(lock_file, **init_params)
```
But `init_params` is constructed by filtering `all_params`.

If `FilePathLock.__init__` is `def __init__(self, file_path):`.

If I pass `lock_file` positionally, it will be assigned to `file_path`.

```python
        # The `lock_file` parameter is required
        init_params["lock_file"] = lock_file

        instance = super().__call__(**init_params)
```

If I change this to:

```python
        # The `lock_file` parameter is required
        # init_params["lock_file"] = lock_file # Don't force it into kwargs

        # We need to pass lock_file positionally.
        
        # But super().__call__ calls type.__call__, which calls cls.__new__ and cls.__init__.
        # We cannot easily separate positional and keyword arguments for cls.__init__ here because we don't know which parameter in cls.__init__ corresponds to lock_file.
```

The comment says:
```python
118	        # Workaround to make `__init__`'s params optional in subclasses
119	        # E.g. virtualenv changes the signature of the `__init__` method in the `BaseFileLock` class descendant
120	        # (https://github.com/tox-dev/filelock/pull/340)
```

If `virtualenv` changes signature, maybe they do:
```python
class VirtualEnvLock(FileLock):
     def __init__(self, lock_file, some_other_arg):
         super().__init__(lock_file)
```
Here `lock_file` is present.

But in the bug report:
```python
class FilePathLock(FileLock):
    def __init__(self, file_path):
        super().__init__(file_path + ".lock")
```
The parameter is named `file_path`.

If `FileLockMeta` wants to support this, it should probably pass `lock_file` as the first positional argument, and only pass other arguments if they are accepted by `__init__`.

Let's see what `inspect.signature(cls.__init__).parameters` gives for `FilePathLock`.

It should give `self` and `file_path`.

If `FileLockMeta.__call__` is:

```python
82	    def __call__(  # noqa: PLR0913
83	        cls,
84	        lock_file: str | os.PathLike[str],
...
91	        **kwargs: Any,  # capture remaining kwargs for subclasses  # noqa: ANN401
92	    ) -> BaseFileLock:
```

When `FilePathLock(path)` is called:
`cls` is `FilePathLock`.
`lock_file` is `path`.
`kwargs` is empty.

`all_params` will have `lock_file` = `path`.

`present_params` will be `{'self', 'file_path'}` (or just `{'file_path'}` depending on how inspect works on bound methods, but here it is `cls.__init__`, so unbound).

`init_params` will be empty.

`init_params["lock_file"] = lock_file`.

`super().__call__(**init_params)` calls `FilePathLock.__init__(lock_file=path)`.

And `FilePathLock.__init__` expects `file_path`.

If we want to support renaming the first argument, we must pass it positionally.

```python
        present_params = list(inspect.signature(cls.__init__).parameters.values())
        
        # The first parameter is usually 'self', we want the first argument after self.
        # If it's a method, self is not in parameters? Let's check.
```

I'll use `run_python` to check `inspect.signature`.
- Evidence: The reproduction script fails with TypeError: FilePathLock.__init__() got an unexpected keyword argument 'lock_file', confirming that 'lock_file' is passed as a keyword argument to a constructor that doesn't accept it. (tool calls 5)

### H2 (rejected)

The issue is in `BaseFileLock.__init__` not accepting `**kwargs`.

- Predicts: If I add `**kwargs` to `BaseFileLock.__init__`, the error will change or disappear.
- Evidence: The error is in FilePathLock.__init__, not BaseFileLock.__init__. BaseFileLock.__init__ is not even reached. (tool calls 5)

## Patch

```diff
diff --git a/src/filelock/_api.py b/src/filelock/_api.py
index 7db0e01..9d04fa6 100644
--- a/src/filelock/_api.py
+++ b/src/filelock/_api.py
@@ -132,9 +132,11 @@ class FileLockMeta(ABCMeta):
         present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
         init_params = {key: value for key, value in all_params.items() if key in present_params}
         # The `lock_file` parameter is required
-        init_params["lock_file"] = lock_file
-
-        instance = super().__call__(**init_params)
+        if "lock_file" in present_params:
+            init_params["lock_file"] = lock_file
+            instance = super().__call__(**init_params)
+        else:
+            instance = super().__call__(lock_file, **init_params)
 
         if is_singleton:
             cls._instances[str(lock_file)] = instance  # type: ignore[attr-defined]
```

## Verification

- Call 17: `run_python reproduction script`: True
- Call 20: `run_tests tests/test_filelock.py`: 86 passed, 20 skipped
- Call 21: `run_tests tests/test_async_filelock.py tests/test_error.py`: 4 passed, 43 skipped

## Evidence

### Call 5: run_python

Arguments: `{"code": "import tempfile\nimport sys\nimport os\n\n# Add src to sys.path\nsys.path.insert(0, os.path.abspath(\"src\"))\n\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDir`

```
[exit 0]
FilePathLock.__init__() got an unexpected keyword argument 'lock_file'
Exception ignored in: <function BaseFileLock.__del__ at 0x79b625a8e7a0>
Traceback (most recent call last):
  File "/work/src/filelock/_api.py", line 400, in __del__
    self.release(force=True)
  File "/work/src/filelock/_api.py", line 361, in release
    if self.is_locked:
  File "/work/src/filelock/_api.py", line 267
```

### Call 17: run_python

Arguments: `{"code": "import tempfile\nimport sys\nimport os\n\n# Add src to sys.path\nsys.path.insert(0, os.path.abspath(\"src\"))\n\nfrom filelock import FileLock\n\nclass FilePathLock(FileLock):\n    def __init__(self, file_path):\n        super().__init__(file_path + \".lock\")\n\nwith tempfile.TemporaryDir`

```
[exit 0]
True

```

### Call 20: run_tests

Arguments: `{"selection": ["tests/test_filelock.py"]}`

```
[exit 0]
............................ssssssssssssssssssss........................ [ 67%]
..................................                                       [100%]
86 passed, 20 skipped in 8.41s

```

### Call 21: run_tests

Arguments: `{"selection": ["tests/test_async_filelock.py", "tests/test_error.py"]}`

```
[exit 0]
sssssssssssssssssssssssssssssssssssssssssss....                          [100%]
=============================== warnings summary ===============================
tests/test_async_filelock.py:14
  /work/tests/test_async_filelock.py:14: PytestUnknownMarkWarning: Unknown pytest.mark.asyncio - is this a typo?  You can register custom marks to avoid this warning - for details, see https://docs.
```

## Limitations

- Could not run tests/test_virtualenv.py because the 'virtualenv' module is not installed in the environment.
