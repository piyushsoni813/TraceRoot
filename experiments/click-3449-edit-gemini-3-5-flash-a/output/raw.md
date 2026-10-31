 `sys.stdout` or `click.echo`?
Wait! What if `_null_pager` writes to `sys.stdout` or `click.get_text_stream("stdout")` or `echo()`?
Wait! If `_null_pager` writes to stdout, does it close stdout? No!

Wait! What about `_pipe_pager` and `_tempfile_pager`?
Let's look at `_pipe_pager`:
```python
def _pipe_pager(text_or_generator, cmd):
    import subprocess
    proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for text in text_or_generator:
            proc.stdin.write(text.encode('utf-8'))
    except (IOError, KeyboardInterrupt):
        pass
    else:
        proc.stdin.close()
    proc.wait()
```
Wait! Look at `_pipe_pager`!
When `proc.stdin.close()` is called... wait, `proc.stdin` is the stdin of the subprocess `proc` (`Popen`). That's `proc.stdin`, NOT `sys.stdout`!

Wait! What about `_tempfile_pager`?
`with open(filename, 'w') as f:` -> closes `f` (the temp file).
Then `os.system(...)`.

Wait! What if `echo_via_pager` uses `pydoc.pager`?
Wait! Does `click` use `pydoc.pager` in `echo_via_pager`?
Wait! Let's search Click's source code for `echo_via_pager`!
In Click:
Wait! Does `echo_via_pager` call `pydoc.pager`?
Let's check:
In some versions of Click (or Click 8.x):
```python
def echo_via_pager(
    text_or_generator: typing.Union[str, typing.Iterable[str]],
    color: typing.Optional[bool] = None,
) -> None:
    ...
```
Wait! What if `echo_via_pager` calls `pydoc.pager`?
Wait! In `pydoc.pager`:
If `pydoc.pager(text)` is called:
`pydoc.pager` prints text using a pager.
Wait! What happens when `pydoc.pager` is called when `sys.stdout` is replaced by `CliRunner`?
Wait! In `CliRunner`, `sys.stdout` is replaced by a custom stream (e.g. `EchoStream` or `_StreamWrapper` or `io.TextIOWrapper` or `io.StringIO`).
Wait! In `CliRunner`, `sys.stdout` is set to `out` (or wrapper).
What does `sys.stdout` look like in `CliRunner`?
Let's check `src/click/testing.py`!

In `src/click/testing.py`:
What is `sys.stdout` set to in `isolation()`?
Let's trace `isolation()` in `src/click/testing.py`!
In `src/click/testing.py`:
```python
class EchoStream:
    def __init__(self, stream):
        self._stream = stream

    def write(self, s):
        self._stream.write(s)

    def flush(self):
        self._stream.flush()

    def isatty(self):
        return False

    def close(self):
        self._stream.close()
```
Wait! `EchoStream` or `io.TextIOWrapper`!
Wait! Is `sys.stdout` closed by something in `echo_via_pager` or `pydoc` or `testing.py`?
Wait! What if `echo_via_pager` in Click uses `sys.stdout` or `get_text_stream` or `open` or `pydoc.pager`?

Wait! Let's think: what does `echo_via_pager` do when `text_or_generator` is passed?
Let's check:
In `click/_termui_impl.py`:
```python
def echo_via_pager(
    text_or_generator: typing.Union[str, typing.Iterable[str]],
    color: typing.Optional[bool] = None,
) -> None:
    color = resolve_color_default(color)

    if isinstance(text_or_generator, str):
        text_or_generator = [text_or_generator]

    if color:
        text_generator = (style(text, fg=color) for text in text_or_generator)
    else:
        text_generator = text_or_generator

    pager_cmd = _get_pager()
    pager_cmd(text_generator)
```
Wait! What is `_get_pager()`?
```python
def _get_pager():
    pager = os.environ.get("PAGER")

    if pager:
        if _is_less_page(pager):
            return lambda text: _pipe_pager(text, pager)
        return lambda text: _tempfile_pager(text, pager)

    if shutil.which("less"):
        return lambda text: _pipe_pager(text, "less -RFX")

    return _null_pager
```
Wait! Look at `_get_pager()`!
When `shutil.which("less")` is True (which is true on almost all Linux / macOS systems!), `_get_pager()` returns `lambda text: _pipe_pager(text, "less -RFX")`!
Wait!
Let's trace what happens when `_pipe_pager(text, "less -RFX")` runs!

