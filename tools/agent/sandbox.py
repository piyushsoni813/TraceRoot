"""One Docker container per run. Every tool executes inside it via `docker exec`."""
import os, subprocess, sys, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGE = "traceroot-sandbox:1"
PY = sys.executable
NOCONV = dict(os.environ, MSYS_NO_PATHCONV="1")


class Sandbox:
    def __init__(self, case_id, workdir):
        self.case_id, self.workdir = case_id, os.path.abspath(workdir)
        self.name = f"tr-{case_id}-{uuid.uuid4().hex[:8]}"

    def start(self):
        subprocess.run([PY, "-I", f"{ROOT}/tools/scripts/build_sandbox_repo.py", self.case_id, self.workdir],
                       check=True, capture_output=True)
        subprocess.run(["docker", "run", "-d", "--rm", "--name", self.name, "--network", "none",
                        "--cpus", "2", "--memory", "2g", "--pids-limit", "256",
                        "-v", f"{self.workdir}:/work", "-e", "PYTHONPATH=/work/src:/work",
                        IMAGE, "sleep", "infinity"],
                       check=True, capture_output=True, env=NOCONV)
        return self

    def exec(self, args, timeout=60):
        """Run args (no shell) in /work. Returns (exit_code, combined_output)."""
        cmd = ["docker", "exec", "-w", "/work", self.name, "timeout", "-k", "2", str(timeout), *args]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                               timeout=timeout + 15, env=NOCONV)
        except subprocess.TimeoutExpired:
            return 124, "timed out"
        return r.returncode, r.stdout + r.stderr

    def stop(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
