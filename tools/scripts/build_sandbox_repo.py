"""Build the agent's workspace: the repo at the faulty revision with no trace of the fix.

usage: build_sandbox_repo.py <case_id> <dest_dir>

Steps: clone, detach at the faulty revision, make a single branch `main` there, drop the
remote, every other ref, reflogs and unreachable objects. Then verify nothing after the
faulty revision is reachable or even present in the object store.
"""
import json, os, shutil, stat, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
case, dest = sys.argv[1], sys.argv[2]
meta = json.load(open(f"{ROOT}/cases/{case}/metadata.json"))
faulty = meta["faulty_revision"]
fixed = meta.get("fixed_revision")
if not fixed:  # flask-5160 was admitted before fixed_revision was added to metadata
    fixed = json.load(open(f"{ROOT}/cases/{case}/reference/validation.json"))["reference_revision"]
upstream = f"{ROOT}/cases/{case}/upstream"


def git(*args, check=True):
    r = subprocess.run(["git", "-C", dest, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def rm_readonly(fn, path, _):
    os.chmod(path, stat.S_IWRITE)
    fn(path)


if os.path.exists(dest):
    shutil.rmtree(dest, onerror=rm_readonly)
subprocess.run(["git", "clone", "-q", "--no-local", upstream, dest], check=True, capture_output=True)
git("checkout", "-q", "--detach", faulty)
git("checkout", "-q", "-B", "main")
git("remote", "remove", "origin")
for ref in git("for-each-ref", "--format=%(refname)").stdout.split():
    if ref != "refs/heads/main":
        git("update-ref", "-d", ref)
git("reflog", "expire", "--expire=now", "--all")
git("gc", "-q", "--prune=now", "--aggressive")
for f in ("packed-refs", "ORIG_HEAD", "FETCH_HEAD"):
    p = f"{dest}/.git/{f}"
    if os.path.exists(p) and f != "packed-refs":
        os.remove(p)

# Verification: the fix and everything after the faulty revision must be gone.
problems = []
if git("cat-file", "-e", fixed, check=False).returncode == 0:
    problems.append("fixed revision still in object store")
if fixed in git("log", "--all", "--format=%H").stdout:
    problems.append("fixed revision listed by git log --all")
if git("rev-parse", "HEAD").stdout.strip() != faulty:
    problems.append("HEAD is not the faulty revision")
if git("tag").stdout.strip():
    problems.append("tags remain")
if git("branch", "-a", "--format=%(refname)").stdout.split() != ["refs/heads/main"]:
    problems.append("extra branches remain")
if git("remote").stdout.strip():
    problems.append("remote remains")
if "fatal" not in git("rev-list", "--count", f"{faulty}..{fixed}", check=False).stderr:
    problems.append("faulty..fixed range is resolvable")
bc = meta.get("breaking_commit")
if bc and git("cat-file", "-e", bc, check=False).returncode:
    problems.append("breaking commit missing from history (should stay visible)")
if problems:
    sys.exit("LEAK CHECK FAILED: " + "; ".join(problems))
n = git("rev-list", "--count", "HEAD").stdout.strip()
print(f"ok {case}: {dest} at {faulty[:8]}, {n} commits, fix absent")
