/* ═══════════════════════════════════════════════════════════════════════════
   VAAS — Frontend Runtime  (Sprint 11)
   • Global toast notification system
   • SSE listener: gate events, exceptions, rejections, dispositions
   • Gate stream border animations (idle / open / alert / rejected)
   • Exception disposition: Admit / Reject / Register
   • Web Audio API ping on new exception
   • UTC clock + live stat counters
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Toast system (global — available on all pages) ────────────────────────── */
window.showToast = function (message, type /* 'success'|'error'|'warning'|'info' */) {
  type = type || 'info';
  const stack = document.getElementById('toast-stack');
  if (!stack) return;

  const icons = {
    success: 'bi-check-circle-fill',
    error:   'bi-x-circle-fill',
    warning: 'bi-exclamation-triangle-fill',
    info:    'bi-info-circle-fill',
  };

  const el = document.createElement('div');
  el.className = `vaas-toast toast-${type}`;
  el.innerHTML = `
    <i class="bi ${icons[type] || icons.info} vaas-toast-icon"></i>
    <div class="vaas-toast-body">${message}</div>
    <button class="vaas-toast-close" aria-label="Close">
      <i class="bi bi-x"></i>
    </button>`;

  el.querySelector('.vaas-toast-close').addEventListener('click', () => dismissToast(el));
  stack.appendChild(el);

  setTimeout(() => dismissToast(el), 5000);
};

function dismissToast(el) {
  if (!el.parentNode) return;
  el.classList.add('toast-out');
  setTimeout(() => el.remove(), 200);
}

