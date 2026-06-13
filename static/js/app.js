// ── API helpers ─────────────────────────────────────────────
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...opts,
  });
  if (!res.ok) {
    let err = "Request failed";
    try { err = (await res.json()).error || err; } catch {}
    throw new Error(err);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Date helpers ─────────────────────────────────────────────
function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function today() { return isoDate(new Date()); }
function mondayOf(d) {
  const x = new Date(d);
  const day = x.getDay(); // 0=Sun..6=Sat
  const diff = (day === 0 ? -6 : 1 - day);
  x.setDate(x.getDate() + diff);
  x.setHours(0, 0, 0, 0);
  return x;
}
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function formatDay(d) {
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}
function formatDayShort(d) {
  return d.toLocaleDateString(undefined, { weekday: "short" });
}
function formatRange(start, end) {
  const opts = { month: "short", day: "numeric" };
  return `${start.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(undefined, opts)}`;
}

// ── State ─────────────────────────────────────────────
const state = {
  user: null,
  activities: [],
  weekStart: mondayOf(new Date()),
};

// ── Auth UI ─────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

function switchAuthTab(name) {
  $$("[data-auth-tab]").forEach(t => t.classList.toggle("active", t.dataset.authTab === name));
  $("#login-form").classList.toggle("hidden", name !== "login");
  $("#register-form").classList.toggle("hidden", name !== "register");
}

$$("[data-auth-tab]").forEach(t => t.addEventListener("click", () => switchAuthTab(t.dataset.authTab)));

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    const user = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#login-username").value,
        password: $("#login-password").value,
      }),
    });
    state.user = user;
    enterApp();
  } catch (e) { $("#login-error").textContent = e.message; }
});

$("#register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#register-error").textContent = "";
  try {
    const user = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: $("#register-username").value,
        password: $("#register-password").value,
      }),
    });
    state.user = user;
    enterApp();
  } catch (e) { $("#register-error").textContent = e.message; }
});

$("#logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  state.user = null;
  show($("#auth-screen"));
  hide($("#app-screen"));
});

