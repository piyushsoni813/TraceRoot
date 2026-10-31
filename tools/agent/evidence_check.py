"""Check that what the report claims is backed by the saved transcript. No model, no network.

usage: python -I evidence_check.py <run_dir>

Reads report.json, submission.json, workspace.patch and transcript.jsonl. Writes
evidence_check.json. Every item is verified, unverifiable (the transcript cannot back it) or
contradicted (the transcript says the opposite). A run passes only with no contradicted and no
unverifiable items. What is checked:
  hypothesis_call  each cited call exists, came before the update, is an evidence tool and did not return an error
  verification     the call is a run_tests/run_python after the last edit, matches the command, and the claimed
                   counts and pass/fail agree with the real output
  line_citation    "path.py:NN" / "path.py, line NN" was actually shown to the agent (read_file, search, blame, traceback)
  commit           every commit hash in the report appears in a git tool output or the bug report
  quote            inline `code` of 12+ chars appears in something the agent saw or wrote
  root_cause_file  the reported file was opened or searched
  patch            report edits equal the successful apply_edit calls and the saved diff
It cannot judge whether an argument is sound. That is for the human reviewer.
"""
import json, os, re, sys

EVIDENCE_TOOLS = {"read_file", "search", "git_log", "git_show", "git_blame", "run_python", "run_tests", "list_dir"}
COUNT_WORDS = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)")
HASH = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
LINE_CITES = [re.compile(r"([\w./\\-]+\.py):(\d+)"), re.compile(r"([\w./\\-]+\.py)[ ,(]+lines? (\d+)")]
SPAN = re.compile(r"`([^`\n]{12,})`")


