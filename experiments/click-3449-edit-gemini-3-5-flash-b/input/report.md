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
