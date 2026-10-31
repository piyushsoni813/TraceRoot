"""Agent tools. Each returns a string and never raises; errors come back as text."""
import hashlib, json, os, re

MAX_OUT = 20 * 1024
SCOPE = "src/"
REV = re.compile(r"^(?:[0-9a-fA-F]{4,40}|HEAD(?:~\d{1,4})?)$")
TEST_SEL = re.compile(r"^[\w./\-\[\]:=,\"' ()]+$")

READ_SNIPPET = (
    "import sys\n"
    "s, e, p = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]\n"
    "for i, l in enumerate(open(p, errors='replace'), 1):\n"
    "    if i > e: break\n"
    "    if i >= s: print(f'{i}\\t{l}', end='')\n"
)


def _clip(text):
    if len(text) <= MAX_OUT:
        return text
    return text[:MAX_OUT] + f"\n[output truncated: {len(text)} chars, showing first {MAX_OUT}]"


def _bad_path(p):
    if (not isinstance(p, str) or not p or p.startswith(("/", "-", "~", "\\")) or "\x00" in p
            or ".." in p.replace("\\", "/").split("/")):
        return "invalid path: must be relative to the repo root, without '..'"
    return None


def _int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


SPECS = [
    {"name": "list_dir", "description": "List files and directories at a path in the repo.",
     "parameters": _obj({"path": {"type": "string", "description": "Relative path, default '.'"}})},
    {"name": "read_file", "description": "Read a file with line numbers. Use start/end (1-based, inclusive); default is 400 lines from start.",
     "parameters": _obj({"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"])},
    {"name": "search", "description": "Regex search (grep -E) over files under a path. Returns file:line:text.",
     "parameters": _obj({"regex": {"type": "string"}, "path": {"type": "string", "description": "Default '.'"}}, ["regex"])},
    {"name": "git_log", "description": "Recent commits (hash, date, author, subject), optionally limited to a path.",
     "parameters": _obj({"path": {"type": "string"}, "n": {"type": "integer", "description": "1-50, default 10"}})},
    {"name": "git_show", "description": "Show one commit (message and diff). Optionally limit to a path.",
     "parameters": _obj({"rev": {"type": "string", "description": "Commit hash or HEAD~N"}, "path": {"type": "string"}}, ["rev"])},
    {"name": "git_blame", "description": "Blame a line range of a file.",
     "parameters": _obj({"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path", "start", "end"])},
    {"name": "run_python", "description": "Run a short Python script in the repo (no network, 60 s). Use for diagnostics.",
     "parameters": _obj({"code": {"type": "string"}}, ["code"])},
    {"name": "run_tests", "description": "Run pytest on the given paths or node ids (120 s).",
     "parameters": _obj({"selection": {"type": "array", "items": {"type": "string"}}}, ["selection"])},
    {"name": "record_hypothesis",
     "description": "Record one candidate explanation of the bug and what you would observe if it were true. Record at least two competing ones before submitting.",
     "parameters": _obj({"text": {"type": "string"}, "predicts": {"type": "string", "description": "An observation that would confirm or rule it out"}}, ["text", "predicts"])},
    {"name": "update_hypothesis",
     "description": "Resolve a hypothesis after a check. status: supported, rejected or open. calls: numbers of the earlier tool calls that gave the evidence.",
     "parameters": _obj({"id": {"type": "string", "description": "e.g. H1"}, "status": {"type": "string", "enum": ["supported", "rejected", "open"]},
                         "evidence": {"type": "string"}, "calls": {"type": "array", "items": {"type": "integer"}}}, ["id", "status", "evidence", "calls"])},
    {"name": "apply_edit",
     "description": "Edit a file in the working copy so you can test your fix. path must be under src/. search must match exactly once in the file's current text. Edits are recorded and become your patch. Tests are not editable.",
     "parameters": _obj({"path": {"type": "string"}, "search": {"type": "string"}, "replace": {"type": "string"}}, ["path", "search", "replace"])},
    {"name": "submit",
     "description": "End the run and hand the recorded edits plus your report to a human reviewer. Needs: at least two hypotheses all resolved with one supported, at least one apply_edit, and a run_tests call after the last edit. Report your findings in the fields below.",
     "parameters": _obj({"report": _obj({
         "root_cause": _obj({"file": {"type": "string"}, "function": {"type": "string"},
                             "mechanism": {"type": "string", "description": "Why the code fails, in a few sentences"},
                             "breaking_commit": {"type": "string", "description": "Commit hash if you identified it, else empty"}},
                            ["file", "function", "mechanism"]),
         "verification": {"type": "array", "items": _obj({"command": {"type": "string"}, "result": {"type": "string"},
                                                           "call": {"type": "integer", "description": "tool call number of the run"}},
                                                          ["command", "result", "call"])},
         "limitations": {"type": "array", "items": {"type": "string"}}},
         ["root_cause", "verification", "limitations"])}, ["report"])},
]
TOOLS_HASH = hashlib.sha256(json.dumps(SPECS, sort_keys=True).encode()).hexdigest()
_NAMES = {s["name"] for s in SPECS}


