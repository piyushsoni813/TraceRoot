"""Run one protocol-v2 experiment: invoke model, apply edits mechanically, evaluate.

usage: run_edit_experiment.py <run_dir> <local|gemini> [model]
Gemini key is read from GEMINI_API_KEY. Local uses llama-server on 127.0.0.1:8091.
"""
import json, os, re, shutil, stat, subprocess, sys, urllib.request

ROOT = "D:/TraceRoot"
PY = ROOT + "/.venv/Scripts/python.exe"
run, provider = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else ""
os.chdir(run)
os.makedirs("output", exist_ok=True)
_run_cfg = json.load(open("run.json"))
CASE = _run_cfg["case_id"]
SCOPE = _run_cfg.get("scope_prefix", "src/flask/")
_case_dir = f"{ROOT}/cases/{CASE}"
_meta = json.load(open(f"{_case_dir}/metadata.json"))
FAULTY = _meta["faulty_revision"]
TESTS = _meta.get("targeted_tests", ["tests/test_helpers.py", "tests/test_instance_config.py"])
UPSTREAM = f"{_case_dir}/upstream" if os.path.isdir(f"{_case_dir}/upstream") else f"{_case_dir}/reference-fixed"
_env_path = f"{_case_dir}/reference/env.json"
ENVCFG = json.load(open(_env_path)) if os.path.exists(_env_path) else {}
prompt = open("prompt.md", encoding="utf-8").read()

def invoke():
    if provider == "gemini":
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "topP": 1, "topK": 1, "maxOutputTokens": _run_cfg.get("inference", {}).get("max_output_tokens", 16384)}}
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            json.dumps(body).encode(),
            {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        raw = urllib.request.urlopen(req, timeout=600).read()
        d = json.loads(raw)
        text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
    else:
        body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0, "top_p": 1,
                "top_k": 1, "min_p": 0, "max_tokens": 1024, "stream": False}
        req = urllib.request.Request("http://127.0.0.1:8091/v1/chat/completions",
                                     json.dumps(body).encode(), {"Content-Type": "application/json"})
        raw = urllib.request.urlopen(req, timeout=600).read()
        text = json.loads(raw)["choices"][0]["message"]["content"]
    open("output/response.json", "wb").write(raw)
    open("output/raw.md", "w", encoding="utf-8", newline="").write(text)

if os.path.exists("output/raw.md"):
    print("raw.md already exists; not invoking again")
else:
    invoke()
text = open("output/raw.md", encoding="utf-8", newline="").read()

def finish(outcome, **extra):
    ev = {"outcome": outcome, "protocol": "edit-format (experiments/PROTOCOL_EDIT_FORMAT.md)", **extra}
    open("evaluation.json", "w").write(json.dumps(ev, indent=2))
    print(outcome, json.dumps(extra)[:400])
    sys.exit(0)

# 1. output contract
blocks = re.findall(r"```edit\n(.*?)\n```", text, re.S)
outside = re.sub(r"```edit\n.*?\n```", "", text, flags=re.S).strip()
if not blocks:
    finish("no_patch" if "```" not in text else "invalid_output_contract", detail="no edit block")
if len(blocks) > 1 or outside:
    finish("invalid_output_contract", detail="multiple blocks or prose outside the block")
edits = re.findall(r"FILE: *(\S+)\n<<<<<<< SEARCH\n(.*?)\n?=======\n(.*?)\n?>>>>>>> REPLACE", blocks[0], re.S)
if not edits:
    finish("invalid_output_contract", detail="no parsable edits")

# 2. scope
for f, _, _ in edits:
    if not f.startswith(SCOPE) or ".." in f:
        finish("disallowed_patch_scope", path=f)

# 3. clean checkout + mechanical apply
name = os.path.basename(os.getcwd())
co = os.path.join(ROOT, ".tmp", "co-" + name)


def _rm(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


if os.path.exists(co):
    shutil.rmtree(co, onerror=_rm)
subprocess.run(["git", "clone", "-q", "--no-checkout", UPSTREAM, co], check=True)
subprocess.run(["git", "checkout", "-q", FAULTY], cwd=co, check=True)
for rel, shim_text in ENVCFG.get("shim_files", {}).items():
    open(os.path.join(co, rel), "w").write(shim_text)
for f, search, repl in edits:
    path = os.path.join(co, f)
    if not os.path.isfile(path):
        finish("patch_does_not_apply", detail=f"file not found: {f}")
    src = open(path, encoding="utf-8", newline="").read()
    n = src.count(search)
    if n != 1:
        finish("patch_does_not_apply", detail=f"SEARCH text matched {n} times (needs exactly 1)", file=f, search_preview=search[:200])
    open(path, "w", encoding="utf-8", newline="").write(src.replace(search, repl))
diff =subprocess.run(["git", "diff"], cwd=co, capture_output=True, text=True).stdout
open("output/applied.patch", "w", encoding="utf-8", newline="").write(diff)

# 4. evaluate
env = dict(os.environ, PYTHONPATH=os.path.join(co, "src"), TMP=ROOT + "/.tmp", TEMP=ROOT + "/.tmp", PYTHONDONTWRITEBYTECODE="1")
r = subprocess.run([PY, f"{_case_dir}/reference/reproduce.py"], env=env, capture_output=True, text=True)
if r.returncode != 0:
    finish("evaluator_still_fails", reproduce_exit_code=r.returncode, stderr_tail=r.stderr.strip().splitlines()[-1:], applied_diff="output/applied.patch")
# evaluator-held tests: the upstream versions of the targeted test files at the fixed revision
if _meta.get("fixed_revision"):
    for tf in TESTS:
        shown = subprocess.run(["git", "show", f"{_meta['fixed_revision']}:{tf}"], cwd=UPSTREAM, capture_output=True)
        if shown.returncode == 0:
            open(os.path.join(co, tf), "wb").write(shown.stdout)
t = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", ROOT + "/.tmp/pt-" + name,
                    *ENVCFG.get("pytest_args", []), *TESTS], cwd=co, env=env, capture_output=True, text=True)
tail = t.stdout.strip().splitlines()[-1:]
if t.returncode != 0:
    finish("upstream_regression_check_fails", reproduce_exit_code=0, pytest_tail=tail)
finish("success", reproduce_exit_code=0, pytest_tail=tail, applied_diff="output/applied.patch")
