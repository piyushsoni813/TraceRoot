"""Where do the 40 tool calls go? Reads every agent run's transcript and prints one row per run.

usage: python -I analyze_budget.py [--md]   (--md prints Markdown tables)

Columns: outcome, calls, how many went to each kind of tool, wasted calls (repeats of an identical
read-only call, calls that returned an error, rejected submits), the call number of the first
hypothesis, the first successful edit and the first test run after it, and why submits were refused.
"""
import collections, glob, json, os, re, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIND = {"list_dir": "read", "read_file": "read", "search": "read",
        "git_log": "git", "git_show": "git", "git_blame": "git",
        "run_python": "exec", "run_tests": "exec",
        "record_hypothesis": "hyp", "update_hypothesis": "hyp",
        "apply_edit": "edit", "submit": "submit"}


def analyse(d):
    ev = [json.loads(l) for l in open(f"{d}/transcript.jsonl", encoding="utf-8")]
    calls = [e for e in ev if e["event"] == "tool_call"]
    res = json.load(open(f"{d}/result.json"))
    kinds = collections.Counter(KIND.get(c["name"], "other") for c in calls)
    repeats = sum(1 for c in calls if c["result"].startswith("[note: identical"))
    errors = sum(1 for c in calls if c["result"].startswith(("error", "invalid")))
    rejected = [c for c in calls if c["name"] == "submit" and c["result"].startswith("rejected")]
    reasons = collections.Counter()
    for c in rejected:
        for line in c["result"].splitlines()[1:]:
            reasons[re.sub(r"[\d,; ]*H\d+.*|\(.*\)|: .*", "", line).strip()[:60]] += 1
    first = lambda pred: next((c["n"] for c in calls if pred(c)), None)
    first_hyp = first(lambda c: c["name"] == "record_hypothesis")
    first_edit = first(lambda c: c["name"] == "apply_edit" and c["result"].startswith("applied"))
    test_after = next((c["n"] for c in calls if c["name"] == "run_tests" and first_edit and c["n"] > first_edit), None)
    read_chars = sum(len(c["result"]) for c in calls if c["name"] in ("read_file", "git_show", "search", "list_dir"))
    big_reads = sum(1 for c in calls if c["name"] == "read_file" and len(c["result"]) > 8000)
    return {"run": os.path.basename(d), "outcome": res["outcome"], "calls": len(calls), **{k: kinds.get(k, 0) for k in ("read", "git", "exec", "hyp", "edit", "submit")},
            "repeats": repeats, "errors": errors, "rejected_submits": len(rejected), "reject_reasons": dict(reasons),
            "first_hyp": first_hyp, "first_edit": first_edit, "test_after_edit": test_after,
            "read_kchars": round(read_chars / 1000), "big_reads": big_reads,
            "edits_ok": sum(1 for c in calls if c["name"] == "apply_edit" and c["result"].startswith("applied"))}


rows = [analyse(d) for d in sorted(glob.glob(f"{ROOT}/experiments/*-agent-*"))
        if os.path.exists(f"{d}/result.json") and os.path.exists(f"{d}/transcript.jsonl")]
groups = {"budget_exhausted": [r for r in rows if r["outcome"] == "budget_exhausted"],
          "submitted": [r for r in rows if r["outcome"] == "submitted"]}
cols = ["calls", "read", "git", "exec", "hyp", "edit", "submit", "repeats", "errors", "rejected_submits", "read_kchars", "big_reads"]
md = "--md" in sys.argv
for name, rs in groups.items():
    print(f"\n## {name}: {len(rs)} runs\n")
    hdr = ["run"] + cols + ["first_hyp", "first_edit", "test_after_edit"]
    print("| " + " | ".join(hdr) + " |" if md else "  ".join(h[:8].rjust(8) for h in hdr))
    if md:
        print("|" + " --- |" * len(hdr))
    for r in rs:
        vals = [r["run"].replace("-agent-", " ").replace("gemini-", "")[:48]] + [str(r[c]) for c in cols] + [str(r[k]) for k in ("first_hyp", "first_edit", "test_after_edit")]
        print("| " + " | ".join(vals) + " |" if md else vals[0].ljust(48) + "  ".join(v.rjust(8) for v in vals[1:]))
    if rs:
        print("\nmedians: " + ", ".join(f"{c}={statistics.median(r[c] for r in rs)}" for c in cols))
        for k in ("first_hyp", "first_edit"):
            vals = [r[k] for r in rs if r[k]]
            print(f"{k}: median {statistics.median(vals) if vals else '-'}, missing in {sum(1 for r in rs if not r[k])} runs")
        reasons = collections.Counter()
        for r in rs:
            reasons.update(r["reject_reasons"])
        print("submit refusals:", dict(reasons) or "none")
