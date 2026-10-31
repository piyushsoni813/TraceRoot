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

Invoking a command that calls `echo_via_pager` through the test runner raises
`ValueError: I/O operation on closed file`. This did not happen in the previous
release.

```python
from click import command, echo_via_pager
from click.testing import CliRunner

@command()
def cli():
    echo_via_pager("Hello, Click!")

result = CliRunner().invoke(cli)
print(repr(result.output))
```

Expected behavior: the command runs and its output is captured, with no exception.

## Stack trace

```text
Traceback (most recent call last):
  File "reproduce.py", line 11, in <module>
    result = CliRunner().invoke(cli)
  File "src/click/testing.py", line 676, in invoke
    sys.stdout.flush()
ValueError: I/O operation on closed file.
```
