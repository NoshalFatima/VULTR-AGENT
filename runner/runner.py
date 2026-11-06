"""Sandbox runner (private VPC only). Every request is HMAC-signed by the control plane.
One fresh gVisor container per step; hostile output is size-capped and re-validated on the host."""
import asyncio, base64, hashlib, hmac, json, os, re, time, uuid
from fastapi import FastAPI, HTTPException, Request

E = os.environ
SECRET = E["RUNNER_SECRET"].encode()
PY_IMAGE, BR_IMAGE = E.get("PY_IMAGE", "sbx-python:1"), E.get("BR_IMAGE", "sbx-browser:1")
TIMEOUT, BR_TIMEOUT = int(E.get("EXEC_TIMEOUT", "30")), int(E.get("BROWSER_TIMEOUT", "60"))
ALLOW = [d.strip().lower() for d in E.get("BROWSER_ALLOWLIST", "example.com,wikipedia.org").split(",") if d.strip()]
LIMIT = asyncio.Semaphore(int(E.get("MAX_PARALLEL", "3")))
NAME, EXT = re.compile(r"[\w.\-]{1,64}"), {".png", ".csv", ".txt", ".json"}
MAX_OUT, MAX_FILE, MAX_RESP = 20_000, 1_000_000, 8_000_000
SEEN: dict[str, float] = {}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

async def signed(request: Request) -> bytes:
    body = await request.body()
    ts, sig = request.headers.get("x-ts", ""), request.headers.get("x-sig", "")
    if len(body) > 200_000 or not ts.isdigit() or abs(time.time() - int(ts)) > 30: raise HTTPException(401)
    if not hmac.compare_digest(hmac.new(SECRET, ts.encode() + b"." + body, "sha256").hexdigest(), sig): raise HTTPException(401)
    now = time.time()
    for k in [k for k, v in SEEN.items() if now - v > 60]: SEEN.pop(k)
    if sig in SEEN: raise HTTPException(401)
    SEEN[sig] = now
    return body

async def drain(stream, limit):
    buf = bytearray()
    while chunk := await stream.read(65536):
        if len(buf) < limit: buf += chunk[: limit - len(buf)]
    return bytes(buf)

