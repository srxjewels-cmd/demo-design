/* DM Assistant dashboard — vanilla JS, no build step. */

const $ = (sel, el = document) => el.querySelector(sel);

const loginView = $("#login-view");
const appView = $("#app-view");
const inboxList = $("#inbox-list");
const historyList = $("#history-list");
const inboxEmpty = $("#inbox-empty");
const inboxCount = $("#inbox-count");
const connDot = $("#conn-dot");

let vapidPublicKey = null;

/* ── boot ── */
(async function boot() {
  if ("serviceWorker" in navigator) {
    try { await navigator.serviceWorker.register("/sw.js"); } catch (_) {}
  }
  const me = await fetch("/api/me").then(r => r.json());
  vapidPublicKey = me.vapid_public_key;
  if (me.authenticated) enterApp();
  else loginView.classList.remove("hidden");
})();

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("#password").value }),
  });
  if (r.ok) { loginView.classList.add("hidden"); enterApp(); }
  else $("#login-error").classList.remove("hidden");
});

async function enterApp() {
  appView.classList.remove("hidden");
  await refreshState();
  connectSSE();
}

/* ── tabs ── */
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab-panel").forEach(p =>
      p.classList.toggle("hidden", p.id !== btn.dataset.tab));
  });
});

/* ── state ── */
async function refreshState() {
  const r = await fetch("/api/state");
  if (r.status === 401) { location.reload(); return; }
  const { pending, history } = await r.json();
  inboxList.innerHTML = "";
  pending.forEach(d => inboxList.appendChild(renderCard(d, false)));
  historyList.innerHTML = "";
  history.forEach(d => historyList.appendChild(renderCard(d, true)));
  updateEmpty();
}

function updateEmpty() {
  const n = inboxList.children.length;
  inboxEmpty.classList.toggle("hidden", n > 0);
  inboxCount.textContent = n;
  inboxCount.classList.toggle("hidden", n === 0);
}

/* ── card rendering ── */
function renderCard(d, isHistory) {
  const node = $("#card-template").content.firstElementChild.cloneNode(true);
  node.dataset.id = d.id;
  if (d.flagged) node.classList.add("flagged");

  const avatar = $(".avatar", node);
  if (d.profile_pic) avatar.src = d.profile_pic;
  else avatar.style.visibility = "hidden";

  $(".name", node).textContent = d.name || d.sender_id;
  $(".crm", node).textContent = d.crm_summary || "";
  $(".customer-msg", node).textContent = d.customer_message || "";
  $(".draft-text", node).textContent =
    (isHistory && d.final_text) ? d.final_text : d.draft_text;

  const flag = $(".flag", node);
  if (d.flagged) { flag.classList.remove("hidden"); flag.title = d.flag_reason || "review carefully"; }

  if (isHistory) {
    $(".actions", node).innerHTML =
      `<span class="status-chip status-${d.status}">${d.status}</span>`;
    return node;
  }

  const editBox = $(".draft-edit", node);
  const btns = {
    approve: $(".approve", node), edit: $(".edit", node), send: $(".send", node),
    cancel: $(".cancel", node), skip: $(".skip", node),
  };

  const setBusy = (busy) => Object.values(btns).forEach(b => b.disabled = busy);

  btns.approve.addEventListener("click", async () => {
    setBusy(true);
    const ok = await act(d.id, "approve");
    if (!ok) setBusy(false);
  });

  btns.edit.addEventListener("click", () => {
    editBox.value = d.draft_text;
    editBox.classList.remove("hidden");
    $(".draft-text", node).classList.add("hidden");
    btns.approve.classList.add("hidden");
    btns.edit.classList.add("hidden");
    btns.send.classList.remove("hidden");
    btns.cancel.classList.remove("hidden");
    editBox.focus();
  });

  btns.cancel.addEventListener("click", () => {
    editBox.classList.add("hidden");
    $(".draft-text", node).classList.remove("hidden");
    btns.approve.classList.remove("hidden");
    btns.edit.classList.remove("hidden");
    btns.send.classList.add("hidden");
    btns.cancel.classList.add("hidden");
  });

  btns.send.addEventListener("click", async () => {
    setBusy(true);
    const ok = await act(d.id, "edit", { text: editBox.value });
    if (!ok) setBusy(false);
  });

  btns.skip.addEventListener("click", async () => {
    setBusy(true);
    const ok = await act(d.id, "skip");
    if (!ok) setBusy(false);
  });

  return node;
}

async function act(id, action, body) {
  const r = await fetch(`/api/drafts/${id}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert(err.detail || `Action failed (${r.status})`);
    if (r.status === 409) refreshState();
    return false;
  }
  return true;
}

/* ── live updates (SSE) ── */
function connectSSE() {
  const es = new EventSource("/api/events");
  es.onopen = () => connDot.classList.add("live");
  es.onerror = () => connDot.classList.remove("live");
  es.onmessage = (e) => {
    const { type, data } = JSON.parse(e.data);
    if (type === "draft") {
      inboxList.prepend(renderCard(data, false));
      updateEmpty();
    } else if (type === "resolved") {
      const card = inboxList.querySelector(`[data-id="${data.id}"]`);
      if (card) card.remove();
      updateEmpty();
      refreshHistory();
    }
  };
}

async function refreshHistory() {
  const r = await fetch("/api/state");
  if (!r.ok) return;
  const { history } = await r.json();
  historyList.innerHTML = "";
  history.forEach(d => historyList.appendChild(renderCard(d, true)));
}

/* ── push notifications ── */
$("#notify-btn").addEventListener("click", async () => {
  if (!("Notification" in window) || !("serviceWorker" in navigator)) {
    alert("Push not supported in this browser. On iOS, add the app to your home screen first.");
    return;
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlB64ToUint8Array(vapidPublicKey),
  });
  const r = await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub.toJSON()),
  });
  $("#notify-btn").textContent = r.ok ? "🔕" : "🔔";
  if (r.ok) alert("Push notifications enabled ✔");
});

function urlB64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}
