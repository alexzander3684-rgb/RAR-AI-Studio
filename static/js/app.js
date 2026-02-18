(function () {
  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

  // ---------------------------
  // Shared: copy/download (Studio)
  // ---------------------------
  async function copyFrom(selector) {
    const el = qs(selector);
    if (!el) return;
    const text = el.innerText || el.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      alert("Copied!");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      alert("Copied!");
    }
  }

  function downloadFrom(selector, filename) {
    const el = qs(selector);
    if (!el) return;
    const text = el.innerText || el.textContent || "";
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename || "rar_output.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }

  qsa("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", () => copyFrom(btn.getAttribute("data-copy")));
  });

  qsa("[data-download]").forEach((btn) => {
    btn.addEventListener("click", () => downloadFrom(btn.getAttribute("data-download"), "rar_marketing_pack.txt"));
  });

  // ---------------------------
  // Salesperson dashboard
  // ---------------------------
  const page = qs("#salespersonPage");
  if (!page) return;

  const els = {
    leadList: qs("#leadList"),
    thread: qs("#thread"),
    chatInput: qs("#chatInput"),
    sendBtn: qs("#sendBtn"),
    activeLeadName: qs("#activeLeadName"),
    activeLeadStage: qs("#activeLeadStage"),
    saveProfileBtn: qs("#saveProfileBtn"),
    addLeadBtn: qs("#addLeadBtn"),
    deleteLeadBtn: qs("#deleteLeadBtn"),
    bulkDeleteBtn: qs("#bulkDeleteBtn"),
    bulkStage: qs("#bulkStage"),
    usageText: qs("#usageText"),
    statusBanner: qs("#statusBanner"),

    autoSendToggleBtn: qs("#autoSendToggleBtn"),
    queueLastReplyBtn: qs("#queueLastReplyBtn"),
    runOutboxBtn: qs("#runOutboxBtn"),
  };

  let state = {
    leads: [],
    activeLeadId: null,
    profile: null,
    usage: null,
    autoSendEnabled: false
  };

  function escapeHtml(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function showBanner(msg, kind) {
    if (!els.statusBanner) return;
    els.statusBanner.style.display = "block";
    els.statusBanner.textContent = msg;
    els.statusBanner.style.border = "1px solid rgba(255,255,255,.12)";
    els.statusBanner.style.background = kind === "error"
      ? "rgba(255, 80, 80, 0.10)"
      : kind === "ok"
        ? "rgba(80, 255, 140, 0.08)"
        : "rgba(255,255,255,0.06)";
  }

  function clearBanner() {
    if (!els.statusBanner) return;
    els.statusBanner.style.display = "none";
    els.statusBanner.textContent = "";
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({
      headers: { "Content-Type": "application/json" }
    }, opts || {}));

    let data = null;
    try { data = await res.json(); } catch { /* ignore */ }

    if (!res.ok) {
      const msg = (data && (data.error || data.detail))
        ? (data.error || data.detail)
        : `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function renderUsage() {
    if (!els.usageText) return;
    if (!state.usage) { els.usageText.textContent = "—"; return; }
    const u = state.usage;
    els.usageText.textContent = `${u.used_leads}/${u.lead_cap} leads · ${u.month}`;
  }

  function renderAutoSend() {
    if (!els.autoSendToggleBtn) return;
    els.autoSendToggleBtn.textContent = `Auto-Send: ${state.autoSendEnabled ? "ON" : "OFF"}`;
  }

  function renderLeads() {
    if (!els.leadList) return;
    if (!state.leads.length) {
      els.leadList.innerHTML = `<div class="tiny" style="opacity:.75;">No leads yet. Add one on the right.</div>`;
      return;
    }

    const html = state.leads.map(l => {
      const active = l.id === state.activeLeadId ? "is-active" : "";
      const name = (l.name || "Lead").trim() || "Lead";
      const contact = (l.contact || "").trim();
      const stage = (l.stage || "New").trim();
      const sub = contact ? `· ${escapeHtml(contact)}` : "";
      return `
        <button class="leadRow ${active}" data-lead-id="${l.id}" type="button" style="width:100%;text-align:left;">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
            <div>
              <div style="font-weight:700;">${escapeHtml(name)}</div>
              <div class="tiny" style="opacity:.8;">${sub}</div>
            </div>
            <div class="tiny" style="opacity:.75;">${escapeHtml(stage)}</div>
          </div>
        </button>
      `;
    }).join("");

    els.leadList.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px;">${html}</div>`;

    qsa(".leadRow").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-lead-id");
        setActiveLead(id);
      });
    });
  }

  function renderThread(messages) {
    if (!els.thread) return;
    if (!messages || !messages.length) {
      els.thread.innerHTML = `<div class="tiny" style="opacity:.75;">No messages yet.</div>`;
      return;
    }

    const html = messages.map(m => {
      const role = m.role || "assistant";
      const isUser = role === "user";
      const bubbleStyle = isUser
        ? "background: rgba(80,255,140,0.10); border: 1px solid rgba(80,255,140,0.15); margin-left:auto;"
        : "background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);";
      const align = isUser ? "justify-content:flex-end;" : "justify-content:flex-start;";
      return `
        <div style="display:flex;${align} margin:10px 0;">
          <div style="${bubbleStyle} padding:12px 12px; border-radius:14px; max-width: 90%;">
            <div style="white-space:pre-wrap;">${escapeHtml(m.content || "")}</div>
            <div class="tiny" style="opacity:.6;margin-top:6px;">${escapeHtml(m.created_at || "")}</div>
          </div>
        </div>
      `;
    }).join("");

    els.thread.innerHTML = html;
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  function renderActiveMeta() {
    const lead = state.leads.find(l => l.id === state.activeLeadId);
    if (els.activeLeadName) els.activeLeadName.textContent = lead ? (lead.name || "Lead") : "—";
    if (els.activeLeadStage) els.activeLeadStage.textContent = lead ? (lead.stage || "—") : "—";
  }

  async function loadUsage() {
    try {
      const data = await api("/api/usage");
      state.usage = data;
      renderUsage();
    } catch {
      state.usage = null;
      renderUsage();
    }
  }

  async function loadLeads() {
    const data = await api("/api/leads");
    state.leads = data.leads || [];

    if (!state.activeLeadId && state.leads.length) {
      state.activeLeadId = state.leads[0].id;
    }
    if (state.activeLeadId && !state.leads.some(l => l.id === state.activeLeadId)) {
      state.activeLeadId = state.leads.length ? state.leads[0].id : null;
    }

    renderLeads();
    renderActiveMeta();

    if (state.activeLeadId) {
      await loadConvo(state.activeLeadId);
    } else {
      renderThread([]);
    }
  }

  async function loadConvo(leadId) {
    const data = await api(`/api/convo/${leadId}`);
    renderThread(data.messages || []);
  }

  async function setActiveLead(leadId) {
    state.activeLeadId = leadId;
    renderLeads();
    renderActiveMeta();
    clearBanner();
    await loadConvo(leadId);
  }

  async function sendMessage() {
    clearBanner();
    const leadId = state.activeLeadId;
    if (!leadId) return showBanner("Select a lead first.", "error");

    const msg = (els.chatInput.value || "").trim();
    if (!msg) return;

    if (els.sendBtn) els.sendBtn.disabled = true;
    try {
      const data = await api("/api/salesperson/chat", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, message: msg })
      });

      els.chatInput.value = "";

      if (data.usage) state.usage = data.usage;
      await loadUsage();

      await loadLeads();
      await loadConvo(leadId);

      // Auto-send pipeline: enqueue last reply + run outbox
      if (state.autoSendEnabled) {
        await api("/api/outbox/enqueue_last_reply", {
          method: "POST",
          body: JSON.stringify({ lead_id: leadId })
        });
        const run = await api("/api/outbox/run", { method: "POST", body: "{}" });
        showBanner(`Reply generated + auto-sent (simulated). Sent=${run.sent || 0}`, "ok");
      } else {
        showBanner("Reply generated.", "ok");
      }

    } catch (e) {
      showBanner(e.message || "Send failed.", "error");
    } finally {
      if (els.sendBtn) els.sendBtn.disabled = false;
    }
  }

  async function moveStage(stage) {
    clearBanner();
    const leadId = state.activeLeadId;
    if (!leadId) return showBanner("Select a lead first.", "error");
    try {
      await api("/api/funnel/move", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, stage })
      });
      await loadLeads();
      showBanner(`Moved to ${stage}.`, "ok");
    } catch (e) {
      showBanner(e.message || "Stage update failed.", "error");
    }
  }

  async function saveProfile() {
    clearBanner();
    const payload = {
      biz_name: (page.querySelector('input[name="biz_name"]').value || "").trim(),
      biz_type: (page.querySelector('input[name="biz_type"]').value || "").trim(),
      offer: (page.querySelector('input[name="offer"]').value || "").trim(),
      location: (page.querySelector('input[name="location"]').value || "").trim(),
      tone: (page.querySelector('select[name="tone"]').value || "confident").trim(),
      contact_method: (page.querySelector('select[name="contact_method"]').value || "dm").trim()
    };

    try {
      await api("/api/profile", { method: "POST", body: JSON.stringify(payload) });
      showBanner("Business profile saved.", "ok");
    } catch (e) {
      showBanner(e.message || "Save failed.", "error");
    }
  }

  async function loadProfile() {
    try {
      const data = await api("/api/profile");
      state.profile = data.profile || {};
      const p = state.profile;

      page.querySelector('input[name="biz_name"]').value = p.biz_name || "";
      page.querySelector('input[name="biz_type"]').value = p.biz_type || "";
      page.querySelector('input[name="offer"]').value = p.offer || "";
      page.querySelector('input[name="location"]').value = p.location || "";
      page.querySelector('select[name="tone"]').value = p.tone || "confident";
      page.querySelector('select[name="contact_method"]').value = p.contact_method || "dm";
    } catch { /* ignore */ }
  }

  async function addLead() {
    clearBanner();
    const name = (page.querySelector('input[name="lead_name"]').value || "").trim();
    const contact = (page.querySelector('input[name="lead_contact"]').value || "").trim();
    const source = (page.querySelector('input[name="lead_source"]').value || "").trim();

    if (!name && !contact) return showBanner("Add at least a name or contact.", "error");

    if (els.addLeadBtn) els.addLeadBtn.disabled = true;
    try {
      const data = await api("/api/leads", {
        method: "POST",
        body: JSON.stringify({ name, contact, source })
      });

      page.querySelector('input[name="lead_name"]').value = "";
      page.querySelector('input[name="lead_contact"]').value = "";
      page.querySelector('input[name="lead_source"]').value = "";

      state.activeLeadId = data.lead.id;
      await loadLeads();
      showBanner("Lead added.", "ok");
    } catch (e) {
      showBanner(e.message || "Add lead failed.", "error");
    } finally {
      if (els.addLeadBtn) els.addLeadBtn.disabled = false;
    }
  }

  async function deleteActiveLead() {
    clearBanner();
    const leadId = state.activeLeadId;
    if (!leadId) return showBanner("Select a lead first.", "error");

    const lead = state.leads.find(l => l.id === leadId);
    const name = lead ? (lead.name || "Lead") : "Lead";
    if (!confirm(`Delete "${name}"? This removes its messages too.`)) return;

    if (els.deleteLeadBtn) els.deleteLeadBtn.disabled = true;
    try {
      await api(`/api/leads/${leadId}`, { method: "DELETE" });
      state.activeLeadId = null;
      await loadLeads();
      await loadUsage();
      showBanner("Lead deleted.", "ok");
    } catch (e) {
      showBanner(e.message || "Delete failed.", "error");
    } finally {
      if (els.deleteLeadBtn) els.deleteLeadBtn.disabled = false;
    }
  }

  async function bulkDelete() {
    clearBanner();
    const stage = (els.bulkStage && els.bulkStage.value) ? els.bulkStage.value : "Lost";
    if (!confirm(`Bulk delete ALL leads in stage "${stage}"?`)) return;

    if (els.bulkDeleteBtn) els.bulkDeleteBtn.disabled = true;
    try {
      const data = await api("/api/leads/bulk_delete", {
        method: "POST",
        body: JSON.stringify({ stage })
      });
      showBanner(`Deleted ${data.deleted || 0} leads in "${stage}".`, "ok");
      state.activeLeadId = null;
      await loadLeads();
      await loadUsage();
    } catch (e) {
      showBanner(e.message || "Bulk delete failed.", "error");
    } finally {
      if (els.bulkDeleteBtn) els.bulkDeleteBtn.disabled = false;
    }
  }

  // Automation controls
  async function loadAutomationState() {
    try {
      const data = await api("/api/automation/state");
      state.autoSendEnabled = !!data.enabled;
    } catch {
      state.autoSendEnabled = false;
    }
    renderAutoSend();
  }

  async function toggleAutomation() {
    clearBanner();
    try {
      const data = await api("/api/automation/toggle", { method: "POST", body: "{}" });
      state.autoSendEnabled = !!data.enabled;
      renderAutoSend();
      showBanner(`Auto-Send is now ${state.autoSendEnabled ? "ON" : "OFF"}.`, "ok");
    } catch (e) {
      showBanner(e.message || "Toggle failed.", "error");
    }
  }

  async function queueLastReply() {
    clearBanner();
    const leadId = state.activeLeadId;
    if (!leadId) return showBanner("Select a lead first.", "error");
    try {
      const data = await api("/api/outbox/enqueue_last_reply", {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId })
      });
      showBanner(`Queued last reply. Outbox=${data.outbox_id}`, "ok");
    } catch (e) {
      showBanner(e.message || "Queue failed.", "error");
    }
  }

  async function runOutbox() {
    clearBanner();
    try {
      const data = await api("/api/outbox/run", { method: "POST", body: "{}" });
      showBanner(`Outbox processed. Sent=${data.sent || 0} Failed=${data.failed || 0}`, "ok");
    } catch (e) {
      showBanner(e.message || "Outbox run failed.", "error");
    }
  }

  // Events
  if (els.sendBtn) els.sendBtn.addEventListener("click", sendMessage);
  if (els.chatInput) {
    els.chatInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") sendMessage();
    });
  }

  qsa('[data-stage]').forEach(btn => {
    btn.addEventListener("click", () => moveStage(btn.getAttribute("data-stage")));
  });

  if (els.saveProfileBtn) els.saveProfileBtn.addEventListener("click", saveProfile);
  if (els.addLeadBtn) els.addLeadBtn.addEventListener("click", addLead);
  if (els.deleteLeadBtn) els.deleteLeadBtn.addEventListener("click", deleteActiveLead);
  if (els.bulkDeleteBtn) els.bulkDeleteBtn.addEventListener("click", bulkDelete);

  if (els.autoSendToggleBtn) els.autoSendToggleBtn.addEventListener("click", toggleAutomation);
  if (els.queueLastReplyBtn) els.queueLastReplyBtn.addEventListener("click", queueLastReply);
  if (els.runOutboxBtn) els.runOutboxBtn.addEventListener("click", runOutbox);

  // Boot
  (async function boot() {
    await loadProfile();
    await loadUsage();
    await loadLeads();
    await loadAutomationState();
  })();
})();
