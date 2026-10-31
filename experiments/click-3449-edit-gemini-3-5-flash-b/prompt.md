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

## Source excerpt

Unmodified code of the functions named in the stack trace:

```python
# src/click/testing.py (lines 616-703)

        # Set up fd capture before isolation replaces sys.stdout and sys.stderr.
        cap_out: _FDCapture | None = None
        cap_err: _FDCapture | None = None

        if self.capture == "fd":
            cap_out = _FDCapture(1)
            cap_err = _FDCapture(2)
            try:
                cap_out.start()
                cap_err.start()
            except OSError:
                cap_out = cap_err = None

        with self.isolation(input=input, env=env, color=color) as outstreams:
            # Point the captured streams' fileno() at the saved (original)
            # fd so that C-level consumers like faulthandler keep working
            # while fd 1/2 are redirected to the capture tmpfile.
            if cap_out is not None and cap_err is not None:
                sys.stdout._original_fd = cap_out.saved_fd  # type: ignore[union-attr]
                sys.stderr._original_fd = cap_err.saved_fd  # type: ignore[union-attr]

            return_value = None
            exception: BaseException | None = None
            exit_code = 0

            if isinstance(args, str):
                args = shlex.split(args)

            try:
                prog_name = extra.pop("prog_name")
            except KeyError:
                prog_name = self.get_default_prog_name(cli)

            try:
                return_value = cli.main(args=args or (), prog_name=prog_name, **extra)
            except SystemExit as e:
                exc_info = sys.exc_info()
                e_code = t.cast("int | t.Any | None", e.code)

                if e_code is None:
                    e_code = 0

                if e_code != 0:
                    exception = e

                if not isinstance(e_code, int):
                    sys.stdout.write(str(e_code))
                    sys.stdout.write("\n")
                    e_code = 1

                exit_code = e_code

            except Exception as e:
                if not catch_exceptions:
                    raise
                exception = e
                exit_code = 1
                exc_info = sys.exc_info()
            finally:
                sys.stdout.flush()
                sys.stderr.flush()

                # Stop fd capture and merge the captured bytes into
                # the stdout/stderr BytesIO streams. BytesIOCopy mirrors
                # those writes into outstreams[2] automatically.
                if cap_out is not None and cap_err is not None:
                    fd_out = cap_out.stop()
                    fd_err = cap_err.stop()
                    if fd_out:
                        outstreams[0].write(fd_out)
                    if fd_err:
                        outstreams[1].write(fd_err)

                stdout = outstreams[0].getvalue()
                stderr = outstreams[1].getvalue()
                output = outstreams[2].getvalue()

        return Result(
            runner=self,
            stdout_bytes=stdout,
            stderr_bytes=stderr,
            output_bytes=output,
            return_value=return_value,
            exit_code=exit_code,
            exception=exception,
            exc_info=exc_info,  # type: ignore
        )
```
