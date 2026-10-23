(function () {
    "use strict";

    const app = document.getElementById("gl-kino-pos-app");
    if (!app) return;

    const publicId = app.dataset.publicId || "";
    const accessMode = app.dataset.accessMode || "device";
    const isInternal = accessMode === "internal";
    const routes = isInternal ? {
        data: "/kino-pos/data",
        todo: "/kino-pos/todo",
        solve: "/kino-pos/ticket/solve",
    } : {
        data: "/kino-pos/device/data",
        todo: "/kino-pos/device/todo",
        solve: "/kino-pos/device/ticket/solve",
    };
    const encoder = new TextEncoder();
    let deviceKeyPromise = null;
    let refreshTimer = null;
    let loading = false;

    const denominations = [500, 200, 100, 50, 20, 10, 5, 2, 1, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01];
    const cashStorageKey = `gl_kino_pos_cash_${isInternal ? "internal" : publicId}`;
    let cashState = loadCashState();

    function esc(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

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
            const req = indexedDB.open("gl_kino_pos_device_keys", 1);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains("keys")) db.createObjectStore("keys");
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error || new Error("Geräteschlüsselspeicher konnte nicht geöffnet werden."));
        });
    }

    async function getDevicePrivateKey() {
        if (!deviceKeyPromise) {
            deviceKeyPromise = (async () => {
                const db = await openDeviceKeyDb();
                try {
                    return await new Promise((resolve, reject) => {
                        const tx = db.transaction("keys", "readonly");
                        const req = tx.objectStore("keys").get(publicId);
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
            throw new Error("Der lokale Geräteschlüssel fehlt. Bitte diesen Rechner in Odoo unter Kino POS → Gerätezugänge neu binden.");
        }
        return key;
    }

    async function signedHeaders(url, params) {
        const key = await getDevicePrivateKey();
        const timestamp = String(Date.now());
        const nonce = b64url(crypto.getRandomValues(new Uint8Array(18)));
        const digest = await crypto.subtle.digest("SHA-256", encoder.encode(canonicalJson(params || {})));
        const message = `${timestamp}\n${nonce}\n${url}\n${hex(digest)}`;
        const signature = await crypto.subtle.sign(
            {name: "ECDSA", hash: "SHA-256"},
            key,
            encoder.encode(message)
        );
        return {
            "X-GL-KINO-POS-Device": publicId,
            "X-GL-KINO-POS-Timestamp": timestamp,
            "X-GL-KINO-POS-Nonce": nonce,
            "X-GL-KINO-POS-Signature": b64url(signature),
        };
    }

    async function rpc(url, params) {
        const rpcParams = params || {};
        const headers = {"Content-Type": "application/json"};
        if (!isInternal) {
            Object.assign(headers, await signedHeaders(url, rpcParams));
        }
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers,
            body: JSON.stringify({jsonrpc: "2.0", method: "call", params: rpcParams, id: Date.now()}),
        });
        const payload = await response.json();
        if (payload.error) {
            const msg = payload.error?.data?.message || payload.error?.message || "Unbekannter Odoo-Fehler";
            throw new Error(msg);
        }
        return payload.result;
    }

    function showError(message) {
        const el = document.getElementById("gl-kino-pos-error");
        if (!message) {
            el.hidden = true;
            el.textContent = "";
            return;
        }
        el.textContent = message;
        el.hidden = false;
    }

    function formatDay(value) {
        const parts = String(value || "").split("-");
        if (parts.length !== 3) return value || "";
        return `${parts[2]}.${parts[1]}.${parts[0]}`;
    }

    function renderHeader(data) {
        document.getElementById("gl-kino-pos-greeting").textContent = data.greeting || "Hallo, schön, dass du da bist";
        const shift = document.getElementById("gl-kino-pos-shift");
        if (data.shift?.employee) {
            shift.textContent = `Kinoschicht am ${formatDay(data.today)} · ${data.shift.employee}`;
            shift.classList.remove("warning");
        } else {
            shift.textContent = `Heute (${formatDay(data.today)}) ist keine besetzte Kinoschicht im Dienstplan eingetragen.`;
            shift.classList.add("warning");
        }
        const ha = document.getElementById("gl-kino-pos-ha");
        if (data.ha_url) {
            ha.href = data.ha_url;
            ha.hidden = false;
        } else {
            ha.hidden = true;
        }
    }

    function renderTickets(data) {
        const container = document.getElementById("gl-kino-pos-tickets");
        const tickets = data.tickets || [];
        document.getElementById("gl-kino-pos-ticket-count").textContent = String(tickets.length);
        if (!tickets.length) {
            container.innerHTML = `<div class="gl-kino-pos-empty"><span>✓</span><strong>Keine offenen Kinoreservierungen</strong><small>Neue Fonio-Anfragen erscheinen automatisch.</small></div>`;
            return;
        }
        container.innerHTML = tickets.map(ticket => {
            const fields = (ticket.fields || []).map(field => {
                let value = esc(field.value || "–");
                if (field.key === "caller_phone" && ticket.phone) {
                    value = `<a class="gl-kino-pos-phone" href="tel:${esc(ticket.phone)}">${value}</a>`;
                }
                const wide = field.key === "summary" ? " wide" : "";
                return `<div class="gl-kino-pos-ticket-field${wide}"><span>${esc(field.label)}</span><strong>${value}</strong></div>`;
            }).join("");
            return `
                <article class="gl-kino-pos-ticket" data-ticket-id="${ticket.id}">
                    <div class="gl-kino-pos-ticket-top">
                        <div>
                            <div class="gl-kino-pos-ticket-id">${esc(ticket.ticket_name)}</div>
                            <div class="gl-kino-pos-ticket-time">Eingegangen: ${esc(ticket.created_at || "–")}</div>
                        </div>
                        <button type="button" class="gl-kino-pos-solve" data-ticket-id="${ticket.id}">Als gelöst markieren</button>
                    </div>
                    <div class="gl-kino-pos-ticket-grid">${fields}</div>
                </article>`;
        }).join("");

        container.querySelectorAll(".gl-kino-pos-solve").forEach(button => {
            button.addEventListener("click", async () => {
                const ticketId = Number(button.dataset.ticketId || 0);
                if (!ticketId) return;
                if (!window.confirm("Reservierung wirklich als gelöst markieren? Das Kundenticket wird in die Phase „Gelöst“ verschoben.")) return;
                button.disabled = true;
                try {
                    const result = await rpc(routes.solve, {ticket_id: ticketId});
                    showError("");
                    renderAll(result);
                } catch (error) {
                    showError(error?.message || "Das Ticket konnte nicht gelöst werden.");
                    button.disabled = false;
                }
            });
        });
    }

    function renderTodos(data) {
        const container = document.getElementById("gl-kino-pos-todos");
        const thanks = document.getElementById("gl-kino-pos-todo-thanks");
        const todos = data.todos || [];
        thanks.hidden = !data.todos_all_done;

        if (!data.shift?.employee) {
            container.innerHTML = `<div class="gl-kino-pos-empty compact"><strong>Keine Schicht erkannt</strong><small>Aufgaben werden angezeigt, sobald für heute eine Person im Kino-Dienstplan eingetragen ist.</small></div>`;
            return;
        }
        if (!todos.length) {
            container.innerHTML = `<div class="gl-kino-pos-empty compact"><strong>Keine Aufgaben fällig</strong><small>Im Backend können unter „Was gibt's zu tun“ Aufgaben angelegt werden.</small></div>`;
            return;
        }
        container.innerHTML = todos.map(todo => `
            <label class="gl-kino-pos-todo ${todo.checked ? "done" : ""}">
                <input type="checkbox" data-item-id="${todo.id}" ${todo.checked ? "checked" : ""}/>
                <span class="gl-kino-pos-checkmark"></span>
                <span class="gl-kino-pos-todo-copy">
                    <strong>${esc(todo.name)}</strong>
                    <small>${esc(todo.frequency_label || "")}${todo.note ? ` · ${esc(todo.note)}` : ""}</small>
                </span>
            </label>`).join("");

        container.querySelectorAll('input[type="checkbox"]').forEach(input => {
            input.addEventListener("change", async () => {
                const itemId = Number(input.dataset.itemId || 0);
                const checked = input.checked;
                input.disabled = true;
                try {
                    const result = await rpc(routes.todo, {item_id: itemId, checked});
                    showError("");
                    renderAll(result);
                } catch (error) {
                    input.checked = !checked;
                    input.disabled = false;
                    showError(error?.message || "Die Aufgabe konnte nicht gespeichert werden.");
                }
            });
        });
    }

    function loadCashState() {
        try {
            const raw = JSON.parse(localStorage.getItem(cashStorageKey) || "{}");
            return raw && typeof raw === "object" ? raw : {};
        } catch (_) {
            return {};
        }
    }

    function saveCashState() {
        localStorage.setItem(cashStorageKey, JSON.stringify(cashState));
    }

    function denominationKey(value) {
        return Number(value).toFixed(2);
    }

    function formatMoney(value) {
        return new Intl.NumberFormat("de-DE", {style: "currency", currency: "EUR"}).format(Number(value || 0));
    }

    function denominationLabel(value) {
        if (value >= 5) return `${Number(value).toLocaleString("de-DE")} €`;
        if (value >= 1) return `${Number(value).toLocaleString("de-DE", {minimumFractionDigits: 0, maximumFractionDigits: 0})} €`;
        return `${Math.round(value * 100)} ct`;
    }

    function updateCashTotal() {
        let total = 0;
        denominations.forEach(value => {
            const count = Math.max(0, Number(cashState[denominationKey(value)] || 0));
            total += value * count;
        });
        document.getElementById("gl-kino-pos-cash-total").textContent = formatMoney(total);
    }

    function renderCash() {
        const container = document.getElementById("gl-kino-pos-cash");
        container.innerHTML = denominations.map(value => {
            const key = denominationKey(value);
            const count = Math.max(0, parseInt(cashState[key] || 0, 10) || 0);
            return `
                <div class="gl-kino-pos-cash-row" data-key="${key}" data-value="${value}">
                    <span class="gl-kino-pos-denomination">${denominationLabel(value)}</span>
                    <div class="gl-kino-pos-stepper">
                        <button type="button" class="minus" aria-label="Minus">−</button>
                        <input type="number" min="0" step="1" inputmode="numeric" value="${count}" aria-label="Anzahl ${denominationLabel(value)}"/>
                        <button type="button" class="plus" aria-label="Plus">+</button>
                    </div>
                    <strong class="gl-kino-pos-line-total">${formatMoney(value * count)}</strong>
                </div>`;
        }).join("");

        container.querySelectorAll(".gl-kino-pos-cash-row").forEach(row => {
            const key = row.dataset.key;
            const value = Number(row.dataset.value || 0);
            const input = row.querySelector("input");
            const lineTotal = row.querySelector(".gl-kino-pos-line-total");
            const setCount = next => {
                const count = Math.max(0, Math.floor(Number(next) || 0));
                cashState[key] = count;
                input.value = String(count);
                lineTotal.textContent = formatMoney(value * count);
                saveCashState();
                updateCashTotal();
            };
            row.querySelector(".minus").addEventListener("click", () => setCount(Number(input.value || 0) - 1));
            row.querySelector(".plus").addEventListener("click", () => setCount(Number(input.value || 0) + 1));
            input.addEventListener("input", () => setCount(input.value));
        });
        updateCashTotal();
    }

    function renderAll(data) {
        renderHeader(data);
        renderTickets(data);
        renderTodos(data);
        const seconds = Math.max(Number(data.refresh_seconds || 30), 10);
        window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(loadData, seconds * 1000);
    }

    async function loadData() {
        if (loading) return;
        loading = true;
        try {
            const data = await rpc(routes.data, {});
            showError("");
            renderAll(data);
        } catch (error) {
            console.error(error);
            showError(error?.message || "Kino POS konnte nicht aktualisiert werden.");
            window.clearTimeout(refreshTimer);
            refreshTimer = window.setTimeout(loadData, 15000);
        } finally {
            loading = false;
        }
    }

    document.getElementById("gl-kino-pos-cash-reset").addEventListener("click", () => {
        if (!window.confirm("Geldzähler wirklich vollständig auf 0 setzen?")) return;
        cashState = {};
        saveCashState();
        renderCash();
    });

    renderCash();
    loadData();
})();
