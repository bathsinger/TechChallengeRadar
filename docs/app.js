(function () {
  "use strict";

  const state = {
    entries: [],
    query: "",
    region: "",
    topics: new Set(),
    sort: "deadline",
  };

  const els = {
    list: document.getElementById("list"),
    count: document.getElementById("result-count"),
    q: document.getElementById("q"),
    sort: document.getElementById("sort"),
    region: document.getElementById("region"),
    chips: document.getElementById("topic-chips"),
    lastUpdated: document.getElementById("last-updated"),
    statTotal: document.getElementById("stat-total"),
    statOpen: document.getElementById("stat-open"),
    statEu: document.getElementById("stat-eu"),
    blips: document.getElementById("scope-blips"),
    repoLink: document.getElementById("repo-link"),
  };

  const TOPIC_LABELS = {
    robotics: "Robotics",
    hardware: "Hardware",
    automation: "Automation",
    autonomous: "Autonomous",
    engineering: "Engineering",
    sensors: "Sensors",
    manufacturing: "Manufacturing",
    space: "Space",
    medicine: "Medicine",
    "3d-print": "3D Print",
  };

  function daysUntil(iso) {
    if (!iso) return null;
    const d = new Date(iso + "T00:00:00Z");
    if (isNaN(d.getTime())) return null;
    const now = new Date();
    const nowUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    return Math.round((d.getTime() - nowUtc) / 86400000);
  }

  function urgencyClass(deadline) {
    const days = daysUntil(deadline);
    if (days === null) return "";
    if (days <= 14) return "urgent";
    if (days <= 45) return "soon";
    return "";
  }

  function fmtDate(iso) {
    if (!iso) return "date TBA";
    const d = new Date(iso + "T00:00:00Z");
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
  }

  function fmtDeadlineLabel(iso) {
    const days = daysUntil(iso);
    if (days === null) return fmtDate(iso);
    if (days < 0) return `closed · ${fmtDate(iso)}`;
    if (days === 0) return `closes today`;
    return `${days}d left · ${fmtDate(iso)}`;
  }

  async function load() {
    try {
      const res = await fetch("data.json", { cache: "no-store" });
      const data = await res.json();
      state.entries = data.entries || [];
      if (data.last_updated) {
        const d = new Date(data.last_updated);
        els.lastUpdated.textContent = "last sweep: " + d.toLocaleString(undefined, {
          year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
        });
      }
    } catch (e) {
      els.lastUpdated.textContent = "last sweep: unavailable";
      state.entries = [];
    }
    buildFilters();
    render();
  }

  function buildFilters() {
    const regions = new Set();
    const topicCounts = {};
    state.entries.forEach((e) => {
      if (e.region) regions.add(e.region);
      (e.topics || []).forEach((t) => { topicCounts[t] = (topicCounts[t] || 0) + 1; });
    });

    [...regions].sort().forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r; opt.textContent = r;
      els.region.appendChild(opt);
    });

    Object.keys(TOPIC_LABELS).forEach((t) => {
      if (!topicCounts[t]) return;
      const btn = document.createElement("button");
      btn.className = "chip";
      btn.type = "button";
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = `${TOPIC_LABELS[t]} (${topicCounts[t]})`;
      btn.addEventListener("click", () => {
        if (state.topics.has(t)) { state.topics.delete(t); btn.setAttribute("aria-pressed", "false"); }
        else { state.topics.add(t); btn.setAttribute("aria-pressed", "true"); }
        render();
      });
      els.chips.appendChild(btn);
    });
  }

  function filteredSorted() {
    const q = state.query.trim().toLowerCase();
    let out = state.entries.filter((e) => {
      if (state.region && e.region !== state.region) return false;
      if (state.topics.size) {
        const t = e.topics || [];
        if (![...state.topics].every((wanted) => t.includes(wanted))) return false;
      }
      if (q) {
        const hay = `${e.name} ${e.short_description} ${e.organizer}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    if (state.sort === "deadline") {
      out.sort((a, b) => {
        const da = daysUntil(a.deadline), db = daysUntil(b.deadline);
        if (da === null && db === null) return 0;
        if (da === null) return 1;
        if (db === null) return -1;
        return da - db;
      });
    } else if (state.sort === "new") {
      out.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""));
    } else if (state.sort === "name") {
      out.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    }
    return out;
  }

  function render() {
    const items = filteredSorted();
    els.count.textContent = `${items.length} contact${items.length === 1 ? "" : "s"}`;

    els.list.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No contacts match these filters. Widen the scan — clear a filter or search term.";
      els.list.appendChild(empty);
    } else {
      items.forEach((e) => els.list.appendChild(renderCard(e)));
    }

    renderStats(items);
    renderScope();
  }

  function renderCard(e) {
    const card = document.createElement("article");
    card.className = "card";
    const uCls = urgencyClass(e.deadline);

    const topicsHtml = (e.topics || [])
      .map((t) => `<span class="tag">${TOPIC_LABELS[t] || t}</span>`)
      .join("");

    card.innerHTML = `
      <div>
        <h3><a href="${escAttr(e.url)}" target="_blank" rel="noopener">${esc(e.name)}</a></h3>
        <p class="desc">${esc(e.short_description || "No description available.")}</p>
        <div class="tag-row">
          ${e.reward && e.reward !== "Unknown" ? `<span class="tag reward">${esc(e.reward)}</span>` : ""}
          <span class="tag deadline ${uCls}">${esc(fmtDeadlineLabel(e.deadline))}</span>
          ${e.start_date ? `<span class="tag">starts ${esc(fmtDate(e.start_date))}</span>` : ""}
          <span class="tag">${esc(e.region || "Unknown region")}</span>
          ${topicsHtml}
        </div>
      </div>
      <div class="meta">
        <span>${esc(e.organizer || "Unknown organizer")}</span>
        <span>found ${esc(fmtDate(e.first_seen))}</span>
        <a href="${escAttr(e.url)}" target="_blank" rel="noopener">Open source →</a>
      </div>
    `;
    return card;
  }

  function renderStats(items) {
    els.statTotal.textContent = state.entries.length;
    els.statOpen.textContent = state.entries.filter((e) => {
      const d = daysUntil(e.deadline);
      return d !== null && d >= 0 && d <= 30;
    }).length;
    els.statEu.textContent = state.entries.filter((e) =>
      (e.region || "").toLowerCase().includes("europe")
    ).length;
  }

  function renderScope() {
    els.blips.innerHTML = "";
    const cx = 200, cy = 200, maxR = 178, minR = 22;
    const items = state.entries.slice(0, 60);
    items.forEach((e, i) => {
      const days = daysUntil(e.deadline);
      const norm = days === null ? 0.92 : Math.max(0, Math.min(1, days / 120));
      const r = minR + norm * (maxR - minR);
      const angle = (hashCode(e.name || String(i)) % 360) * (Math.PI / 180);
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      const cls = days !== null && days <= 14 ? "urgent" : days !== null && days <= 45 ? "soon" : "";

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", `blip ${cls}`);
      g.innerHTML = `
        <circle class="ping" cx="${x}" cy="${y}" r="4"></circle>
        <circle class="dot" cx="${x}" cy="${y}" r="3.4"></circle>
        <title>${esc(e.name)} — ${esc(fmtDeadlineLabel(e.deadline))}</title>
      `;
      g.addEventListener("click", () => window.open(e.url, "_blank", "noopener"));
      els.blips.appendChild(g);
    });
  }

  function hashCode(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) { h = (h << 5) - h + str.charCodeAt(i); h |= 0; }
    return Math.abs(h);
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }
  function escAttr(s) { return esc(s || "#"); }

  els.q.addEventListener("input", (e) => { state.query = e.target.value; render(); });
  els.sort.addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  els.region.addEventListener("change", (e) => { state.region = e.target.value; render(); });

  // point the footer link at wherever this page is actually hosted
  try {
    if (location.hostname.endsWith("github.io")) {
      const parts = location.hostname.split(".")[0];
      els.repoLink.href = `https://github.com/${parts}/${location.pathname.split("/")[1] || ""}`;
    }
  } catch (e) { /* noop */ }

  load();
})();
