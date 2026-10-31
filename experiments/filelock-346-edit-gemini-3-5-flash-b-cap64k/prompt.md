You are repairing a Python regression. You have only the bug report, stack
trace, and source excerpt below. Do not assume access to the rest of the repository, tests, Git history, or any
other tools.

Return your fix as edits inside exactly one fenced code block whose info string
is `edit`. Each edit has this exact form:

```edit
FILE: src/example/module.py
<<<<<<< SEARCH
exact original lines, copied character for character including indentation
=======
the replacement lines
>>>>>>> REPLACE
```

The SEARCH text must match the original code exactly and occur exactly once in
that file. You may put several edits inside the one block. Edits may modify only
files under `src/`. Do not modify, add, or delete tests, dependency files,
configuration, or generated files. Do not include prose outside the code block.

## Bug report

A subclass of `FileLock` whose constructor takes a differently named first
parameter can no longer be created. This worked in the previous release.

```python
import tempfile
from filelock import FileLock

class FilePathLock(FileLock):
    def __init__(self, file_path):
        super().__init__(file_path + ".lock")

with tempfile.TemporaryDirectory() as d:
    path = d + "/a"
    lock = FilePathLock(path)
    print(lock.lock_file == path + ".lock")
```

Expected behavior: the lock is created and `True` is printed.

## Stack trace

```text
Exception ignored in: <function BaseFileLock.__del__ at 0x0000020AA0FC4680>
Traceback (most recent call last):
  File "src/filelock/_api.py", line 400, in __del__
    self.release(force=True)
  File "src/filelock/_api.py", line 361, in release
    if self.is_locked:
  File "src/filelock/_api.py", line 267, in is_locked
    return self._context.lock_file_fd is not None
AttributeError: 'FilePathLock' object has no attribute '_context'
Traceback (most recent call last):
  File "reproduce.py", line 13, in <module>
    lock = FilePathLock(path)
  File "src/filelock/_api.py", line 137, in __call__
    instance = super().__call__(**init_params)
TypeError: FilePathLock.__init__() got an unexpected keyword argument 'lock_file'
```

## Source excerpt

Unmodified code of the functions named in the stack trace:

```python
# src/filelock/_api.py (lines 398-400)
    def __del__(self) -> None:
        """Called when the lock object is deleted."""
        self.release(force=True)

# src/filelock/_api.py (lines 353-370)
    def release(self, force: bool = False) -> None:  # noqa: FBT001, FBT002
        """
        Releases the file lock. Please note, that the lock is only completely released, if the lock counter is 0.
        Also note, that the lock file itself is not automatically deleted.

        :param force: If true, the lock counter is ignored and the lock is released in every case/

        """
        if self.is_locked:
            self._context.lock_counter -= 1

            if self._context.lock_counter == 0 or force:
                lock_id, lock_filename = id(self), self.lock_file

                _LOGGER.debug("Attempting to release lock %s on %s", lock_id, lock_filename)
                self._release()
                self._context.lock_counter = 0
                _LOGGER.debug("Lock %s released on %s", lock_id, lock_filename)

# src/filelock/_api.py (lines 258-267)
    def is_locked(self) -> bool:
        """

        :return: A boolean indicating if the lock file is holding the lock currently.

        .. versionchanged:: 2.0.0

            This was previously a method and is now a property.
        """
        return self._context.lock_file_fd is not None

# src/filelock/_api.py (lines 82-142)
    def __call__(  # noqa: PLR0913
        cls,
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        mode: int = 0o644,
        thread_local: bool = True,  # noqa: FBT001, FBT002
        *,
        blocking: bool = True,
        is_singleton: bool = False,
        **kwargs: Any,  # capture remaining kwargs for subclasses  # noqa: ANN401
    ) -> BaseFileLock:
        if is_singleton:
            instance = cls._instances.get(str(lock_file))  # type: ignore[attr-defined]
            if instance:
                params_to_check = {
                    "thread_local": (thread_local, instance.is_thread_local()),
                    "timeout": (timeout, instance.timeout),
                    "mode": (mode, instance.mode),
                    "blocking": (blocking, instance.blocking),
                }

                non_matching_params = {
                    name: (passed_param, set_param)
                    for name, (passed_param, set_param) in params_to_check.items()
                    if passed_param != set_param
                }
                if not non_matching_params:
                    return cast(BaseFileLock, instance)

                # parameters do not match; raise error
                msg = "Singleton lock instances cannot be initialized with differing arguments"
                msg += "\nNon-matching arguments: "
                for param_name, (passed_param, set_param) in non_matching_params.items():
                    msg += f"\n\t{param_name} (existing lock has {set_param} but {passed_param} was passed)"
                raise ValueError(msg)

        # Workaround to make `__init__`'s params optional in subclasses
        # E.g. virtualenv changes the signature of the `__init__` method in the `BaseFileLock` class descendant
        # (https://github.com/tox-dev/filelock/pull/340)

        all_params = {
            "lock_file": lock_file,
            "timeout": timeout,
            "mode": mode,
            "thread_local": thread_local,
            "blocking": blocking,
            "is_singleton": is_singleton,
            **kwargs,
        }

        present_params = set(inspect.signature(cls.__init__).parameters)  # type: ignore[misc]
        init_params = {key: value for key, value in all_params.items() if key in present_params}
        # The `lock_file` parameter is required
        init_params["lock_file"] = lock_file

        instance = super().__call__(**init_params)

        if is_singleton:
            cls._instances[str(lock_file)] = instance  # type: ignore[attr-defined]

        return cast(BaseFileLock, instance)
```
