(function () {
    "use strict";

    const app = document.getElementById("gl-ha-app");
    if (!app) return;

    const slug = app.dataset.slug || "";
    const roomsEl = document.getElementById("gl-ha-rooms");
    const alertsEl = document.getElementById("gl-ha-alerts");
    const statusEl = document.getElementById("gl-ha-status");
    const windowsEl = document.getElementById("gl-ha-windows");
    const periodEl = document.getElementById("gl-ha-period");
    const refreshBtn = document.getElementById("gl-ha-refresh");

    let state = null;
    let history = {};
    let historyFetchedAt = 0;
    let refreshTimer = null;
    const draftValues = new Map();

    function esc(value) {
        return String(value == null ? "" : value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    async function rpc(url, params) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({jsonrpc: "2.0", method: "call", params: params || {}, id: Date.now()}),
        });
        const payload = await response.json();
        if (payload.error) {
            const msg = payload.error?.data?.message || payload.error?.message || "Unbekannter Odoo-Fehler";
            throw new Error(msg);
        }
        return payload.result;
    }

    function parseUtc(value) {
        if (!value) return null;
        const iso = value.includes("T") ? value : value.replace(" ", "T");
        return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
    }

    function formatDate(value) {
        const d = parseUtc(value);
        if (!d || Number.isNaN(d.getTime())) return "–";
        return new Intl.DateTimeFormat("de-DE", {
            day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"
        }).format(d);
    }

    function formatValue(entity) {
        if (entity.domain === "climate" && entity.has_numeric_value) {
            return `${Number(entity.numeric_value).toFixed(1)}${entity.unit || " °C"}`;
        }
        if (entity.has_numeric_value && entity.domain !== "switch" && entity.domain !== "light" && entity.domain !== "fan" && entity.domain !== "binary_sensor" && entity.domain !== "input_boolean") {
            const v = Math.abs(entity.numeric_value) >= 100 ? Number(entity.numeric_value).toFixed(0) : Number(entity.numeric_value).toFixed(1);
            return `${v}${entity.unit ? " " + entity.unit : ""}`;
        }
        const lower = String(entity.state || "").toLowerCase();
        if (lower === "on") return "EIN";
        if (lower === "off") return "AUS";
        return entity.state || "–";
    }

    function statusClass(entity) {
        if (!entity.is_available) return "gl-ha-entity offline";
        const lower = String(entity.state || "").toLowerCase();
        if (["on", "heat", "heating", "cool", "cooling"].includes(lower)) return "gl-ha-entity active";
        return "gl-ha-entity";
    }

    function renderStatus() {
        if (!state) return;
        const c = state.connection || {};
        const online = (state.entities || []).filter(e => e.is_available).length;
        const total = (state.entities || []).length;
        statusEl.innerHTML = `
            <div class="gl-ha-status-card"><span>Entitäten</span><strong>${online}/${total} erreichbar</strong></div>
            <div class="gl-ha-status-card"><span>Letzter Statusabruf</span><strong>${esc(formatDate(c.last_state_sync_at))}</strong></div>
            <div class="gl-ha-status-card"><span>Zeitfenster</span><strong>${esc(formatDate(c.last_schedule_sync_at))}</strong></div>
            <div class="gl-ha-status-card"><span>Automatik</span><strong>${esc(formatDate(c.last_automation_at))}</strong></div>`;
    }

    function renderAlerts() {
        const alerts = state?.alerts || [];
        if (!alerts.length) {
            alertsEl.innerHTML = "";
            return;
        }
        alertsEl.innerHTML = `<div class="gl-ha-alert-title">Aktive Warnungen</div>` + alerts.map(a => `
            <div class="gl-ha-alert ${esc(a.severity)}">
                <div><strong>${esc(a.name)}</strong><div>${esc(a.message)}</div></div>
                <time>${esc(formatDate(a.last_seen))}</time>
            </div>`).join("");
    }

    function renderWindows() {
        const windows = state?.windows || [];
        if (!windows.length) {
            windowsEl.innerHTML = "";
            return;
        }
        const first = windows.slice(0, 8);
        windowsEl.innerHTML = `
            <div class="gl-ha-section-head"><h2>Nächste Automatik-Zeitfenster</h2><span>24 h</span></div>
            <div class="gl-ha-window-strip">${first.map(w => `
                <div class="gl-ha-window">
                    <span class="gl-ha-window-source">${w.source === "cinema" ? "Kino" : "Event"}</span>
                    <strong>${esc(w.name)}</strong>
                    <small>${esc(formatDate(w.start_at))} – ${esc(formatDate(w.end_at))}${w.details ? " · " + esc(w.details) : ""}</small>
                </div>`).join("")}</div>`;
    }

    function controlHtml(entity) {
        if (!entity.controllable) return "";
        if (entity.control_type === "toggle") {
            return `<div class="gl-ha-controls">
                <button class="gl-ha-command" data-id="${entity.id}" data-command="on">Ein</button>
                <button class="gl-ha-command" data-id="${entity.id}" data-command="off">Aus</button>
                ${entity.override_active ? `<button class="gl-ha-command secondary" data-id="${entity.id}" data-command="auto">Automatik</button>` : ""}
            </div>`;
        }
        if (entity.control_type === "temperature" || entity.control_type === "number") {
            const current = draftValues.has(entity.id)
                ? draftValues.get(entity.id)
                : (entity.has_control_value ? entity.control_value : entity.numeric_value);
            const step = entity.step || (entity.control_type === "temperature" ? 0.5 : 1);
            return `<div class="gl-ha-controls gl-ha-number-control">
                <button class="gl-ha-adjust" data-id="${entity.id}" data-delta="-${step}">−</button>
                <span class="gl-ha-draft" data-value-id="${entity.id}">${Number(current || 0).toFixed(step < 1 ? 1 : 0)}${entity.control_type === "temperature" ? " °C" : ""}</span>
                <button class="gl-ha-adjust" data-id="${entity.id}" data-delta="${step}">+</button>
                <button class="gl-ha-command" data-id="${entity.id}" data-command="set">Setzen</button>
                ${entity.override_active ? `<button class="gl-ha-command secondary" data-id="${entity.id}" data-command="auto">Automatik</button>` : ""}
            </div>`;
        }
        return "";
    }

    function entityHtml(entity) {
        const override = entity.override_active
            ? `<div class="gl-ha-override">Manuell bis ${esc(formatDate(entity.override_until))}</div>`
            : "";
        const chart = entity.history_enabled && entity.has_numeric_value
            ? `<div class="gl-ha-chart-wrap"><canvas class="gl-ha-chart" data-entity-id="${entity.id}"></canvas></div>`
            : "";
        return `<article class="${statusClass(entity)}" data-entity-id="${entity.id}">
            <div class="gl-ha-entity-head">
                <div>
                    <h3>${esc(entity.name)}</h3>
                    <small>${esc(entity.entity_id)}</small>
                </div>
                <span class="gl-ha-dot" title="${entity.is_available ? "Erreichbar" : "Nicht erreichbar"}"></span>
            </div>
            <div class="gl-ha-main-value">${esc(formatValue(entity))}</div>
            ${entity.domain === "climate" && entity.has_control_value ? `<div class="gl-ha-subvalue">Soll: ${Number(entity.control_value).toFixed(1)} °C</div>` : ""}
            ${override}
            ${chart}
            ${controlHtml(entity)}
            <div class="gl-ha-lastseen">zuletzt gesehen: ${esc(formatDate(entity.last_seen_at))}</div>
        </article>`;
    }

    function renderRooms() {
        if (!state) return;
        const grouped = new Map();
        (state.entities || []).forEach(entity => {
            const room = entity.room || "Allgemein";
            if (!grouped.has(room)) grouped.set(room, []);
            grouped.get(room).push(entity);
        });
        if (!grouped.size) {
            roomsEl.innerHTML = `<div class="gl-ha-empty">Noch keine Entitäten ausgewählt. Zuerst in Odoo „Entitäten synchronisieren“ und die gewünschten Geräte dem Dashboard zuordnen.</div>`;
            return;
        }
        roomsEl.innerHTML = [...grouped.entries()].map(([room, entities]) => `
            <section class="gl-ha-room">
                <div class="gl-ha-section-head"><h2>${esc(room)}</h2><span>${entities.length} Entitäten</span></div>
                <div class="gl-ha-grid">${entities.map(entityHtml).join("")}</div>
            </section>`).join("");
        drawAllCharts();
    }

    function drawChart(canvas, points) {
        if (!points || points.length < 2) return;
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const width = Math.max(260, Math.floor(rect.width));
        const height = Math.max(92, Math.floor(rect.height));
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        const ctx = canvas.getContext("2d");
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, width, height);

        const values = points.map(p => Number(p.v)).filter(Number.isFinite);
        if (!values.length) return;
        let min = Math.min(...values);
        let max = Math.max(...values);
        if (min === max) { min -= 1; max += 1; }
        const pad = 8;
        const innerW = width - pad * 2;
        const innerH = height - pad * 2;

        ctx.strokeStyle = "rgba(255,255,255,.10)";
        ctx.lineWidth = 1;
        for (let i = 1; i < 4; i++) {
            const y = pad + (innerH * i / 4);
            ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(width - pad, y); ctx.stroke();
        }

        ctx.strokeStyle = "#ff3b3f";
        ctx.lineWidth = 2;
        ctx.beginPath();
        points.forEach((p, i) => {
            const x = pad + innerW * (i / Math.max(1, points.length - 1));
            const y = pad + innerH * (1 - ((Number(p.v) - min) / (max - min)));
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    function drawAllCharts() {
        document.querySelectorAll("canvas.gl-ha-chart").forEach(canvas => {
            drawChart(canvas, history[String(canvas.dataset.entityId)] || []);
        });
    }

    function renderAll() {
        renderStatus();
        renderAlerts();
        renderWindows();
        renderRooms();
    }

    async function loadHistory(force) {
        if (!state) return;
        const now = Date.now();
        if (!force && now - historyFetchedAt < 60000) return;
        const ids = (state.entities || []).filter(e => e.history_enabled && e.has_numeric_value).map(e => e.id);
        if (!ids.length) return;
        try {
            history = await rpc("/groundlift/ha/history", {
                slug,
                entity_ids: ids,
                hours: Number(periodEl.value || state.dashboard.history_hours || 24),
            }) || {};
            historyFetchedAt = now;
            drawAllCharts();
        } catch (err) {
            console.error(err);
        }
    }

    async function loadData(forceHistory) {
        refreshBtn.disabled = true;
        try {
            state = await rpc("/groundlift/ha/data", {slug});
            if (state?.dashboard?.history_hours && !periodEl.dataset.initialized) {
                periodEl.value = String(state.dashboard.history_hours);
                periodEl.dataset.initialized = "1";
            }
            renderAll();
            await loadHistory(!!forceHistory);
            scheduleRefresh();
        } catch (err) {
            statusEl.innerHTML = `<div class="gl-ha-error"><strong>Dashboard konnte nicht geladen werden.</strong><span>${esc(err.message)}</span></div>`;
        } finally {
            refreshBtn.disabled = false;
        }
    }

    function scheduleRefresh() {
        if (refreshTimer) clearTimeout(refreshTimer);
        const seconds = Math.max(5, Number(state?.dashboard?.refresh_seconds || 15));
        refreshTimer = setTimeout(() => loadData(false), seconds * 1000);
    }

    function findEntity(id) {
        return (state?.entities || []).find(e => e.id === Number(id));
    }

    async function sendCommand(id, command) {
        const entity = findEntity(id);
        if (!entity) return;
        let value = null;
        if (command === "set") {
            value = draftValues.has(entity.id)
                ? draftValues.get(entity.id)
                : (entity.has_control_value ? entity.control_value : entity.numeric_value);
        }
        const card = document.querySelector(`.gl-ha-entity[data-entity-id="${entity.id}"]`);
        if (card) card.classList.add("busy");
        try {
            const updated = await rpc("/groundlift/ha/command", {
                slug,
                entity_id: entity.id,
                command,
                value,
            });
            const index = state.entities.findIndex(e => e.id === entity.id);
            if (index >= 0) state.entities[index] = updated;
            if (command === "set") draftValues.delete(entity.id);
            renderRooms();
        } catch (err) {
            window.alert(err.message);
        } finally {
            if (card) card.classList.remove("busy");
        }
    }

    roomsEl.addEventListener("click", (event) => {
        const adjust = event.target.closest(".gl-ha-adjust");
        if (adjust) {
            const entity = findEntity(adjust.dataset.id);
            if (!entity) return;
            const step = Number(adjust.dataset.delta || 0);
            let current = draftValues.has(entity.id)
                ? Number(draftValues.get(entity.id))
                : Number(entity.has_control_value ? entity.control_value : entity.numeric_value);
            current += step;
            if (entity.has_min_value) current = Math.max(entity.min_value, current);
            if (entity.has_max_value) current = Math.min(entity.max_value, current);
            const precision = (entity.step || 1) < 1 ? 1 : 0;
            current = Number(current.toFixed(precision));
            draftValues.set(entity.id, current);
            const el = roomsEl.querySelector(`[data-value-id="${entity.id}"]`);
            if (el) el.textContent = `${current.toFixed(precision)}${entity.control_type === "temperature" ? " °C" : ""}`;
            return;
        }
        const button = event.target.closest(".gl-ha-command");
        if (button) sendCommand(button.dataset.id, button.dataset.command);
    });

    refreshBtn.addEventListener("click", () => loadData(true));
    periodEl.addEventListener("change", () => loadHistory(true));
    window.addEventListener("resize", drawAllCharts);

    loadData(true);
})();
