', 'file_path', 'timeout'}`.
`init_params`: `{'timeout': -1}`.
Is `"lock_file"` in `init_params`? NO!
`instance = super().__call__(lock_file, **init_params)` -> `super().__call__(lock_file, timeout=-1)`.
`cls.__init__(instance, lock_file, timeout=-1)` receives `self=instance`, `file_path=lock_file`, `timeout=-1`.
Works!

Suppose `cls` is a subclass with `def __init__(self, lock_file, **kwargs)`:
`sig.parameters` keys: `'self'`, `'lock_file'`, `'kwargs'`.
`has_var_kw`: True.
`init_params`: `all_params` (contains `'lock_file': lock_file`, ...).
Is `"lock_file"` in `init_params`? YES!
`instance = super().__call__(**init_params)`
Works!

Suppose `cls` is a subclass with `def __init__(self, file_path, **kwargs)`:
`sig.parameters` keys: `'self'`, `'file_path'`, `'kwargs'`.
`has_var_kw`: True.
`all_params`: contains `'lock_file'`, `'timeout'`, ...
Wait! If `has_var_kw` is True, but `"lock_file"` is NOT in `sig.parameters`:
If `init_params` was `all_params`, `init_params` would have `"lock_file": lock_file`.
If `"lock_file"` is in `init_params`, it would call `super().__call__(**init_params)`.
`cls.__init__(instance, lock_file=path, timeout=-1, ...)`:
`file_path` is positional-or-keyword, but was not supplied positionally or as keyword `file_path`. `lock_file` goes into `kwargs`. `file_path` gets no argument -> `TypeError: __init__() missing 1 required positional argument: 'file_path'`.
So if `"lock_file"` is NOT in `sig.parameters` (even if `has_var_kw` is True), `"lock_file"` should NOT be in `init_params` when calling `super().__call__(lock_file, **init_params)`!

Let's check how to construct `init_params` to make sure:
If `"lock_file"` is in `sig.parameters` (or `present_params`):
If `has_var_kw`:
  `init_params = all_params`
Else:
  `init_params = {key: value for key, value in all_params.items() if key in present_params}`
`instance = super().__call__(**init_params)`

If `"lock_file"` is NOT in `sig.parameters`:
If `has_var_kw`:
  `init_