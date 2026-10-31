# First benchmark-case research

Research date: 2026-10-23

## Selection criteria

The first case should be a public Python repository with a permissive license,
a pinned faulty revision, a self-contained bug report and traceback, a known
upstream repair, and a fast deterministic evaluator. Model inputs must not
include the repair commit, patch, or any evaluator-only test derived from it.

## Recommended candidate: Flask issue 5160

| Field | Evidence |
| --- | --- |
| Project | [pallets/flask](https://github.com/pallets/flask) |
| License | BSD-3-Clause, declared in the project's `pyproject.toml` at the faulty revision. |
| Bug report | [Issue 5160](https://github.com/pallets/flask/issues/5160), "Switch to importlib breaks scripts with `app.run()`". |
| Faulty revision | [`84e11a1e827c0f55f9b9ee15952eddcf8a6492e0`](https://github.com/pallets/flask/commit/84e11a1e827c0f55f9b9ee15952eddcf8a6492e0), `use importlib instead of pkgutil`. |
| Repair | [PR 5161](https://github.com/pallets/flask/pull/5161), merged as [`4be9f521425b7ad659b182c319dc3afb8fe64f53`](https://github.com/pallets/flask/commit/4be9f521425b7ad659b182c319dc3afb8fe64f53). |
| Python requirement | `>=3.8`; the workspace has Python 3.13.7, which satisfies the declared requirement. |
| Failure shape | A five-line Flask script fails at app construction with `ValueError: __main__.__spec__ is None`. |
| External services | None. The evaluator can run locally without a server request or network service. |

The issue report identifies the regression commit and supplies both a minimal
reproducer and a traceback. The repair is a small, focused change to handling
of `importlib.util.find_spec` failures. These properties make causal attribution
and pass/fail evaluation straightforward for a first baseline.

### Evaluator design

At the faulty revision, create an evaluator-only script from the issue's
reproducer and run it with the repository's source on `PYTHONPATH`. Its
acceptance condition is process exit code 0 after constructing `Flask(__name__)`.
The faulty revision should exit nonzero with the reported `ValueError`; a repair
candidate should exit 0. Run the relevant existing Flask tests after this targeted
check, subject to environment compatibility.

The initial model input should contain only a normalized bug report and stack
trace copied from issue 5160. It must omit the faulty commit identifier, linked
PR, repair commit, any patch, and evaluator script.

### Case admission checklist

- [ ] Clone exactly the faulty revision into an isolated case checkout.
- [ ] Install the project's pinned runtime and test dependencies in `.venv`.
- [ ] Run the issue reproducer and record the actual traceback and exit status.
- [ ] Apply the upstream repair in a separate evaluator-only checkout and repeat
  the reproducer.
- [ ] Run a relevant upstream test selection on both revisions and record results.
- [ ] Create a case manifest with interpreter version, dependency versions,
  commands, revision hashes, and artifact hashes.
- [ ] Store the upstream repair and evaluator test under `cases/flask-5160/reference/`.

No item in this checklist has been run yet.

## Other candidates screened

| Candidate | Why it was not selected first |
| --- | --- |
| [pytest 9765](https://github.com/pytest-dev/pytest/issues/9765) | Has a useful Windows traceback and an associated repair ([PR 11708](https://github.com/pytest-dev/pytest/pull/11708)), but needs a MSYS path-case setup and Python 3.9 behavior. It is harder to make deterministic in the current Python 3.13 environment. |
| [Flask 2767](https://github.com/pallets/flask/issues/2767) | Clearly reported regression, but targets Flask 1.0 and Python 3.5-era dependencies, creating avoidable compatibility work. |
| [Sphinx 11542](https://github.com/sphinx-doc/sphinx/issues/11542) | Clear regression report, but validation involves link checking and therefore external network behavior. |
| [Flask 5804](https://github.com/pallets/flask/issues/5804) | It has a detailed current reproducible report, but its behavior depends on streaming request lifecycle details and is more complex than needed for the first baseline. |

## Research caveat

GitHub search results contain many unmerged or AI-generated pull requests.
Candidate admission therefore requires verification against the original issue,
the merged upstream repair, and a locally reproduced failure. The research above
uses only the linked issue, the regression commit, the merged PR, and the faulty
revision's metadata.

## Second-round screening (2026-10-24)

Goal: more cases for the same protocol. The scan covered closed issues containing
a traceback in ten permissively licensed Python projects, kept those closed after
2022 by a merged PR that touches exactly one non-test `.py` file, adds or changes
tests, and has at most 60 changed lines. Five were shortlisted for diversity of
project and bug type. Licenses were read from the GitHub repository metadata.

**Status: screened only. None is admitted.** Nothing below has been cloned,
reproduced, or run, and the admission checklist above has not been started for any
of them. Revisions come from the GitHub API; for merge commits with two parents,
the first parent is the mainline revision before the PR landed and still needs to
be confirmed locally.

| Candidate | Issue and traceback | Repair PR (files, size) | Fix commit and revision before it | License |
| --- | --- | --- | --- | --- |
| attrs 1284 | [attrs#1284](https://github.com/python-attrs/attrs/issues/1284): `SyntaxError` in generated `__init__` with `kw_only` default plus `__attrs_pre_init__`; five-line reproducer and traceback | [PR 1319](https://github.com/python-attrs/attrs/pull/1319): `src/attr/_make.py` plus tests, +27/-5 | fix `09161fc9181bf94aa3bbc5509c663d736a9553dc`, before `689a0e64012d1e576ebd99e786a254bc537582c6` | MIT |
| attrs 1416 | [attrs#1416](https://github.com/python-attrs/attrs/issues/1416): subclass instance raises `unexpected keyword argument`; minimal reproducer given | [PR 1417](https://github.com/python-attrs/attrs/pull/1417): `src/attr/_make.py` plus tests, +17/-1 | fix `3b0378dd66d33ebddb52be85b8c4aac6a914b1a2`, before `19943b775d40c018e844f2cb1728442f58112a3b` | MIT |
| Jinja 1701 | [jinja#1701](https://github.com/pallets/jinja/issues/1701): `TypeError` rendering a block through `NativeEnvironment`; one-line reproducer and traceback | [PR 1702](https://github.com/pallets/jinja/pull/1702): `src/jinja2/runtime.py` plus tests, +16/-2 | fix `a4abbfd7538e9ff216244266579232585033136c`, first parent `791dd3b0415b99faac229d42a81db1d7096b003c` | BSD-3-Clause |
| Jinja 2027 | [jinja#2027](https://github.com/pallets/jinja/issues/2027): `PicklingError` for `jinja2.utils.missing`; three-line reproducer and traceback | [PR 2029](https://github.com/pallets/jinja/pull/2029): `src/jinja2/utils.py` plus tests, +25/-2 | fix `1dc04bccf9384cced4262d7ca7157638b0ebd970`, first parent `ba8847a466d0f3ad622502f86e819737a4b9fdc7` | BSD-3-Clause |
| Werkzeug 2955 | [werkzeug#2955](https://github.com/pallets/werkzeug/issues/2955): `IndexError` parsing `Authorization.from_header("Digest =foo")`; one-line reproducer and traceback | [PR 2956](https://github.com/pallets/werkzeug/pull/2956): `src/werkzeug/http.py` plus tests, +19/-3 | fix `6732b579eeaaa2cfb562e57bed55994e4f93ccfb`, first parent `40319f91dbbae0a780526eab037a009b1a7e4d36` | BSD-3-Clause |

Also seen but not shortlisted: Rich 2197 (import fails when the working directory
was deleted; Windows cannot delete the current directory, so the reproducer would
need a simulated failure), Click 2790 (wrong help hint, no traceback in the report),
and Rich 2294 and attrs 1328 (repairs touch several source files).

Known risks to check at admission: whether each faulty revision runs on Python
3.13.7 with compatible test dependencies, and whether the issue's reproducer still
fails at that revision, since a report can predate the exact parent commit.

## Regression re-screen and admission (2026-10-24)

The project goal is repairing regressions: something worked, a change broke it. The
five shortlisted above were not all regressions, so the pool was re-screened for
issues whose text or fixing PR says the behavior worked in an earlier release. Jinja
1701, Jinja 2027, Werkzeug 2955 and the rest of that shortlist showed no such
evidence in the issue or PR text and were **not admitted**. That is a statement
about the text only; they may still be regressions.

Admitted (all four validated on this machine, Python 3.13.7, pytest 7.3.1):

| Case | Reproducer on faulty revision | Reproducer on fixed revision | Targeted tests faulty / fixed | Breaking commit (found by `git bisect run`) |
| --- | --- | --- | --- | --- |
| attrs-1416 | exit 1, `TypeError ... unexpected keyword argument 'dag_id'` | exit 0 | 13 / 14 passed | `e048efcb` "Perform attr order checks after field transformer (#1401)" |
| packaging-638 | exit 1, `TypeError: expected string or bytes-like object` | exit 0 | 2221 / 2222 passed | `53dbb257` "Adhere to PEP 685 when evaluating markers with extras (#545)" |
| filelock-346 | exit 1, `TypeError ... unexpected keyword argument 'lock_file'` | exit 0 | 103 / 104 passed, 3 skipped | `192f1efc` "Use a metaclass to implement the singleton pattern (#340)" |
| click-3449 | exit 1, `ValueError: I/O operation on closed file` | exit 0 | 258 / 259 passed, 21 skipped | `c69643b6` "Add file-like pager: click.get_pager_file() (#1572)" |

Per-case files are in `cases/<id>/`: `metadata.json`, `report.md`, `stacktrace.txt`
(model inputs, normalized from the issue and a real run), `reference/reproduce.py`,
`reference/validation_run.json`, and a full clone in `upstream/`. The validation
runner is `tools/scripts/admit_case.py`.

Environment notes that affect reproduction:
- `filelock-346`: `src/filelock/version.py` is generated by hatch-vcs and gitignored,
  so a stand-in is written into each checkout (`reference/env.json`).
- `click-3449`: pytest 7.3.1 on Python 3.13 raises `ast.Str` DeprecationWarning as an
  error under Click's config, so tests run with `-W ignore::DeprecationWarning`.
- Test dependencies installed into `.venv`: hypothesis, pretend, pytest-mock,
  pytest-timeout, pyparsing (needed to run packaging 21.3 during bisect).
- A first bisect for packaging stopped at a layout change and at a bump commit
  because of missing `pyparsing`; it was rerun after the fix. Bisect results were
  checked against the issue text, and each matches what the report describes.
- The report inputs include the issue's own reproducer code. The original
  `flask-5160` input does not, so Flask results are not directly comparable.
