(() => {
    "use strict";

    const root = document.getElementById("gl-editor-root");
    const posterId = parseInt(root?.dataset?.posterId || "0", 10);

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
            img.crossOrigin = "anonymous";
            img.onload = () => resolve(img);
            img.onerror = reject;
            img.src = src;
        });
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

    function currentTemplate() {
        return state.data.templates.find((t) => t.key === state.selectedTemplateKey) || state.data.templates[0];
    }

    function ensureVariant(templateKey) {
        state.editorState.variants = state.editorState.variants || {};
        if (!state.editorState.variants[templateKey]) {
            state.editorState.variants[templateKey] = {
                image: { offsetX: 0, offsetY: 0, scale: 1, rotation: 0 },
                qr: { dx: 0, dy: 0, scale: 1 },
                externalLogo: { dx: 0, dy: 0, scale: 1 },
                sticker: { dx: 0, dy: 0, scale: 1 },
            };
        }
        return state.editorState.variants[templateKey];
    }

    async function ensureTemplateAssets(template) {
        if (!template) return null;
        if (state.templateCache.has(template.key)) return state.templateCache.get(template.key);
        const imagesByRole = {};
        const bboxes = {};
        const geometries = {};
        const staticOverlays = [];
        for (const asset of template.assets || []) {
            try {
                const image = await loadImage(asset.url);
                if (!image) continue;
                if (!imagesByRole[asset.role]) imagesByRole[asset.role] = image;
                if (asset.role.startsWith("static_")) staticOverlays.push({ role: asset.role, image });
                const geometry = alphaGeometry(image);
                geometries[asset.role] = geometry;
                bboxes[asset.role] = geometry ? geometry.bbox : null;
            } catch (error) {
                console.warn("Template asset konnte nicht geladen werden", asset, error);
            }
        }
        const info = { template, imagesByRole, bboxes, geometries, staticOverlays };
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
            <div class="gl-editor">
                <div class="gl-toolbar">
                    <button class="btn btn-light btn-sm" id="backBtn"><i class="fa fa-arrow-left"></i> Zurück</button>
                    <strong class="text-truncate">${escapeHtml(p.event_name || "Grafikeditor")}</strong>
                    <span class="flex-grow-1"></span>
                    <button class="btn btn-outline-primary btn-sm" id="saveBtn"><i class="fa fa-save"></i> Speichern</button>
                    <button class="btn btn-outline-secondary btn-sm" id="downloadBtn"><i class="fa fa-download"></i> Aktuelles JPG</button>
                    <button class="btn btn-primary btn-sm" id="zipBtn"><i class="fa fa-file-archive-o"></i> Alle als ZIP</button>
                </div>
                <div class="gl-workspace">
                    <aside class="gl-sidebar">
                        <div class="gl-section">
                            <label class="form-label fw-bold">Ausspielformat</label>
                            <select class="form-select form-select-sm" id="templateSelect">
                                ${state.data.templates.map((t) => `<option value="${escapeHtml(t.key)}">${escapeHtml(t.name)}</option>`).join("")}
                            </select>
                        </div>
                        <div class="gl-section">
                            <button class="btn btn-outline-primary btn-sm w-100 mb-2" id="uploadBtn">Bild hochladen / ersetzen</button>
                            <input type="file" accept="image/*" id="sourceFile" class="gl-hidden"/>
                            <div class="gl-small">Im Bild ziehen = verschieben, Mausrad = sanft zoomen. Zahlenwerte gelten je Format.</div>
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
                            <label class="form-label fw-bold">Verlauf</label>
                            <div class="d-flex gap-2">
                                <input type="color" class="form-control form-control-color flex-fill gl-field" data-field="color_1" value="${escapeHtml(state.fields.color_1)}"/>
                                <input type="color" class="form-control form-control-color flex-fill gl-field" data-field="color_2" value="${escapeHtml(state.fields.color_2)}"/>
                            </div>
                        </div>
                        <div class="gl-section">
                            <label class="form-label fw-bold">Aktuelles Format justieren</label>
                            <div class="row g-2">
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
        return `<div class="mb-2"><label class="form-label">${label}</label><input class="form-control form-control-sm gl-field" data-field="${field}" value="${escapeHtml(state.fields[field] || "")}"/></div>`;
    }

    function textarea(field, label, rows) {
        return `<div class="mb-2"><label class="form-label">${label}</label><textarea class="form-control form-control-sm gl-field" rows="${rows}" data-field="${field}">${escapeHtml(state.fields[field] || "")}</textarea></div>`;
    }

    function numberInput(path, label, step = "1") {
        return `<div class="col-6"><label class="form-label">${label}</label><input class="form-control form-control-sm gl-number" type="number" step="${step}" data-path="${path}"/></div>`;
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
                variant[group][field] = parseFloat(ev.target.value || 0);
                await renderCanvas();
            });
        });
        document.getElementById("saveBtn").onclick = () => saveAll(false);
        document.getElementById("downloadBtn").onclick = () => saveAll("current");
        document.getElementById("zipBtn").onclick = () => saveAll("zip");

        const canvas = document.getElementById("posterCanvas");
        canvas.addEventListener("wheel", async (ev) => {
            ev.preventDefault();
            const variant = ensureVariant(state.selectedTemplateKey);
            variant.image.scale = clamp((variant.image.scale || 1) * (ev.deltaY < 0 ? 1.03 : 0.97), 0.2, 5);
            syncVariantInputs();
            await renderCanvas();
        }, { passive: false });
        canvas.addEventListener("pointerdown", onPointerDown);
    }

    function syncVariantInputs() {
        const variant = ensureVariant(state.selectedTemplateKey);
        root.querySelectorAll(".gl-number").forEach((node) => {
            const [group, field] = node.dataset.path.split(".");
            node.value = variant[group]?.[field] ?? 0;
        });
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
        const template = info.template;
        ctx.clearRect(0, 0, template.canvas_width, template.canvas_height);
        drawGradient(ctx, template);
        await drawSourceImage(ctx, info, variant);

        const qrImg = state.qrImageBase64 ? await loadImage(dataUrlFromBase64(state.qrImageBase64, "image/png")) : null;
        for (const overlay of info.staticOverlays) {
            ctx.drawImage(overlay.image, 0, 0, template.canvas_width, template.canvas_height);
        }

        const img = info.imagesByRole;
        const box = info.bboxes;
        if (img.frame) ctx.drawImage(img.frame, 0, 0, template.canvas_width, template.canvas_height);
        if (img.sticker && state.fields.sticker_mode !== "hidden" && box.sticker) ctx.drawImage(img.sticker, box.sticker.x, box.sticker.y, box.sticker.width, box.sticker.height);
        if (img.logo) ctx.drawImage(img.logo, 0, 0, template.canvas_width, template.canvas_height);

        drawDateTitle(ctx, box.date_title || box.title);
        drawTimeSubtitle(ctx, box.time_subtitle);
        drawTimeTicketlink(ctx, box.time_ticketlink);
        drawTitleOnly(ctx, box.title);
        drawSubtitleOnly(ctx, box.subtitle);
        drawParagraphBox(ctx, state.fields.summary_text, box.summary);
        drawSingleLine(ctx, state.fields.photo_credit, box.photo_credit, "400 28px Arial, sans-serif", "center");
        drawSingleLine(ctx, state.fields.ticket_link_text, box.ticket_link, "600 28px Arial Narrow, Arial, sans-serif", "center");
        if (qrImg && box.qr) drawImageBox(ctx, qrImg, applyBoxVariant(box.qr, variant.qr));

        if (showGuides && info.geometries.image_mask?.corners) {
            ctx.save();
            ctx.strokeStyle = "rgba(255,255,255,.85)";
            ctx.lineWidth = 2;
            ctx.beginPath();
            drawPolygonPath(ctx, info.geometries.image_mask.corners);
            ctx.stroke();
            ctx.restore();
        }
    }

    function drawGradient(ctx, template) {
        const gradient = ctx.createLinearGradient(0, 0, template.canvas_width, template.canvas_height);
        gradient.addColorStop(0, state.fields.color_1 || "#000033");
        gradient.addColorStop(1, state.fields.color_2 || "#002E59");
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, template.canvas_width, template.canvas_height);
    }

    async function drawSourceImage(ctx, info, variant) {
        const geometry = info.geometries.image_mask;
        const box = geometry?.bbox || info.bboxes.image_mask;
        if (!state.sourceImageBase64 || !box) return;
        const src = dataUrlFromBase64(state.sourceImageBase64, extensionMime(state.sourceImageFilename, "image/jpeg"));
        const image = await loadImage(src);
        const coverScale = Math.max(box.width / image.width, box.height / image.height);
        const scale = coverScale * (variant.image.scale || 1);
        const drawW = image.width * scale;
        const drawH = image.height * scale;
        const cx = box.x + box.width / 2 + (variant.image.offsetX || 0);
        const cy = box.y + box.height / 2 + (variant.image.offsetY || 0);

        ctx.save();
        ctx.beginPath();
        if (geometry?.corners?.length === 4) drawPolygonPath(ctx, geometry.corners);
        else ctx.rect(box.x, box.y, box.width, box.height);
        ctx.clip();
        ctx.translate(cx, cy);
        ctx.rotate((variant.image.rotation || 0) * Math.PI / 180);
        ctx.drawImage(image, -drawW / 2, -drawH / 2, drawW, drawH);
        ctx.restore();
    }

    function drawDateTitle(ctx, bbox) {
        if (!bbox) return;
        drawSplit(ctx, bbox, [state.fields.date_text], [state.fields.event_title], { leftRatio: 0.42, boldRight: true });
    }

    function drawTimeSubtitle(ctx, bbox) {
        if (!bbox) return;
        const lines = String(state.fields.event_subtitle || "").split(/\n+/).filter(Boolean);
        drawSplit(ctx, bbox, [state.fields.time_text], lines, { leftRatio: 0.38, leftBottom: state.fields.event_type_text, boldRight: false });
    }

    function drawTimeTicketlink(ctx, bbox) {
        if (!bbox) return;
        const lines = String(state.fields.ticket_link_text || "").split(/\n+/).filter(Boolean);
        drawSplit(ctx, bbox, [state.fields.time_text], lines, { leftRatio: 0.42, leftBottom: state.fields.event_type_text, boldRight: false });
    }

    function drawSplit(ctx, bbox, leftTopLines, rightLines, options = {}) {
        const leftRatio = options.leftRatio || 0.4;
        const dividerGap = Math.max(18, bbox.width * 0.018);
        const dividerX = bbox.x + bbox.width * leftRatio;
        const leftBox = { x: bbox.x, y: bbox.y, width: Math.max(1, bbox.width * leftRatio - dividerGap), height: bbox.height };
        const rightBox = { x: dividerX + dividerGap, y: bbox.y, width: Math.max(1, bbox.x + bbox.width - dividerX - dividerGap), height: bbox.height };
        ctx.save();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = Math.max(4, bbox.height * 0.018);
        ctx.beginPath();
        ctx.moveTo(dividerX, bbox.y + 4);
        ctx.lineTo(dividerX, bbox.y + bbox.height - 4);
        ctx.stroke();
        ctx.restore();
        drawFitText(ctx, leftTopLines, { ...leftBox, height: options.leftBottom ? leftBox.height * 0.68 : leftBox.height }, "900 64px Arial Black, Arial, sans-serif", "center");
        if (options.leftBottom) {
            drawFitText(ctx, [options.leftBottom], { x: leftBox.x, y: leftBox.y + leftBox.height * 0.66, width: leftBox.width, height: leftBox.height * 0.34 }, "400 34px Arial, sans-serif", "center");
        }
        drawFitText(ctx, rightLines, rightBox, `${options.boldRight === false ? 500 : 900} 52px Arial Black, Arial, sans-serif`, "left");
    }

    function drawTitleOnly(ctx, bbox) {
        if (!bbox) return;
        drawFitText(ctx, [state.fields.event_title], bbox, "900 64px Arial Black, Arial, sans-serif", "center");
    }

    function drawSubtitleOnly(ctx, bbox) {
        if (!bbox) return;
        const lines = String(state.fields.event_subtitle || "").split(/\n+/).filter(Boolean);
        drawFitText(ctx, lines, bbox, "500 46px Arial, sans-serif", "left");
    }

    function drawParagraphBox(ctx, text, bbox) {
        if (!bbox || !text) return;
        drawParagraph(ctx, String(text), bbox, "400 34px Arial, sans-serif");
    }

    function drawSingleLine(ctx, text, bbox, font, align = "left") {
        if (!bbox || !text) return;
        drawFitText(ctx, [String(text).toUpperCase()], bbox, font, align);
    }

    function drawFitText(ctx, lines, bbox, font, align = "left") {
        const clean = (lines || []).filter(Boolean).map((l) => String(l).toUpperCase());
        if (!clean.length || !bbox) return;
        let size = parseInt((font.match(/(\d+)px/) || ["", "40"])[1], 10);
        const fontTemplate = font;
        while (size > 8) {
            ctx.font = fontTemplate.replace(/\d+px/, `${size}px`);
            const maxWidth = Math.max(...clean.map((line) => ctx.measureText(line).width));
            const totalHeight = clean.length * size * 1.08;
            if (maxWidth <= bbox.width && totalHeight <= bbox.height) break;
            size -= 2;
        }
        ctx.save();
        ctx.font = fontTemplate.replace(/\d+px/, `${size}px`);
        ctx.fillStyle = "#fff";
        ctx.textAlign = align;
        ctx.textBaseline = "middle";
        const lineHeight = size * 1.08;
        let y = bbox.y + (bbox.height - clean.length * lineHeight) / 2 + lineHeight / 2;
        for (const line of clean) {
            const x = align === "center" ? bbox.x + bbox.width / 2 : align === "right" ? bbox.x + bbox.width : bbox.x;
            ctx.fillText(line, x, y);
            y += lineHeight;
        }
        ctx.restore();
    }

    function drawParagraph(ctx, text, bbox, font) {
        const words = text.split(/\s+/).filter(Boolean);
        let size = parseInt((font.match(/(\d+)px/) || ["", "32"])[1], 10);
        const fontTemplate = font;
        let lines = [];
        while (size > 9) {
            ctx.font = fontTemplate.replace(/\d+px/, `${size}px`);
            lines = [];
            let current = "";
            for (const word of words) {
                const probe = current ? `${current} ${word}` : word;
                if (ctx.measureText(probe).width <= bbox.width) current = probe;
                else {
                    if (current) lines.push(current);
                    current = word;
                }
            }
            if (current) lines.push(current);
            if (lines.length * size * 1.25 <= bbox.height) break;
            size -= 2;
        }
        drawFitText(ctx, lines, bbox, fontTemplate.replace(/\d+px/, `${size}px`), "left");
    }

    function drawImageBox(ctx, image, box) {
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

    function onPointerDown(ev) {
        const canvas = document.getElementById("posterCanvas");
        const template = currentTemplate();
        const info = state.templateCache.get(template.key);
        const geometry = info?.geometries?.image_mask;
        const bbox = geometry?.bbox || info?.bboxes?.image_mask;
        if (!bbox) return;
        const rect = canvas.getBoundingClientRect();
        const x = ((ev.clientX - rect.left) / rect.width) * canvas.width;
        const y = ((ev.clientY - rect.top) / rect.height) * canvas.height;
        const inside = geometry?.corners?.length === 4 ? pointInPolygon(x, y, geometry.corners) : (x >= bbox.x && x <= bbox.x + bbox.width && y >= bbox.y && y <= bbox.y + bbox.height);
        if (!inside) return;
        ev.preventDefault();
        const variant = ensureVariant(state.selectedTemplateKey);
        const start = { x: ev.clientX, y: ev.clientY, ox: variant.image.offsetX || 0, oy: variant.image.offsetY || 0 };
        const move = async (moveEv) => {
            variant.image.offsetX = start.ox + (moveEv.clientX - start.x) * (canvas.width / rect.width);
            variant.image.offsetY = start.oy + (moveEv.clientY - start.y) * (canvas.height / rect.height);
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
            const p = data.poster;
            state.sourceImageBase64 = p.source_image;
            state.sourceImageFilename = p.source_image_filename;
            state.externalLogoBase64 = p.external_logo_image;
            state.externalLogoFilename = p.external_logo_filename;
            state.qrImageBase64 = data.qr_image || "";
            state.editorState = p.editor_state || {};
            state.selectedTemplateKey = state.editorState.selectedTemplateKey || (data.templates[0] && data.templates[0].key) || "";
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
