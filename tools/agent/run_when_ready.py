"""Wait until a model stops answering HTTP 503 ("high demand"), then run one or more batches with it.

usage: python -I run_when_ready.py <model> <batch> [<batch> ...] [--wait-hours=H] [--probes=N] [--gap-min=M] [--key-env=NAME]

  <batch>  variant:protocol[:case,case,...]   e.g. v2b:v2:filelock-346,packaging-638   or   v3a:v3 (all five cases)

Waits H hours (default 0), then sends one tiny request. On any answer other than HTTP 200 it waits M minutes
(default 30) and tries again, up to N probes (default 8). On the first 200 it runs each batch in order through
run_batch.py, which skips run folders that already exist. Gives up, with exit code 1 and no run started, if
every probe fails. Each probe costs one request of the model's daily quota. The key is read from .env and never
printed.
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import agent  # for load_env and the default key variable

PY = f"{ROOT}/.venv/Scripts/python.exe" if os.path.exists(f"{ROOT}/.venv/Scripts/python.exe") else sys.executable


def probe(model, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": "Reply with OK."}]}]}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        urllib.request.urlopen(req, timeout=60).read()
        return 200
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1  # network error or timeout


def say(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def parse_batch(spec):
    parts = spec.split(":")
    if len(parts) not in (2, 3) or parts[1] not in ("v1", "v2", "v3"):
        raise SystemExit(f"bad batch {spec!r}: expected variant:protocol[:case,case,...]")
    return parts[0], parts[1], parts[2].split(",") if len(parts) == 3 else []


if __name__ == "__main__":
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if len(pos) < 2:
        raise SystemExit(__doc__)
    model, batches = pos[0], [parse_batch(s) for s in pos[1:]]
    key_env = opts.get("key-env", agent.KEY_ENV)
    agent.load_env()
    key = os.environ.get(key_env) or sys.exit(f"{key_env} is not set in .env")

    wait = float(opts.get("wait-hours", 0)) * 3600
    if wait:
        say(f"waiting {wait / 3600:g} hours before the first probe")
        time.sleep(wait)
    probes, gap = int(opts.get("probes", 8)), float(opts.get("gap-min", 30)) * 60
    for i in range(probes):
        code = probe(model, key)
        say(f"probe {i + 1} of {probes}: HTTP {code}")
        if code == 200:
            break
        if i + 1 < probes:
            time.sleep(gap)
    else:
        say("model still busy; no run started")
        sys.exit(1)

    for variant, protocol, cases in batches:
        say(f"running {variant} under protocol {protocol} on {', '.join(cases) or 'all cases'}")
        subprocess.run([PY, "-I", f"{HERE}/run_batch.py", model, variant, *cases,
                        f"--protocol={protocol}", f"--key-env={key_env}"])
    say("done")
