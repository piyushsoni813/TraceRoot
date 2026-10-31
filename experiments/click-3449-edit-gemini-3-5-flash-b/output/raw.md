An issue occurs when `echo_via_pager` (or command execution) closes stdout/stderr before command completion. Calling `flush()` on a closed stream in the `finally` block raises `ValueError: I/O operation on closed file`.

To fix this regression, we safely handle `(ValueError, OSError)` when flushing `sys.stdout` and `sys.stderr`.

```edit
FILE: src/click/testing.py
<<<<<<< SEARCH
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
=======
            finally:
                try:
                    sys.stdout.flush()
                except (ValueError, OSError):
                    pass
                try:
                    sys.stderr.flush()
                except (ValueError, OSError):
                    pass
>>>>>>> REPLACE
```