import base64, json, os, subprocess, sys
job = json.load(sys.stdin)
try:
    p = subprocess.run([sys.executable, "-c", job["code"]], capture_output=True, timeout=job["timeout"], cwd="/work")
    so, se, rc = p.stdout[:20000].decode("utf8", "replace"), p.stderr[:20000].decode("utf8", "replace"), p.returncode
except subprocess.TimeoutExpired:
    so, se, rc = "", "TIMEOUT", 124
files = []
try:
    for e in list(os.scandir("/out"))[:20]:
        if len(files) < 5 and e.is_file(follow_symlinks=False) and e.stat(follow_symlinks=False).st_size <= 1_000_000:
            files.append({"name": e.name, "b64": base64.b64encode(open(e.path, "rb").read()).decode()})
except Exception:
    pass
print(json.dumps({"stdout": so, "stderr": se, "exit_code": rc, "files": files}))