// ── Passkeys ─────────────────────────────────────────────
function b64urlToBuf(s) {
  const pad = "=".repeat((4 - s.length % 4) % 4);
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}
function bufToB64url(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

$("#passkey-add-btn").addEventListener("click", async () => {
  try {
    const opts = await api("/api/auth/webauthn/register-options", { method: "POST" });
    opts.challenge = b64urlToBuf(opts.challenge);
    opts.user.id = b64urlToBuf(opts.user.id);
    if (opts.excludeCredentials) opts.excludeCredentials.forEach(c => c.id = b64urlToBuf(c.id));
    const cred = await navigator.credentials.create({ publicKey: opts });
    const payload = {
      id: cred.id,
      rawId: bufToB64url(cred.rawId),
      type: cred.type,
      response: {
        attestationObject: bufToB64url(cred.response.attestationObject),
        clientDataJSON: bufToB64url(cred.response.clientDataJSON),
      },
    };
    await api("/api/auth/webauthn/register-verify", { method: "POST", body: JSON.stringify(payload) });
    alert("Passkey added!");
  } catch (e) { alert("Couldn't add passkey: " + e.message); }
});

$("#passkey-login-btn").addEventListener("click", async () => {
  $("#login-error").textContent = "";
  try {
    const username = $("#login-username").value.trim();
    const opts = await api("/api/auth/webauthn/login-options", {
      method: "POST",
      body: JSON.stringify({ username }),
    });
    opts.challenge = b64urlToBuf(opts.challenge);
    if (opts.allowCredentials) opts.allowCredentials.forEach(c => c.id = b64urlToBuf(c.id));
    const cred = await navigator.credentials.get({ publicKey: opts });
    const payload = {
      id: cred.id,
      rawId: bufToB64url(cred.rawId),
      type: cred.type,
      response: {
        authenticatorData: bufToB64url(cred.response.authenticatorData),
        clientDataJSON: bufToB64url(cred.response.clientDataJSON),
        signature: bufToB64url(cred.response.signature),
        userHandle: cred.response.userHandle ? bufToB64url(cred.response.userHandle) : null,
      },
    };
    const user = await api("/api/auth/webauthn/login-verify", { method: "POST", body: JSON.stringify(payload) });
    state.user = user;
    enterApp();
  } catch (e) { $("#login-error").textContent = e.message || "Passkey sign-in failed"; }
});

// ── App tabs ─────────────────────────────────────────────
$$(".nav-tab").forEach(t => t.addEventListener("click", () => {
  const name = t.dataset.tab;
  $$(".nav-tab").forEach(x => x.classList.toggle("active", x === t));
  $$(".tab-panel").forEach(p => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "today") renderToday();
  if (name === "week") renderWeek();
  if (name === "activities") renderActivitiesManage();
}));

async function enterApp() {
  hide($("#auth-screen"));
  show($("#app-screen"));
  $("#user-name").textContent = state.user.username;
  await loadActivities();
  await renderToday();
}

// ── Activities ─────────────────────────────────────────────
async function loadActivities() {
  state.activities = await api("/api/activities");
}

// ── Today ─────────────────────────────────────────────
async function renderToday() {
  const date = today();
  const d = new Date();
  $("#today-date-label").textContent = formatDay(d);

  const week = await api(`/api/week?start=${isoDate(mondayOf(d))}`);
  const todayDay = week.days.find(x => x.date === date);
  const total = todayDay ? todayDay.points : 0;

  const totalEl = $("#today-total");
  totalEl.textContent = total > 0 ? `+${total}` : total;
  totalEl.classList.toggle("pos", total > 0);
  totalEl.classList.toggle("neg", total < 0);

  // Activity tap list
  const listEl = $("#today-activities");
  const active = state.activities.filter(a => !a.is_archived);
  if (active.length === 0) {
    listEl.innerHTML = `<div class="empty">No activities yet. Add some on the Activities tab.</div>`;
  } else {
    listEl.innerHTML = active.map(a => `
      <div class="activity-row">
        <div class="name">${escapeHtml(a.name)}</div>
        <div class="pts ${a.points >= 0 ? "pos" : "neg"}">${a.points >= 0 ? "+" : ""}${a.points}</div>
        <button class="log-btn" data-log="${a.id}">+</button>
      </div>
    `).join("");
    listEl.querySelectorAll("[data-log]").forEach(btn => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await api("/api/completions", {
            method: "POST",
            body: JSON.stringify({ activity_id: Number(btn.dataset.log), date }),
          });
          await renderToday();
        } catch (e) { alert(e.message); btn.disabled = false; }
      });
    });
  }

  // Today's log entries (most recent first)
  const logEl = $("#today-log");
  const comps = todayDay ? [...todayDay.completions].reverse() : [];
  if (comps.length === 0) {
    logEl.innerHTML = `<div class="empty">Nothing logged yet today.</div>`;
  } else {
    logEl.innerHTML = comps.map(c => `
      <div class="log-row">
        <div class="log-name">${escapeHtml(c.activity_name)}</div>
        <div class="log-pts ${c.points >= 0 ? "pos" : "neg"}">${c.points >= 0 ? "+" : ""}${c.points}</div>
        <button class="undo-btn" data-undo="${c.id}" title="Undo">×</button>
      </div>
    `).join("");
    logEl.querySelectorAll("[data-undo]").forEach(btn => {
      btn.addEventListener("click", async () => {
        await api(`/api/completions/${btn.dataset.undo}`, { method: "DELETE" });
        await renderToday();
      });
    });
  }
}

