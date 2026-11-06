# lablab.ai submission text

**Title:** Blast Radius Zero Agent

**Short description:** A web agent that writes and runs code or drives a real browser, with every action inside a gVisor sandbox on Vultr, and returns hashed, verifiable results.

**Long description:**
Most agents only describe what they would do. Blast Radius Zero Agent does the work and proves it. A chat UI sends a task to a control layer on Vultr, where an LLM from Vultr Serverless Inference plans the steps. Each step is dispatched over a private Vultr VPC to a runner VM, which starts a fresh gVisor container, executes the code or Playwright browser actions, returns real output, screenshots and files, and destroys the container. Errors are fed back so the agent fixes itself. Every step shows SHA-256 hashes of code and output, and the final answer is checked: any number not found in the executed output is flagged.
Containment comes first: no network (browser traffic only through an HTTPS allowlist proxy that blocks private and metadata IPs), read-only filesystem, non-root, dropped capabilities, memory/CPU/pid/time limits, no secrets in the sandbox, HMAC-signed control-to-runner requests, and a live "Run attack tests" panel that shows eight real attacks being blocked.

**Tags:** Vultr, AI agents, sandboxing, gVisor, Docker, Playwright, FastAPI, Serverless Inference, security
**Category:** Challenge 1: Blast Radius Zero

**Demo video checklist (about 3 min):**
1. Code mode: "Generate a 200-row sales dataset, compute revenue by region, save a bar chart to /out" (show code, output, hashes, chart)
2. Browser mode: "Open https://example.com, read the h1, count its words" (show screenshot, verified answer)
3. Containment moment: Secure → Run attack tests, all blocked
4. History drawer: reopen an old run
5. Show the Vultr console: two instances, VPC, firewall
