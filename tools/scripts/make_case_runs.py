"""Create protocol-v2 run folders for a case: prompt, inputs, run.json, protocol copy.

usage: make_case_runs.py <case_id>
Creates experiments/<case>-edit-<model>-<a|b> for qwen3-8b and gemini-3-5-flash.
Variant a = report + stack trace; variant b adds a source excerpt built from the stack trace.
"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = "D:/TraceRoot"
case = sys.argv[1]
cdir = f"{ROOT}/cases/{case}"
meta = json.load(open(f"{cdir}/metadata.json"))
report = open(f"{cdir}/report.md", encoding="utf-8").read().rstrip("\n")
trace = open(f"{cdir}/stacktrace.txt", encoding="utf-8").read().rstrip("\n")
up = f"{cdir}/upstream"

CONTRACT = """Return your fix as edits inside exactly one fenced code block whose info string
is `edit`. Each edit has this exact form:

```edit
FILE: src/example/module.py
<<<<<<< SEARCH
exact original lines, copied character for character including indentation
=======
the replacement lines
>>>>>>> REPLACE
```

The SEARCH text must match the original code exactly and occur exactly once in
that file. You may put several edits inside the one block. Edits may modify only
files under `src/`. Do not modify, add, or delete tests, dependency files,
configuration, or generated files. Do not include prose outside the code block."""


def intro(with_source):
    extra = ", and source excerpt" if with_source else ""
    return (f"You are repairing a Python regression. You have only the bug report, stack\n"
            f"trace{extra} below. Do not assume access to the rest of the repository, tests, "
            f"Git history, or any\nother tools.")


def excerpt():
    frames = []
    for m in re.finditer(r'File "(src/[^"]+)", line (\d+)', trace):
        key = (m.group(1), int(m.group(2)))
        if key not in frames:
            frames.append(key)
    parts, seen = [], set()
    for path, line in frames:
        src = subprocess.run(["git", "show", f"{meta['faulty_revision']}:{path}"], cwd=up,
                             capture_output=True, text=True).stdout
        lines = src.split("\n")
        best = None
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= node.end_lineno:
                if best is None or node.lineno > best.lineno:
                    best = node
        if best is None:
            continue
        start, end = best.lineno, best.end_lineno
        if end - start + 1 > 120:
            start, end = max(best.lineno, line - 60), min(best.end_lineno, line + 60)
        if (path, start, end) in seen:
            continue
        seen.add((path, start, end))
        parts.append(f"# {path} (lines {start}-{end})\n" + "\n".join(lines[start - 1:end]))
    return "\n\n".join(parts)


def prompt(with_source, exc):
    p = (intro(with_source) + "\n\n" + CONTRACT + "\n\n## Bug report\n\n" + report +
         "\n\n## Stack trace\n\n```text\n" + trace + "\n```\n")
    if with_source:
        p += ("\n## Source excerpt\n\nUnmodified code of the functions named in the stack trace:\n\n"
              "```python\n" + exc + "\n```\n")
    return p


QWEN = {"provider": "local", "runtime": "llama.cpp", "runtime_build": "b11840-36e36e63a",
        "model_file": r"D:\New folder\Qwen3-8B-Q4_K_M.gguf", "gpu_layers": 99, "context_length": 8192,
        "thinking_enabled": False, "temperature": 0, "top_p": 1, "top_k": 1, "max_generated_tokens": 1024}
GEM = {"provider": "Google Gemini API", "model": "gemini-3.5-flash", "temperature": 0, "top_p": 1,
       "top_k": 1, "max_output_tokens": 16384, "thinking": "model default"}

exc = excerpt()
variants = [("a", False)]
if exc:
    variants.append(("b", True))
else:
    print("no project frames in stack trace: no 'with source' variant for", case)
for tag, ws in variants:
    p = prompt(ws, exc)
    for model, inf in (("qwen3-8b", QWEN), ("gemini-3-5-flash", GEM)):
        d = f"{ROOT}/experiments/{case}-edit-{model}-{tag}"
        os.makedirs(d + "/input", exist_ok=True)
        open(d + "/prompt.md", "w", encoding="utf-8", newline="\n").write(p)
        open(d + "/input/report.md", "w", encoding="utf-8", newline="\n").write(report + "\n")
        open(d + "/input/stacktrace.txt", "w", encoding="utf-8", newline="\n").write(trace + "\n")
        if ws:
            open(d + "/input/source_excerpt.txt", "w", encoding="utf-8", newline="\n").write(exc + "\n")
        shutil.copy(f"{ROOT}/experiments/PROTOCOL_EDIT_FORMAT.md", d + "/protocol.md")
        files = ["prompt.md"] + ["input/" + f for f in sorted(os.listdir(d + "/input"))]
        json.dump({"case_id": case, "protocol": "edit-format", "status": "ready_to_invoke",
                   "run_date": "2026-10-24", "scope_prefix": "src/",
                   "input_variant": "with source excerpt" if ws else "report + stack trace only",
                   "input_sha256": {k: hashlib.sha256(open(f"{d}/{k}", "rb").read()).hexdigest().upper() for k in files},
                   "inference": inf, "runner": "tools/scripts/run_edit_experiment.py"},
                  open(d + "/run.json", "w"), indent=2)
        print(os.path.basename(d), "prompt chars", len(p))