async def sandbox(image, job, net="none", timeout=30, mem="256m", cpus="0.5", pids="64", user="65534:65534", extra=()):
    name, t0 = "sbx-" + uuid.uuid4().hex[:12], time.time()
    args = ["docker", "run", "--rm", "-i", "--name", name, "--runtime=" + E.get("SANDBOX_RUNTIME", "runsc"), "--network", net, "--read-only",
        "--tmpfs", "/work:rw,size=64m,mode=1777,noexec,nosuid", "--tmpfs", "/out:rw,size=24m,mode=1777,noexec,nosuid",
        "--tmpfs", "/tmp:rw,size=64m,mode=1777,nosuid", "--user", user, "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--memory", mem, "--memory-swap", mem, "--cpus", cpus, "--pids-limit", pids,
        "--ulimit", "nofile=256", "--ulimit", "fsize=30000000", "--log-driver", "none",
        "-e", "HOME=/work", "-e", "MPLBACKEND=Agg", *extra, image]
    proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    timed_out, out, err = False, b"", b""
    try:
        proc.stdin.write(json.dumps(job).encode()); await proc.stdin.drain(); proc.stdin.close()
    except Exception: pass
    try:
        out, err = await asyncio.wait_for(asyncio.gather(drain(proc.stdout, MAX_RESP), drain(proc.stderr, 4000)), timeout)
        await proc.wait()
    except asyncio.TimeoutError:
        timed_out = True
        k = await asyncio.create_subprocess_exec("docker", "kill", name, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await k.wait()
    return finish(out, err, t0, timed_out, timeout)

def finish(out, err, t0, timed_out, timeout):
    res = {"stdout": "", "stderr": "", "exit_code": 125, "files": []}
    if timed_out: res.update(stderr=f"TIMEOUT: killed after {timeout}s", exit_code=124)
    else:
        try:
            d = json.loads(out)
            res.update(stdout=str(d["stdout"])[:MAX_OUT], stderr=str(d["stderr"])[:MAX_OUT], exit_code=int(d["exit_code"]))
            for f in list(d.get("files", []))[:5]:
                raw, name = base64.b64decode(f["b64"], validate=True), str(f["name"])
                ext = os.path.splitext(name)[1].lower()
                if not NAME.fullmatch(name) or ext not in EXT or len(raw) > MAX_FILE: continue
                if ext == ".png" and raw[:8] != b"\x89PNG\r\n\x1a\n": continue
                res["files"].append({"name": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "b64": base64.b64encode(raw).decode()})
        except Exception:
            res["stderr"] = err.decode("utf8", "replace")[:2000] or "sandbox failed"
    res["duration"] = round(time.time() - t0, 2)
    res["output_sha256"] = hashlib.sha256((res["stdout"] + res["stderr"]).encode()).hexdigest()
    return res

def check_actions(actions):
    if not isinstance(actions, list) or not 0 < len(actions) <= 12: raise HTTPException(400, "bad actions")
    for a in actions:
        if a.get("do") == "goto":
            from urllib.parse import urlparse
            u = urlparse(str(a.get("url", ""))); h = (u.hostname or "").lower()
            if u.scheme != "https" or not any(h == d or h.endswith("." + d) for d in ALLOW): raise HTTPException(400, "domain not allowed")
        elif a.get("do") not in ("text", "click", "screenshot"): raise HTTPException(400, "bad action")
    return actions

@app.post("/exec/python")
async def exec_python(request: Request):
    code = str(json.loads(await signed(request)).get("code", ""))[:20000]
    async with LIMIT:
        return await sandbox(PY_IMAGE, {"code": code, "timeout": TIMEOUT - 3}, timeout=TIMEOUT)

@app.post("/exec/browser")
async def exec_browser(request: Request):
    acts = check_actions(json.loads(await signed(request)).get("actions"))
    async with LIMIT:
        return await sandbox(BR_IMAGE, {"actions": acts}, net="sbx-internal", timeout=BR_TIMEOUT, mem="1g", cpus="1", pids="256",
                             user="pwuser", extra=["--shm-size=256m"])

TESTS = [
 ("Network access is blocked", "import urllib.request\nurllib.request.urlopen('https://example.com', timeout=3)", lambda r: r["exit_code"] != 0),
 ("Root filesystem is read-only", "open('/etc/pwned','w').write('x')", lambda r: r["exit_code"] != 0),
 ("rm -rf cannot destroy the system", "import subprocess,os\nsubprocess.run(['rm','-rf','/usr/local/lib'],capture_output=True)\nprint('SURVIVED' if os.path.exists('/usr/local/lib') else 'DELETED')", lambda r: "SURVIVED" in r["stdout"]),
 ("Fork bomb is capped", "import subprocess\ntry:\n    [subprocess.Popen(['sleep','5']) for _ in range(500)]\nexcept Exception:\n    print('CAPPED')", lambda r: "CAPPED" in r["stdout"] or r["exit_code"] != 0),
 ("Memory bomb is killed", "x = b'x' * (1 << 30)", lambda r: r["exit_code"] != 0),
 ("Infinite loop is timed out", "while True: pass", lambda r: r["exit_code"] != 0),
 ("Runs as non-root user", "import os; print(os.getuid())", lambda r: r["stdout"].strip() == "65534"),
 ("No secrets in environment", "import os\nprint('LEAK' if any(k in os.environ for k in ('RUNNER_SECRET','GEMINI_API_KEY','ANTHROPIC_API_KEY','SESSION_SECRET')) else 'CLEAN')", lambda r: "CLEAN" in r["stdout"]),
]

@app.post("/selftest")
async def selftest(request: Request):
    await signed(request)
    async def one(t):
        async with LIMIT:
            r = await sandbox(PY_IMAGE, {"code": t[1], "timeout": 5}, timeout=8)
        return {"name": t[0], "passed": bool(t[2](r)), "exit_code": r["exit_code"]}
    return {"results": await asyncio.gather(*[one(t) for t in TESTS])}
