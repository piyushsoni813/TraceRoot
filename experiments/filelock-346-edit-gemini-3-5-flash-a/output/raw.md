to pass keyword arguments, OR maybe to do something else with `init_params`?
Wait, if someone bound `*args, **kwargs` using `inspect.signature(BaseFileLock.__init__)`:
Why is that wrong?
1. It breaks any subclass that overrides `__init__` with different parameter names (like `file_path` instead of `lock_file`).
2. It breaks positional arguments if `__init__` expects positional-only or renamed parameters.
3. Passing `*args, **kwargs` directly to `super().__call__(*args, **kwargs)` allows Python's native argument binding to work for whatever `cls.__init__` (or `cls.__new__`) actually expects!

Wait! What if `__call__` needed `init_params` or `bound` for something else?
Wait! Is `init_params` used for anything else in `__call__`?
Let's think: could `init_params` be used for anything else in `__call__`?
What if `__call__` does:
```python
        # ...
        instance = super().__call__(*args, **kwargs)
```
Wait, if `super().__call__(*args, **kwargs)` is used instead of `super().__call__(**init_params)`:
Let's test what happens if `super().__call__(*args, **kwargs)` is used!

Let's trace:
Suppose `FilePathLock(path)` is called.
`args = (path,)`, `kwargs = {}`.
`instance = super().__call__(*args, **kwargs)` calls `type.__call__(cls, *args, **kwargs)`.
`type.__call__` calls:
1) `instance = FilePathLock.__new__(FilePathLock, path)`
2) `FilePathLock.__init__(instance, path)`
Inside `FilePathLock.__init__`:
`def __init__(self, file_path):`
`super().__init__(file_path + ".lock")`
`BaseFileLock.__init__(self, lock_file)` -> sets `self.lock_file = path + ".lock"`, etc.

`instance` is returned by `__call__`.
Then `lock = FilePathLock(path)` gets `instance`.
`lock.lock_file == path + ".lock"` is `True`!

Wait! What if `FilePathLock` was called with keyword args, e.g. `FilePathLock(file_path=path)`?
`args = ()`, `kwargs = {'file_path': path}`.
`instance = super().__call__(*args, **kwargs)` -> `type.__call__(cls, file_path=path)`.
`FilePathLock.__init__(instance, file_path=path)` -> works!

What if `FileLock(path, timeout=10)` is called?
`args = (path,)`, `kwargs = {'timeout': 10}`.
`instance