def norm_path(p):
    p = p.replace("\\", "/")
    for pre in ("/work/", "./"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def load(run_dir):
    ev = [json.loads(l) for l in open(f"{run_dir}/transcript.jsonl", encoding="utf-8")]
    calls = {e["n"]: e for e in ev if e["event"] == "tool_call"}
    start = next(e for e in ev if e["event"] == "run_start")
    return calls, start


def seen_lines(calls):
    """(path, line) pairs that were shown to the agent, and the set of paths it opened."""
    seen, opened = set(), set()
    for e in calls.values():
        a, r = e.get("args") or {}, e.get("result") or ""
        if e["name"] == "read_file" and isinstance(a.get("path"), str) and not r.startswith("error"):
            p = norm_path(a["path"])
            opened.add(p)
            for m in re.finditer(r"^(\d+)\t", r, re.M):
                seen.add((p, int(m.group(1))))
        elif e["name"] == "search":
            for m in re.finditer(r"^(.+?):(\d+):", r, re.M):
                seen.add((norm_path(m.group(1)), int(m.group(2))))
                opened.add(norm_path(m.group(1)))
        elif e["name"] == "git_blame" and isinstance(a.get("path"), str) and not r.startswith("error"):
            p = norm_path(a["path"])
            opened.add(p)
            try:
                seen.update((p, n) for n in range(int(a["start"]), int(a["end"]) + 1))
            except (KeyError, TypeError, ValueError):
                pass
        elif e["name"] == "git_show":
            opened.update(norm_path(m) for m in re.findall(r"^diff --git a/(\S+)", r, re.M))
        for m in re.finditer(r'File "([^"]+)", line (\d+)', r):
            seen.add((norm_path(m.group(1)), int(m.group(2))))
            opened.add(norm_path(m.group(1)))
        for m in re.finditer(r"^(?:\./)?([\w./-]+\.py):(\d+):", r, re.M):  # pytest "file.py:123: Error"
            seen.add((norm_path(m.group(1)), int(m.group(2))))
    return seen, opened


def check(run_dir):
    run_dir = os.path.normpath(run_dir)
    report = json.load(open(f"{run_dir}/report.json", encoding="utf-8"))
    sub = json.load(open(f"{run_dir}/submission.json", encoding="utf-8"))
    calls, start = load(run_dir)
    items = []

    def add(kind, status, detail, ref=None):
        items.append({"kind": kind, "status": status, "detail": detail, "ref": ref})

    seen, opened = seen_lines(calls)
    results_text = ws(" ".join((e.get("result") or "") for e in calls.values()))
    own_text = ws(" ".join(a for e in calls.values() if e["name"] in ("apply_edit", "run_python")
                           for a in ((e.get("args") or {}).get("search", ""), (e.get("args") or {}).get("replace", ""), (e.get("args") or {}).get("code", ""))
                           if isinstance(a, str)))
    seen_text = results_text + " " + own_text + " " + ws(start.get("user_prompt", ""))
    ok_edit_calls = [n for n, e in sorted(calls.items()) if e["name"] == "apply_edit" and (e.get("result") or "").startswith("applied")]
    last_edit = max(ok_edit_calls, default=0)

    # hypothesis evidence
    for h in sub["hypotheses"]:
        upd = h.get("updated_at_call", 10**9)
        for n in h["calls"]:
            e = calls.get(n)
            ref = f"{h['id']} -> call {n}"
            if e is None:
                add("hypothesis_call", "contradicted", "cited call does not exist", ref)
            elif n >= upd:
                add("hypothesis_call", "contradicted", f"call {n} came at or after the update (call {upd})", ref)
            elif e["name"] not in EVIDENCE_TOOLS:
                add("hypothesis_call", "unverifiable", f"call {n} is {e['name']}, which produces no evidence", ref)
            elif (e.get("result") or "").startswith(("error", "invalid")):
                add("hypothesis_call", "unverifiable", f"call {n} returned an error", ref)
            else:
                add("hypothesis_call", "verified", f"call {n} is {e['name']} with output", ref)

    # verification steps
    for i, v in enumerate(report["verification"]):
        n, ref = v["call"], f"verification[{i}] -> call {n}"
        e = calls.get(n)
        if e is None or e["name"] not in ("run_tests", "run_python"):
            add("verification", "contradicted" if e is None else "unverifiable", "cited call is not a test or script run", ref)
            continue
        if n <= last_edit:
            add("verification", "unverifiable", f"call {n} ran before the last edit (call {last_edit})", ref)
            continue
        a, out = e.get("args") or {}, e.get("result") or ""
        cmd = ws(v["command"])
        if e["name"] == "run_tests":
            sel = a.get("selection") or []
            if not all(str(s) in cmd for s in sel):
                add("verification", "unverifiable", "command does not name the tests that were run", ref)
                continue
        elif ws(a.get("code", ""))[:30] not in cmd:
            add("verification", "unverifiable", "command does not match the script that was run", ref)
            continue
        m = re.match(r"\[exit (-?\d+)\]", out)
        code = int(m.group(1)) if m else None
        claim = v["result"].lower()
        if "pass" in claim and "fail" not in claim and code not in (0, None):
            add("verification", "contradicted", f"claims a pass but the run exited {code}", ref)
            continue
        actual = {(int(c), w.rstrip("s") if w.startswith("error") else w) for c, w in COUNT_WORDS.findall(out)}
        wrong = [f"{c} {w}" for c, w in COUNT_WORDS.findall(claim)
                 if (int(c), w.rstrip("s") if w.startswith("error") else w) not in actual]
        if wrong:
            add("verification", "contradicted", f"claimed {', '.join(wrong)} but the output shows {sorted(actual) or 'no counts'}", ref)
        else:
            add("verification", "verified", f"call {n} ran after the last edit and the claim agrees with the output", ref)

    # free text: root cause mechanism, hypothesis text and evidence, verification results, limitations
    rc = report["root_cause"]
    texts = [("root_cause.mechanism", rc.get("mechanism", ""))] + [(f"{h['id']}.evidence", h["evidence"]) for h in report["hypotheses"]] \
        + [(f"{h['id']}.text", h["text"]) for h in report["hypotheses"]]
    for where, text in texts:
        for rx in LINE_CITES:
            for path, line in rx.findall(text):
                p = norm_path(path)
                hit = (p, int(line)) in seen
                add("line_citation", "verified" if hit else "unverifiable",
                    f"{p}:{line} " + ("was shown to the agent" if hit else "was never shown to the agent"), where)
        for span in SPAN.findall(text):
            hit = ws(span) in seen_text
            add("quote", "verified" if hit else "unverifiable", f"`{span[:60]}` " + ("appears in the transcript" if hit else "appears nowhere in the transcript"), where)
    git_text = " ".join((e.get("result") or "") for e in calls.values() if e["name"] in ("git_log", "git_show", "git_blame")).lower() \
        + " " + start.get("user_prompt", "").lower()
    commit_texts = texts + [("root_cause.breaking_commit", rc.get("breaking_commit", ""))]
    for where, text in commit_texts:
        for h in sorted(set(HASH.findall(text.lower()))):
            hit = h in git_text
            add("commit", "verified" if hit else "unverifiable", f"{h} " + ("appears in a git output" if hit else "appears in no git output"), where)
    if (rc.get("file") or "").strip():
        p = norm_path(rc["file"])
        add("root_cause_file", "verified" if p in opened else "unverifiable",
            f"{p} " + ("was opened or searched" if p in opened else "was never opened or found by a search"), "root_cause.file")

    # patch consistency: report edits == successful apply_edit calls == submission, diff == saved workspace diff
    applied = [{k: calls[n]["args"][k] for k in ("path", "search", "replace")} for n in ok_edit_calls]
    add("patch", "verified" if report["patch"]["edits"] == applied == sub["edits"] else "contradicted",
        "report edits equal the successful apply_edit calls" if report["patch"]["edits"] == applied == sub["edits"]
        else "report edits differ from the apply_edit calls in the transcript", "patch.edits")
    saved = open(f"{run_dir}/workspace.patch", encoding="utf-8").read()
    add("patch", "verified" if report["patch"]["diff"] == saved else "contradicted",
        "report diff equals the saved workspace diff" if report["patch"]["diff"] == saved else "report diff differs from workspace.patch", "patch.diff")

    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("verified", "unverifiable", "contradicted")}
    out = {"passed": counts["unverifiable"] == 0 and counts["contradicted"] == 0 and len(items) > 0, "counts": counts,
           "total": len(items), "verified_fraction": round(counts["verified"] / len(items), 3) if items else 0.0, "items": items}
    json.dump(out, open(f"{run_dir}/evidence_check.json", "w", encoding="utf-8"), indent=2)
    return out


if __name__ == "__main__":
    r = check(sys.argv[1])
    print("PASSED" if r["passed"] else "NOT PASSED", r["counts"])
    for i in r["items"]:
        if i["status"] != "verified":
            print(f"  {i['status']}: [{i['kind']}] {i['detail']} ({i['ref']})")
    sys.exit(0 if r["passed"] else 1)