class Toolset:
    def __init__(self, sandbox):
        self.sb = sandbox
        self.submission = None
        self.n_calls = 0          # 1-based number of the tool call being served; evidence cites these
        self.hypotheses = {}
        self.edits = []           # applied edits in order: {path, search, replace}
        self.last_edit_call = 0
        self.last_tests_call = 0

    def call(self, name, args):
        self.n_calls += 1
        fn = getattr(self, "t_" + name, None) if name in _NAMES else None
        if fn is None:
            return f"error: unknown tool {name!r}"
        try:
            out = _clip(fn(**(args or {})))
            if name == "run_tests" and out.startswith("[exit"):
                self.last_tests_call = self.n_calls
            return out
        except TypeError as e:
            return f"error: bad arguments: {e}"

    def t_list_dir(self, path="."):
        if path != "." and (e := _bad_path(path)):
            return e
        code, out = self.sb.exec(["ls", "-1Ap", "--", path])
        return out if code == 0 else f"error: {out.strip()}"

    def t_read_file(self, path, start=1, end=None):
        if e := _bad_path(path):
            return e
        s = _int(start, 1, 1, 10**7)
        last = _int(end, s + 399, s, 10**7) if end is not None else s + 399
        code, out = self.sb.exec(["python", "-c", READ_SNIPPET, str(s), str(last), path])
        if code != 0:
            return f"error: {out.strip().splitlines()[-1] if out.strip() else code}"
        return out or "(nothing in that range: past the end of the file, or the file is empty)"

    def t_search(self, regex, path="."):
        if path != "." and (e := _bad_path(path)):
            return e
        code, out = self.sb.exec(["grep", "-rnIE", "--exclude-dir=.git", "-e", regex, "--", path])
        if code == 1:
            return "no matches"
        if code != 0:
            return f"error: {out.strip()}"
        lines = out.splitlines()
        return "\n".join(lines[:200]) + (f"\n[{len(lines) - 200} more matches not shown]" if len(lines) > 200 else "")

    def t_git_log(self, path=None, n=10):
        a = ["git", "log", "-n", str(_int(n, 10, 1, 50)), "--format=%h %ad %an %s", "--date=short"]
        if path:
            if e := _bad_path(path):
                return e
            a += ["--", path]
        return self.sb.exec(a)[1]

    def t_git_show(self, rev, path=None):
        if not isinstance(rev, str) or not REV.match(rev):
            return "invalid rev: use a commit hash or HEAD~N"
        a = ["git", "show", "--no-color", "--format=%H%n%an %ad%n%n%B", "--date=short", rev]
        if path:
            if e := _bad_path(path):
                return e
            a += ["--", path]
        code, out = self.sb.exec(a)
        return out if code == 0 else f"error: {out.strip()}"

    def t_git_blame(self, path, start, end):
        if e := _bad_path(path):
            return e
        s = _int(start, 1, 1, 10**7)
        code, out = self.sb.exec(["git", "blame", "-L", f"{s},{_int(end, s, s, s + 300)}", "--", path])
        return out if code == 0 else f"error: {out.strip()}"

    def t_run_python(self, code):
        if not isinstance(code, str):
            return "error: code must be a string"
        c, out = self.sb.exec(["python", "-W", "ignore::DeprecationWarning", "-c", code], timeout=60)
        return f"[exit {c}]\n{out}"

    def t_run_tests(self, selection):
        ok = isinstance(selection, list) and selection and all(
            isinstance(s, str) and TEST_SEL.match(s) and not _bad_path(s.split("::")[0]) for s in selection)
        if not ok:
            return "error: selection must be a non-empty list of test paths or node ids"
        c, out = self.sb.exec(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning",
                               "--timeout", "60", *selection], timeout=120)
        return f"[exit {c}]\n{out}"

    def t_record_hypothesis(self, text, predicts):
        if not (isinstance(text, str) and text.strip() and isinstance(predicts, str) and predicts.strip()):
            return "error: text and predicts must be non-empty strings"
        hid = f"H{len(self.hypotheses) + 1}"
        self.hypotheses[hid] = {"id": hid, "text": text, "predicts": predicts, "status": "open",
                                "evidence": "", "calls": [], "recorded_at_call": self.n_calls}
        return f"recorded {hid}"

    def t_update_hypothesis(self, id, status, evidence, calls):
        h = self.hypotheses.get(id)
        if h is None:
            return f"error: unknown hypothesis {id!r}; known: {', '.join(self.hypotheses) or 'none'}"
        if status not in ("supported", "rejected", "open"):
            return "error: status must be supported, rejected or open"
        if not isinstance(evidence, str) or not evidence.strip():
            return "error: evidence must be a non-empty string"
        # a cited call must be an earlier call, not this one and not one in the future
        if (not isinstance(calls, list) or not all(isinstance(c, int) and not isinstance(c, bool) and 1 <= c < self.n_calls for c in calls)
                or (status != "open" and not calls)):
            return f"error: calls must be earlier tool call numbers (1 to {self.n_calls - 1}), and are required unless status is open"
        h.update(status=status, evidence=evidence, calls=calls, updated_at_call=self.n_calls)
        return f"{id} is now {status}"

    def _host_path(self, rel):
        full = os.path.realpath(os.path.join(self.sb.workdir, rel))
        root = os.path.realpath(self.sb.workdir)
        return full if full.startswith(root + os.sep) else None

    def t_apply_edit(self, path, search, replace):
        if _bad_path(path) or not path.startswith(SCOPE):
            return f"error: path must be a relative path under {SCOPE}"
        if not isinstance(search, str) or not search or not isinstance(replace, str):
            return "error: search must be a non-empty string and replace a string"
        full = self._host_path(path)
        if full is None or not os.path.isfile(full):
            return f"error: file not found: {path}"
        text = open(full, encoding="utf-8", newline="").read()
        n = text.count(search)
        if n != 1:
            return f"error: search text matches {n} times in {path} (needs exactly 1)"
        open(full, "w", encoding="utf-8", newline="").write(text.replace(search, replace))
        self.edits.append({"path": path, "search": search, "replace": replace})
        self.last_edit_call = self.n_calls
        return f"applied edit {len(self.edits)} to {path}. Run tests to check it."

    def _workspace_matches_edits(self):
        """True if the files under src/ equal HEAD plus the recorded edits and nothing else."""
        code, out = self.sb.exec(["git", "status", "--porcelain", "--", SCOPE])
        changed = {l[3:].strip() for l in out.splitlines()}
        expected = {}
        for ed in self.edits:
            if ed["path"] not in expected:
                c, orig = self.sb.exec(["git", "show", f"HEAD:{ed['path']}"])
                if c != 0:
                    return False, f"{ed['path']} not found at HEAD"
                expected[ed["path"]] = orig
            expected[ed["path"]] = expected[ed["path"]].replace(ed["search"], ed["replace"], 1)
        stray = changed - set(expected)
        if stray:
            return False, "files changed without apply_edit: " + ", ".join(sorted(stray))
        for rel, want in expected.items():
            if open(self._host_path(rel), encoding="utf-8", newline="").read().replace("\r\n", "\n") != want.replace("\r\n", "\n"):
                return False, f"{rel} differs from HEAD plus the recorded edits (changed some other way)"
        return True, ""

    def t_submit(self, report):
        if not isinstance(report, dict):
            return "error: report must be an object"
        problems = []
        if len(self.hypotheses) < 2:
            problems.append("record at least two competing hypotheses first")
        unresolved = [h for h, v in self.hypotheses.items() if v["status"] == "open"]
        if unresolved:
            problems.append(f"resolve every hypothesis (supported or rejected) first; still open: {', '.join(unresolved)}")
        if self.hypotheses and not any(v["status"] == "supported" for v in self.hypotheses.values()):
            problems.append("no hypothesis is supported; the root cause must be one of them")
        if not self.edits:
            problems.append("no fix applied; use apply_edit first")
        elif self.last_tests_call < self.last_edit_call:
            problems.append("run_tests has not been run since your last apply_edit")
        elif not problems:
            ok, why = self._workspace_matches_edits()
            if not ok:
                problems.append(why + "; reapply the change with apply_edit")
        if problems:
            return "rejected, fix and resubmit:\n" + "\n".join(problems)
        self.submission = {"edits": self.edits, "report": report, "hypotheses": list(self.hypotheses.values())}
        return "submitted"
