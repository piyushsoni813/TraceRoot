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