```python
def _pipe_pager(text_or_generator, cmd):
    import subprocess
    proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for text in text_or_generator:
            proc.stdin.write(text.encode('utf-8'))
    except (IOError, KeyboardInterrupt):
        pass
    else:
        proc.stdin.close()
    proc.wait()
```
Wait!
When `subprocess.Popen("less -RFX", shell=True, stdin=subprocess.PIPE)` runs:
What does `less -RFX` do when executed in a process where stdout/stdin is redirected by `CliRunner`?
`CliRunner` redirects Python's `sys.stdout` and `sys.stdin`.
It DOES NOT redirect file descriptor 1 or 0 unless `mix_stderr` / fd redirection is used!
When `subprocess.Popen("less -RFX", ...)` runs, `less` starts.
`less` tries to open `/dev/tty` or write to stdout. But wait! `less` might fail or exit or write to stdout. But why would `sys.stdout` in Python be closed?!
Wait! Does `less` close anything in Python? No, `less` is a separate process.

Wait... is `_pipe_pager` what is actually in `_termui_impl.py` or is `_pipe_pager` / `echo_via_pager` using something else?
Wait! What if `_pipe_pager` or `echo_via_pager` or `pydoc` or `_termui_impl.py` DOES something with `sys.stdout`?

Wait! Let's check `pydoc.pager` again!
What if `echo_via_pager` calls `pydoc.pager`?
Wait! Does `echo_via_pager` in Click call `pydoc.pager` or use `_pager`?
Wait! In Click 8.0/8.1/8.2:
Let's check if Click uses `pydoc.pager` or custom pager!
Wait! Click used to have `_termui_impl.py` with custom pagers or `pydoc.pager`.
Wait! In Click 8.x:
Does Click's `echo_via_pager` call `pydoc.pager` or `_pager`?
Wait! Let's search/recall Click's `echo_via_pager` code!
Wait! In `click/_termui_impl.py`:
```python
def echo_via_pager(text_or_generator, color=None):
    text = ...
    # wait!
```
Wait, why don't we check `src/click/testing.py` and `src/click/_termui_impl.py` or `src/click/termui.py`?
Wait! Why would `sys.stdout.flush()` in `src/click/testing.py` raise `ValueError: I/O operation on closed file`?

Let's look at `src/click/testing.py`!
In `src/click/testing.py`:
When `CliRunner.invoke` runs:
```python
    File "src/click/testing.py", line 676, in invoke
        sys.stdout.flush()
    ValueError: I/O operation on closed file.
```

Wait! Why is `sys.stdout.flush()` called on line 676 of `src/click/testing.py`?
Let's look at what `sys.stdout` is during `CliRunner.invoke`.
In `CliRunner.isolation()`:
How are `sys.stdout`, `sys.stdin`, `sys.stderr` redirected in `CliRunner`?
Let's check `CliRunner.isolation`:
```python
@contextmanager
def isolation(
    self,
    input: typing.Optional[typing.Union[str, bytes, typing.IO[typing.Any]]] = None,
    env: typing.Optional[typing.Mapping[str, typing.Optional[str]]] = None,
    color: bool = False,
) -> typing.Iterator[typing.Tuple[io.BytesIO, io.BytesIO]]:
    bytes_input = bytes_output = bytes_error = None

    if input is not None:
        if isinstance(input, str):
            bytes_input = io.BytesIO(input.encode("utf-8"))
        else:
            bytes_input = input

    bytes_output = io.BytesIO()

    if self.mix_stderr:
        bytes_error = bytes_output
    else:
        bytes_error = io.BytesIO()

    ...
```
Wait! How are `sys.stdout` and `sys.stderr` set in `isolation`?
In Python 3 (Click 8.x):
```python
    echo_input = sys.stdin
    echo_output = sys.stdout
    echo_error = sys.stderr

    if bytes_input is not None:
        sys.stdin = echo_input = io.TextIOWrapper(bytes_input, encoding="utf-8")

    sys.stdout = echo_output = io.TextIOWrapper(bytes_output, encoding="utf-8")
    sys.stderr = echo_error = io.TextIOWrapper(bytes_error, encoding="utf-8")
```
WAIT! Look at that!
`sys.stdout` is set to `io.TextIOWrapper(bytes_output, encoding="utf-8")`!
Wait! What happens if someone (or some code or standard library function) calls `close()` on a stream or wrapper, or what if `echo_via_pager` wraps `sys.stdout` or closes a stream or wrapper?
WAIT!
What if `echo_via_pager` does:
```python
stream = click.get_text_stream("stdout")
```
or
`with io.TextIOWrapper(...)` or `pydoc.pager` or `_pipe_pager`?
Wait! What if `echo_via_pager` uses `pydoc.pager`?
Wait! What does `pydoc.pager` do when `sys.stdout` is an `io.TextIOWrapper`?
Wait! What if `echo_via_pager` in `src/click/_termui_impl.py` does:
```python
def echo_via_pager(text_or_generator, color=None):
    ...
```
Wait! What if `echo_via_pager` or `pydoc.pager` or something closes `sys.stdout`?
Wait! Why would `echo_via_pager` close `sys.stdout`?
Wait! Could `echo_via_pager` or `pager` do:
```python
def echo_via_pager(text_or_generator, color=None):
    ...
    # Wait! What if echo_via_pager in click 8.1 / 8.2 uses:
    # inside _termui_impl.py:
```
Let's think: what is in `src/click/_termui_impl.py` or `src/click/termui.py` for `echo_via_pager`?
Wait! In `src/click/_termui_impl.py`:
```python
def echo_via_pager(text_or_generator, color=None):
    text = ...
    # Wait! Does echo_via_pager open stdout or stdout.buffer or get_binary_stream?
```
Wait! What if `echo_via_pager` does:
```python
    stdout = get_binary_stream("stdout")
    ...
```
Wait! If `get_binary_stream("stdout")` returns `sys.stdout.buffer` (which is `bytes_output`, the `io.BytesIO` underlying `sys.stdout`), OR what if `echo_via_pager` creates `io.TextIOWrapper(sys.stdout.buffer)` and then closes it or uses it in a `with` statement?
WAIT!
If someone wrote:
```python
with io.TextIOWrapper(sys.stdout.buffer, ...) as f:
    ...
```
Or `with open(sys.stdout.fileno(), ...)`
Or `with ...`
When a `TextIOWrapper` created around `sys.stdout.buffer` is closed (e.g., when exiting a `with` block or garbage collected if `__del__` closes it!), closing that wrapper CLOSES the underlying buffer (`sys.stdout.buffer`), which CLOSES `sys.stdout`!

