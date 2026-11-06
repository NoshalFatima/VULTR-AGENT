"use strict";
const $ = s => document.querySelector(s), NS = "http://www.w3.org/2000/svg";
const P = {menu:'<path d="M3 6h18M3 12h18M3 18h18"/>',up:'<path d="M12 19V5M5 12l7-7 7 7"/>',shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',plus:'<path d="M12 5v14M5 12h14"/>',trash:'<path d="M3 6h18M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>',code:'<path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>',globe:'<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20a15 15 0 0 1 0-20z"/>',check:'<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4L12 14l-3-3"/>',dl:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>'};
function ico(n, s = 18) {
  const e = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({viewBox:"0 0 24 24",width:s,height:s,fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"})) e.setAttribute(k, v);
  e.innerHTML = P[n]; return e;
}
function h(tag, p = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [a, v] of Object.entries(p)) {
    if (a === "class") e.className = v; else if (a.startsWith("on")) e[a] = v; else if (v !== false && v != null) e.setAttribute(a, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}
document.querySelectorAll("[data-i]").forEach(e => e.append(ico(e.dataset.i, +(e.dataset.s || 18))));
const st = {chat: null, mode: "code", busy: false, ctx: null};

async function api(path, o = {}) {
  const r = await fetch(path, {...o, credentials: "same-origin", headers: {"X-Requested-With": "fetch", "Content-Type": "application/json"}});
  if (r.status === 401) { $("#login").hidden = false; throw new Error("auth"); }
  return r;
}
function panel(open, which) {
  $("#drawer").classList.toggle("open", open === "d"); $("#sheet").classList.toggle("open", open === "s"); $("#scrim").hidden = !open;
}

function render(e) {
  const f = $("#feed"); let c = st.ctx;
  if (e.type === "user") {
    f.querySelector(".hello")?.remove();
    f.append(h("div", {class: "me"}, e.text));
    c = st.ctx = {blk: h("div", {class: "bot"}), items: null, done: 0, head: null};
    f.append(h("div", {class: "row"}, h("div", {class: "av"}, ico("shield", 14)), c.blk));
  } else if (!c) { return; }
  else if (e.type === "plan") {
    c.items = e.items.map(t => h("li", {}, t)); c.head = h("span", {}, `0 of ${e.items.length} done`);
    c.blk.append(h("div", {class: "card"}, h("div", {class: "ch"}, h("span", {}, "Plan"), c.head), h("ul", {class: "plan"}, c.items)));
  } else if (e.type === "step") {
    if (e.ok && c.items && c.done < c.items.length) { c.items[c.done++].classList.add("done"); c.head.textContent = `${c.done} of ${c.items.length} done`; }
    const src = e.kind === "python" ? e.code : e.actions.map(a => a.do + (a.url ? " " + a.url : a.selector ? " " + a.selector : "")).join("\n");
    const out = (e.stdout + (e.stderr ? "\n" + e.stderr : "")).trim();
    const arts = e.artifacts || [];
    c.blk.append(h("div", {class: "card"},
      h("div", {class: "ch"}, h("span", {}, `Step ${e.n} · ${e.kind === "python" ? "Python" : "Browser"}`), h("span", {class: e.ok ? "ok" : "bad"}, `exit ${e.exit_code} · ${e.duration}s`)),
      h("pre", {}, src), h("pre", {class: "out" + (e.ok ? "" : " err")}, out || "(no output)"),
      arts.filter(a => a.image).map(a => h("img", {class: "shot", src: a.url, alt: a.name})),
      h("div", {class: "hash"}, `code sha256 ${e.code_sha256.slice(0, 12)}… · output sha256 ${e.output_sha256.slice(0, 12)}…`),
      arts.length ? h("div", {class: "chips"}, arts.map(a => h("a", {class: "chip", href: a.url, download: a.name}, ico("dl", 12), a.name))) : null));
  } else if (e.type === "final") {
    c.blk.append(h("div", {class: "final" + (e.verified ? "" : " warn")},
      h("div", {class: "fl"}, ico("check", 14), e.verified ? "Verified from executed output" : "Not fully verified"), h("p", {}, e.answer),
      e.unverified && e.unverified.length ? h("small", {}, "Numbers not found in output: " + e.unverified.join(", ")) : null));
  } else if (e.type === "error") { c.blk.append(h("div", {class: "errmsg"}, e.message)); }
  f.scrollTop = f.scrollHeight;
}

async function hist() {
  const list = await (await api("/api/chats")).json(), box = $("#hist"); box.replaceChildren();
  const today = new Date(new Date().toDateString()); let last = "";
  for (const c of list) {
    const d = (today - new Date(new Date(c.created * 1000).toDateString())) / 864e5, g = d < 1 ? "Today" : d < 2 ? "Yesterday" : "Earlier";
    if (g !== last) { box.append(h("div", {class: "lab"}, g)); last = g; }
    box.append(h("div", {class: "hi" + (c.id === st.chat ? " on" : ""), onclick: () => openChat(c.id, c.mode)},
      ico(c.mode === "browser" ? "globe" : "code", 16), h("div", {}, c.title, h("small", {}, `${c.mode} · ${c.steps} steps`))));
  }
}
function reset() { $("#feed").replaceChildren(h("div", {class: "hello"}, h("h2", {}, "Give a task. Watch it run."), h("p", {}, "Every line of code runs in an isolated sandbox on Vultr."))); st.ctx = null; st.chat = null; }
async function openChat(id, mode) {
  const d = await (await api("/api/chats/" + id)).json();
  reset(); st.chat = id; setMode(mode); d.events.forEach(render); panel(null); hist();
}
function setMode(m) { st.mode = m; document.querySelectorAll(".seg button").forEach(b => b.classList.toggle("on", b.dataset.m === m)); }

async function run(task) {
  st.busy = true; $("#send").disabled = true;
  try {
    const r = await api("/api/run", {method: "POST", body: JSON.stringify({task, mode: st.mode, chat_id: st.chat})});
    if (!r.ok) { const m = (await r.json().catch(() => ({}))).detail || "Request failed"; render({type: "user", text: task}); render({type: "error", message: String(m)}); return; }
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    for (;;) {
      const {value, done} = await rd.read(); if (done) break;
      buf += dec.decode(value, {stream: true}); let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!chunk.startsWith("data: ")) continue;
        const e = JSON.parse(chunk.slice(6)); if (e.type === "chat") st.chat = e.id; else render(e);
      }
    }
  } catch (x) { if (x.message !== "auth") render({type: "error", message: "Connection lost."}); }
  finally { st.busy = false; $("#send").disabled = false; hist().catch(() => {}); }
}

$("#form").onsubmit = ev => {
  ev.preventDefault(); const t = $("#task").value.trim(); if (!t || st.busy) return;
  $("#task").value = ""; $("#task").style.height = "auto"; run(t);
};
$("#task").onkeydown = ev => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); $("#form").requestSubmit(); } };
$("#task").oninput = ev => { const t = ev.target; t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; };
document.querySelectorAll(".seg button").forEach(b => b.onclick = () => setMode(b.dataset.m));
$("#menu").onclick = () => { hist(); panel("d"); };
$("#scrim").onclick = $("#close").onclick = () => panel(null);
$("#new").onclick = () => { reset(); panel(null); hist(); };
$("#clear").onclick = async () => { if (confirm("Delete all your chats and files?")) { await api("/api/chats", {method: "DELETE"}); reset(); hist(); panel(null); } };
$("#shield").onclick = async () => {
  const d = await (await api("/api/containment")).json(); $("#srows").replaceChildren(...d.rows.map(r => h("div", {class: "r"}, h("span", {}, r[0]), h("span", {}, r[1]))));
  $("#sstate").textContent = d.runner; panel("s");
};
$("#run").onclick = async () => {
  const b = $("#run"); b.disabled = true; b.textContent = "Running attacks…"; $("#atk").replaceChildren();
  try {
    const r = await api("/api/selftest", {method: "POST", body: "{}"});
    if (!r.ok) throw 0; const d = await r.json();
    $("#atk").replaceChildren(h("div", {class: "lab"}, "Live results from the sandbox"), ...d.results.map(t => h("div", {class: "r"}, h("span", {}, t.name), h("span", {class: t.passed ? "ok" : "bad"}, t.passed ? "blocked" : "FAILED"))));
  } catch { $("#atk").replaceChildren(h("div", {class: "errmsg"}, "Could not run tests. Try again later.")); }
  b.disabled = false; b.textContent = "Run attack tests";
};
$("#lform").onsubmit = async ev => {
  ev.preventDefault();
  const r = await fetch("/api/login", {method: "POST", credentials: "same-origin", headers: {"X-Requested-With": "fetch", "Content-Type": "application/json"}, body: JSON.stringify({code: $("#code").value})});
  if (r.ok) { $("#login").hidden = true; hist(); } else $("#lerr").textContent = r.status === 429 ? "Too many attempts." : "Wrong code.";
};
(async () => { const me = await (await fetch("/api/me", {credentials: "same-origin"})).json(); if (me.need_login) $("#login").hidden = false; else hist().catch(() => {}); })();
