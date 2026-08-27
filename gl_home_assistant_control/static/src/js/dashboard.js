(function () {
    "use strict";

    const app = document.getElementById("gl-ha-app");
    if (!app) return;

    const slug = app.dataset.slug || "";
    const pageSlug = app.dataset.pageSlug || "";
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
    const expandedPlans = new Set();

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

    function formatDay(value) {
        const parts = String(value || "").split("-");
        if (parts.length !== 3) return esc(value || "–");
        return `${parts[2]}.${parts[1]}.${parts[0]}`;
    }

    function formatTime(value) {
        const d = parseUtc(value);
        if (!d || Number.isNaN(d.getTime())) return "–";
        return new Intl.DateTimeFormat("de-DE", {hour: "2-digit", minute: "2-digit"}).format(d) + " Uhr";
    }

    function formatValue(entity) {
        if (entity.domain === "climate" && entity.has_numeric_value) {
            return `${Number(entity.numeric_value).toFixed(1)}${entity.unit || " °C"}`;
        }
        if (entity.has_numeric_value && !["switch", "light", "fan", "binary_sensor", "input_boolean"].includes(entity.domain)) {
            const v = Math.abs(entity.numeric_value) >= 100
                ? Number(entity.numeric_value).toFixed(0)
                : Number(entity.numeric_value).toFixed(1);
            return `${v}${entity.unit ? " " + entity.unit : ""}`;
        }
        const lower = String(entity.state || "").toLowerCase();
        if (lower === "on") return "EIN";
        if (lower === "off") return "AUS";
        return entity.state || "–";
    }

    function statusClass(entity, baseClass) {
        let cls = baseClass || "gl-ha-entity";
        if (!entity.is_available) return `${cls} offline`;
        const lower = String(entity.state || "").toLowerCase();
        if (["on", "heat", "heating", "cool", "cooling"].includes(lower)) cls += " active";
        return cls;
    }

    function renderStatus() {
        if (!state?.view?.show_status) {
            statusEl.innerHTML = "";
            statusEl.style.display = "none";
            return;
        }
        statusEl.style.display = "grid";
        const c = state.connection || {};
        const online = (state.entities || []).filter(e => e.is_available).length;
        const total = (state.entities || []).length;
        statusEl.innerHTML = `
            <div class="gl-ha-status-card"><span>Angezeigt</span><strong>${online}/${total} erreichbar</strong></div>
            <div class="gl-ha-status-card"><span>Letzter Statusabruf</span><strong>${esc(formatDate(c.last_state_sync_at))}</strong></div>
            <div class="gl-ha-status-card"><span>Zeitfenster</span><strong>${esc(formatDate(c.last_schedule_sync_at))}</strong></div>
            <div class="gl-ha-status-card"><span>Automatik</span><strong>${esc(formatDate(c.last_automation_at))}</strong></div>`;
    }

    function renderAlerts() {
        if (!state?.view?.show_alerts) {
            alertsEl.innerHTML = "";
            return;
        }
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

    function planKey(item) {
        return `${item.date}:${item.target_id}`;
    }

    function planStatusLabel(status) {
        return status === "active" ? "AKTIV" : "GEPLANT";
    }

    function planSourceLabel(detail) {
        if (detail.source === "cinema") return "Kino";
        if (detail.source === "event") return `Veranstaltung: ${detail.source_name || "–"}`;
        return detail.source_name || detail.source || "–";
    }

    function detailTimingStatus(detail) {
        const start = parseUtc(detail.start_at);
        const end = parseUtc(detail.end_at);
        const now = Date.now();
        return start && end && start.getTime() <= now && now <= end.getTime() ? "active" : "planned";
    }

    function planDetailHtml(item, detail) {
        const status = detailTimingStatus(detail);
        const conditioned = Number(detail.condition_count || 0) > 0
            ? `<span class="gl-ha-plan-condition">sensorabhängig</span>`
            : "";
        const meta = [detail.rule_name ? `Regel: ${detail.rule_name}` : "", detail.source_details || ""]
            .filter(Boolean).join(" · ");
        return `<div class="gl-ha-plan-detail-row">
            <div class="gl-ha-plan-date">${esc(formatDay(item.date))}</div>
            <div class="gl-ha-plan-target">${esc(item.target_name)}</div>
            <div><span class="gl-ha-plan-status ${esc(status)}">${planStatusLabel(status)}</span></div>
            <div class="gl-ha-plan-time"><span>AN</span><strong>${esc(formatTime(detail.start_at))}</strong></div>
            <div class="gl-ha-plan-time"><span>AUS</span><strong>${esc(formatTime(detail.end_at))}</strong></div>
            <div class="gl-ha-plan-source">(${esc(planSourceLabel(detail))}) ${conditioned}</div>
            ${meta ? `<div class="gl-ha-plan-meta">${esc(meta)}</div>` : ""}
        </div>`;
    }

    function renderWindows() {
        if (!state?.view?.show_windows) {
            windowsEl.innerHTML = "";
            return;
        }
        const plan = state?.automation_plan || [];
        if (!plan.length) {
            windowsEl.innerHTML = `
                <div class="gl-ha-section-head"><h2>Nächste Automatik-Zeitfenster</h2><span>24 h</span></div>
                <div class="gl-ha-empty">In den nächsten 24 Stunden sind keine automatischen Schaltvorgänge geplant.</div>`;
            return;
        }

        windowsEl.innerHTML = `
            <div class="gl-ha-section-head"><h2>Nächste Automatik-Zeitfenster</h2><span>24 h</span></div>
            <div class="gl-ha-plan-list">
                <div class="gl-ha-plan-head" aria-hidden="true">
                    <div>Datum</div><div>Element</div><div>Status</div><div>AN</div><div>AUS</div><div></div>
                </div>
                ${plan.map(item => {
                    const key = planKey(item);
                    const expanded = expandedPlans.has(key);
                    const multiPhase = Number(item.phase_count || 1) > 1
                        ? `<span class="gl-ha-plan-phase-note">${Number(item.phase_count)} Schaltphasen</span>`
                        : "";
                    return `<div class="gl-ha-plan-item ${expanded ? "open" : ""}" data-plan-key="${esc(key)}">
                        <button type="button" class="gl-ha-plan-row" aria-expanded="${expanded ? "true" : "false"}">
                            <div class="gl-ha-plan-date">${esc(formatDay(item.date))}</div>
                            <div class="gl-ha-plan-target">${esc(item.target_name)} ${multiPhase}</div>
                            <div><span class="gl-ha-plan-status ${esc(item.status)}">${planStatusLabel(item.status)}</span></div>
                            <div class="gl-ha-plan-time"><span>AN</span><strong>${esc(formatTime(item.start_at))}</strong></div>
                            <div class="gl-ha-plan-time"><span>AUS</span><strong>${esc(formatTime(item.end_at))}</strong></div>
                            <div class="gl-ha-plan-toggle" aria-hidden="true">⌄</div>
                        </button>
                        <div class="gl-ha-plan-details" ${expanded ? "" : "hidden"}>
                            ${(item.details || []).map(detail => planDetailHtml(item, detail)).join("")}
                        </div>
                    </div>`;
                }).join("")}
            </div>`;
    }

    function controlHtml(entity) {
        if (!entity.controllable || entity.display_role !== "control") return "";
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

    function chartHtml(entity, compact) {
        if (!state?.view?.show_history_charts || !entity.history_enabled || !entity.has_numeric_value) return "";
        return `<div class="gl-ha-chart-wrap${compact ? " compact" : ""}"><canvas class="gl-ha-chart" data-entity-id="${entity.id}"></canvas></div>`;
    }

    function technicalHtml(entity) {
        return state?.view?.show_entity_ids ? `<small>${esc(entity.entity_id)}</small>` : "";
    }

    function lastSeenHtml(entity) {
        return state?.view?.show_last_seen
            ? `<div class="gl-ha-lastseen">zuletzt gesehen: ${esc(formatDate(entity.last_seen_at))}</div>`
            : "";
    }

    function entityHtml(entity) {
        const override = entity.override_active
            ? `<div class="gl-ha-override">Manuell bis ${esc(formatDate(entity.override_until))}</div>`
            : "";
        return `<article class="${statusClass(entity, "gl-ha-entity gl-ha-item")}" data-entity-id="${entity.id}">
            <div class="gl-ha-entity-head">
                <div>
                    <h3>${esc(entity.name)}</h3>
                    ${technicalHtml(entity)}
                </div>
                <span class="gl-ha-dot" title="${entity.is_available ? "Erreichbar" : "Nicht erreichbar"}"></span>
            </div>
            <div class="gl-ha-main-value">${esc(formatValue(entity))}</div>
            ${entity.domain === "climate" && entity.has_control_value ? `<div class="gl-ha-subvalue">Soll: ${Number(entity.control_value).toFixed(1)} °C</div>` : ""}
            ${override}
            ${chartHtml(entity, false)}
            ${controlHtml(entity)}
            ${lastSeenHtml(entity)}
        </article>`;
    }

    function sensorHtml(entity) {
        return `<article class="${statusClass(entity, "gl-ha-sensor gl-ha-item")}" data-entity-id="${entity.id}">
            <div class="gl-ha-sensor-head">
                <div class="gl-ha-sensor-name">${esc(entity.name)}</div>
                <span class="gl-ha-dot" title="${entity.is_available ? "Erreichbar" : "Nicht erreichbar"}"></span>
            </div>
            ${technicalHtml(entity)}
            <div class="gl-ha-sensor-value">${esc(formatValue(entity))}</div>
            ${entity.domain === "climate" && entity.has_control_value ? `<div class="gl-ha-subvalue">Soll: ${Number(entity.control_value).toFixed(1)} °C</div>` : ""}
            ${chartHtml(entity, true)}
            ${lastSeenHtml(entity)}
        </article>`;
    }

    function groupEntities(entities) {
        const grouped = new Map();
        const mode = state?.view?.group_mode || "custom";
        entities.forEach(entity => {
            let group = "";
            if (mode === "room") group = entity.room || "Allgemein";
            else if (mode === "custom") group = entity.dashboard_group || entity.room || "Allgemein";
            if (!grouped.has(group)) grouped.set(group, []);
            grouped.get(group).push(entity);
        });
        return grouped;
    }

    function roomBlocks(entities, compactSensors) {
        const grouped = groupEntities(entities);
        return [...grouped.entries()].map(([room, items]) => `
            <section class="gl-ha-room">
                ${room ? `<div class="gl-ha-section-head gl-ha-room-head"><h3>${esc(room)}</h3><span>${items.length}</span></div>` : ""}
                <div class="${compactSensors ? "gl-ha-sensor-grid" : "gl-ha-grid"}">
                    ${items.map(compactSensors ? sensorHtml : entityHtml).join("")}
                </div>
            </section>`).join("");
    }

    function roleSection(title, entities, compactSensors) {
        if (!entities.length) return "";
        return `<section class="gl-ha-role-section">
            <div class="gl-ha-role-head"><h2>${esc(title)}</h2><span>${entities.length} Elemente</span></div>
            ${roomBlocks(entities, compactSensors)}
        </section>`;
    }

    function renderRooms() {
        if (!state) return;
        const entities = state.entities || [];
        if (!entities.length) {
            roomsEl.innerHTML = `<div class="gl-ha-empty"><strong>Auf dieser Seite sind noch keine Entitäten ausgewählt.</strong><br/>Die Auswahl erfolgt in Odoo unter Gebäudesteuerung → Dashboards bzw. Dashboard-Unterseiten.</div>`;
            return;
        }

        const columns = Math.min(6, Math.max(2, Number(state?.view?.grid_columns || 4)));
        roomsEl.style.setProperty("--gl-cols", columns);

        if (state?.view?.separate_controls_sensors) {
            const controls = entities.filter(e => e.display_role === "control");
            const sensors = entities.filter(e => e.display_role !== "control");
            const compactSensors = state?.view?.sensor_layout === "compact";
            roomsEl.innerHTML =
                roleSection("Steuerung", controls, false) +
                roleSection("Sensoren & Messwerte", sensors, compactSensors);
        } else {
            roomsEl.innerHTML = roomBlocks(entities, false);
        }
        drawAllCharts();
    }

    function drawChart(canvas, points) {
        if (!points || points.length < 2) return;
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const width = Math.max(180, Math.floor(rect.width));
        const height = Math.max(56, Math.floor(rect.height));
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
        const pad = 6;
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
        periodEl.style.display = state?.view?.show_history_charts ? "block" : "none";
        renderStatus();
        renderAlerts();
        renderWindows();
        renderRooms();
    }

    async function loadHistory(force) {
        if (!state || !state?.view?.show_history_charts) {
            history = {};
            return;
        }
        const now = Date.now();
        if (!force && now - historyFetchedAt < 60000) return;
        const ids = (state.entities || [])
            .filter(e => e.history_enabled && e.has_numeric_value)
            .map(e => e.id);
        if (!ids.length) return;
        try {
            history = await rpc("/groundlift/ha/history", {
                slug,
                page_slug: pageSlug,
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
            state = await rpc("/groundlift/ha/data", {slug, page_slug: pageSlug});
            if (state?.dashboard?.history_hours && !periodEl.dataset.initialized) {
                periodEl.value = String(state.dashboard.history_hours);
                periodEl.dataset.initialized = "1";
            }
            renderAll();
            await loadHistory(!!forceHistory);
            scheduleRefresh();
        } catch (err) {
            statusEl.style.display = "block";
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
        const card = document.querySelector(`[data-entity-id="${entity.id}"]`);
        if (card) card.classList.add("busy");
        try {
            const updated = await rpc("/groundlift/ha/command", {
                slug,
                page_slug: pageSlug,
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

    windowsEl.addEventListener("click", (event) => {
        const row = event.target.closest(".gl-ha-plan-row");
        if (!row) return;
        const item = row.closest(".gl-ha-plan-item");
        if (!item) return;
        const key = item.dataset.planKey;
        if (expandedPlans.has(key)) expandedPlans.delete(key);
        else expandedPlans.add(key);
        item.classList.toggle("open", expandedPlans.has(key));
        row.setAttribute("aria-expanded", expandedPlans.has(key) ? "true" : "false");
        const details = item.querySelector(".gl-ha-plan-details");
        if (details) details.hidden = !expandedPlans.has(key);
    });

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
