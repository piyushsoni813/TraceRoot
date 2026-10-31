"""Score one agent run with the same independent evaluator as the baseline.

usage: python -I score.py <run_dir>

Writes <run_dir>/evaluation.json with four parts:
  repair          same checks as the baseline: apply edits to a clean checkout at the faulty
                  revision, evaluator reproducer must exit 0, held-out upstream tests must pass.
  root_cause      the report is compared with the real fix by script: breaking commit, files,
                  function. A match on commit is a match; file plus function is "likely" and
                  needs a person to confirm the mechanism; anything else is partial or a miss.
  evidence        result of the evidence checker if evidence_check.json exists (else null).
  cost            tool calls, model calls, tokens, wall time from result.json.
The agent's own workspace is never used: the edits are replayed on a fresh checkout.
"""
import json, os, re, shutil, stat, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = f"{ROOT}/.venv/Scripts/python.exe" if os.path.exists(f"{ROOT}/.venv/Scripts/python.exe") else sys.executable
SCOPE = "src/"


def _rm(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def case_info(case):
    d = f"{ROOT}/cases/{case}"
    meta = json.load(open(f"{d}/metadata.json", encoding="utf-8"))
    fixed, breaking = meta.get("fixed_revision"), meta.get("breaking_commit")
    if not fixed:  # flask-5160 was admitted before these fields existed
        fixed = json.load(open(f"{d}/reference/validation.json", encoding="utf-8"))["reference_revision"]
    if not breaking:  # for flask the faulty revision is itself the change that broke it
        breaking = meta["faulty_revision"]
    tests = meta.get("targeted_tests") or ["tests/test_helpers.py", "tests/test_instance_config.py"]
    env_path = f"{d}/reference/env.json"
    return {"dir": d, "faulty": meta["faulty_revision"], "fixed": fixed, "breaking": breaking, "tests": tests,
            "upstream": f"{d}/upstream", "env": json.load(open(env_path)) if os.path.exists(env_path) else {}}


def score_repair(case, info, edits, name):
    """Returns (outcome, detail dict). Outcome names match the baseline runner."""
    for ed in edits:
        p = ed["path"]
        if not p.startswith(SCOPE) or ".." in p.replace("\\", "/").split("/"):
            return "disallowed_patch_scope", {"path": p}
    co = f"{ROOT}/.tmp/score-{name}"
    if os.path.exists(co):
        shutil.rmtree(co, onerror=_rm)
    subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "-q", "--no-checkout", info["upstream"], co], check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", info["faulty"]], cwd=co, check=True, capture_output=True)
    for rel, text in info["env"].get("shim_files", {}).items():
        open(os.path.join(co, rel), "w").write(text)
    for ed in edits:
        path = os.path.join(co, ed["path"])
        if not os.path.isfile(path):
            return "patch_does_not_apply", {"detail": f"file not found: {ed['path']}"}
        src = open(path, encoding="utf-8", newline="").read()
        n = src.count(ed["search"])
        if n != 1:
            return "patch_does_not_apply", {"detail": f"search matched {n} times (needs exactly 1)", "file": ed["path"]}
        open(path, "w", encoding="utf-8", newline="").write(src.replace(ed["search"], ed["replace"], 1))
    applied = subprocess.run(["git", "diff"], cwd=co, capture_output=True, text=True).stdout
    env = dict(os.environ, PYTHONPATH=os.path.join(co, "src"), TMP=ROOT + "/.tmp", TEMP=ROOT + "/.tmp", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([PY, f"{info['dir']}/reference/reproduce.py"], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        return "evaluator_still_fails", {"reproduce_exit_code": r.returncode, "stderr_tail": r.stderr.strip().splitlines()[-1:], "applied_diff": applied}
    for tf in info["tests"]:  # held-out tests: the upstream versions at the fixed revision
        shown = subprocess.run(["git", "show", f"{info['fixed']}:{tf}"], cwd=info["upstream"], capture_output=True)
        if shown.returncode == 0:
            open(os.path.join(co, tf), "wb").write(shown.stdout)
    t = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", f"{ROOT}/.tmp/pt-score-{name}",
                        *info["env"].get("pytest_args", []), *info["tests"]], cwd=co, env=env, capture_output=True, text=True)
    tail = t.stdout.strip().splitlines()[-1:]
    if t.returncode != 0:
        return "upstream_regression_check_fails", {"reproduce_exit_code": 0, "pytest_tail": tail, "applied_diff": applied}
    shutil.rmtree(co, onerror=_rm)
    return "success", {"reproduce_exit_code": 0, "pytest_tail": tail, "applied_diff": applied}


