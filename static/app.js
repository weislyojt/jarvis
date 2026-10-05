/* Jarvis app: chat, voice in/out, wake word, approvals, reminders, memory viewer. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };

  const settings = Object.assign(
    { voiceOn: true, wake: false, lang: "en-US", voiceName: "", rate: 1.0 },
    store.get("jv_settings", {})
  );
  const saveSettings = () => store.set("jv_settings", settings);

  const state = {
    token: store.get("jv_token", ""),
    lastNote: store.get("jv_last_note", null),
    name: "Jarvis",
    callMe: "sir",
    busy: false,
    speaking: false,
    rendered: new Set(),
  };

  // ------------------------------------------------------------------ helpers
  const TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { return ""; } })();
  const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
  const installed = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function device() {
    const h = location.hostname, ua = navigator.userAgent;
    if (h === "localhost" || h === "127.0.0.1") return "pc";
    if (/Android/i.test(ua)) return "phone (Android)";
    if (/iPhone|iPad|iPod/i.test(ua)) return "phone (iPhone)";
    return "another computer (browser)";
  }

  let toastTimer;
  function toast(text, ms = 3500) {
    const t = $("#toast");
    t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), ms);
  }

  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers.Authorization = "Bearer " + state.token;
    const res = await fetch(path, {
      method: opts.method || "GET", headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (res.status === 401 && path !== "/api/login") { lockLocal(); throw new Error("login"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
    $("#conn-dot").classList.remove("off");
    return data;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function md(text) {
    let h = esc(text);
    h = h.replace(/```([\s\S]*?)```/g, (_, c) => "<code>" + c.trim() + "</code>");
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
    h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    h = h.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
    h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/^\s*[-*] /gm, "• ");
    return h.replace(/\n/g, "<br>");
  }

  const STATE_LABELS = { idle: "Standing by", listening: "Listening…", thinking: "Working on it…", speaking: "Speaking" };
  function setOrb(s) {
    document.body.dataset.state = s;
    $("#state-label").textContent = STATE_LABELS[s] || s;
  }

  // ------------------------------------------------------------------ transcript
  const tx = () => $("#transcript");
  function scrollDown() { const t = tx(); t.scrollTop = t.scrollHeight; }

  function addMsg(role, text, opts = {}) {
    document.body.classList.add("has-chat");
    const el = document.createElement("div");
    el.className = "msg " + role + (opts.cls ? " " + opts.cls : "");
    el.innerHTML = opts.html || md(text);
    if (opts.sources && opts.sources.length) {
      const s = document.createElement("div");
      s.className = "sources";
      for (const src of opts.sources) {
        let host = src.url;
        try { host = new URL(src.url).hostname.replace(/^www\./, ""); } catch {}
        const a = document.createElement("a");
        a.href = src.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = host; a.title = src.title || src.url;
        s.appendChild(a);
      }
      el.appendChild(s);
    }
    tx().appendChild(el);
    scrollDown();
    return el;
  }

  function systemNote(text) {
    let m = text.match(/approved action #\d+ \(([\s\S]*?)\)\. It ran/);
    if (m) return "You approved: " + m[1];
    m = text.match(/denied action #\d+: ([\s\S]*?)\. It did not run/);
    if (m) return "You denied: " + m[1];
    return null;
  }

  let typingEl = null;
  function showTyping(on) {
    if (on && !typingEl) {
      typingEl = document.createElement("div");
      typingEl.className = "typing";
      typingEl.innerHTML = "<i></i><i></i><i></i>";
      tx().appendChild(typingEl); scrollDown();
    } else if (!on && typingEl) { typingEl.remove(); typingEl = null; }
  }

  function renderPending(list) {
    const ids = new Set((list || []).map((p) => p.id));
    document.querySelectorAll(".approval").forEach((card) => {
      if (!ids.has(+card.dataset.id)) card.classList.add("done");
    });
    for (const p of list || []) {
      if (state.rendered.has(p.id)) continue;
      state.rendered.add(p.id);
      const card = document.createElement("div");
      card.className = "approval"; card.dataset.id = p.id;
      card.innerHTML = '<p class="what">Needs your OK</p><code></code>' +
        '<div class="btns"><button class="ok">Approve</button><button class="no">Deny</button></div>';
      card.querySelector("code").textContent = p.summary;
      card.querySelector(".ok").onclick = () => decide(p.id, true, card);
      card.querySelector(".no").onclick = () => decide(p.id, false, card);
      tx().appendChild(card);
      document.body.classList.add("has-chat");
      scrollDown();
    }
  }

  async function decide(id, approve, card) {
    card.classList.add("done");
    addMsg("note", (approve ? "You approved: " : "You denied: ") + card.querySelector("code").textContent);
    state.busy = true; setOrb("thinking"); showTyping(true);
    try {
      const r = await api(`/api/actions/${id}/${approve ? "approve" : "deny"}`, { method: "POST", body: { device: device() } });
      handleReply(r);
    } catch (e) {
      if (e.message !== "login") toast("Couldn't reach Jarvis.");
      setOrb("idle");
    } finally { state.busy = false; showTyping(false); }
  }

  // ------------------------------------------------------------------ chat
  async function send(text) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    stopSpeaking();
    $("#input").value = "";
    addMsg("user", text);
    state.busy = true; setOrb("thinking"); showTyping(true);
    try {
      const r = await api("/api/chat", { method: "POST", body: { message: text, device: device(), tz: TZ } });
      handleReply(r);
    } catch (e) {
      if (e.message !== "login") {
        $("#conn-dot").classList.add("off");
        addMsg("assistant", "I can't reach the PC right now. Check that Jarvis is running and this device is online.");
      }
      setOrb("idle");
    } finally { state.busy = false; showTyping(false); }
  }

  function handleReply(r) {
    showTyping(false);
    if (r.reply) addMsg("assistant", r.reply, { sources: r.sources });
    renderPending(r.pending);
    for (const a of r.client_actions || []) {
      if (a.type === "open_url") {
        const w = window.open(a.url, "_blank", "noopener");
        if (!w) addMsg("assistant", "", { html: `Tap to open: <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.url)}</a>` });
      }
    }
    if (r.reply) speak(r.reply); else setOrb("idle");
  }

  // ------------------------------------------------------------------ voice out
  function voices() { return "speechSynthesis" in window ? speechSynthesis.getVoices() : []; }
  function pickVoice() {
    const all = voices();
    if (settings.voiceName) { const v = all.find((x) => x.name === settings.voiceName); if (v) return v; }
    const base = settings.lang.slice(0, 2);
    const sameLang = all.filter((v) => v.lang.toLowerCase().startsWith(base));
    return sameLang.find((v) => /en-GB/i.test(v.lang) && /male|daniel|george|ryan|arthur|thomas/i.test(v.name) && !/female/i.test(v.name))
      || sameLang.find((v) => /male|daniel|george|ryan|guy|arthur/i.test(v.name) && !/female/i.test(v.name))
      || sameLang.find((v) => v.lang === settings.lang) || sameLang[0] || null;
  }

  function forSpeech(t) {
    return t.replace(/```[\s\S]*?```/g, " (code on screen) ")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/https?:\/\/\S+/g, "the link")
      .replace(/[*_#>`|]/g, "").replace(/\s+/g, " ").trim();
  }

  function chunks(text) {
    const parts = text.match(/[^.!?。]+[.!?。]*\s*/g) || [text];
    const out = []; let cur = "";
    for (const p of parts) {
      if ((cur + p).length > 180 && cur) { out.push(cur); cur = p; } else cur += p;
    }
    if (cur.trim()) out.push(cur);
    return out;
  }

  function speak(text) {
    if (!settings.voiceOn || !("speechSynthesis" in window)) { setOrb("idle"); return; }
    speechSynthesis.cancel();
    const pieces = chunks(forSpeech(text));
    if (!pieces.length) { setOrb("idle"); return; }
    const v = pickVoice();
    pauseWake();
    state.speaking = true; setOrb("speaking");
    pieces.forEach((piece, i) => {
      const u = new SpeechSynthesisUtterance(piece);
      if (v) { u.voice = v; u.lang = v.lang; } else u.lang = settings.lang;
      u.rate = settings.rate; u.pitch = 0.95;
      if (i === pieces.length - 1) u.onend = u.onerror = doneSpeaking;
      speechSynthesis.speak(u);
    });
  }
  function doneSpeaking() {
    if (!state.speaking) return;
    state.speaking = false;
    if (!state.busy && document.body.dataset.state === "speaking") setOrb("idle");
    resumeWake();
  }
  function stopSpeaking() {
    if ("speechSynthesis" in window && (speechSynthesis.speaking || speechSynthesis.pending)) speechSynthesis.cancel();
    doneSpeaking();
  }

  function chime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = 880; o.type = "sine";
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
      o.connect(g).connect(ctx.destination); o.start(); o.stop(ctx.currentTime + 0.26);
    } catch {}
  }

  // ------------------------------------------------------------------ voice in
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, recMode = null, awaitingCommand = false, awaitTimer = null;

  function voiceUnavailable() {
    if (!SR) return "Voice input needs Chrome, Edge or Safari.";
    if (!window.isSecureContext) return "Voice needs a secure link (https). Use the Tailscale address from the guide.";
    return "";
  }

  function stopRec() {
    if (rec) { try { rec.onend = null; rec.abort(); } catch {} }
    rec = null; recMode = null;
  }

  function startTalk() {
    const why = voiceUnavailable();
    if (why) { toast(why, 5000); return; }
    if (recMode === "talk") { try { rec.stop(); } catch {} return; }
    stopSpeaking(); stopRec();
    let finalText = "";
    recMode = "talk";
    rec = new SR();
    rec.lang = settings.lang; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      $("#input").value = (finalText + interim).trim();
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") toast("Microphone is blocked. Allow it in your browser's site settings.", 5000);
      else if (e.error === "no-speech") toast("I didn't hear anything.");
    };
    rec.onend = () => {
      rec = null; recMode = null;
      if (!state.busy && document.body.dataset.state === "listening") setOrb("idle");
      if (finalText.trim()) send(finalText); else resumeWake();
    };
    try { rec.start(); setOrb("listening"); } catch { recMode = null; rec = null; }
  }

  function wakeWords() {
    const n = (state.name || "jarvis").toLowerCase();
    return Array.from(new Set([n, "jarvis", "jarvis,"]));
  }

  function onWakeSpeech(said) {
    const text = said.trim();
    if (!text) return;
    if (awaitingCommand) {
      awaitingCommand = false; clearTimeout(awaitTimer);
      send(text); return;
    }
    const lower = text.toLowerCase();
    let idx = -1, len = 0;
    for (const w of wakeWords()) {
      const i = lower.indexOf(w);
      if (i >= 0 && (idx < 0 || i < idx)) { idx = i; len = w.length; }
    }
    if (idx < 0) return;
    const cmd = text.slice(idx + len).replace(/^[\s,.!?:]+/, "");
    if (cmd.length > 2) { send(cmd); return; }
    awaitingCommand = true; chime(); setOrb("listening");
    clearTimeout(awaitTimer);
    awaitTimer = setTimeout(() => { awaitingCommand = false; if (document.body.dataset.state === "listening") setOrb("idle"); }, 8000);
  }

  function startWake() {
    if (!settings.wake || voiceUnavailable() || rec || state.speaking || document.hidden) return;
    recMode = "wake";
    rec = new SR();
    rec.lang = settings.lang; rec.continuous = true; rec.interimResults = false;
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) onWakeSpeech(e.results[i][0].transcript);
      }
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        settings.wake = false; saveSettings(); $("#set-wake").checked = false;
        toast("Microphone is blocked, so always-listening is off.", 5000);
      }
    };
    rec.onend = () => { rec = null; recMode = null; setTimeout(startWake, 400); };
    try { rec.start(); } catch { rec = null; recMode = null; }
  }
  function pauseWake() { if (recMode === "wake") stopRec(); }
  function resumeWake() { if (settings.wake && !rec) setTimeout(startWake, 300); }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseWake(); else { resumeWake(); poll(); }
  });

  // ------------------------------------------------------------------ notifications
  async function poll() {
    if (!state.token) return;
    try {
      const r = await api("/api/notifications?after=" + (state.lastNote || 0));
      for (const n of r.items) {
        state.lastNote = Math.max(state.lastNote || 0, n.id);
        if (n.kind === "reminder") {
          addMsg("assistant", "", { cls: "reminder", html: "<strong>Reminder</strong><br>" + md(n.text) });
          speak(`Reminder, ${state.callMe}: ${n.text}`);
          if (!store.get("jv_push", false)) notifyDevice("Reminder", n.text);
        } else addMsg("assistant", n.text);
      }
      store.set("jv_last_note", state.lastNote);
      renderPending(r.pending);
    } catch (e) {
      if (e.message !== "login") $("#conn-dot").classList.add("off");
    }
  }

  async function notifyDevice(title, body) {
    if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
    try {
      const reg = await navigator.serviceWorker?.getRegistration();
      if (reg) reg.showNotification(`${state.name}: ${title}`, { body, icon: "/static/icon-192.png", tag: "jarvis-" + Date.now() });
      else new Notification(`${state.name}: ${title}`, { body });
    } catch {}
  }

  // ------------------------------------------------------------------ settings sheet
  function openSheet(tab = "voice") {
    $("#sheet").hidden = false; $("#sheet-backdrop").hidden = false;
    selectTab(tab);
  }
  function closeSheet() { $("#sheet").hidden = true; $("#sheet-backdrop").hidden = true; }
  function selectTab(name) {
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== "tab-" + name));
    if (name === "memory") loadMemories();
    if (name === "reminders") loadReminders();
  }

  function fillVoices() {
    const sel = $("#set-voicename");
    const list = voices();
    sel.innerHTML = '<option value="">Automatic</option>' +
      list.map((v) => `<option value="${esc(v.name)}">${esc(v.name)} (${esc(v.lang)})</option>`).join("");
    sel.value = settings.voiceName;
  }

  async function loadMemories() {
    const ul = $("#memory-list");
    ul.innerHTML = '<li class="empty">Loading…</li>';
    try {
      const rows = await api("/api/memories");
      if (!rows.length) { ul.innerHTML = '<li class="empty">Nothing yet. Tell Jarvis about yourself and it will remember.</li>'; return; }
      ul.innerHTML = "";
      for (const m of rows.slice().reverse()) {
        const li = document.createElement("li");
        li.innerHTML = `<div><span class="cat">${esc(m.category)}</span>${esc(m.content)}</div><button>Remove</button>`;
        li.querySelector("button").onclick = async () => { await api("/api/memories/" + m.id, { method: "DELETE" }); li.remove(); };
        ul.appendChild(li);
      }
    } catch { ul.innerHTML = '<li class="empty">Couldn\'t load memories.</li>'; }
  }

  async function loadReminders() {
    const ul = $("#reminder-list");
    ul.innerHTML = '<li class="empty">Loading…</li>';
    try {
      const rows = await api("/api/reminders");
      if (!rows.length) { ul.innerHTML = '<li class="empty">No reminders set.</li>'; return; }
      ul.innerHTML = "";
      for (const r of rows) {
        const when = new Date(r.due_at).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
        const li = document.createElement("li");
        li.innerHTML = `<div><span class="cat">${esc(when)}${r.repeat !== "none" ? " · repeats " + esc(r.repeat) : ""}</span>${esc(r.text)}</div><button>Cancel</button>`;
        li.querySelector("button").onclick = async () => { await api("/api/reminders/" + r.id, { method: "DELETE" }); li.remove(); };
        ul.appendChild(li);
      }
    } catch { ul.innerHTML = '<li class="empty">Couldn\'t load reminders.</li>'; }
  }

  function bindSettings() {
    $("#open-settings").onclick = () => openSheet();
    $("#close-settings").onclick = closeSheet;
    $("#sheet-backdrop").onclick = closeSheet;
    document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => selectTab(b.dataset.tab)));

    $("#set-voice").checked = settings.voiceOn;
    $("#set-voice").onchange = (e) => { settings.voiceOn = e.target.checked; saveSettings(); if (!settings.voiceOn) stopSpeaking(); };
    $("#set-wake").checked = settings.wake;
    $("#set-wake").onchange = (e) => {
      const why = voiceUnavailable();
      if (e.target.checked && why) { e.target.checked = false; toast(why, 5000); return; }
      settings.wake = e.target.checked; saveSettings(); updateHint();
      if (settings.wake) startWake(); else pauseWake();
    };
    $("#set-lang").value = settings.lang;
    $("#set-lang").onchange = (e) => { settings.lang = e.target.value; saveSettings(); stopRec(); resumeWake(); };
    $("#set-voicename").onchange = (e) => { settings.voiceName = e.target.value; saveSettings(); };
    $("#set-rate").value = settings.rate; $("#rate-out").textContent = (+settings.rate).toFixed(2);
    $("#set-rate").oninput = (e) => { settings.rate = +e.target.value; $("#rate-out").textContent = settings.rate.toFixed(2); saveSettings(); };
    $("#test-voice").onclick = () => speak(`Good to be online, ${state.callMe}. All systems ready.`);
    fillVoices();
    if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = fillVoices;

    $("#enable-notify").onclick = enablePush;
    $("#test-notify").onclick = async () => {
      try {
        const r = await api("/api/push/test", { method: "POST" });
        toast(r.devices ? "Sent. It should pop up in a few seconds." : "No device is signed up yet. Tap the button above first.");
      } catch { toast("Couldn't reach Jarvis."); }
    };
    $("#new-convo").onclick = async () => {
      await api("/api/new", { method: "POST" });
      tx().innerHTML = ""; document.body.classList.remove("has-chat"); state.rendered.clear();
      closeSheet(); toast("Fresh conversation. Memories are kept.");
    };
    $("#logout").onclick = async () => {
      try { await api("/api/logout", { method: "POST" }); } catch {}
      lockLocal();
    };
  }

  function b64ToBytes(b64) {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }

  async function enablePush() {
    if (isIOS && !installed) {
      toast("On iPhone, first tap Share → Add to Home Screen, open Jarvis from there, then try again.", 7000);
      return;
    }
    if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      toast("This browser can't receive notifications. Try Chrome on Android or the Home Screen app on iPhone.", 6000);
      return;
    }
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { toast("Notifications were not allowed. You can allow them in the browser's site settings.", 6000); return; }
    try {
      const reg = await navigator.serviceWorker.ready;
      const { key } = await api("/api/push/key");
      let sub = await reg.pushManager.getSubscription();
      if (sub) {
        const current = sub.options && sub.options.applicationServerKey;
        const same = current && btoa(String.fromCharCode(...new Uint8Array(current))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") === key;
        if (!same) { await sub.unsubscribe(); sub = null; }
      }
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
      await api("/api/push/subscribe", { method: "POST", body: { subscription: sub.toJSON(), device: device() } });
      store.set("jv_push", true);
      toast("Done. Reminders will reach this phone even when Jarvis is closed.", 5000);
    } catch (e) {
      toast("Couldn't turn on notifications: " + (e.message || e), 6000);
    }
  }

  // Keep this device's notification sign-up fresh (phones sometimes renew it).
  async function refreshPush() {
    if (!store.get("jv_push", false) || !("serviceWorker" in navigator) || Notification.permission !== "granted") return;
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) await api("/api/push/subscribe", { method: "POST", body: { subscription: sub.toJSON(), device: device() } });
    } catch {}
  }

  function updateHint() {
    $("#hint").textContent = settings.wake
      ? `Say "${state.name}" and then what you need.`
      : "Tap the mic and talk, or type below.";
  }

  // ------------------------------------------------------------------ boot
  function lockLocal() {
    state.token = ""; store.del("jv_token"); stopRec(); stopSpeaking();
    $("#main").hidden = true; $("#login").hidden = false; closeSheet();
    setTimeout(() => $("#pin").focus(), 50);
  }

  async function enter() {
    const s = await api("/api/status?tz=" + encodeURIComponent(TZ));
    state.name = s.name || "Jarvis"; state.callMe = s.call_me || "sir";
    document.title = state.name;
    $("#name").textContent = state.name;
    $("#input").placeholder = `Ask or tell ${state.name} anything`;
    $("#about").textContent = `Brain: ${s.model}. Running ${s.cloud ? "in the cloud" : "on your PC"}. ` +
      `Risky actions ${s.auto_approve ? "run automatically" : "ask for your OK first"}.`;
    if (state.lastNote === null) { state.lastNote = s.last_notification; store.set("jv_last_note", state.lastNote); }
    $("#login").hidden = true; $("#main").hidden = false;
    updateHint();

    tx().innerHTML = ""; state.rendered.clear();
    const hist = await api("/api/history");
    for (const h of hist) {
      if (h.kind === "system") { const n = systemNote(h.text); if (n) addMsg("note", n); continue; }
      addMsg(h.role, h.text, { sources: h.sources });
    }
    renderPending(s.pending);
    if (!hist.length) document.body.classList.remove("has-chat");
    poll();
    refreshPush();
    resumeWake();
  }

  $("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    $("#login-error").textContent = "";
    // Unlock speech on mobile: it must start from a tap.
    if ("speechSynthesis" in window) { const u = new SpeechSynthesisUtterance(""); u.volume = 0; speechSynthesis.speak(u); }
    try {
      const r = await api("/api/login", { method: "POST", body: { pin: $("#pin").value, device: device() } });
      state.token = r.token; store.set("jv_token", r.token); $("#pin").value = "";
      await enter();
    } catch (err) {
      $("#login-error").textContent = err.message === "Failed to fetch" ? "Can't reach Jarvis. Is the PC on?" : err.message;
    }
  };

  $("#composer").onsubmit = (e) => { e.preventDefault(); send($("#input").value); };
  $("#mic").onclick = startTalk;
  $("#presence").onclick = () => { if (state.speaking) stopSpeaking(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeSheet(); stopSpeaking(); } });

  bindSettings();
  setInterval(poll, 10000);
  if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("/sw.js").catch(() => {});

  if (state.token) enter().catch((e) => { if (e.message !== "login") { $("#login").hidden = false; $("#login-error").textContent = "Can't reach Jarvis. Is the PC on?"; } });
  else lockLocal();
})();