/* ─────────────────────────────────────────────────────────────────────────── */
/* Operator dashboard — only runs when the events table is present            */
/* ─────────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  const eventsBody = document.getElementById("events-table")?.querySelector("tbody");
  if (!eventsBody) return;   // not on the operator dashboard

  /* ── DOM refs ───────────────────────────────────────────────────────────── */
  const exceptBody    = document.getElementById("exceptions-table").querySelector("tbody");
  const excCountBadge = document.getElementById("exc-count-badge");
  const excEmpty      = document.getElementById("exc-empty");
  const statToday     = document.getElementById("stat-today");
  const statExc       = document.getElementById("stat-exceptions");
  const statSession   = document.getElementById("stat-session");
  const sseStatus     = document.getElementById("sse-status");
  const sseLabel      = document.getElementById("sse-label");
  const clockEl       = document.getElementById("clock");

  /* ── State ──────────────────────────────────────────────────────────────── */
  const MAX_ROWS   = 20;
  let sessionEvts  = 0;
  let pendingCount = parseInt(excCountBadge?.textContent || "0", 10);

  /* ── Web Audio ping ─────────────────────────────────────────────────────── */
  let audioCtx = null;
  function playPing() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc  = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0, audioCtx.currentTime);
      gain.gain.linearRampToValueAtTime(0.18, audioCtx.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
      osc.start(audioCtx.currentTime);
      osc.stop(audioCtx.currentTime + 0.25);
    } catch (_) { /* non-fatal */ }
  }

  /* ── Gate status management ─────────────────────────────────────────────── */
  const wrappers = {
    GATE_A: document.getElementById("wrapper-GATE_A"),
    GATE_B: document.getElementById("wrapper-GATE_B"),
  };
  const badges = {
    GATE_A: document.getElementById("badge-GATE_A"),
    GATE_B: document.getElementById("badge-GATE_B"),
  };
  const gateTimers = {};
  const STATUS_CLASSES = ["gate-idle", "gate-open", "gate-alert", "gate-rejected"];

  function setGateStatus(gateId, cls, icon, text, autoresetMs) {
    const w = wrappers[gateId];
    const b = badges[gateId];
    if (!w || !b) return;
    w.classList.remove(...STATUS_CLASSES);
    void w.offsetWidth;               // force reflow → restart CSS animation
    w.classList.add(cls);
    b.innerHTML = `<i class="bi ${icon}"></i> ${text}`;
    clearTimeout(gateTimers[gateId]);
    if (autoresetMs) {
      gateTimers[gateId] = setTimeout(() => {
        w.classList.remove(...STATUS_CLASSES);
        w.classList.add("gate-idle");
        b.innerHTML = `<i class="bi bi-circle"></i> IDLE`;
      }, autoresetMs);
    }
  }

  /* ── Status badge HTML ──────────────────────────────────────────────────── */
  const OK_STATUSES      = ["ON_TIME_ENTRY", "ON_TIME_EXIT", "VISITOR_ADMITTED"];
  const BAD_STATUSES     = ["SUSPENDED", "EXPIRED", "VISITOR_REJECTED", "VISITOR_TIMEOUT_REJECT"];
  const LATE_STATUSES    = ["LATE_ARRIVAL", "EARLY_DEPARTURE", "EARLY_ARRIVAL"];
  const VIS_STATUSES     = ["VISITOR"];
  const ANOMALY_STATUSES = ["DOUBLE_ENTRY", "UNMATCHED_EXIT"];

  function statusBadge(s) {
    let cls = "bs-default";
    if (OK_STATUSES.includes(s))                      cls = "bs-ok";
    else if (BAD_STATUSES.includes(s))                cls = "bs-rejected";
    else if (LATE_STATUSES.includes(s))               cls = "bs-late";
    else if (VIS_STATUSES.some(v => s.startsWith(v))) cls = "bs-visitor";
    else if (ANOMALY_STATUSES.includes(s))            cls = "bs-anomaly";
    return `<span class="badge-status ${cls}">${s.replace(/_/g, " ")}</span>`;
  }

  /* ── Confidence bar HTML ────────────────────────────────────────────────── */
  function confBar(conf) {
    const pct = Math.round((conf || 0) * 100);
    const color = pct >= 80 ? 'var(--green)' : pct >= 60 ? 'var(--amber)' : 'var(--red)';
    return `<div class="conf-bar">
      <div class="conf-bar-track">
        <div class="conf-bar-fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <span class="conf-pct">${pct}%</span>
    </div>`;
  }

  /* ── UTC clock ──────────────────────────────────────────────────────────── */
  function tickClock() {
    if (clockEl) clockEl.textContent = new Date().toUTCString().slice(17, 25);
  }
  tickClock();
  setInterval(tickClock, 1000);

  /* ── Live Events table: poll /api/recent every 4 s ─────────────────────── */
  // This is the primary refresh path for the gate events table.
  // SSE also pushes gate_event messages (which call prependEventRow directly)
  // but polling guarantees the table is current even when SSE reconnects.
  let _lastSeenId = 0;

  function refreshEventsTable() {
    fetch("/api/recent")
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(rows => {
        if (!rows || !rows.length) return;

        // Update today-counter with full dataset length
        if (statToday) statToday.textContent = rows.length;

        // Find the newest row id we haven't rendered yet
        const newRows = rows.filter(r => r.id > _lastSeenId);
        if (!newRows.length) return;

        // Prepend new rows newest-first (they arrive newest-first from the API)
        newRows.forEach(evt => {
          const ts  = (evt.timestamp || "").slice(11, 19);
          const dir = evt.direction === "ENTRY"
            ? `<span class="text-green"><i class="bi bi-arrow-up-right"></i> ENTRY</span>`
            : `<span class="text-accent"><i class="bi bi-arrow-down-left"></i> EXIT</span>`;
          const tr = document.createElement("tr");
          tr.className = "flash-new";
          tr.dataset.id = evt.id;
          tr.innerHTML =
            `<td style="color:var(--text-muted);font-family:var(--font-mono);font-size:.75rem">${ts}</td>` +
            `<td class="plate-cell">${evt.plate_number ?? "—"}</td>` +
            `<td style="color:var(--text-secondary)">${evt.gate_id ?? ""}</td>` +
            `<td>${dir}</td>` +
            `<td>${statusBadge(evt.status ?? "")}</td>` +
            `<td>${confBar(evt.confidence_score)}</td>`;
          eventsBody.prepend(tr);
          sessionEvts++;
        });

        // Update watermark and trim table
        _lastSeenId = rows[0].id;
        while (eventsBody.rows.length > MAX_ROWS) eventsBody.deleteRow(eventsBody.rows.length - 1);
        if (statSession) statSession.textContent = sessionEvts;

        // Flash gate border for the most recent event
        const latest = newRows[0];
        if (latest) {
          const gId = latest.gate_id;
          const s   = latest.status ?? "";
          if (OK_STATUSES.includes(s))
            setGateStatus(gId, "gate-open",     "bi-unlock-fill",         "OPEN",        4000);
          else if (LATE_STATUSES.includes(s))
            setGateStatus(gId, "gate-open",     "bi-exclamation",         "OPEN / LATE", 4000);
          else if (BAD_STATUSES.includes(s))
            setGateStatus(gId, "gate-rejected", "bi-x-circle-fill",       "DENIED",      5000);
          else if (ANOMALY_STATUSES.includes(s))
            setGateStatus(gId, "gate-alert",    "bi-exclamation-diamond", "ANOMALY",     6000);
        }
      })
      .catch(() => {});
  }

  // Seed _lastSeenId from the initial server-rendered rows (if any)
  (function seedLastSeenId() {
    const firstRow = eventsBody.querySelector("tr");
    if (!firstRow) return;
    // The server renders rows newest-first; first <tr> has the highest id.
    // We use a data attribute written by the template if available, otherwise
    // fall back to counting existing rows as the baseline.
    // Since the template doesn't stamp row ids, just mark that we've already
    // seen whatever was on page load so we only flash TRULY new events.
    fetch("/api/recent")
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(rows => { if (rows && rows.length) _lastSeenId = rows[0].id; })
      .catch(() => {});
  })();

  // Poll every 4 seconds
  setInterval(refreshEventsTable, 4000);

  /* ── Exception counter ──────────────────────────────────────────────────── */
  function updateExcCount(delta) {
    pendingCount = Math.max(0, pendingCount + delta);
    if (excCountBadge) {
      excCountBadge.textContent = pendingCount;
      excCountBadge.style.display = pendingCount ? "inline-flex" : "none";
    }
    if (statExc) statExc.textContent = pendingCount;
    if (excEmpty) excEmpty.style.display = pendingCount ? "none" : "flex";
  }

  /* ── Prepend row to live events table ───────────────────────────────────── */
  function prependEventRow(evt) {
    const ts  = (evt.timestamp || "").slice(11, 19);
    const dir = evt.direction === "ENTRY"
      ? `<span class="text-green"><i class="bi bi-arrow-up-right"></i> ENTRY</span>`
      : `<span class="text-accent"><i class="bi bi-arrow-down-left"></i> EXIT</span>`;
    const tr = document.createElement("tr");
    tr.className = "flash-new";
    tr.dataset.id = evt.id ?? evt.access_log_id ?? "";
    tr.innerHTML =
      `<td style="color:var(--text-muted);font-family:var(--font-mono);font-size:.75rem">${ts}</td>` +
      `<td class="plate-cell">${evt.plate ?? evt.plate_number ?? "—"}</td>` +
      `<td style="color:var(--text-secondary)">${evt.gate ?? evt.gate_id ?? ""}</td>` +
      `<td>${dir}</td>` +
      `<td>${statusBadge(evt.status ?? "")}</td>` +
      `<td>${confBar(evt.confidence)}</td>`;
    eventsBody.prepend(tr);
    while (eventsBody.rows.length > MAX_ROWS) eventsBody.deleteRow(eventsBody.rows.length - 1);
    sessionEvts++;
    if (statSession) statSession.textContent = sessionEvts;
    if (statToday)   statToday.textContent   = parseInt(statToday.textContent || "0", 10) + 1;
  }

  /* ── Add row to exception queue ─────────────────────────────────────────── */
  function addExceptionRow(evt) {
    const ts  = (evt.timestamp || "").slice(11, 19);
    const pct = Math.round((evt.confidence || 0) * 100);
    const tr  = document.createElement("tr");
    tr.dataset.id = evt.id;
    tr.className  = "flash-new";
    tr.innerHTML =
      `<td style="color:var(--text-muted);font-family:var(--font-mono);font-size:.75rem">${ts}</td>` +
      `<td><span class="plate-lg">${evt.raw_plate ?? evt.plate_number ?? "—"}</span></td>` +
      `<td style="color:var(--text-secondary)">${evt.gate ?? evt.gate_id ?? ""}</td>` +
      `<td><span style="font-family:var(--font-mono);color:var(--text-muted);font-size:.8rem">${pct}%</span></td>` +
      `<td>
         <div class="exc-actions">
           <button class="btn-admit dispose"    data-action="ADMIT">
             <i class="bi bi-check-lg"></i> Admit
           </button>
           <button class="btn-reject dispose"   data-action="REJECT">
             <i class="bi bi-x-lg"></i> Reject
           </button>
           <button class="btn-register dispose" data-action="REGISTER">
             <i class="bi bi-person-plus"></i> Register
           </button>
         </div>
       </td>`;
    exceptBody.prepend(tr);
    updateExcCount(+1);
    playPing();
  }

  function removeExceptionRow(id) {
    const tr = exceptBody.querySelector(`tr[data-id="${id}"]`);
    if (tr) { tr.remove(); updateExcCount(-1); }
  }

  /* ── SSE connection ─────────────────────────────────────────────────────── */
  let evtSource = null;

  function connectSSE() {
    evtSource = new EventSource("/operator/sse");

    evtSource.onopen = function () {
      sseStatus?.classList.add("connected");
      sseStatus?.classList.remove("error");
      if (sseLabel) sseLabel.textContent = "Live";
    };

    evtSource.onmessage = function (e) {
      let evt;
      try { evt = JSON.parse(e.data); } catch { return; }
      const gateId = evt.gate ?? evt.gate_id;

      if (evt.type === "gate_event") {
        prependEventRow(evt);
        const s = evt.status ?? "";
        if (OK_STATUSES.includes(s))
          setGateStatus(gateId, "gate-open",     "bi-unlock-fill",         "OPEN",        4000);
        else if (LATE_STATUSES.includes(s))
          setGateStatus(gateId, "gate-open",     "bi-exclamation",         "OPEN / LATE", 4000);
        else if (BAD_STATUSES.includes(s))
          setGateStatus(gateId, "gate-rejected", "bi-x-circle-fill",       "DENIED",      5000);
        else if (ANOMALY_STATUSES.includes(s))
          setGateStatus(gateId, "gate-alert",    "bi-exclamation-diamond", "ANOMALY",     6000);
      }

      if (evt.type === "exception") {
        addExceptionRow(evt);
        setGateStatus(gateId, "gate-alert", "bi-exclamation-triangle-fill", "EXCEPTION", 0);
      }

      if (evt.type === "rejection") {
        setGateStatus(gateId, "gate-rejected", "bi-x-circle-fill", "DENIED", 5000);
      }

      if (evt.type === "exception_disposed" || evt.type === "exception_timeout") {
        removeExceptionRow(evt.id);

        // Update the status badge in the Live Gate Events table for the same row
        const evtRow = eventsBody.querySelector(`tr[data-id="${evt.id}"]`);
        if (evtRow) {
          const statusCell = evtRow.cells[4];   // 0:time 1:plate 2:gate 3:dir 4:status 5:conf
          if (statusCell) {
            const newStatus = evt.type === "exception_timeout"
              ? "VISITOR_TIMEOUT_REJECT"
              : (evt.new_status || "");
            if (newStatus) statusCell.innerHTML = statusBadge(newStatus);
          }
        }

        if (pendingCount === 0) setGateStatus(gateId, "gate-idle", "bi-circle", "IDLE", 0);
      }
    };

    evtSource.onerror = function () {
      sseStatus?.classList.remove("connected");
      sseStatus?.classList.add("error");
      if (sseLabel) sseLabel.textContent = "Reconnecting…";
      evtSource.close();
      setTimeout(connectSSE, 3000);
    };
  }

  connectSSE();

  /* ── Exception disposition (delegated click) ────────────────────────────── */
  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".dispose");
    if (!btn) return;
    const tr = btn.closest("tr[data-id]");
    if (!tr)  return;

    const id     = tr.dataset.id;
    const action = btn.dataset.action;

    tr.querySelectorAll(".dispose").forEach(b => (b.disabled = true));
    btn.innerHTML = `<i class="bi bi-hourglass-split"></i>`;

    fetch(`/operator/exception/${id}/dispose`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ disposition: action }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.redirect) {
          window.location.href = data.redirect;
        } else {
          removeExceptionRow(id);
          const labels = { ADMIT: "Admitted", REJECT: "Rejected", REGISTER: "Registered" };
          const types  = { ADMIT: "success",  REJECT: "error",    REGISTER: "warning" };
          showToast(`Exception ${labels[action] || action} successfully.`, types[action] || "info");
        }
      })
      .catch(() => {
        tr.querySelectorAll(".dispose").forEach(b => (b.disabled = false));
        btn.innerHTML = action;
        showToast("Disposition request failed — check server logs.", "error");
      });
  });

})();
