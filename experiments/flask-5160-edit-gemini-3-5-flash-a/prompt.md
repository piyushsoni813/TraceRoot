You are repairing a Python regression. You have only the bug report and stack
trace below. Do not assume access to the repository, tests, Git history, or any
other tools.

Return your fix as edits inside exactly one fenced code block whose info string
is `edit`. Each edit has this exact form:

```edit
FILE: src/flask/scaffold.py
<<<<<<< SEARCH
exact original lines, copied character for character including indentation
=======
the replacement lines
>>>>>>> REPLACE
```

The SEARCH text must match the original code exactly and occur exactly once in
that file. You may put several edits inside the one block. Edits may modify only
files under `src/flask/`. Do not modify, add, or delete tests, dependency files,
configuration, or generated files. Do not include prose outside the code block.

## Bug report

Creating a Flask application in a Python script fails before the development
server starts. The same pattern previously worked. The failure occurs while the
framework determines the application's instance path.

Environment reported by the original reporter:

- Python 3.11.4
- Flask development branch

Expected behavior: constructing the application should succeed and the script
should be able to continue to its server startup code.

## Stack trace

```text
Traceback (most recent call last):
  File "app.py", line 3, in <module>
    app = Flask(__name__)
  File "flask/app.py", line 376, in __init__
    instance_path = self.auto_find_instance_path()
  File "flask/app.py", line 630, in auto_find_instance_path
    prefix, package_path = find_package(self.import_name)
  File "flask/scaffold.py", line 898, in find_package
    package_path = _find_package_path(import_name)
  File "flask/scaffold.py", line 858, in _find_package_path
    spec = importlib.util.find_spec(root_mod_name)
  File "<frozen importlib.util>", line 111, in find_spec
ValueError: __main__.__spec__ is None
```