def score_root_cause(info, rc):
    """Compare the reported root cause with the real fix. Returns a dict."""
    rc = rc or {}
    diff = subprocess.run(["git", "diff", "-U3", info["faulty"], info["fixed"], "--", "src"],
                          cwd=info["upstream"], capture_output=True, text=True, errors="replace").stdout
    fix_files = sorted(set(re.findall(r"^\+\+\+ b/(\S+)", diff, re.M)))
    claimed_commit = (rc.get("breaking_commit") or "").strip().lower()
    real = info["breaking"].lower()
    commit_match = len(claimed_commit) >= 7 and (real.startswith(claimed_commit) or claimed_commit.startswith(real))
    claimed_file = (rc.get("file") or "").strip().replace("\\", "/")
    # a report may name several files or functions: "a.py, b.py", "a.py and b.py", "f; g"
    claimed_files = [p.strip("`'\" ") for p in re.split(r",|;|\band\b|\s+", claimed_file) if p.strip("`'\" ").endswith(".py")]
    file_match = any(p in fix_files for p in claimed_files)
    names = [n.strip("`'\"() ") for n in re.split(r",|;|\band\b|\s+", (rc.get("function") or "").strip())]
    fns = [re.split(r"[.:]", n)[-1] for n in names if n.strip("`'\"() ")]
    function_match = any(fn and re.search(r"\b" + re.escape(fn) + r"\b", diff) for fn in fns)
    if commit_match:
        status = "match"
    elif file_match and function_match:
        status = "likely"
    elif file_match or function_match:
        status = "partial"
    else:
        status = "miss"
    return {"status": status, "commit_match": commit_match, "file_match": file_match, "function_match": function_match,
            "fix_files": fix_files, "claimed": {"file": claimed_file, "function": rc.get("function", ""), "breaking_commit": claimed_commit},
            "needs_human_review": status in ("likely", "partial")}


def score(run_dir):
    run_dir = os.path.normpath(run_dir)
    cfg = json.load(open(f"{run_dir}/run.json", encoding="utf-8"))
    info = case_info(cfg["case_id"])
    name = os.path.basename(run_dir)
    result = json.load(open(f"{run_dir}/result.json", encoding="utf-8")) if os.path.exists(f"{run_dir}/result.json") else {}
    sub_path = f"{run_dir}/submission.json"
    if os.path.exists(sub_path):
        sub = json.load(open(sub_path, encoding="utf-8"))
        outcome, detail = score_repair(cfg["case_id"], info, sub["edits"], name)
        root = score_root_cause(info, (sub.get("report") or {}).get("root_cause"))
    else:
        outcome, detail, root = "no_submission", {"run_outcome": result.get("outcome")}, None
    ev_path = f"{run_dir}/evidence_check.json"
    ev = {"protocol": "agent run, scored by tools/agent/score.py (same evaluator as the edit-format baseline)",
          "case_id": cfg["case_id"], "model": cfg["model"],
          "repair": {"outcome": outcome, **detail},
          "root_cause": root,
          "evidence": json.load(open(ev_path)) if os.path.exists(ev_path) else None,
          "cost": {k: result.get(k) for k in ("tool_calls", "model_calls", "total_tokens", "seconds", "active_seconds", "waited_seconds", "models_used")}}
    json.dump(ev, open(f"{run_dir}/evaluation.json", "w", encoding="utf-8"), indent=2)
    return ev


if __name__ == "__main__":
    e = score(sys.argv[1])
    print(e["repair"]["outcome"], "| root cause:", (e["root_cause"] or {}).get("status"), "| cost:", e["cost"])
