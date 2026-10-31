"""Evaluator-only reproduction derived from tox-dev/filelock issue 346. Exit 0 means fixed."""
import tempfile
from filelock import FileLock


class FilePathLock(FileLock):
    def __init__(self, file_path):
        super().__init__(file_path + ".lock")


with tempfile.TemporaryDirectory() as d:
    path = d + "/a"
    lock = FilePathLock(path)
    assert lock.lock_file == path + ".lock", lock.lock_file
    print(lock.lock_file == path + ".lock")
