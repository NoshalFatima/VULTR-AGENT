# Blast Radius Zero Agent

> A web agent that does real work, writing and running code or operating a real browser, with **every action contained in a gVisor sandbox on Vultr**. It plans, dispatches, and returns **hashed, verifiable output**.

Built for the **Vultr: Agent Rush Hackathon**, Challenge 1 "Blast Radius Zero". License: MIT.

- **Live demo:** https://64-177-57-193.nip.io (access code is provided in the LabLab submission)
- **Demo video:** [ADD VIDEO LINK]

## What it does
Give it a task in a chat UI. The agent loop runs on a Vultr VM:

1. **Plan:** the LLM (Vultr Serverless Inference) breaks the task into steps.
2. **Dispatch:** each step (Python code, or a list of browser actions) is sent to an isolated runner.
3. **Execute:** the runner starts a fresh gVisor container, runs the step, returns real stdout/stderr, exit code, files and screenshots, then destroys the container.
4. **Retry:** errors go back to the LLM, which fixes the code (up to 3 failures).
5. **Verify:** each step shows SHA-256 of code and output. The final answer is checked: every number in it must appear in executed output, otherwise it is flagged "Not fully verified".

Pattern A (sandboxed code execution) and Pattern B (sandboxed browser use with Playwright) are both implemented.
Example tasks: CSV analysis and charts, self-healing code runs, "open a page, read a heading", site checks.

## Use case
Teams and individuals often want an AI agent to *do* things, such as analyze a file, draw a chart, check a web page, or fix a script, but cannot let model-written code run on their own machines. This agent gives them real execution with a hard blast radius: whatever the model writes runs in a throwaway sandbox with no network, no secrets, strict limits, and an audit trail (hashes of code and output).

## Architecture
```mermaid
flowchart LR
    U["Browser"] -->|HTTPS| C["Caddy"]
    C --> A["Control VM: FastAPI, SQLite, agent loop"]
    A -->|"all LLM calls"| V["Vultr Serverless Inference"]
    A -->|"HMAC-signed, Vultr VPC private IP"| R["Runner VM: Docker + gVisor runsc"]
    R -->|"python step, no network"| P["Fresh Python sandbox, destroyed after each step"]
    R -->|"browser step, internal network"| B["Fresh Playwright sandbox"]
    B --> X["HTTPS allowlist proxy"]
    X -->|"allowlisted domains only"| I["Internet"]
```

- **Control VM** serves the web app (behind Caddy with automatic HTTPS), holds sessions and chat history, holds the API keys, and calls Vultr Serverless Inference. It never executes model-written code.
- **Runner VM** is the only machine that executes code. It accepts only HMAC-signed requests from the control VM's private IP and runs every step in a fresh gVisor (`runsc`) container.
- **Egress proxy** is the only exit for browser containers. It allows HTTPS `CONNECT` to allowlisted hosts only.

## Vultr services used
| Service | Role |
|---|---|
| **Vultr Cloud Compute** | Control VM (web app, orchestration, history) and Runner VM (sandbox host). Vultr is the control layer. |
| **Vultr Serverless Inference** | Every planner and agent LLM call (`https://api.vultrinference.com/v1/chat/completions`). The live demo uses `mimo-v2.6-pro`. |
| **Vultr VPC 2.0** | Private network between control and runner; the runner has no public service port |
| **Vultr Firewall + UFW** | Runner accepts port 8001 only from the control VM private IP |

## Containment
| Focus | What we do |
|---|---|
| **Process isolation** | gVisor user-space kernel, read-only rootfs, tmpfs work dir, non-root user, all capabilities dropped, no-new-privileges. Python containers have no network (`--network none`). Browser containers have no route to the internet except the allowlist proxy. |
| **Secret hygiene** | API keys exist only on the control VM. The sandbox environment has no secrets (checked live by an attack test). |
| **Resource limits** | 256 MB RAM (1 GB browser), 0.5 CPU, 64 pids, 30 s timeout (60 s browser), file size and output caps |
| **Lifecycle** | Fresh container per step, destroyed after (`--rm`), timeouts hard-kill the container |

Extra hardening: HMAC-signed control-to-runner requests with timestamp and replay cache; the browser proxy is HTTPS-only, allowlisted, blocks private and metadata IPs and connects by resolved IP (no DNS rebinding); control and runner both re-check URLs; sandbox output is untrusted (re-validated, PNG magic check, artifacts served with a `sandbox` CSP); web content is wrapped as untrusted data against prompt injection; strict CSP with no inline scripts, HttpOnly SameSite=Strict cookies, CSRF header, rate limits, one run at a time per visitor.