// ── Week ─────────────────────────────────────────────
async function renderWeek() {
  const start = state.weekStart;
  const end = addDays(start, 6);
  $("#week-range").textContent = formatRange(start, end);

  const week = await api(`/api/week?start=${isoDate(start)}`);
  const total = week.total;
  const totalEl = $("#week-total");
  totalEl.textContent = total > 0 ? `+${total}` : total;
  totalEl.classList.toggle("pos", total > 0);
  totalEl.classList.toggle("neg", total < 0);

  const todayStr = today();
  const grid = $("#week-grid");
  grid.innerHTML = week.days.map((day, i) => {
    const d = addDays(start, i);
    const isToday = day.date === todayStr;
    const cls = day.points > 0 ? "pos" : day.points < 0 ? "neg" : "zero";
    const sign = day.points > 0 ? "+" : "";
    const detail = day.completions.length === 0
      ? `<div class="empty">No activity</div>`
      : day.completions.map(c => `
          <div class="log-row">
            <div class="log-name">${escapeHtml(c.activity_name)}</div>
            <div class="log-pts ${c.points >= 0 ? "pos" : "neg"}">${c.points >= 0 ? "+" : ""}${c.points}</div>
          </div>
        `).join("");
    return `
      <div class="day-row ${isToday ? "today" : ""}" data-day="${i}">
        <div class="day-row-head">
          <div>
            <span class="day-row-name">${formatDayShort(d)}</span>
            <span class="day-row-date">${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
          </div>
          <div class="day-row-points ${cls}">${sign}${day.points}</div>
        </div>
        <div class="day-row-detail">${detail}</div>
      </div>
    `;
  }).join("");

  grid.querySelectorAll(".day-row").forEach(row => {
    row.querySelector(".day-row-head").addEventListener("click", () => {
      row.classList.toggle("expanded");
    });
  });
}

$("#week-prev").addEventListener("click", () => {
  state.weekStart = addDays(state.weekStart, -7);
  renderWeek();
});
$("#week-next").addEventListener("click", () => {
  state.weekStart = addDays(state.weekStart, 7);
  renderWeek();
});

// ── Manage activities ─────────────────────────────────────────────
async function renderActivitiesManage() {
  const includeArchived = $("#show-archived").checked;
  const list = includeArchived
    ? await api("/api/activities?include_archived=true")
    : state.activities;

  const el = $("#activities-list");
  if (list.length === 0) {
    el.innerHTML = `<div class="empty">No activities yet.</div>`;
    return;
  }
  el.innerHTML = list.map(a => `
    <div class="manage-row ${a.is_archived ? "archived" : ""}" data-id="${a.id}">
      <input type="text" class="edit-name" value="${escapeHtml(a.name)}" />
      <input type="number" class="edit-points" value="${a.points}" />
      <button class="small-btn save-btn">Save</button>
      <button class="small-btn ${a.is_archived ? "" : ""}">${a.is_archived ? "Unarchive" : "Archive"}</button>
      <button class="small-btn danger delete-btn">Delete</button>
    </div>
  `).join("");

  el.querySelectorAll(".manage-row").forEach(row => {
    const id = Number(row.dataset.id);
    row.querySelector(".save-btn").addEventListener("click", async () => {
      const name = row.querySelector(".edit-name").value;
      const points = Number(row.querySelector(".edit-points").value);
      await api(`/api/activities/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name, points }),
      });
      await loadActivities();
      await renderActivitiesManage();
    });
    const archiveBtn = row.querySelectorAll(".small-btn")[1];
    archiveBtn.addEventListener("click", async () => {
      const isArchived = archiveBtn.textContent.trim() === "Unarchive";
      await api(`/api/activities/${id}`, {
        method: "PUT",
        body: JSON.stringify({ is_archived: !isArchived }),
      });
      await loadActivities();
      await renderActivitiesManage();
    });
    row.querySelector(".delete-btn").addEventListener("click", async () => {
      if (!confirm("Delete this activity and all its completions?")) return;
      await api(`/api/activities/${id}`, { method: "DELETE" });
      await loadActivities();
      await renderActivitiesManage();
    });
  });
}

$("#new-activity-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#new-activity-name").value;
  const points = Number($("#new-activity-points").value);
  await api("/api/activities", {
    method: "POST",
    body: JSON.stringify({ name, points }),
  });
  $("#new-activity-name").value = "";
  $("#new-activity-points").value = "";
  await loadActivities();
  await renderActivitiesManage();
});

$("#show-archived").addEventListener("change", renderActivitiesManage);

// ── Utils ─────────────────────────────────────────────
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ── Boot ─────────────────────────────────────────────
(async function boot() {
  try {
    const user = await api("/api/auth/me");
    state.user = user;
    enterApp();
  } catch {
    show($("#auth-screen"));
    hide($("#app-screen"));
  }
})();
