"""Validate a case: run the reproducer and targeted tests on the faulty and fixed revisions.

usage: admit_case.py <case_id> <faulty_rev> <fixed_rev> <test files...>
Uses cases/<id>/upstream (full clone) through throwaway clones under .tmp.
Reproducer exit code 0 means the bug is fixed. Writes reference/validation_run.json.
"""
import json
import os
import shutil
import stat
import subprocess
import sys

ROOT = "D:/TraceRoot"
PY = ROOT + "/.venv/Scripts/python.exe"
case, faulty, fixed, tests = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
up = f"{ROOT}/cases/{case}/upstream"
repro = f"{ROOT}/cases/{case}/reference/reproduce.py"


def _rm(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


# optional per-case environment details: {"shim_files": {path: text}, "pytest_args": [...]}
cfg_path = f"{ROOT}/cases/{case}/reference/env.json"
cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}


def run(cmd, cwd, env):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip().splitlines()


result = {"case_id": case, "faulty_revision": faulty, "fixed_revision": fixed, "tests": tests}
for label, rev in (("faulty", faulty), ("fixed", fixed)):
    co = f"{ROOT}/.tmp/adm-{case}-{label}"
    shutil.rmtree(co, onerror=_rm) if os.path.exists(co) else None
    subprocess.run(["git", "clone", "-q", "--no-checkout", up, co], check=True)
    subprocess.run(["git", "checkout", "-q", rev], cwd=co, check=True)
    for rel, text in cfg.get("shim_files", {}).items():
        open(os.path.join(co, rel), "w").write(text)
    env = dict(os.environ, PYTHONPATH=co + "/src", TMP=ROOT + "/.tmp", TEMP=ROOT + "/.tmp",
               PYTHONDONTWRITEBYTECODE="1")
    rc, out = run([PY, repro], co, env)
    trc, tout = run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp",
                     f"{ROOT}/.tmp/pt-{case}-{label}", *cfg.get("pytest_args", []), *tests], co, env)
    result[label] = {"reproduce_exit_code": rc, "reproduce_tail": out[-3:],
                     "pytest_exit_code": trc, "pytest_tail": tout[-3:]}
    print(label, json.dumps(result[label], indent=1))
open(f"{ROOT}/cases/{case}/reference/validation_run.json", "w").write(json.dumps(result, indent=2))
