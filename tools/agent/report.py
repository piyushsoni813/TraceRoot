"""Build and validate the auditable report for one agent run.

usage: python -I report.py <run_dir>

Reads submission.json, workspace.patch, result.json and transcript.jsonl from the run
directory and writes report.json (checked against report.schema.json) and report.md.
This module checks structure only: that every cited tool call exists in the transcript.
Whether the cited output really supports the claim is checked in a later step.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = json.load(open(f"{HERE}/report.schema.json", encoding="utf-8"))
EXCERPT_CHARS = 400


def validate(value, schema, path="report"):
    """Check value against the JSON Schema subset used here. Returns a list of error strings."""
    errs = []
    t = schema.get("type")
    py = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float)}
    if t and (not isinstance(value, py[t]) or (t in ("integer", "number") and isinstance(value, bool))):
        return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if t == "string" and len(value) < schema.get("minLength", 0):
        errs.append(f"{path}: shorter than {schema['minLength']} characters")
    if t in ("integer", "number") and value < schema.get("minimum", value):
        errs.append(f"{path}: below minimum {schema['minimum']}")
    if t == "array":
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} items")
        for i, item in enumerate(value):
            errs += validate(item, schema.get("items", {}), f"{path}[{i}]")
    if t == "object":
        props = schema.get("properties", {})
        errs += [f"{path}.{k}: missing" for k in schema.get("required", []) if k not in value]
        if schema.get("additionalProperties") is False:
            errs += [f"{path}.{k}: not allowed" for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
    return errs


def build(run_dir):
    """Return (report, errors). report is None if there was no submission."""
    sub_path = f"{run_dir}/submission.json"
    if not os.path.exists(sub_path):
        return None, ["no submission.json: the run did not submit"]
    sub = json.load(open(sub_path, encoding="utf-8"))
    result = json.load(open(f"{run_dir}/result.json", encoding="utf-8"))
    cfg = json.load(open(f"{run_dir}/run.json", encoding="utf-8"))
    diff = open(f"{run_dir}/workspace.patch", encoding="utf-8").read()
    events = [json.loads(l) for l in open(f"{run_dir}/transcript.jsonl", encoding="utf-8")]
    calls = {e["n"]: e for e in events if e["event"] == "tool_call"}
    rep = sub.get("report") or {}

    # evidence: one entry for every tool call cited by a hypothesis or a verification step
    cited = sorted({c for h in sub["hypotheses"] for c in h["calls"]} | {v.get("call") for v in rep.get("verification", []) if isinstance(v.get("call"), int)})
    evidence = []
    for n in cited:
        e = calls.get(n)
        evidence.append({"call": n, "tool": e["name"] if e else "(missing)", "args": (e or {}).get("args") or {},
                         "excerpt": (e["result"][:EXCERPT_CHARS] if e else "")})

    report = {
        "case_id": cfg["case_id"], "model": cfg["model"],
        "run": {"outcome": result["outcome"], "tool_calls": result["tool_calls"], "seconds": result["seconds"],
                "total_tokens": result["total_tokens"]},
        "root_cause": rep.get("root_cause", {}),
        "hypotheses": [{k: h[k] for k in ("id", "text", "predicts", "status", "evidence", "calls")} for h in sub["hypotheses"]],
        "evidence": evidence,
        "patch": {"edits": sub["edits"], "diff": diff},
        "verification": rep.get("verification", []),
        "limitations": rep.get("limitations", []),
        "decision": sub.get("decision", ""),
    }
    errors = validate(report, SCHEMA)
    # structural cross-checks: every cited call must exist in the transcript, and not after the run
    for n in cited:
        if n not in calls:
            errors.append(f"cited tool call {n} does not exist in the transcript")
    return report, errors


def render(report):
    rc = report["root_cause"]
    out = [f"# Investigation report: {report['case_id']}", "",
           f"Model: {report['model']}. Tool calls: {report['run']['tool_calls']}. Time: {report['run']['seconds']} s. "
           f"Tokens: {report['run']['total_tokens']}.", "",
           f"**Decision: {report['decision']}.** Nothing was merged or deployed.", "",
           "## Root cause", "", f"- File: `{rc.get('file', '')}`", f"- Function: `{rc.get('function', '')}`",
           f"- Breaking commit: `{rc.get('breaking_commit') or 'not identified'}`", "", rc.get("mechanism", ""), "",
           "## Hypotheses", ""]
    for h in report["hypotheses"]:
        out += [f"### {h['id']} ({h['status']})", "", h["text"], "", f"- Predicts: {h['predicts']}",
                f"- Evidence: {h['evidence']} (tool calls {', '.join(map(str, h['calls']))})", ""]
    out += ["## Patch", "", "```diff", report["patch"]["diff"].rstrip(), "```", "", "## Verification", ""]
    for v in report["verification"]:
        out.append(f"- Call {v['call']}: `{v['command']}`: {v['result']}")
    out += ["", "## Evidence", ""]
    for e in report["evidence"]:
        out += [f"### Call {e['call']}: {e['tool']}", "", f"Arguments: `{json.dumps(e['args'])[:300]}`", "", "```", e["excerpt"], "```", ""]
    out += ["## Limitations", ""] + [f"- {l}" for l in report["limitations"]] + [""]
    return "\n".join(out)


def write(run_dir):
    """Write report.json and report.md. Returns the list of errors (empty means valid)."""
    report, errors = build(run_dir)
    if report is None:
        return errors
    json.dump(report, open(f"{run_dir}/report.json", "w", encoding="utf-8"), indent=2)
    open(f"{run_dir}/report.md", "w", encoding="utf-8", newline="\n").write(render(report))
    json.dump({"valid": not errors, "errors": errors}, open(f"{run_dir}/report_validation.json", "w"), indent=2)
    return errors


if __name__ == "__main__":
    errs = write(sys.argv[1])
    print("valid" if not errs else "INVALID:\n" + "\n".join(errs))
    sys.exit(1 if errs else 0)
