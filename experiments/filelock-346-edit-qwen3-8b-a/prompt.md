You are repairing a Python regression. You have only the bug report, stack
trace below. Do not assume access to the rest of the repository, tests, Git history, or any
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
