import base64, json, sys
from playwright.sync_api import sync_playwright
job = json.load(sys.stdin)
log, files, rc, shots = [], [], 0, 0
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"], proxy={"server": "http://egress-proxy:3128"})
        page = b.new_context(viewport={"width": 1024, "height": 720}, accept_downloads=False, service_workers="block").new_page()
        page.set_default_timeout(10000)
        for a in job["actions"][:12]:
            d = a["do"]
            if d == "goto":
                if not a["url"].startswith("https://"): raise ValueError("https only")
                r = page.goto(a["url"], wait_until="domcontentloaded"); log.append(f"goto {a['url']} -> HTTP {r.status if r else '?'}")
            elif d == "text":
                log.append(f"text[{a['selector']}]: " + page.inner_text(a["selector"])[:4000])
            elif d == "click":
                page.click(a["selector"]); page.wait_for_load_state("domcontentloaded"); log.append(f"click {a['selector']} -> {page.url}")
            elif d == "screenshot" and shots < 3:
                shots += 1; files.append({"name": f"shot{shots}.png", "b64": base64.b64encode(page.screenshot()).decode()}); log.append("screenshot saved")
        b.close()
except Exception as e:
    log.append(f"ERROR: {type(e).__name__}: {str(e)[:300]}"); rc = 1
print(json.dumps({"stdout": "\n".join(log)[:20000], "stderr": "", "exit_code": rc, "files": files}))
