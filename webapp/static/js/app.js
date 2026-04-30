/* VAAS — operator dashboard SSE listener + exception disposition */

(function () {
  "use strict";

  /* ------------------------------------------------------------------ *
   * SSE listener — only active on the operator dashboard               *
   * ------------------------------------------------------------------ */
  const eventsBody = document.getElementById("events-table")?.querySelector("tbody");
  const exceptBody = document.getElementById("exceptions-table")?.querySelector("tbody");
  const statusA = document.getElementById("status-a");
  const statusB = document.getElementById("status-b");

  if (!eventsBody) return;   // not on dashboard — nothing to do

  const MAX_ROWS = 20;

  function setGateStatus(gateId, cssClass, text) {
    const el = gateId === "GATE_A" ? statusA : statusB;
    if (!el) return;
    el.className = "gate-status " + cssClass;
    el.textContent = text;
    // auto-reset to IDLE after 4 seconds
    clearTimeout(el._timer);
    el._timer = setTimeout(() => {
      el.className = "gate-status status-idle";
      el.textContent = "IDLE";
    }, 4000);
  }

  function prependEventRow(evt) {
    const tr = document.createElement("tr");
    tr.className = "flash-new";
    const conf = typeof evt.confidence === "number"
      ? evt.confidence.toFixed(2) : "—";
    tr.innerHTML =
      `<td>${evt.timestamp ?? ""}</td>` +
      `<td>${evt.plate ?? evt.plate_number ?? ""}</td>` +
      `<td>${evt.gate ?? evt.gate_id ?? ""}</td>` +
      `<td>${evt.direction ?? ""}</td>` +
      `<td><span class="badge bg-secondary">${evt.status ?? ""}</span></td>` +
      `<td>${conf}</td>`;
    eventsBody.prepend(tr);
    // Trim table to MAX_ROWS
    while (eventsBody.rows.length > MAX_ROWS) {
      eventsBody.deleteRow(eventsBody.rows.length - 1);
    }
  }

  function addExceptionRow(evt) {
    const tr = document.createElement("tr");
    tr.dataset.id = evt.id;
    tr.className = "flash-new";
    const conf = typeof evt.confidence === "number"
      ? evt.confidence.toFixed(2) : "—";
    tr.innerHTML =
      `<td>${evt.timestamp ?? ""}</td>` +
      `<td>${evt.raw_plate ?? evt.plate_number ?? ""}</td>` +
      `<td>${evt.gate ?? evt.gate_id ?? ""}</td>` +
      `<td>${conf}</td>` +
      `<td>
        <button class="btn btn-success btn-sm dispose" data-action="ADMIT">Admit</button>
        <button class="btn btn-danger  btn-sm dispose" data-action="REJECT">Reject</button>
        <button class="btn btn-warning btn-sm dispose" data-action="REGISTER">Register</button>
      </td>`;
    exceptBody.prepend(tr);
  }

  function removeExceptionRow(id) {
    const tr = exceptBody.querySelector(`tr[data-id="${id}"]`);
    if (tr) tr.remove();
  }

  /* ---- SSE connection ---- */
  const evtSource = new EventSource("/operator/sse");

  evtSource.onmessage = function (e) {
    let evt;
    try { evt = JSON.parse(e.data); } catch { return; }

    const type = evt.type;

    if (type === "gate_event") {
      prependEventRow(evt);
      const gateId = evt.gate ?? evt.gate_id;
      const status = evt.status ?? "";
      if (status === "ON_TIME_ENTRY" || status === "LATE_ARRIVAL" ||
          status === "EARLY_ARRIVAL" || status === "BARRIER_OPENED") {
        setGateStatus(gateId, "status-open", "OPEN ✓");
      } else if (status === "ON_TIME_EXIT" || status === "EARLY_DEPARTURE") {
        setGateStatus(gateId, "status-open", "EXIT ✓");
      }
    }

    if (type === "exception") {
      addExceptionRow(evt);
      setGateStatus(evt.gate ?? evt.gate_id, "status-alert", "! EXCEPTION");
    }

    if (type === "rejection") {
      setGateStatus(evt.gate, "status-closed", "REJECTED ✗");
    }

    if (type === "exception_disposed" || type === "exception_timeout") {
      removeExceptionRow(evt.id);
      if (evt.disposition === "ADMIT") {
        // handled by gate_event that follows
      }
    }
  };

  evtSource.onerror = function () {
    console.warn("VAAS SSE connection lost — retrying…");
  };

  /* ------------------------------------------------------------------ *
   * Exception disposition buttons (delegated, catches both pre-rendered *
   * rows and rows injected by SSE above)                                *
   * ------------------------------------------------------------------ */
  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest(".dispose");
    if (!btn) return;
    const tr = btn.closest("tr[data-id]");
    if (!tr) return;

    const id = tr.dataset.id;
    const action = btn.dataset.action;

    // Optimistic UI
    btn.disabled = true;
    btn.textContent = "…";

    fetch(`/operator/exception/${id}/dispose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disposition: action }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.redirect) {
          window.location.href = data.redirect;
        } else {
          removeExceptionRow(id);
        }
      })
      .catch(() => {
        btn.disabled = false;
        btn.textContent = action;
        alert("Disposition failed — check server logs.");
      });
  });
})();
