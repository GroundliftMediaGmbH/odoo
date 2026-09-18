(function () {
    "use strict";

    const app = document.getElementById("gl-ha-app");
    if (!app) return;

    const slug = app.dataset.slug || "";
    const pageSlug = app.dataset.pageSlug || "";
    const deviceMode = app.dataset.deviceMode === "1";
    const devicePublicId = app.dataset.devicePublicId || "";
    const apiBase = deviceMode ? "/groundlift/ha/device" : "/groundlift/ha";
    const roomsEl = document.getElementById("gl-ha-rooms");
    const comfortChartEl = document.getElementById("gl-ha-comfort-chart");
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

    const encoder = new TextEncoder();
    let deviceKeyPromise = null;

    function b64url(bytes) {
        let binary = "";
        const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
        data.forEach(byte => { binary += String.fromCharCode(byte); });
        return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
    }

    function hex(bytes) {
        return [...new Uint8Array(bytes)].map(v => v.toString(16).padStart(2, "0")).join("");
    }

    function canonicalize(value) {
        if (Array.isArray(value)) return value.map(canonicalize);
        if (value && typeof value === "object") {
            const out = {};
            Object.keys(value).sort().forEach(key => { out[key] = canonicalize(value[key]); });
            return out;
        }
        return value;
    }

    function canonicalJson(value) {
        return JSON.stringify(canonicalize(value));
    }

    function openDeviceKeyDb() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open("gl_ha_device_keys", 1);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains("keys")) db.createObjectStore("keys");
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error || new Error("Geräteschlüsselspeicher konnte nicht geöffnet werden."));
        });
    }

    async function getDevicePrivateKey() {
        if (!deviceMode) return null;
        if (!deviceKeyPromise) {
            deviceKeyPromise = (async () => {
                const db = await openDeviceKeyDb();
                try {
                    return await new Promise((resolve, reject) => {
                        const tx = db.transaction("keys", "readonly");
                        const req = tx.objectStore("keys").get(devicePublicId);
                        req.onsuccess = () => resolve(req.result || null);
                        req.onerror = () => reject(req.error || new Error("Geräteschlüssel konnte nicht gelesen werden."));
                    });
                } finally {
                    db.close();
                }
            })();
        }
        const key = await deviceKeyPromise;
        if (!key) {
            throw new Error("Der lokale Geräteschlüssel fehlt. Bitte diesen Rechner in Odoo unter Gebäudesteuerung → Gerätezugänge neu binden.");
        }
        return key;
    }

    async function signedHeaders(url, params) {
        const key = await getDevicePrivateKey();
        const timestamp = String(Date.now());
        const nonceBytes = crypto.getRandomValues(new Uint8Array(18));
        const nonce = b64url(nonceBytes);
        const digest = await crypto.subtle.digest("SHA-256", encoder.encode(canonicalJson(params || {})));
        const message = `${timestamp}\n${nonce}\n${url}\n${hex(digest)}`;
        const signature = await crypto.subtle.sign(
            {name: "ECDSA", hash: "SHA-256"},
            key,
            encoder.encode(message)
        );
        return {
            "X-GL-HA-Device": devicePublicId,
            "X-GL-HA-Timestamp": timestamp,
            "X-GL-HA-Nonce": nonce,
            "X-GL-HA-Signature": b64url(signature),
        };
    }

    async function rpc(url, params) {
        const rpcParams = params || {};
        const body = JSON.stringify({jsonrpc: "2.0", method: "call", params: rpcParams, id: Date.now()});
        const headers = {"Content-Type": "application/json"};
        if (deviceMode) Object.assign(headers, await signedHeaders(url, rpcParams));
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers,
            body,
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

    function hasFiniteNumber(value) {
        return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
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
        if (detail.source === "daily") return "Zeitprogramm";
        if (detail.source === "project") return `Projekt: ${detail.source_name || "–"}`;
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

    function comfortClass(entity) {
        const code = entity?.comfort?.code || "";
        return code ? ` comfort-${code}` : "";
    }

    function comfortBadge(entity) {
        const c = entity?.comfort;
        if (!c?.paired) return "";
        const title = `${c.label}: ${Number(c.temperature).toFixed(1)} °C / ${Number(c.humidity).toFixed(1)} %${c.mould_enabled ? " · Schimmelprüfung aktiv" : ""}`;
        return `<div class="gl-ha-comfort-badge" title="${esc(title)}">${esc(c.label)}</div>`;
    }

    function comfortGroupClass(group) {
        const code = group?.comfort?.code || "";
        return code ? ` comfort-${code}` : "";
    }

    function entityById(id) {
        return (state?.entities || []).find(entity => entity.id === Number(id));
    }

    function comfortGroupHistoryHtml(group, compact) {
        if (!state?.view?.show_history_charts) return "";
        const temp = entityById(group.temperature_entity_id);
        const humidity = entityById(group.humidity_entity_id);
        const parts = [];
        if (temp?.history_enabled && temp?.has_numeric_value) {
            parts.push(`<div class="gl-ha-climate-history"><span>Temperatur</span>${chartHtml(temp, compact)}</div>`);
        }
        if (humidity?.history_enabled && humidity?.has_numeric_value) {
            parts.push(`<div class="gl-ha-climate-history"><span>Luftfeuchte</span>${chartHtml(humidity, compact)}</div>`);
        }
        return parts.length ? `<div class="gl-ha-climate-history-grid">${parts.join("")}</div>` : "";
    }

    function comfortGroupHtml(group, compact) {
        const status = group?.comfort?.label || (group.is_available ? "Keine Bewertung" : "Nicht erreichbar");
        const temp = hasFiniteNumber(group.temperature) ? `${Number(group.temperature).toFixed(1)} ${esc(group.temperature_unit || "°C")}` : "–";
        const humidity = hasFiniteNumber(group.humidity) ? `${Number(group.humidity).toFixed(1)} ${esc(group.humidity_unit || "%")}` : "–";
        const tempEntity = entityById(group.temperature_entity_id);
        const humidityEntity = entityById(group.humidity_entity_id);
        const technical = state?.view?.show_entity_ids
            ? `<small>${esc(tempEntity?.entity_id || "")} · ${esc(humidityEntity?.entity_id || "")}</small>`
            : "";
        const base = compact ? "gl-ha-sensor gl-ha-item gl-ha-climate-card" : "gl-ha-entity gl-ha-item gl-ha-climate-card";
        return `<article class="${base}${comfortGroupClass(group)}${group.is_available ? "" : " offline"}" data-comfort-group-id="${group.id}">
            <div class="${compact ? "gl-ha-sensor-head" : "gl-ha-entity-head"}">
                <div>
                    <div class="${compact ? "gl-ha-sensor-name" : "gl-ha-climate-title"}">${esc(group.name)}</div>
                    ${technical}
                </div>
                <span class="gl-ha-dot" title="${group.is_available ? "Erreichbar" : "Nicht erreichbar"}"></span>
            </div>
            <div class="gl-ha-climate-values">
                <div><span>Temperatur</span><strong>${temp}</strong></div>
                <div><span>Luftfeuchtigkeit</span><strong>${humidity}</strong></div>
            </div>
            <div class="gl-ha-comfort-badge" title="${esc(status)}${group.mould_enabled ? " · Schimmelprüfung aktiv" : ""}">${esc(status)}</div>
            ${comfortGroupHistoryHtml(group, compact)}
        </article>`;
    }

    function thermostatHtml(zone) {
        const temp = hasFiniteNumber(zone.temperature) ? `${Number(zone.temperature).toFixed(1)} ${esc(zone.temperature_unit || "°C")}` : "–";
        const setpoint = hasFiniteNumber(zone.setpoint) ? Number(zone.setpoint).toFixed(1) : "–";
        const demand = zone.heat_demand ? "Heizt" : "Kein Wärmebedarf";
        const override = zone.manual_override_active
            ? `<div class="gl-ha-override">Manuell bis ${esc(formatDate(zone.manual_override_until))}</div>`
            : "";
        const canControl = Boolean(zone.can_control);
        const controls = canControl ? `<div class="gl-ha-thermostat-controls">
            <button type="button" class="gl-ha-thermostat-adjust" data-zone-id="${zone.id}" data-delta="-${Number(zone.step || 0.5)}" aria-label="Solltemperatur senken">−</button>
            <div class="gl-ha-thermostat-target"><span>Soll</span><strong>${setpoint} °C</strong></div>
            <button type="button" class="gl-ha-thermostat-adjust" data-zone-id="${zone.id}" data-delta="${Number(zone.step || 0.5)}" aria-label="Solltemperatur erhöhen">+</button>
            ${zone.manual_override_active ? `<button type="button" class="gl-ha-thermostat-command secondary" data-zone-id="${zone.id}" data-command="auto">Automatik</button>` : ""}
        </div>` : `<div class="gl-ha-thermostat-target readonly"><span>Soll</span><strong>${setpoint} °C</strong></div>`;
        const statusBits = [
            zone.valve?.name ? `Ventil ${zone.valve.on ? "EIN" : "AUS"}` : "",
            zone.pump?.name ? `Pumpe ${zone.pump.on ? "EIN" : "AUS"}` : "",
            zone.ventilation?.name ? `Lüftung ${zone.ventilation.on ? "EIN" : "AUS"}` : "",
        ].filter(Boolean).join(" · ");
        return `<article class="gl-ha-entity gl-ha-item gl-ha-thermostat${zone.heat_demand ? " active" : ""}${zone.is_available ? "" : " offline"}" data-thermostat-id="${zone.id}">
            <div class="gl-ha-entity-head">
                <div>
                    <h3>${esc(zone.name)}</h3>
                    <small>${esc(zone.setpoint_source || "Grundtemperatur")}</small>
                </div>
                <span class="gl-ha-dot" title="${zone.is_available ? "Temperatursensor erreichbar" : "Temperatursensor nicht verfügbar"}"></span>
            </div>
            <div class="gl-ha-thermostat-readings">
                <div><span>Ist</span><strong>${temp}</strong></div>
                <div><span>Status</span><strong>${esc(demand)}</strong></div>
            </div>
            ${controls}
            ${override}
            ${statusBits ? `<div class="gl-ha-thermostat-devices">${esc(statusBits)}</div>` : ""}
            ${zone.last_message ? `<div class="gl-ha-lastseen">${esc(zone.last_message)}</div>` : ""}
        </article>`;
    }

    function combinedDisplayItems(entities) {
        const entityIds = new Set(entities.map(entity => entity.id));
        const used = new Set();
        const groups = (state?.comfort_groups || [])
            .filter(group => {
                if (!entityIds.has(group.temperature_entity_id) || !entityIds.has(group.humidity_entity_id)) return false;
                const temp = entityById(group.temperature_entity_id);
                const humidity = entityById(group.humidity_entity_id);
                return temp?.display_role !== "control" && humidity?.display_role !== "control";
            })
            .map(group => ({
                ...group,
                is_comfort_group: true,
                display_role: "sensor",
                room: group.room || group.name || "Allgemein",
                dashboard_group: group.dashboard_group || "",
            }));
        groups.forEach(group => {
            used.add(group.temperature_entity_id);
            used.add(group.humidity_entity_id);
        });
        const thermostats = (state?.thermostats || []).map(zone => ({
            ...zone,
            is_thermostat: true,
            display_role: "control",
            room: zone.room || zone.name || "Heizung",
            dashboard_group: zone.room || zone.name || "Heizung",
        }));
        return [...entities.filter(entity => !used.has(entity.id)), ...groups, ...thermostats];
    }

    function sensorHtml(entity) {
        return `<article class="${statusClass(entity, "gl-ha-sensor gl-ha-item")}${comfortClass(entity)}" data-entity-id="${entity.id}">
            <div class="gl-ha-sensor-head">
                <div class="gl-ha-sensor-name">${esc(entity.name)}</div>
                <span class="gl-ha-dot" title="${entity.is_available ? "Erreichbar" : "Nicht erreichbar"}"></span>
            </div>
            ${technicalHtml(entity)}
            <div class="gl-ha-sensor-value">${esc(formatValue(entity))}</div>
            ${comfortBadge(entity)}
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
                    ${items.map(item => item.is_thermostat ? thermostatHtml(item) : (item.is_comfort_group ? comfortGroupHtml(item, compactSensors) : (compactSensors ? sensorHtml(item) : entityHtml(item)))).join("")}
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
        const rawEntities = state.entities || [];
        const entities = combinedDisplayItems(rawEntities);
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

    function comfortColor(code) {
        return {
            comfortable: "#4bd18b",
            acceptable: "#f2a744",
            uncomfortable: "#ff5055",
            mould: "#be69ff",
        }[code] || "#d7d7dc";
    }

    function renderComfortChart() {
        if (!comfortChartEl) return;
        if (!state?.view?.show_comfort_chart) {
            comfortChartEl.innerHTML = "";
            comfortChartEl.style.display = "none";
            return;
        }

        const requested = new Set((state?.view?.comfort_group_ids || []).map(Number));
        const groups = (state?.comfort_groups || []).filter(group =>
            (!requested.size || requested.has(Number(group.id)))
            && group.is_available
            && hasFiniteNumber(group.temperature)
            && hasFiniteNumber(group.humidity)
        );
        comfortChartEl.style.display = "block";
        if (!groups.length) {
            comfortChartEl.innerHTML = `<div class="gl-ha-section-head"><h2>Behaglichkeit</h2><span>Temperatur / Luftfeuchte</span></div>
                <div class="gl-ha-empty">Für dieses Diagramm sind noch keine vollständig verfügbaren Temperatur-/Feuchtegruppen ausgewählt.</div>`;
            return;
        }

        const model = state?.comfort_chart || {};
        const xMin = Number(model.x_min ?? 12), xMax = Number(model.x_max ?? 28);
        const yMin = Number(model.y_min ?? 0), yMax = Number(model.y_max ?? 100);
        const portrait = window.innerWidth < 700;
        const W = portrait ? 700 : 1100;
        const H = portrait ? 820 : 650;
        const margin = portrait
            ? {left: 88, right: 34, top: 70, bottom: 92}
            : {left: 92, right: 42, top: 52, bottom: 82};
        const plotW = W - margin.left - margin.right;
        const plotH = H - margin.top - margin.bottom;
        const x = value => margin.left + ((Number(value) - xMin) / (xMax - xMin)) * plotW;
        const y = value => margin.top + (1 - ((Number(value) - yMin) / (yMax - yMin))) * plotH;
        const polygonPoints = polygon => (polygon || []).map(([px, py]) => `${x(px).toFixed(1)},${y(py).toFixed(1)}`).join(" ");
        const acceptable = polygonPoints(model.acceptable_polygon || []);
        const comfortable = polygonPoints(model.comfortable_polygon || []);

        const xTicks = [];
        for (let t = 12; t <= 28; t += 2) xTicks.push(t);
        const yTicks = [];
        for (let h = 0; h <= 100; h += 10) yTicks.push(h);

        const grid = [
            ...xTicks.map(t => `<line x1="${x(t)}" y1="${margin.top}" x2="${x(t)}" y2="${margin.top + plotH}" class="gl-ha-comfort-grid-line"/><text x="${x(t)}" y="${margin.top + plotH + 30}" text-anchor="middle" class="gl-ha-comfort-axis-tick">${t}</text>`),
            ...yTicks.map(h => `<line x1="${margin.left}" y1="${y(h)}" x2="${margin.left + plotW}" y2="${y(h)}" class="gl-ha-comfort-grid-line"/><text x="${margin.left - 14}" y="${y(h) + 5}" text-anchor="end" class="gl-ha-comfort-axis-tick">${h}</text>`),
        ].join("");

        const plotted = groups.filter(group => Number(group.temperature) >= xMin && Number(group.temperature) <= xMax && Number(group.humidity) >= yMin && Number(group.humidity) <= yMax);
        const points = plotted.map((group, index) => {
            const px = x(group.temperature), py = y(group.humidity);
            const color = comfortColor(group?.comfort?.code);
            const dx = index % 2 === 0 ? 13 : -13;
            const anchor = dx > 0 ? "start" : "end";
            const dy = index % 3 === 0 ? -13 : 22;
            const label = `${group.name} · ${Number(group.temperature).toFixed(1)} °C / ${Number(group.humidity).toFixed(0)} %`;
            return `<g class="gl-ha-comfort-point">
                <circle cx="${px}" cy="${py}" r="9" fill="${color}" stroke="rgba(255,255,255,.95)" stroke-width="3"><title>${esc(label)} · ${esc(group?.comfort?.label || "")}</title></circle>
                <text x="${px + dx}" y="${py + dy}" text-anchor="${anchor}" class="gl-ha-comfort-point-label" style="paint-order:stroke;stroke:#0a0a0b;stroke-width:5px;stroke-linejoin:round;">${esc(group.name)}</text>
            </g>`;
        }).join("");

        const unplotted = groups.length - plotted.length;
        const note = unplotted ? ` · ${unplotted} Punkt${unplotted === 1 ? "" : "e"} außerhalb 12–28 °C / 0–100 %` : "";
        comfortChartEl.innerHTML = `
            <div class="gl-ha-section-head"><h2>Behaglichkeit</h2><span>${groups.length} Räume${esc(note)}</span></div>
            <div class="gl-ha-comfort-diagram">
                <svg class="gl-ha-comfort-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Behaglichkeitsdiagramm für Raumlufttemperatur und relative Luftfeuchtigkeit">
                    <rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" rx="4" class="gl-ha-comfort-zone-uncomfortable"/>
                    ${grid}
                    <polygon points="${acceptable}" class="gl-ha-comfort-zone-acceptable"/>
                    <polygon points="${comfortable}" class="gl-ha-comfort-zone-comfortable"/>
                    <rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="none" class="gl-ha-comfort-frame"/>
                    <text x="${margin.left + plotW / 2}" y="${H - 22}" text-anchor="middle" class="gl-ha-comfort-axis-title">Raumlufttemperatur [°C]</text>
                    <text transform="translate(26 ${margin.top + plotH / 2}) rotate(-90)" text-anchor="middle" class="gl-ha-comfort-axis-title">Relative Raumluftfeuchte [%]</text>
                    <text x="${x(20.6)}" y="${y(55)}" text-anchor="middle" class="gl-ha-comfort-zone-label">behaglich</text>
                    <text x="${x(22.2)}" y="${y(24)}" text-anchor="middle" class="gl-ha-comfort-zone-label muted">noch behaglich</text>
                    <text x="${x(14.2)}" y="${y(12)}" text-anchor="middle" class="gl-ha-comfort-zone-label muted">unbehaglich trocken</text>
                    <text x="${x(25.0)}" y="${y(88)}" text-anchor="middle" class="gl-ha-comfort-zone-label muted">unbehaglich feucht</text>
                    ${points}
                </svg>
                <div class="gl-ha-comfort-legend">
                    <span><i class="comfortable"></i>Behaglich</span>
                    <span><i class="acceptable"></i>Noch behaglich</span>
                    <span><i class="uncomfortable"></i>Außerhalb Bereich</span>
                    <span><i class="mould"></i>Schimmelrisiko erhöht</span>
                </div>
            </div>`;
    }

    function chartValueLabel(value, unit, range) {
        if (!Number.isFinite(value)) return "–";
        const absRange = Math.abs(Number(range || 0));
        let digits = 1;
        if (absRange >= 100) digits = 0;
        else if (absRange > 0 && absRange < 2) digits = 2;
        const formatted = new Intl.NumberFormat("de-DE", {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(value);
        return `${formatted}${unit ? " " + unit : ""}`;
    }

    function chartTimeLabel(timestamp, hours) {
        const date = parseUtc(timestamp);
        if (!date || Number.isNaN(date.getTime())) return "";
        const longPeriod = Number(hours || 24) > 48;
        return new Intl.DateTimeFormat("de-DE", longPeriod
            ? {day: "2-digit", month: "2-digit"}
            : {hour: "2-digit", minute: "2-digit"}
        ).format(date);
    }

    function drawChart(canvas, points, entity) {
        if (!points || points.length < 2) return;
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const width = Math.max(180, Math.floor(rect.width));
        const height = Math.max(82, Math.floor(rect.height));
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        const ctx = canvas.getContext("2d");
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, width, height);

        const validPoints = points
            .map((p, index) => ({...p, _index: index, _value: Number(p.v), _time: parseUtc(p.t)?.getTime()}))
            .filter(p => Number.isFinite(p._value));
        if (validPoints.length < 2) return;

        const values = validPoints.map(p => p._value);
        let min = Math.min(...values);
        let max = Math.max(...values);
        if (min === max) { min -= 1; max += 1; }
        const range = max - min;
        // Kleine Reserve, damit Min/Max-Werte nicht direkt auf dem Rahmen kleben.
        const yReserve = range * 0.06;
        const chartMin = min - yReserve;
        const chartMax = max + yReserve;
        const chartRange = chartMax - chartMin;

        const compact = canvas.closest(".gl-ha-chart-wrap")?.classList.contains("compact");
        const left = compact ? 49 : 54;
        const right = 7;
        const top = 8;
        const bottom = compact ? 21 : 23;
        const plotW = Math.max(1, width - left - right);
        const plotH = Math.max(1, height - top - bottom);
        const unit = entity?.unit || "";
        const hours = Number(periodEl?.value || state?.dashboard?.history_hours || 24);

        const timed = validPoints.filter(p => Number.isFinite(p._time));
        const minTime = timed.length ? Math.min(...timed.map(p => p._time)) : null;
        const maxTime = timed.length ? Math.max(...timed.map(p => p._time)) : null;
        const timeRange = minTime != null && maxTime != null && maxTime > minTime ? maxTime - minTime : null;
        const xFor = (p, i) => {
            if (timeRange && Number.isFinite(p._time)) return left + plotW * ((p._time - minTime) / timeRange);
            return left + plotW * (i / Math.max(1, validPoints.length - 1));
        };
        const yFor = value => top + plotH * (1 - ((value - chartMin) / chartRange));

        // Raster und Y-Achsenwerte: oben, Mitte, unten.
        ctx.font = `${compact ? 9 : 10}px Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.textBaseline = "middle";
        const yTicks = [max, (max + min) / 2, min];
        yTicks.forEach((value, index) => {
            const y = top + plotH * (index / 2);
            ctx.strokeStyle = "rgba(255,255,255,.10)";
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
            ctx.fillStyle = "rgba(210,210,218,.72)";
            ctx.textAlign = "right";
            ctx.fillText(chartValueLabel(value, unit, range), left - 6, y);
        });

        // X-Achse: tatsächlicher Beginn, Mitte und Ende des gelieferten Verlaufs.
        const first = validPoints[0];
        const last = validPoints[validPoints.length - 1];
        let middle = validPoints[Math.floor((validPoints.length - 1) / 2)];
        if (timeRange) {
            const midTime = minTime + timeRange / 2;
            middle = validPoints.reduce((best, p) => {
                if (!Number.isFinite(p._time)) return best;
                if (!best || Math.abs(p._time - midTime) < Math.abs(best._time - midTime)) return p;
                return best;
            }, null) || middle;
        }
        const xTicks = width < 320 ? [first, last] : [first, middle, last];
        ctx.textBaseline = "bottom";
        xTicks.forEach((point, index) => {
            const x = xFor(point, validPoints.indexOf(point));
            ctx.strokeStyle = "rgba(255,255,255,.07)";
            ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + plotH); ctx.stroke();
            ctx.fillStyle = "rgba(210,210,218,.68)";
            ctx.textAlign = index === 0 ? "left" : (index === xTicks.length - 1 ? "right" : "center");
            ctx.fillText(chartTimeLabel(point.t, hours), x, height - 2);
        });

        // Verlaufslinie.
        ctx.save();
        ctx.beginPath();
        ctx.rect(left, top, plotW, plotH);
        ctx.clip();
        ctx.strokeStyle = "#ff3b3f";
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        validPoints.forEach((p, i) => {
            const x = xFor(p, i);
            const y = yFor(p._value);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.restore();
    }

    function drawAllCharts() {
        document.querySelectorAll("canvas.gl-ha-chart").forEach(canvas => {
            const entityId = Number(canvas.dataset.entityId);
            const entity = (state?.entities || []).find(item => item.id === entityId);
            drawChart(canvas, history[String(entityId)] || [], entity);
        });
    }

    function renderAll() {
        periodEl.style.display = state?.view?.show_history_charts ? "block" : "none";
        renderStatus();
        renderAlerts();
        renderWindows();
        renderComfortChart();
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
            history = await rpc(`${apiBase}/history`, {
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
            state = await rpc(`${apiBase}/data`, {slug, page_slug: pageSlug});
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
            const updated = await rpc(`${apiBase}/command`, {
                slug,
                page_slug: pageSlug,
                entity_id: entity.id,
                command,
                value,
                override_minutes: null,
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

    async function sendThermostatCommand(zoneId, command, value) {
        const zone = (state?.thermostats || []).find(item => item.id === Number(zoneId));
        if (!zone) return;
        const card = document.querySelector(`[data-thermostat-id="${zone.id}"]`);
        if (card) card.classList.add("busy");
        try {
            await rpc(`${apiBase}/thermostat-command`, {
                slug,
                page_slug: pageSlug,
                zone_id: zone.id,
                command,
                value: value == null ? null : Number(value),
                override_minutes: null,
            });
            await loadData(false);
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
        const thermostatAdjust = event.target.closest(".gl-ha-thermostat-adjust");
        if (thermostatAdjust) {
            sendThermostatCommand(thermostatAdjust.dataset.zoneId, "adjust", thermostatAdjust.dataset.delta);
            return;
        }
        const thermostatCommand = event.target.closest(".gl-ha-thermostat-command");
        if (thermostatCommand) {
            sendThermostatCommand(thermostatCommand.dataset.zoneId, thermostatCommand.dataset.command, null);
            return;
        }
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
    window.addEventListener("resize", () => {
        renderComfortChart();
        drawAllCharts();
    });

    loadData(true);
})();
