"""HTTPS-only allowlist egress proxy. CONNECT :443 to allowlisted hosts only; blocks private/metadata IPs;
connects by resolved IP (no DNS rebinding)."""
import asyncio, ipaddress, os, socket
ALLOW = [d.strip().lower() for d in os.environ["ALLOW"].split(",") if d.strip()]
SEM = asyncio.Semaphore(50)

async def safe_ip(host):
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = [ipaddress.ip_address(i[4][0]) for i in infos]
    if not ips or any(not ip.is_global for ip in ips): return None
    return str(ips[0])

async def pipe(r, w):
    try:
        while d := await r.read(65536): w.write(d); await w.drain()
    except Exception: pass
    finally: w.close()

async def handle(r, w):
    try:
        async with SEM:
            parts = (await asyncio.wait_for(r.readline(), 10)).decode("latin1").split()
            while (await asyncio.wait_for(r.readline(), 10)) not in (b"\r\n", b"\n", b""): pass
            if len(parts) < 2 or parts[0] != "CONNECT": w.write(b"HTTP/1.1 403 Forbidden\r\n\r\n"); return
            host, _, port = parts[1].rpartition(":"); host = host.lower().strip("[]")
            if port != "443" or not any(host == d or host.endswith("." + d) for d in ALLOW): w.write(b"HTTP/1.1 403 Forbidden\r\n\r\n"); return
            ip = await safe_ip(host)
            if not ip: w.write(b"HTTP/1.1 403 Forbidden\r\n\r\n"); return
            ur, uw = await asyncio.wait_for(asyncio.open_connection(ip, 443), 10)
            w.write(b"HTTP/1.1 200 Connection established\r\n\r\n"); await w.drain()
            await asyncio.wait_for(asyncio.gather(pipe(r, uw), pipe(ur, w)), 90)
    except Exception:
        try: w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        except Exception: pass
    finally: w.close()

async def main():
    s = await asyncio.start_server(handle, "0.0.0.0", 3128)
    async with s: await s.serve_forever()
asyncio.run(main())
