"""Self-test of score.py: the real fix must score success, bad submissions must fail the right way.
usage: python -I selftest_score.py [case_id ...]   (no API calls)"""
import json, os, shutil, stat, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score
from score import ROOT

cases = sys.argv[1:] or ["flask-5160", "attrs-1416", "packaging-638", "filelock-346", "click-3449"]
RUNS = f"{ROOT}/.tmp/score-selftest"
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {str(detail)[:300]!r}"))
    if not cond:
        fails.append(name)


def rm(p):
    if os.path.exists(p):
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def git_show(info, rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=info["upstream"], capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def fix_as_edits(info):
    """Whole-file search/replace for every src file the real fix touches."""
    names = subprocess.run(["git", "diff", "--name-only", info["faulty"], info["fixed"], "--", "src"],
                           cwd=info["upstream"], capture_output=True, text=True).stdout.split()
    return [{"path": n, "search": git_show(info, info["faulty"], n), "replace": git_show(info, info["fixed"], n)} for n in names]


def make_run(case, name, edits, root_cause=None, with_submission=True):
    d = f"{RUNS}/{name}"
    rm(d)
    os.makedirs(d)
    json.dump({"case_id": case, "model": "selftest"}, open(f"{d}/run.json", "w"))
    json.dump({"outcome": "submitted" if with_submission else "budget_exhausted", "tool_calls": 7, "model_calls": 7,
               "total_tokens": 1234, "seconds": 9.5}, open(f"{d}/result.json", "w"))
    if with_submission:
        json.dump({"edits": edits, "report": {"root_cause": root_cause or {}}, "hypotheses": []}, open(f"{d}/submission.json", "w"))
    return d


os.makedirs(RUNS, exist_ok=True)
for case in cases:
    print(f"== {case}")
    info = score.case_info(case)
    edits = fix_as_edits(info)
    check("fix touches src files", len(edits) >= 1 and all(e["search"] and e["replace"] for e in edits))
    fn = "unknown_function"
    ev = score.score(make_run(case, f"{case}-good", edits, {"file": edits[0]["path"], "function": fn, "breaking_commit": info["breaking"][:10]}))
    check("real fix scores success", ev["repair"]["outcome"] == "success", ev["repair"])
    check("root cause matched by commit", ev["root_cause"]["status"] == "match" and ev["root_cause"]["commit_match"], ev["root_cause"])
    check("cost is carried over", ev["cost"] == {"tool_calls": 7, "model_calls": 7, "total_tokens": 1234, "seconds": 9.5}, ev["cost"])
    check("evidence is null without an evidence check", ev["evidence"] is None)
    d_ev = make_run(case, f"{case}-ev", edits)
    json.dump({"passed": True, "counts": {"verified": 3, "unverifiable": 0, "contradicted": 0}}, open(f"{d_ev}/evidence_check.json", "w"))
    check("evidence check result is carried into the evaluation", score.score(d_ev)["evidence"]["counts"]["verified"] == 3)

    # wrong commit, right file, function that is in the diff -> likely (needs a person)
    diff_fn = None
    d = subprocess.run(["git", "diff", "-U3", info["faulty"], info["fixed"], "--", "src"], cwd=info["upstream"], capture_output=True, text=True, errors="replace").stdout
    import re
    m = re.search(r"^@@[^@]*@@\s+(?:async\s+)?(?:def|class)\s+(\w+)", d, re.M) or re.search(r"^[+-]\s*(?:async\s+)?def\s+(\w+)", d, re.M)
    if m:
        diff_fn = m.group(1)
        rc = score.score_root_cause(info, {"file": edits[0]["path"], "function": diff_fn, "breaking_commit": "deadbeefdeadbeef"})
        check("file and function without commit is likely", rc["status"] == "likely" and rc["needs_human_review"], rc)
    rc = score.score_root_cause(info, {"file": edits[0]["path"], "function": "zzz_nope", "breaking_commit": ""})
    check("file only is partial", rc["status"] == "partial" and rc["needs_human_review"], rc)
    rc = score.score_root_cause(info, {"file": "src/other/thing.py", "function": "zzz_nope", "breaking_commit": "abc"})
    check("nothing matching is a miss", rc["status"] == "miss" and not rc["needs_human_review"], rc)
    rc = score.score_root_cause(info, {"file": "x", "function": "y", "breaking_commit": info["breaking"][:5]})
    check("short commit prefix does not count", not rc["commit_match"], rc)

    # failing submissions
    noop = [{"path": edits[0]["path"], "search": edits[0]["search"], "replace": edits[0]["search"]}]
    ev = score.score(make_run(case, f"{case}-noop", noop))
    check("a no-op change leaves the evaluator failing", ev["repair"]["outcome"] == "evaluator_still_fails", ev["repair"])
    ev = score.score(make_run(case, f"{case}-scope", [{"path": "tests/x.py", "search": "a", "replace": "b"}]))
    check("edit outside src is refused", ev["repair"]["outcome"] == "disallowed_patch_scope", ev["repair"])
    ev = score.score(make_run(case, f"{case}-trav", [{"path": "src/../setup.py", "search": "a", "replace": "b"}]))
    check("path traversal is refused", ev["repair"]["outcome"] == "disallowed_patch_scope", ev["repair"])
    ev = score.score(make_run(case, f"{case}-nomatch", [{"path": edits[0]["path"], "search": "zzz_not_there", "replace": "b"}]))
    check("search that does not match fails to apply", ev["repair"]["outcome"] == "patch_does_not_apply", ev["repair"])
    ev = score.score(make_run(case, f"{case}-nofile", [{"path": "src/nope.py", "search": "a", "replace": "b"}]))
    check("missing file fails to apply", ev["repair"]["outcome"] == "patch_does_not_apply", ev["repair"])
    ev = score.score(make_run(case, f"{case}-nosub", [], with_submission=False))
    check("no submission is recorded as such", ev["repair"]["outcome"] == "no_submission" and ev["root_cause"] is None, ev["repair"])

# a fix that satisfies the reproducer but breaks something else must fail the held-out tests
case = "click-3449" if "click-3449" in cases else cases[0]
if case == "click-3449":
    info = score.case_info(case)
    edits = fix_as_edits(info)
    breaker = [dict(e) for e in edits]
    breaker[0]["replace"] = breaker[0]["replace"] + "\nraise RuntimeError('breaks every import')\n"
    ev = score.score(make_run(case, "click-breaker", breaker))
    check("a fix that breaks other behaviour is rejected", ev["repair"]["outcome"] in ("upstream_regression_check_fails", "evaluator_still_fails"), ev["repair"])

rm(RUNS)
for d in os.listdir(f"{ROOT}/.tmp"):
    if d.startswith(("score-", "pt-score-")):
        rm(f"{ROOT}/.tmp/{d}")
print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