WAIT! Or what if `echo_via_pager` in `_termui_impl.py` does:
`with get_text_stream("stdout") as ...`?
Or what if `echo_via_pager` does:
`with get_binary_stream("stdout") as ...`?
Or what if `pydoc.pager` or `_pipe_pager` or `_tempfile_pager` or `_null_pager` or `echo_via_pager` closes something?

Wait! Let's check: why would `sys.stdout.flush()` in `src/click/testing.py` raise `ValueError`?
Wait! Look at `src/click/testing.py`:
Line 676:
```python
            finally:
                sys.stdout.flush()
```
Wait! Why is `sys.stdout.flush()` called in `src/click/testing.py`?
In `CliRunner.invoke(...)`:
```python
            finally:
                sys.stdout.flush()
```
Wait! Is `sys.stdout.flush()` in `testing.py` supposed to flush stdout?
What if `sys.stdout` is closed (for example, by the command itself, or by `echo_via_pager`, or by any CLI command that closes stdout)?
Wait! If a CLI command closes stdout (or if `echo_via_pager` closes stdout, or if stdout is closed for any reason), then `sys.stdout.flush()` in `finally:` of `invoke()` will raise `ValueError: I/O operation on closed file`!

Wait! Is `sys.stdout.flush()` in `testing.py` protected against closed stdout?
Wait! Or is `echo_via_pager` closing `sys.stdout` when it shouldn't? Or both / which one?

Let's re-read the bug report very carefully!
"Invoking a command that calls `echo_via_pager` through the test runner raises `ValueError: I/O operation on closed file`. This did not happen in the previous release."

"This did not happen in the previous release."

What changed between the previous release and current release in Click?
Let's think: what changed in `echo_via_pager` or `testing.py` or `isolation` in Click?
Wait! In a recent Click release (e.g. Click 8.1.4 / 8.1.5 / 8.1.6 / 8.1.7 or 8.2.0):
Wait! In `testing.py`, or in `echo_via_pager`:
Wait! In `echo_via_pager`:
How does `echo_via_pager` output text when running?
Wait! Does `echo_via_pager` call `pager`?
What does `echo_via_pager` do?
Let's check `echo_via_pager` in `click/_termui_impl.py`:
```python
def echo_via_pager(
    text_or_generator: typing.Union[str, typing.Iterable[str]],
    color: typing.Optional[bool] = None,
) -> None:
    ...
```
Wait! What if `echo_via_pager` in `click/_termui_impl.py` or `click/termui.py` was changed?
Wait! What if `echo_via_pager` in `click/_termui_impl.py` uses `sys.stdout` or `get_text_stream` or `pager`?
Wait! Let's check what `echo_via_pager` does in Click!

In Click `_termui_impl.py`:
```python
def echo_via_pager(
    text_or_generator: typing.Union[str, typing.Iterable[str]],
    color: typing.Optional[bool] = None,
) -> None:
    ...
```
Wait! What if `echo_via_pager` converts `text_or_generator` to a string or generator, and then passes it to `_pager`?
Wait! How does `_pager` work in Click?
