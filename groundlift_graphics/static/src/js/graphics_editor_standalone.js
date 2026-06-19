(() => {
    "use strict";

    const root = document.getElementById("gl-editor-root");
    const posterId = parseInt(root?.dataset?.posterId || "0", 10);
    const APP_VERSION = "19.0.1.3.5";

    const state = {
        loading: true,
        saving: false,
        data: null,
        selectedTemplateKey: "",
        sourceImageBase64: "",
        sourceImageFilename: "",
        externalLogoBase64: "",
        externalLogoFilename: "",
        qrImageBase64: "",
        fields: {},
        editorState: {},
        templateCache: new Map(),
        imageEditMode: "global",
        activeHandle: null,
    };

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function dataUrlFromBase64(base64, mime = "image/png") {
        return base64 ? `data:${mime};base64,${base64}` : "";
    }

    function extensionMime(filename, fallback = "image/png") {
        const extension = (filename || "").split(".").pop().toLowerCase();
        return ({ png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" }[extension]) || fallback;
    }

    function fontMime(filename) {
        const extension = (filename || "").split(".").pop().toLowerCase();
        return ({ ttf: "font/ttf", otf: "font/otf", woff: "font/woff", woff2: "font/woff2" }[extension]) || "font/ttf";
    }

    async function registerEditorFonts(templateInfo) {
        const fonts = [
            ["GroundliftRegular", templateInfo?.font_regular_file, templateInfo?.font_regular_filename],
            ["GroundliftBold", templateInfo?.font_bold_file, templateInfo?.font_bold_filename],
            ["GroundliftCondensed", templateInfo?.font_condensed_file, templateInfo?.font_condensed_filename],
        ];
        for (const [family, base64, filename] of fonts) {
            if (!base64 || !("FontFace" in window)) continue;
            try {
                const face = new FontFace(family, `url(${dataUrlFromBase64(base64, fontMime(filename))})`);
                await face.load();
                document.fonts.add(face);
            } catch (error) {
                console.warn(`Font konnte nicht geladen werden: ${family}`, error);
            }
        }
        try {
            await document.fonts.ready;
        } catch {
            // ignore
        }
    }

    const FONT_REGULAR = "GroundliftRegular, Arial, sans-serif";
    const FONT_BOLD = "GroundliftBold, Arial Black, Arial, sans-serif";
    const FONT_CONDENSED = "GroundliftCondensed, Arial Narrow, Arial, sans-serif";

    async function rpc(model, method, args = [], kwargs = {}) {
        const response = await fetch("/web/dataset/call_kw", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: { model, method, args, kwargs },
                id: Date.now(),
            }),
        });
        const payload = await response.json();
        if (payload.error) {
            throw new Error(payload.error.data?.message || payload.error.message || "RPC Fehler");
        }
        return payload.result;
    }

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (c) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;",
        }[c]));
    }

    function loadImage(src) {
        return new Promise((resolve, reject) => {
            if (!src) {
                resolve(null);
                return;
            }
            const img = new Image();
            try {
                const parsed = new URL(src, window.location.href);
                if (parsed.protocol.startsWith("http") && parsed.origin !== window.location.origin) {
                    img.crossOrigin = "anonymous";
                }
            } catch {
                // Relative oder data:-URL. Kein crossOrigin setzen, damit Odoo-Static-Dateien und Base64-Bilder sicher laden.
            }
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error(`Bild konnte nicht geladen werden: ${String(src).slice(0, 160)}`));
            img.src = src;
        });
    }

    async function safeLayer(label, fn) {
        try {
            return await fn();
        } catch (error) {
            console.warn(`Grafik-Layer übersprungen: ${label}`, error);
            return null;
        }
    }

    function safeDrawImage(ctx, image, x, y, width, height, label = "Bild") {
        if (!ctx || !image) return;
        try {
            if (Number.isFinite(width) && Number.isFinite(height)) {
                ctx.drawImage(image, x, y, width, height);
            } else {
                ctx.drawImage(image, x || 0, y || 0);
            }
        } catch (error) {
            console.warn(`Grafik-Layer konnte nicht gezeichnet werden: ${label}`, error);
        }
    }

    function alphaGeometry(image) {
        if (!image) return null;
        const canvas = document.createElement("canvas");
        canvas.width = image.width;
        canvas.height = image.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(image, 0, 0);
        const { data, width, height } = ctx.getImageData(0, 0, canvas.width, canvas.height);
        let minX = width, minY = height, maxX = -1, maxY = -1;
        let tl = null, tr = null, br = null, bl = null;
        let tlScore = Infinity, trScore = -Infinity, brScore = -Infinity, blScore = Infinity;
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const alpha = data[(y * width + x) * 4 + 3];
                if (alpha <= 8) continue;
                minX = Math.min(minX, x); minY = Math.min(minY, y);
                maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
                const sum = x + y;
                const diff = x - y;
                if (sum < tlScore) { tlScore = sum; tl = { x, y }; }
                if (diff > trScore) { trScore = diff; tr = { x, y }; }
                if (sum > brScore) { brScore = sum; br = { x, y }; }
                if (diff < blScore) { blScore = diff; bl = { x, y }; }
            }
        }
        if (maxX < minX || maxY < minY) return null;
        return {
            bbox: { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 },
            corners: (tl && tr && br && bl) ? [tl, tr, br, bl] : null,
        };
    }

    function drawPolygonPath(ctx, points) {
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
        ctx.closePath();
    }

    function pointInPolygon(x, y, points) {
        if (!points || points.length < 3) return false;
        let inside = false;
        for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
            const xi = points[i].x, yi = points[i].y;
            const xj = points[j].x, yj = points[j].y;
            const intersect = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-6) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function unionBoxes(boxes) {
        const valid = (boxes || []).filter(Boolean);
        if (!valid.length) return null;
        const minX = Math.min(...valid.map((b) => b.x));
        const minY = Math.min(...valid.map((b) => b.y));
        const maxX = Math.max(...valid.map((b) => b.x + b.width));
        const maxY = Math.max(...valid.map((b) => b.y + b.height));
        return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    }

    function insetBox(box, xInset = 0, yInset = xInset) {
        if (!box) return null;
        return {
            x: box.x + xInset,
            y: box.y + yInset,
            width: Math.max(1, box.width - xInset * 2),
            height: Math.max(1, box.height - yInset * 2),
        };
    }

    function boxCenter(box) {
        return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    }

    function groupedAlphaRegions(image) {
        if (!image) return [];
        const base = Math.max(image.width, image.height);
        const downsample = Math.max(1, Math.round(base / 900));
        const width = Math.max(1, Math.round(image.width / downsample));
        const height = Math.max(1, Math.round(image.height / downsample));
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(image, 0, 0, width, height);
        const { data } = ctx.getImageData(0, 0, width, height);
        const occupied = new Uint8Array(width * height);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                if (data[(y * width + x) * 4 + 3] > 8) occupied[y * width + x] = 1;
            }
        }

        const dilate = 2;
        const expanded = new Uint8Array(width * height);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                if (!occupied[y * width + x]) continue;
                for (let dy = -dilate; dy <= dilate; dy++) {
                    for (let dx = -dilate; dx <= dilate; dx++) {
                        const nx = x + dx;
                        const ny = y + dy;
                        if (nx >= 0 && ny >= 0 && nx < width && ny < height) expanded[ny * width + nx] = 1;
                    }
                }
            }
        }

        const visited = new Uint8Array(width * height);
        const boxes = [];
        const minArea = Math.max(4, Math.round(width * height * 0.000035));
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const startIdx = y * width + x;
                if (!expanded[startIdx] || visited[startIdx]) continue;
                const qx = [x], qy = [y];
                visited[startIdx] = 1;
                let head = 0, area = 0, minX = x, minY = y, maxX = x, maxY = y;
                while (head < qx.length) {
                    const cx = qx[head], cy = qy[head];
                    head += 1;
                    area += 1;
                    minX = Math.min(minX, cx); minY = Math.min(minY, cy);
                    maxX = Math.max(maxX, cx); maxY = Math.max(maxY, cy);
                    for (const [dx, dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
                        const nx = cx + dx, ny = cy + dy;
                        if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
                        const idx = ny * width + nx;
                        if (!expanded[idx] || visited[idx]) continue;
                        visited[idx] = 1;
                        qx.push(nx); qy.push(ny);
                    }
                }
                if (area >= minArea) {
                    boxes.push({
                        x: minX * downsample,
                        y: minY * downsample,
                        width: (maxX - minX + 1) * downsample,
                        height: (maxY - minY + 1) * downsample,
                    });
                }
            }
        }
        return boxes
            .filter((b) => b.width > 2 && b.height > 2)
            .sort((a, b) => a.y - b.y || a.x - b.x);
    }

    function drawCroppedLayer(ctx, image, sourceBox, targetBox) {
        if (!ctx || !image || !sourceBox || !targetBox) return;
        if (sourceBox.width <= 0 || sourceBox.height <= 0 || targetBox.width <= 0 || targetBox.height <= 0) return;
        ctx.drawImage(
            image,
            sourceBox.x, sourceBox.y, sourceBox.width, sourceBox.height,
            targetBox.x, targetBox.y, targetBox.width, targetBox.height
        );
    }

    function drawLayerPreserveAspect(ctx, image, sourceBox, targetBox) {
        if (!ctx || !image || !sourceBox || !targetBox) return;
        if (sourceBox.width <= 0 || sourceBox.height <= 0 || targetBox.width <= 0 || targetBox.height <= 0) return;
        const scale = Math.min(targetBox.width / sourceBox.width, targetBox.height / sourceBox.height);
        const width = sourceBox.width * scale;
        const height = sourceBox.height * scale;
        const x = targetBox.x + (targetBox.width - width) / 2;
        const y = targetBox.y + (targetBox.height - height) / 2;
        ctx.drawImage(image, sourceBox.x, sourceBox.y, sourceBox.width, sourceBox.height, x, y, width, height);
    }

    function currentTemplate() {
        return state.data.templates.find((t) => t.key === state.selectedTemplateKey) || state.data.templates[0];
    }

    function defaultImageTransform() {
        return { offsetX: 0, offsetY: 0, scale: 1, rotation: 0 };
    }

    function ensureGlobalImageTransform() {
        state.editorState.globalImage = state.editorState.globalImage || defaultImageTransform();
        for (const key of ["offsetX", "offsetY", "scale", "rotation"]) {
            if (typeof state.editorState.globalImage[key] !== "number") {
                state.editorState.globalImage[key] = defaultImageTransform()[key];
            }
        }
        return state.editorState.globalImage;
    }

    function ensureVariant(templateKey) {
        state.editorState.variants = state.editorState.variants || {};
        if (!state.editorState.variants[templateKey]) {
            state.editorState.variants[templateKey] = {
                image: { ...defaultImageTransform() },
                imageCustom: false,
                qr: { dx: 0, dy: 0, scale: 1 },
                externalLogo: { dx: 0, dy: 0, scale: 1 },
                sticker: { dx: 0, dy: 0, scale: 1 },
            };
        }
        state.editorState.variants[templateKey].image = state.editorState.variants[templateKey].image || { ...defaultImageTransform() };
        state.editorState.variants[templateKey].qr = state.editorState.variants[templateKey].qr || { dx: 0, dy: 0, scale: 1 };
        state.editorState.variants[templateKey].externalLogo = state.editorState.variants[templateKey].externalLogo || { dx: 0, dy: 0, scale: 1 };
        state.editorState.variants[templateKey].sticker = state.editorState.variants[templateKey].sticker || { dx: 0, dy: 0, scale: 1 };
        return state.editorState.variants[templateKey];
    }

    function getImageTransform(templateKey) {
        const variant = ensureVariant(templateKey);
        if (variant.imageCustom) return variant.image;
        return ensureGlobalImageTransform();
    }

    function cacheBustedUrl(url) {
        if (!url || String(url).startsWith("data:")) return url;
        const separator = String(url).includes("?") ? "&" : "?";
        return `${url}${separator}v=${encodeURIComponent(APP_VERSION)}`;
    }

    function setImageTransform(templateKey, transform, forceLocal = false) {
        const variant = ensureVariant(templateKey);
        const clean = {
            offsetX: Number(transform.offsetX || 0),
            offsetY: Number(transform.offsetY || 0),
            scale: clamp(Number(transform.scale || 1), 0.2, 5),
            rotation: Number(transform.rotation || 0),
        };
        if (state.imageEditMode === "local" || forceLocal) {
            variant.imageCustom = true;
            variant.image = clean;
        } else {
            state.editorState.globalImage = clean;
            for (const tmpl of state.data?.templates || []) {
                const v = ensureVariant(tmpl.key);
                if (!v.imageCustom) v.image = { ...clean };
            }
        }
    }

    async function ensureTemplateAssets(template) {
        if (!template) return null;
        if (state.templateCache.has(template.key)) return state.templateCache.get(template.key);
        const imagesByRole = {};
        const bboxes = {};
        const geometries = {};
        const regions = {};
        const staticOverlays = [];
        for (const asset of template.assets || []) {
            try {
                const image = await loadImage(cacheBustedUrl(asset.url));
                if (!image) continue;
                if (!imagesByRole[asset.role]) imagesByRole[asset.role] = image;
                if (asset.role.startsWith("static_")) staticOverlays.push({ role: asset.role, image });
                const geometry = alphaGeometry(image);
                geometries[asset.role] = geometry;
                bboxes[asset.role] = geometry ? geometry.bbox : null;
                if (["date_title", "time_subtitle", "time_ticketlink", "title", "subtitle"].includes(asset.role)) {
                    regions[asset.role] = groupedAlphaRegions(image);
                }
            } catch (error) {
                console.warn("Template asset konnte nicht geladen werden", asset, error);
            }
        }
        const info = { template, imagesByRole, bboxes, geometries, regions, staticOverlays };
        state.templateCache.set(template.key, info);
        return info;
    }

    function currentFields() {
        return state.fields;
    }

    function currentFilename(suffix) {
        const original = state.fields.output_filename || "";
        if (!original.includes("_")) return original || `${suffix}.jpg`;
        return original.replace(/_[^_]+\.jpg$/i, `_${suffix}.jpg`);
    }

    function buildApp() {
        const p = state.data.poster;
        root.innerHTML = `
            <div class="gl-editor o_form_view">
                <div class="gl-toolbar">
                    <button class="gl-btn gl-btn-light" id="backBtn"><i class="fa fa-arrow-left"></i> Zurück</button>
                    <strong class="text-truncate">${escapeHtml(p.event_name || "Grafikeditor")}</strong>
                    <span class="flex-grow-1"></span>
                    <button class="gl-btn gl-btn-secondary" id="saveBtn"><i class="fa fa-save"></i> Speichern</button>
                    <button class="gl-btn gl-btn-secondary" id="downloadBtn"><i class="fa fa-download"></i> Aktuelles JPG</button>
                    <button class="gl-btn gl-btn-primary" id="zipBtn"><i class="fa fa-file-archive-o"></i> Alle als ZIP</button>
                </div>
                <div class="gl-workspace">
                    <aside class="gl-sidebar">
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Ausspielformat</label>
                            <select class="gl-input" id="templateSelect">
                                ${state.data.templates.map((t) => `<option value="${escapeHtml(t.key)}">${escapeHtml(t.name)}</option>`).join("")}
                            </select>
                        </div>
                        <div class="gl-section">
                            <button class="gl-btn gl-btn-secondary w-100 mb-2" id="uploadBtn">Bild hochladen / ersetzen</button>
                            <input type="file" accept="image/*" id="sourceFile" class="gl-hidden"/>
                            <div class="gl-small">Im Bild ziehen = verschieben, Mausrad = sanft zoomen. Seiten-Anfasser = Crop/Position, Eck-Anfasser = Drehen.</div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Bildposition übernehmen</label>
                            <select class="gl-input" id="imageModeSelect">
                                <option value="global">Global für alle Formate</option>
                                <option value="local">Nur aktuelles Format nachbearbeiten</option>
                            </select>
                            <div class="gl-small">Standard: zuerst global positionieren. Danach pro Ausspielformat auf „Nur aktuelles Format“ stellen und feinjustieren.</div>
                        </div>
                        <div class="gl-section">
                            ${input("date_text", "Datum")}
                            ${input("time_text", "Uhrzeit")}
                            ${input("event_type_text", "Kategorie")}
                            ${input("event_title", "Titel")}
                            ${textarea("event_subtitle", "Untertitel", 2)}
                            ${textarea("summary_text", "Kurzzusammenfassung", 4)}
                            ${input("photo_credit", "Fotocredit")}
                            ${input("ticket_link_text", "Ticketlink-Zeile")}
                            ${input("qr_url", "QR-Code-Ziel")}
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Verlauf</label>
                            <div class="d-flex gap-2">
                                <input type="color" class="gl-color gl-field" data-field="color_1" value="${escapeHtml(state.fields.color_1)}"/>
                                <input type="color" class="gl-color gl-field" data-field="color_2" value="${escapeHtml(state.fields.color_2)}"/>
                            </div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Aktuelles Format justieren</label>
                            <div class="gl-grid-2">
                                ${numberInput("image.offsetX", "Bild X")}
                                ${numberInput("image.offsetY", "Bild Y")}
                                ${numberInput("image.scale", "Zoom", "0.05")}
                                ${numberInput("image.rotation", "Rotation")}
                            </div>
                        </div>
                        <div id="status" class="gl-small"></div>
                    </aside>
                    <main class="gl-canvas-area">
                        <div class="gl-canvas-shell"><canvas id="posterCanvas"></canvas></div>
                    </main>
                </div>
            </div>
        `;

        document.getElementById("templateSelect").value = state.selectedTemplateKey;
        bindEvents();
        syncVariantInputs();
    }

    function input(field, label) {
        return `<div class="mb-2"><label class="gl-label">${label}</label><input class="gl-input gl-field" data-field="${field}" value="${escapeHtml(state.fields[field] || "")}"/></div>`;
    }

    function textarea(field, label, rows) {
        return `<div class="mb-2"><label class="gl-label">${label}</label><textarea class="gl-input gl-field" rows="${rows}" data-field="${field}">${escapeHtml(state.fields[field] || "")}</textarea></div>`;
    }

    function numberInput(path, label, step = "1") {
        return `<div class="gl-col"><label class="gl-label">${label}</label><input class="gl-input gl-number" type="number" step="${step}" data-path="${path}"/></div>`;
    }

    function bindEvents() {
        document.getElementById("backBtn").onclick = () => {
            if (document.referrer) window.history.back();
            else window.location.href = "/odoo";
        };
        document.getElementById("uploadBtn").onclick = () => document.getElementById("sourceFile").click();
        document.getElementById("sourceFile").onchange = async (ev) => {
            const file = ev.target.files[0];
            if (!file) return;
            state.sourceImageFilename = file.name;
            state.sourceImageBase64 = await fileToBase64(file);
            await renderCanvas();
        };
        document.getElementById("templateSelect").onchange = async (ev) => {
            state.selectedTemplateKey = ev.target.value;
            state.editorState.selectedTemplateKey = state.selectedTemplateKey;
            syncVariantInputs();
            await renderCanvas();
        };
        document.getElementById("imageModeSelect").value = state.imageEditMode;
        document.getElementById("imageModeSelect").onchange = (ev) => {
            state.imageEditMode = ev.target.value;
            if (state.imageEditMode === "local") {
                const variant = ensureVariant(state.selectedTemplateKey);
                if (!variant.imageCustom) {
                    variant.image = { ...getImageTransform(state.selectedTemplateKey) };
                    variant.imageCustom = true;
                }
            }
            syncVariantInputs();
        };
        root.querySelectorAll(".gl-field").forEach((node) => {
            node.addEventListener("input", async (ev) => {
                state.fields[ev.target.dataset.field] = ev.target.value;
                if (ev.target.dataset.field === "qr_url") {
                    await refreshQr();
                }
                await renderCanvas();
            });
        });
        root.querySelectorAll(".gl-number").forEach((node) => {
            node.addEventListener("input", async (ev) => {
                const variant = ensureVariant(state.selectedTemplateKey);
                const [group, field] = ev.target.dataset.path.split(".");
                if (group === "image") {
                    const transform = { ...getImageTransform(state.selectedTemplateKey) };
                    transform[field] = parseFloat(ev.target.value || 0);
                    setImageTransform(state.selectedTemplateKey, transform);
                } else {
                    variant[group][field] = parseFloat(ev.target.value || 0);
                }
                await renderCanvas();
            });
        });
        document.getElementById("saveBtn").onclick = () => saveAll(false);
        document.getElementById("downloadBtn").onclick = () => saveAll("current");
        document.getElementById("zipBtn").onclick = () => saveAll("zip");

        const canvas = document.getElementById("posterCanvas");
        canvas.addEventListener("wheel", async (ev) => {
            ev.preventDefault();
            const transform = { ...getImageTransform(state.selectedTemplateKey) };
            transform.scale = clamp((transform.scale || 1) * (ev.deltaY < 0 ? 1.03 : 0.97), 0.2, 5);
            setImageTransform(state.selectedTemplateKey, transform);
            syncVariantInputs();
            await renderCanvas();
        }, { passive: false });
        canvas.addEventListener("pointerdown", onPointerDown);
    }

    function syncVariantInputs() {
        const variant = ensureVariant(state.selectedTemplateKey);
        const imageTransform = getImageTransform(state.selectedTemplateKey);
        root.querySelectorAll(".gl-number").forEach((node) => {
            const [group, field] = node.dataset.path.split(".");
            node.value = group === "image" ? (imageTransform[field] ?? 0) : (variant[group]?.[field] ?? 0);
        });
        const modeSelect = document.getElementById("imageModeSelect");
        if (modeSelect) modeSelect.value = state.imageEditMode;
    }

    function fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    async function refreshQr() {
        try {
            state.qrImageBase64 = await rpc("gl.graphics.poster", "generate_qr_base64", [state.fields.qr_url || state.fields.ticket_url || ""]);
        } catch (error) {
            console.warn(error);
        }
    }

    async function renderCanvas() {
        try {
            const template = currentTemplate();
            if (!template) return;
            const info = await ensureTemplateAssets(template);
            const canvas = document.getElementById("posterCanvas");
            canvas.width = template.canvas_width;
            canvas.height = template.canvas_height;
            await paintTemplate(canvas.getContext("2d"), info, ensureVariant(template.key), true);
        } catch (error) {
            console.error(error);
            setStatus(`Render-Fehler: ${error.message}`, true);
        }
    }

    async function paintTemplate(ctx, info, variant, showGuides = false) {
        if (!ctx || !info || !info.template) return;
        const template = info.template;
        ctx.clearRect(0, 0, template.canvas_width, template.canvas_height);

        // Ebenenreihenfolge:
        // 1) Verlauf ganz hinten
        // 2) hochgeladenes Bild
        // 3) alle sonstigen Overlays / Texte / QR / Logos
        // 4) Störer immer ganz oben
        drawGradient(ctx, template);

        // Wichtig: Einzelne fehlerhafte Bilder dürfen den gesamten Renderer nicht mehr abbrechen.
        // Genau sonst bleibt nach dem Verlauf alles leer und Download/Speichern brechen ebenfalls ab.
        await safeLayer("Veranstaltungsbild", () => drawSourceImage(ctx, info, getImageTransform(template.key)));

        const qrImg = state.qrImageBase64
            ? await safeLayer("QR-Code laden", () => loadImage(dataUrlFromBase64(state.qrImageBase64, "image/png")))
            : null;
        for (const overlay of info.staticOverlays || []) {
            safeDrawImage(ctx, overlay.image, 0, 0, template.canvas_width, template.canvas_height, overlay.role || "Static Overlay");
        }

        const img = info.imagesByRole || {};
        const box = info.bboxes || {};
        const regions = info.regions || {};

        // Feste grafische Ebenen, die nicht als "static_*" erkannt werden,
        // aber trotzdem echte sichtbare Layer sind (z. B. Kino-Claim,
        // Sudhaus-Getränkekarte und externe Partnerlogos).
        safeDrawImage(ctx, img.claim, 0, 0, template.canvas_width, template.canvas_height, "Claim");
        safeDrawImage(ctx, img.drink_card, 0, 0, template.canvas_width, template.canvas_height, "Getränkekarte");
        await safeLayer("Externes Logo", () => drawExternalLogo(ctx, img, box, variant, template));

        safeDrawImage(ctx, img.frame, 0, 0, template.canvas_width, template.canvas_height, "Rahmen");
        if (img.logo) {
            await safeLayer("Logo", () => {
                if (img.logo.width === template.canvas_width && img.logo.height === template.canvas_height) {
                    safeDrawImage(ctx, img.logo, 0, 0, template.canvas_width, template.canvas_height, "Logo");
                } else if (box.logo) {
                    drawLayerPreserveAspect(ctx, img.logo, box.logo, box.logo);
                }
            });
        }

        safeLayer("Datum/Titel", () => drawDateTitle(ctx, box.date_title || box.title, regions.date_title || regions.title || []));
        safeLayer("Uhrzeit/Untertitel", () => drawTimeSubtitle(ctx, box.time_subtitle, regions.time_subtitle || []));
        safeLayer("Uhrzeit/Ticketlink", () => drawTimeTicketlink(ctx, box.time_ticketlink, regions.time_ticketlink || []));
        safeLayer("Titel", () => drawTitleOnly(ctx, box.title, regions.title || []));
        safeLayer("Untertitel", () => drawSubtitleOnly(ctx, box.subtitle, regions.subtitle || []));
        safeLayer("Kurzzusammenfassung", () => drawParagraphBox(ctx, state.fields.summary_text, box.summary));
        safeLayer("Fotocredit", () => drawSingleLine(ctx, state.fields.photo_credit, box.photo_credit, "400 28px GroundliftRegular, Arial, sans-serif", "center"));
        safeLayer("Ticketlink", () => drawSingleLine(ctx, state.fields.ticket_link_text, box.ticket_link, "600 28px GroundliftCondensed, Arial Narrow, Arial, sans-serif", "center"));
        if (qrImg && box.qr) safeLayer("QR-Code zeichnen", () => drawImageBox(ctx, qrImg, applyBoxVariant(box.qr, variant.qr)));

        if (img.sticker && state.fields.sticker_mode !== "hidden" && box.sticker) {
            await safeLayer("Störer", () => drawCroppedLayer(ctx, img.sticker, box.sticker, applyBoxVariant(box.sticker, variant.sticker)));
        }

        if (showGuides) {
            safeLayer("Bildgriffe", () => drawImageHandles(ctx, info.geometries.image_mask || { bbox: info.bboxes.image_mask }));
        }
    }

    function drawGradient(ctx, template) {
        const gradient = ctx.createLinearGradient(0, 0, template.canvas_width, template.canvas_height);
        gradient.addColorStop(0, state.fields.color_1 || "#000033");
        gradient.addColorStop(1, state.fields.color_2 || "#002E59");
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, template.canvas_width, template.canvas_height);
    }

    async function drawSourceImage(ctx, info, transform) {
        const geometry = info.geometries.image_mask;
        const box = geometry?.bbox || info.bboxes.image_mask;
        if (!state.sourceImageBase64 || !box) return;
        const src = dataUrlFromBase64(state.sourceImageBase64, extensionMime(state.sourceImageFilename, "image/jpeg"));
        const image = await loadImage(src);
        const imageTransform = transform || { offsetX: 0, offsetY: 0, scale: 1, rotation: 0 };
        const coverScale = Math.max(box.width / image.width, box.height / image.height);
        const scale = coverScale * (imageTransform.scale || 1);
        const drawW = image.width * scale;
        const drawH = image.height * scale;
        const cx = box.x + box.width / 2 + (imageTransform.offsetX || 0);
        const cy = box.y + box.height / 2 + (imageTransform.offsetY || 0);

        ctx.save();
        ctx.beginPath();
        if (geometry?.corners?.length === 4) drawPolygonPath(ctx, geometry.corners);
        else ctx.rect(box.x, box.y, box.width, box.height);
        ctx.clip();
        ctx.translate(cx, cy);
        ctx.rotate((Number(imageTransform.rotation || 0)) * Math.PI / 180);
        ctx.drawImage(image, -drawW / 2, -drawH / 2, drawW, drawH);
        ctx.restore();
    }

    async function drawExternalLogo(ctx, img, box, variant, template) {
        const targetBox = box.external_logo;
        if (!targetBox) {
            if (img.external_logo) ctx.drawImage(img.external_logo, 0, 0, template.canvas_width, template.canvas_height);
            return;
        }

        let logoImage = img.external_logo || null;
        if (state.externalLogoBase64) {
            logoImage = await loadImage(dataUrlFromBase64(
                state.externalLogoBase64,
                extensionMime(state.externalLogoFilename, "image/png")
            ));
        }
        if (!logoImage) return;

        if (!state.externalLogoBase64 && logoImage.width === template.canvas_width && logoImage.height === template.canvas_height) {
            ctx.drawImage(logoImage, 0, 0, template.canvas_width, template.canvas_height);
            return;
        }

        drawLayerPreserveAspect(ctx, logoImage, { x: 0, y: 0, width: logoImage.width, height: logoImage.height }, applyBoxVariant(targetBox, variant.externalLogo));
    }

    function drawDateTitle(ctx, bbox, regions = []) {
        if (!bbox) return;
        const title = state.fields.event_title || "";
        const date = state.fields.date_text || "";
        const layout = resolveDateTitleLayout(bbox, regions);
        if (layout) {
            if (layout.divider) drawDivider(ctx, layout.divider);
            if (layout.left) {
                drawFitText(ctx, [date], insetBox(layout.left, 4), "900 64px GroundliftBold, Arial Black, Arial, sans-serif", "center", {
                    allowWrap: false,
                    valign: "middle",
                    lineHeight: 1.0,
                });
            }
            if (layout.right) {
                drawFitText(ctx, title, insetBox(layout.right, 6, 4), "900 64px GroundliftBold, Arial Black, Arial, sans-serif", "left", {
                    allowWrap: true,
                    maxLines: preferredTitleLineCount(title, layout.right),
                    valign: "middle",
                    lineHeight: 1.0,
                });
            }
            return;
        }
        drawSplit(ctx, bbox, [date], [title], { leftRatio: 0.42, boldRight: true });
    }

    function drawTimeSubtitle(ctx, bbox, regions = []) {
        if (!bbox) return;
        const subtitle = state.fields.event_subtitle || "";
        const lines = String(subtitle).split(/\n+/).filter(Boolean);
        const layout = resolveTimeSubtitleLayout(bbox, regions);
        if (layout) {
            if (layout.leftTop) {
                drawFitText(ctx, [state.fields.time_text], insetBox(layout.leftTop, 3, 2), "900 46px GroundliftBold, Arial Black, Arial, sans-serif", "center", {
                    allowWrap: false,
                    valign: "middle",
                    lineHeight: 1.0,
                });
            }
            if (layout.leftBottom) {
                drawFitText(ctx, [state.fields.event_type_text], insetBox(layout.leftBottom, 3, 2), "400 34px GroundliftRegular, Arial, sans-serif", "center", {
                    allowWrap: false,
                    valign: "middle",
                    lineHeight: 1.0,
                });
            }
            if (layout.right) {
                drawFitText(ctx, lines.length > 1 ? lines : subtitle, insetBox(layout.right, 6, 2), "500 46px GroundliftRegular, Arial, sans-serif", "left", {
                    allowWrap: true,
                    maxLines: preferredSubtitleLineCount(subtitle, layout.right),
                    valign: "top",
                    lineHeight: 1.05,
                });
            }
            return;
        }
        drawSplit(ctx, bbox, [state.fields.time_text], lines, { leftRatio: 0.38, leftBottom: state.fields.event_type_text, boldRight: false });
    }

    function drawTimeTicketlink(ctx, bbox, regions = []) {
        if (!bbox) return;
        const lines = String(state.fields.ticket_link_text || "").split(/\n+/).filter(Boolean);
        const target = regions.length ? insetBox(unionBoxes(regions), 2) : bbox;
        drawFitText(ctx, lines, target, "600 30px GroundliftCondensed, Arial Narrow, Arial, sans-serif", "center");
    }

    function drawSplit(ctx, bbox, leftTopLines, rightLines, options = {}) {
        const leftRatio = options.leftRatio || 0.4;
        const dividerGap = Math.max(18, bbox.width * 0.018);
        const dividerX = bbox.x + bbox.width * leftRatio;
        const leftBox = { x: bbox.x, y: bbox.y, width: Math.max(1, bbox.width * leftRatio - dividerGap), height: bbox.height };
        const rightBox = { x: dividerX + dividerGap, y: bbox.y, width: Math.max(1, bbox.x + bbox.width - dividerX - dividerGap), height: bbox.height };
        drawDivider(ctx, { x: dividerX - 2, y: bbox.y + 4, width: 4, height: Math.max(1, bbox.height - 8) });
        drawFitText(ctx, leftTopLines, { ...leftBox, height: options.leftBottom ? leftBox.height * 0.68 : leftBox.height }, "900 64px GroundliftBold, Arial Black, Arial, sans-serif", "center");
        if (options.leftBottom) {
            drawFitText(ctx, [options.leftBottom], { x: leftBox.x, y: leftBox.y + leftBox.height * 0.66, width: leftBox.width, height: leftBox.height * 0.34 }, "400 34px GroundliftRegular, Arial, sans-serif", "center");
        }
        drawFitText(ctx, rightLines, rightBox, `${options.boldRight === false ? 500 : 900} 52px GroundliftBold, Arial Black, Arial, sans-serif`, "left");
    }

    function drawTitleOnly(ctx, bbox, regions = []) {
        if (!bbox) return;
        if (regions.length && state.fields.event_title) {
            const layout = resolveDateTitleLayout(bbox, regions);
            if (layout?.divider) drawDivider(ctx, layout.divider);
            const target = layout?.right || unionBoxes(regions) || bbox;
            drawFitText(ctx, state.fields.event_title, insetBox(target, 6, 4), "900 64px GroundliftBold, Arial Black, Arial, sans-serif", layout?.right ? "left" : "center", {
                allowWrap: true,
                maxLines: preferredTitleLineCount(state.fields.event_title, target),
                valign: "middle",
                lineHeight: 1.0,
            });
            return;
        }
        drawFitText(ctx, state.fields.event_title, bbox, "900 64px GroundliftBold, Arial Black, Arial, sans-serif", "center", {
            allowWrap: true,
            maxLines: preferredTitleLineCount(state.fields.event_title, bbox),
            valign: "middle",
            lineHeight: 1.0,
        });
    }

    function drawSubtitleOnly(ctx, bbox, regions = []) {
        if (!bbox) return;
        const subtitle = state.fields.event_subtitle || "";
        const lines = String(subtitle).split(/\n+/).filter(Boolean);
        const target = regions.length ? insetBox(unionBoxes(regions) || bbox, 4, 2) : bbox;
        drawFitText(ctx, lines.length > 1 ? lines : subtitle, target, "500 46px GroundliftRegular, Arial, sans-serif", "left", {
            allowWrap: true,
            maxLines: preferredSubtitleLineCount(subtitle, target),
            valign: "top",
            lineHeight: 1.05,
        });
    }

    function resolveDateTitleLayout(bbox, regions) {
        const useful = (regions || []).filter((r) => r.width > 3 && r.height > 3);
        if (!useful.length) return null;
        const divider = useful.find((r) => r.width < bbox.width * 0.08 && r.height > bbox.height * 0.35);
        let splitX = divider ? divider.x + divider.width / 2 : null;
        if (!splitX) {
            const sorted = [...useful].sort((a, b) => boxCenter(a).x - boxCenter(b).x);
            const mid = Math.floor(sorted.length / 2);
            const leftSeed = sorted.slice(0, Math.max(1, mid));
            const rightSeed = sorted.slice(Math.max(1, mid));
            const leftEdge = Math.max(...leftSeed.map((r) => r.x + r.width));
            const rightEdge = Math.min(...rightSeed.map((r) => r.x));
            splitX = Number.isFinite(leftEdge) && Number.isFinite(rightEdge) ? (leftEdge + rightEdge) / 2 : bbox.x + bbox.width * 0.42;
        }
        const gap = Math.max(16, bbox.width * 0.02);
        const left = { x: bbox.x, y: bbox.y, width: Math.max(1, splitX - gap - bbox.x), height: bbox.height };
        const right = { x: splitX + gap, y: bbox.y, width: Math.max(1, bbox.x + bbox.width - (splitX + gap)), height: bbox.height };
        return {
            divider: divider || { x: splitX - 2, y: bbox.y + 4, width: 4, height: Math.max(1, bbox.height - 8) },
            left,
            right,
        };
    }

    function resolveTimeSubtitleLayout(bbox, regions) {
        const useful = (regions || []).filter((r) => r.width > 3 && r.height > 3);
        if (!useful.length) return null;

        let splitGuess = bbox.x + bbox.width * 0.4;
        let leftRegions = useful.filter((r) => boxCenter(r).x < splitGuess);
        let rightRegions = useful.filter((r) => boxCenter(r).x >= splitGuess);
        if (!leftRegions.length || !rightRegions.length) {
            const sorted = [...useful].sort((a, b) => boxCenter(a).x - boxCenter(b).x);
            const mid = Math.floor(sorted.length / 2);
            leftRegions = sorted.slice(0, Math.max(1, mid));
            rightRegions = sorted.slice(Math.max(1, mid));
        }
        leftRegions.sort((a, b) => a.y - b.y || a.x - b.x);
        rightRegions.sort((a, b) => a.y - b.y || a.x - b.x);
        if (!leftRegions.length && !rightRegions.length) return null;

        const leftEdge = leftRegions.length ? Math.max(...leftRegions.map((r) => r.x + r.width)) : bbox.x + bbox.width * 0.32;
        const rightEdge = rightRegions.length ? Math.min(...rightRegions.map((r) => r.x)) : bbox.x + bbox.width * 0.5;
        const splitX = (leftEdge + rightEdge) / 2;
        const gap = Math.max(14, bbox.width * 0.02);
        const leftColumn = { x: bbox.x, y: bbox.y, width: Math.max(1, splitX - gap - bbox.x), height: bbox.height };
        const rightColumn = { x: splitX + gap, y: bbox.y, width: Math.max(1, bbox.x + bbox.width - (splitX + gap)), height: bbox.height };

        let leftTop = null;
        let leftBottom = null;
        if (leftRegions.length === 1) {
            leftTop = leftColumn;
        } else if (leftRegions.length > 1) {
            const topRegion = leftRegions[0];
            const bottomUnion = unionBoxes(leftRegions.slice(1));
            const splitY = clamp((topRegion.y + topRegion.height + bottomUnion.y) / 2, bbox.y + bbox.height * 0.35, bbox.y + bbox.height * 0.7);
            leftTop = { x: leftColumn.x, y: bbox.y, width: leftColumn.width, height: Math.max(1, splitY - bbox.y) };
            leftBottom = { x: leftColumn.x, y: splitY, width: leftColumn.width, height: Math.max(1, bbox.y + bbox.height - splitY) };
        }

        return {
            leftTop,
            leftBottom,
            right: rightRegions.length ? rightColumn : null,
        };
    }

    function drawDivider(ctx, bbox) {
        if (!bbox) return;
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(bbox.x, bbox.y, Math.max(2, bbox.width), bbox.height);
        ctx.restore();
    }

    function drawParagraphBox(ctx, text, bbox) {
        if (!bbox || !text) return;
        drawParagraph(ctx, String(text), bbox, "400 34px GroundliftRegular, Arial, sans-serif");
    }

    function drawSingleLine(ctx, text, bbox, font, align = "left") {
        if (!bbox || !text) return;
        drawFitText(ctx, [String(text).toUpperCase()], bbox, font, align, {
            allowWrap: false,
            valign: "middle",
            lineHeight: 1.0,
        });
    }

    function normalizedLines(content) {
        const parts = Array.isArray(content) ? content : [content];
        return parts
            .flatMap((part) => String(part ?? "").split(/\n+/))
            .map((part) => part.trim())
            .filter(Boolean)
            .map((part) => part.toUpperCase());
    }

    function wrapWordsToLines(ctx, text, maxWidth, maxLines) {
        const words = String(text || "").trim().split(/\s+/).filter(Boolean);
        if (!words.length) return [];
        const lines = [""];
        for (const word of words) {
            let placed = false;
            while (!placed) {
                const idx = lines.length - 1;
                const probe = lines[idx] ? `${lines[idx]} ${word}` : word;
                if (!lines[idx] || ctx.measureText(probe).width <= maxWidth) {
                    lines[idx] = probe;
                    placed = true;
                } else if (lines.length < maxLines) {
                    lines.push("");
                } else {
                    return null;
                }
            }
        }
        if (lines.some((line) => !line)) return null;
        return lines;
    }

    function preferredTitleLineCount(text, bbox) {
        const words = String(text || "").trim().split(/\s+/).filter(Boolean);
        if (words.length <= 1) return 1;
        if ((bbox?.height || 0) > 170 && (bbox?.width || 0) < 420 && words.length >= 4) return 3;
        return 2;
    }

    function preferredSubtitleLineCount(text, bbox) {
        const explicit = String(text || "").split(/\n+/).filter(Boolean).length;
        const words = String(text || "").trim().split(/\s+/).filter(Boolean).length;
        return Math.max(explicit || 1, ((bbox?.height || 0) > 110 && words > 6) ? 3 : 2);
    }

    function fitTextLayout(ctx, content, bbox, font, options = {}) {
        const clean = normalizedLines(content);
        if (!clean.length || !bbox || bbox.width <= 0 || bbox.height <= 0) return null;
        const fontTemplate = font;
        const maxSize = options.maxSize || parseInt((font.match(/(\d+)px/) || ["", "40"])[1], 10);
        const minSize = options.minSize || 10;
        const maxLines = Math.max(1, options.maxLines || clean.length || 1);
        const allowWrap = options.allowWrap !== false;
        const lineHeightFactor = options.lineHeight || 1.08;

        for (let size = maxSize; size >= minSize; size -= 2) {
            ctx.font = fontTemplate.replace(/\d+px/, `${size}px`);
            const candidate = [];
            let possible = true;
            for (const line of clean) {
                const needsWrap = allowWrap && (candidate.length < maxLines) && (ctx.measureText(line).width > bbox.width || maxLines > clean.length);
                if (needsWrap) {
                    const wrapped = wrapWordsToLines(ctx, line, bbox.width, maxLines - candidate.length);
                    if (!wrapped || candidate.length + wrapped.length > maxLines) {
                        possible = false;
                        break;
                    }
                    candidate.push(...wrapped);
                } else {
                    candidate.push(line);
                }
            }
            if (!possible || !candidate.length || candidate.length > maxLines) continue;
            const widest = Math.max(...candidate.map((line) => ctx.measureText(line).width));
            const lineHeight = size * lineHeightFactor;
            const totalHeight = candidate.length * lineHeight;
            if (widest <= bbox.width && totalHeight <= bbox.height) {
                return { size, lines: candidate, lineHeight };
            }
        }

        const fallbackSize = Math.max(minSize, Math.min(maxSize, 12));
        ctx.font = fontTemplate.replace(/\d+px/, `${fallbackSize}px`);
        const fallbackLines = allowWrap ? (wrapWordsToLines(ctx, clean.join(" "), bbox.width, maxLines) || clean.slice(0, maxLines)) : clean.slice(0, maxLines);
        return { size: fallbackSize, lines: fallbackLines, lineHeight: fallbackSize * lineHeightFactor };
    }

    function drawFitText(ctx, content, bbox, font, align = "left", options = {}) {
        const layout = fitTextLayout(ctx, content, bbox, font, options);
        if (!layout) return;
        ctx.save();
        ctx.font = font.replace(/\d+px/, `${layout.size}px`);
        ctx.fillStyle = "#fff";
        ctx.textAlign = align;
        ctx.textBaseline = "middle";
        const totalHeight = layout.lines.length * layout.lineHeight;
        const valign = options.valign || "center";
        let y = bbox.y + layout.lineHeight / 2;
        if (valign === "middle" || valign === "center") {
            y = bbox.y + (bbox.height - totalHeight) / 2 + layout.lineHeight / 2;
        } else if (valign === "bottom") {
            y = bbox.y + bbox.height - totalHeight + layout.lineHeight / 2;
        }
        for (const line of layout.lines) {
            const x = align === "center" ? bbox.x + bbox.width / 2 : align === "right" ? bbox.x + bbox.width : bbox.x;
            ctx.fillText(line, x, y);
            y += layout.lineHeight;
        }
        ctx.restore();
    }

    function drawParagraph(ctx, text, bbox, font) {
        if (!text || !bbox) return;
        drawFitText(ctx, String(text), bbox, font, "left", {
            allowWrap: true,
            maxLines: Math.max(3, Math.floor(bbox.height / 30)),
            valign: "top",
            lineHeight: 1.16,
            minSize: 9,
        });
    }

    function drawImageBox(ctx, image, box) {
        if (!ctx || !image || !box || box.width <= 0 || box.height <= 0) return;
        ctx.drawImage(image, box.x, box.y, box.width, box.height);
    }

    function applyBoxVariant(bbox, variant = {}) {
        const scale = variant.scale || 1;
        return {
            x: bbox.x + (variant.dx || 0),
            y: bbox.y + (variant.dy || 0),
            width: bbox.width * scale,
            height: bbox.height * scale,
        };
    }

    function imageHandlePoints(geometry) {
        const box = geometry?.bbox;
        if (!box) return [];
        const corners = geometry?.corners?.length === 4 ? geometry.corners : [
            { x: box.x, y: box.y },
            { x: box.x + box.width, y: box.y },
            { x: box.x + box.width, y: box.y + box.height },
            { x: box.x, y: box.y + box.height },
        ];
        const midpoint = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
        return [
            { type: "rotate", name: "tl", ...corners[0] },
            { type: "edge", name: "top", ...midpoint(corners[0], corners[1]) },
            { type: "rotate", name: "tr", ...corners[1] },
            { type: "edge", name: "right", ...midpoint(corners[1], corners[2]) },
            { type: "rotate", name: "br", ...corners[2] },
            { type: "edge", name: "bottom", ...midpoint(corners[2], corners[3]) },
            { type: "rotate", name: "bl", ...corners[3] },
            { type: "edge", name: "left", ...midpoint(corners[3], corners[0]) },
        ];
    }

    function drawImageHandles(ctx, geometry) {
        const box = geometry?.bbox;
        if (!box) return;
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,.9)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        if (geometry?.corners?.length === 4) drawPolygonPath(ctx, geometry.corners);
        else ctx.rect(box.x, box.y, box.width, box.height);
        ctx.stroke();

        for (const handle of imageHandlePoints(geometry)) {
            ctx.beginPath();
            ctx.fillStyle = handle.type === "rotate" ? "#714b67" : "#ffffff";
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.arc(handle.x, handle.y, handle.type === "rotate" ? 9 : 7, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
        }
        ctx.restore();
    }

    function hitImageHandle(x, y, geometry, canvas) {
        const radius = Math.max(11, canvas.width / 180);
        for (const handle of imageHandlePoints(geometry)) {
            const dx = x - handle.x;
            const dy = y - handle.y;
            if (Math.sqrt(dx * dx + dy * dy) <= radius) return handle;
        }
        return null;
    }

    function onPointerDown(ev) {
        const canvas = document.getElementById("posterCanvas");
        const template = currentTemplate();
        const info = state.templateCache.get(template.key);
        const geometry = info?.geometries?.image_mask || { bbox: info?.bboxes?.image_mask };
        const bbox = geometry?.bbox;
        if (!bbox) return;
        const rect = canvas.getBoundingClientRect();
        const toCanvas = (event) => ({
            x: ((event.clientX - rect.left) / rect.width) * canvas.width,
            y: ((event.clientY - rect.top) / rect.height) * canvas.height,
        });
        const startPoint = toCanvas(ev);
        const handle = hitImageHandle(startPoint.x, startPoint.y, geometry, canvas);
        const inside = handle ? true : (geometry?.corners?.length === 4
            ? pointInPolygon(startPoint.x, startPoint.y, geometry.corners)
            : (startPoint.x >= bbox.x && startPoint.x <= bbox.x + bbox.width && startPoint.y >= bbox.y && startPoint.y <= bbox.y + bbox.height));
        if (!inside) return;
        ev.preventDefault();

        const center = { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 };
        const initial = { ...getImageTransform(state.selectedTemplateKey) };
        const startAngle = Math.atan2(startPoint.y - center.y, startPoint.x - center.x);

        const move = async (moveEv) => {
            const point = toCanvas(moveEv);
            const dx = point.x - startPoint.x;
            const dy = point.y - startPoint.y;
            const next = { ...initial };

            if (handle?.type === "rotate") {
                const angle = Math.atan2(point.y - center.y, point.x - center.x);
                next.rotation = initial.rotation + (angle - startAngle) * 180 / Math.PI;
            } else if (handle?.type === "edge") {
                const direction = {
                    left: -dx,
                    right: dx,
                    top: -dy,
                    bottom: dy,
                }[handle.name] || 0;
                next.scale = clamp(initial.scale * (1 + direction / 650), 0.2, 5);
                if (handle.name === "left" || handle.name === "right") next.offsetX = initial.offsetX + dx * 0.45;
                if (handle.name === "top" || handle.name === "bottom") next.offsetY = initial.offsetY + dy * 0.45;
            } else {
                next.offsetX = initial.offsetX + dx;
                next.offsetY = initial.offsetY + dy;
            }

            setImageTransform(state.selectedTemplateKey, next);
            syncVariantInputs();
            await renderCanvas();
        };

        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    async function saveAll(downloadMode) {
        try {
            setStatus("Speichere…");
            const renderedOutputs = await renderAllOutputs();
            const current = renderedOutputs[state.selectedTemplateKey];
            const values = {
                source_image: state.sourceImageBase64,
                source_image_filename: state.sourceImageFilename,
                external_logo_image: state.externalLogoBase64,
                external_logo_filename: state.externalLogoFilename,
                ...state.fields,
                editor_state: state.editorState,
                output_filename: current ? current.filename : state.fields.output_filename,
            };
            await rpc("gl.graphics.poster", "save_editor_data", [[posterId], values, current ? current.data : false, renderedOutputs]);
            if (downloadMode === "current") {
                window.location.href = `/web/content?model=gl.graphics.poster&id=${posterId}&field=output_image&filename_field=output_filename&download=true`;
            } else if (downloadMode === "zip") {
                window.location.href = `/groundlift_graphics/poster/${posterId}/outputs.zip`;
            } else {
                setStatus("Gespeichert.");
            }
        } catch (error) {
            console.error(error);
            setStatus(`Speicherfehler: ${error.message}`, true);
        }
    }

    async function renderAllOutputs() {
        const result = {};
        for (const template of state.data.templates) {
            const info = await ensureTemplateAssets(template);
            const canvas = document.createElement("canvas");
            canvas.width = template.canvas_width;
            canvas.height = template.canvas_height;
            await paintTemplate(canvas.getContext("2d"), info, ensureVariant(template.key), false);
            result[template.key] = {
                data: canvas.toDataURL("image/jpeg", 0.96),
                filename: currentFilename(template.output_suffix),
                template_name: template.name,
            };
        }
        return result;
    }

    function setStatus(message, danger = false) {
        const node = document.getElementById("status");
        if (!node) return;
        node.textContent = message || "";
        node.className = danger ? "gl-error" : "gl-small";
    }

    async function init() {
        try {
            if (!posterId) throw new Error("Keine Grafik-ID übergeben.");
            const data = await rpc("gl.graphics.poster", "get_editor_data", [[posterId]]);
            state.data = data;
            await registerEditorFonts(data.template || {});
            const p = data.poster;
            state.sourceImageBase64 = p.source_image;
            state.sourceImageFilename = p.source_image_filename;
            state.externalLogoBase64 = p.external_logo_image;
            state.externalLogoFilename = p.external_logo_filename;
            state.qrImageBase64 = data.qr_image || "";
            state.editorState = p.editor_state || {};
            state.selectedTemplateKey = state.editorState.selectedTemplateKey || (data.templates[0] && data.templates[0].key) || "";
            if (!state.editorState.globalImage) {
                const firstVariant = state.editorState.variants && state.editorState.variants[state.selectedTemplateKey];
                state.editorState.globalImage = firstVariant?.image || defaultImageTransform();
            }
            state.fields = {
                claim: p.claim || "",
                event_title: p.event_title || "",
                event_subtitle: p.event_subtitle || "",
                date_text: p.date_text || "",
                time_text: p.time_text || "",
                event_type_text: p.event_type_text || "",
                summary_text: p.summary_text || "",
                photo_credit: p.photo_credit || "",
                ticket_url: p.ticket_url || "",
                ticket_link_text: p.ticket_link_text || "",
                qr_url: p.qr_url || "",
                color_1: p.color_1 || "#000033",
                color_2: p.color_2 || "#002E59",
                color_contrast: p.color_contrast || false,
                sticker_mode: p.sticker_mode || "original",
                sticker_text: p.sticker_text || "",
                sticker_color: p.sticker_color || "#D6331F",
                drink_card_profile_id: p.drink_card_profile_id || false,
                output_filename: p.output_filename || "",
            };
            buildApp();
            await renderCanvas();
        } catch (error) {
            console.error(error);
            root.innerHTML = `<div class="gl-error">Der isolierte Grafikeditor konnte nicht geladen werden:\n${escapeHtml(error.message)}</div>`;
        }
    }

    init();
})();
