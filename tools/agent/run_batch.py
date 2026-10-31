"""Run the agent on several cases with one model, then score each run.

usage: python -I run_batch.py <model> [variant] [case ...] [--key-env=NAME] [--protocol=v1|v2]

Run directories are experiments/<case>-agent-<model with dots as dashes>-<variant>. A directory that
already exists is skipped, never overwritten. Each run and each scoring step is a separate process.
Stops early if the model's daily quota is used up, so later cases are not burned on errors.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = f"{ROOT}/.venv/Scripts/python.exe" if os.path.exists(f"{ROOT}/.venv/Scripts/python.exe") else sys.executable
CASES = ["filelock-346", "packaging-638", "attrs-1416", "click-3449", "flask-5160"]

args = [a for a in sys.argv[1:] if not a.startswith("--")]
passthrough = [a for a in sys.argv[1:] if a.startswith(("--key-env=", "--protocol="))]
model = args[0]
variant = args[1] if len(args) > 1 else "a"
cases = args[2:] or CASES
slug = model.replace(".", "-").replace(",", "+")
for case in cases:
    run_dir = f"{ROOT}/experiments/{case}-agent-{slug}-{variant}"
    if os.path.exists(run_dir):
        print(f"skip {case}: {run_dir} exists", flush=True)
        continue
    subprocess.run([PY, "-I", f"{ROOT}/tools/agent/agent.py", case, run_dir, model, *passthrough], capture_output=True)
    subprocess.run([PY, "-I", f"{ROOT}/tools/agent/score.py", run_dir], capture_output=True)
    res = json.load(open(f"{run_dir}/result.json")) if os.path.exists(f"{run_dir}/result.json") else {}
    ev = json.load(open(f"{run_dir}/evaluation.json")) if os.path.exists(f"{run_dir}/evaluation.json") else {}
    rc = (ev.get("root_cause") or {}).get("status")
    evid = (ev.get("evidence") or {}).get("counts")
    print(f"{case}: run={res.get('outcome')} repair={(ev.get('repair') or {}).get('outcome')} root_cause={rc} evidence={evid} "
          f"calls={res.get('tool_calls')} requests={res.get('model_calls')} active_s={res.get('active_seconds')}", flush=True)
    if res.get("outcome") == "api_error":
        last = [json.loads(l) for l in open(f"{run_dir}/transcript.jsonl", encoding="utf-8")]
        if any(e["event"] == "api_error" and "daily quota" in e.get("detail", "") for e in last):
            print("daily quota used up; stopping this batch", flush=True)
            break