### Containment moment (try it)
Tap **Secure → Run attack tests** in the app. Eight real attacks run live in the sandbox and each one is shown blocked:

| Attack | Result |
|---|---|
| Network access | blocked |
| Write to the root filesystem | blocked (read-only) |
| `rm -rf` | cannot destroy the system |
| Fork bomb | capped (64 pids) |
| Memory bomb | killed (256 MB) |
| Infinite loop | timed out (30 s) |
| Root user | runs as non-root |
| Secrets in environment | none |

You can also ask the agent to try to reach `https://news.ycombinator.com` in Browser mode. The request is rejected (`domain not allowed`), because only allowlisted domains are reachable.

## Deploy on Vultr (about 20 min)
1. Create a VPC 2.0 (`agent-vpc`) and two Ubuntu 24.04 VMs in it: control (2 vCPU / 4 GB) and runner (4 vCPU / 8 GB), Backups off.
2. Vultr Firewall: control allows 22 (your IP), 80, 443. Runner allows 22 (your IP) and TCP 8001 from the control private IP only.
3. Generate one secret and use it on both VMs: `export S=$(openssl rand -hex 32)`
4. Vultr Console → Serverless → Inference: create a subscription and copy the API key. List the available model IDs with `curl -s https://api.vultrinference.com/v1/models -H "Authorization: Bearer $VULTR_INFERENCE_API_KEY"` and set `MODEL=<id>` (the demo uses `mimo-v2.6-pro`).
5. Runner VM: `git clone <this repo> && cd <repo> && sudo PRIVATE_IP=<runner-private-ip> CONTROL_PRIVATE_IP=<control-private-ip> RUNNER_SECRET=$S ./deploy/setup_runner.sh`
6. Control VM: `sudo RUNNER_PRIVATE_IP=<runner-private-ip> RUNNER_SECRET=$S VULTR_INFERENCE_API_KEY=<key> ACCESS_CODE=<code> ./deploy/setup_control.sh`
7. Open the printed `https://<ip>.nip.io` URL and enter the access code.

Configuration lives in `/etc/agent/control.env` (control VM) and `/etc/agent/runner.env` (runner VM). Useful variables: `MODEL`, `LLM_PROVIDER` (`vultr`), `ACCESS_CODE`, `BROWSER_ALLOWLIST` (comma-separated domains, default `example.com,wikipedia.org`).

### gVisor notes
- A network attached to a **running** gVisor container is not picked up by the sandbox. The setup script therefore restarts the egress proxy container after connecting it to the internal network.
- gVisor containers cannot use Docker's embedded DNS (`127.0.0.11`), so the browser container gets the proxy address through `--add-host`, and the proxy container is given its own `resolv.conf`.

## Run locally (Docker Desktop, no gVisor)
gVisor is Linux-only, so locally use plain Docker with `SANDBOX_RUNTIME=runc`.
```
docker build -t sbx-python:1 -f runner/Dockerfile.python runner/
cd runner && pip install -r requirements.txt
SANDBOX_RUNTIME=runc RUNNER_SECRET=dev uvicorn runner:app --port 8001      # terminal 1
cd control && pip install -r requirements.txt
RUNNER_URL=http://127.0.0.1:8001 RUNNER_SECRET=dev SESSION_SECRET=dev COOKIE_SECURE=0 DATA_DIR=./data \
LLM_PROVIDER=vultr VULTR_INFERENCE_API_KEY=<key> uvicorn app:app --port 8000   # terminal 2
```
Open http://localhost:8000. PowerShell: use `$env:NAME="value"`. Browser mode also needs the `sbx-browser` and `sbx-proxy` images and `docker network create --internal sbx-internal`.

## Repo layout
```
control/   FastAPI app, agent loop, history (SQLite), web UI (static/)
runner/    sandbox runner, in-container harnesses, egress proxy, Dockerfiles
deploy/    setup scripts and systemd units for both VMs
docs/      submission text
```

## Limitations
Artifacts are stored on the control VM disk. Browser mode only visits allowlisted HTTPS domains (`BROWSER_ALLOWLIST`). Vision-model screenshot verification and human approval before final actions are not implemented yet.
