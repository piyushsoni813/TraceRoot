"""Evaluator-only reproduction derived from pallets/click issue 3449. Exit 0 means fixed."""
from click import command, echo_via_pager
from click.testing import CliRunner


@command()
def cli():
    echo_via_pager("Hello, Click!")


result = CliRunner().invoke(cli)
assert result.exception is None, repr(result.exception)
print(repr(result.output))
