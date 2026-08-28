(() => {
    "use strict";

    const root = document.getElementById("gl-editor-root");
    const posterId = parseInt(root?.dataset?.posterId || "0", 10);
    const APP_VERSION = "19.0.1.7.1";

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
        imageObjectCache: new Map(),
        imageEditMode: "global",
        activeHandle: null,
        renderToken: 0,
        activeTextField: "event_title",
        selectedOverlayRole: "",
        odooTemplateDefaults: {},
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


    const TEXT_FIELDS = [
        ["date_text", "Datum"],
        ["time_text", "Uhrzeit"],
        ["event_type_text", "Kategorie"],
        ["event_title", "Titel"],
        ["event_subtitle", "Untertitel"],
        ["summary_text", "Kurzzusammenfassung"],
        ["photo_credit", "Fotocredit"],
        ["ticket_link_text", "Ticketlink"],
    ];

    const TEXT_FIELD_LABELS = Object.fromEntries(TEXT_FIELDS);

    function defaultVariantState() {
        return {
            image: { ...defaultImageTransform() },
            imageCustom: false,
            qr: { dx: 0, dy: 0, scale: 1 },
            externalLogo: { dx: 0, dy: 0, scale: 1 },
            sticker: { dx: 0, dy: 0, scale: 1 },
            divider: { dx: 0, dy: 0, width: 0, height: 0 },
            textStyles: {},
            overlayOverrides: {},
        };
    }

    function defaultTextStyle() {
        return { dx: 0, dy: 0, size: 0, font: "auto", align: "auto" };
    }

    function deepClone(value) {
        return value ? JSON.parse(JSON.stringify(value)) : value;
    }

    function fontChoiceLabel(value) {
        return ({ auto: "Vorlage", regular: "Regular", bold: "Bold", condensed: "Condensed" }[value] || value);
    }

    function templateDisplayName(templateKey) {
        const template = state.data?.templates?.find((t) => t.key === templateKey);
        return template?.name || templateKey;
    }

    async function fetchJson(url, payload = {}) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (data?.error) throw new Error(data.error);
        return data;
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

    function loadImageCached(src) {
        if (!src) return Promise.resolve(null);
        if (!state.imageObjectCache.has(src)) {
            state.imageObjectCache.set(src, loadImage(src));
        }
        return state.imageObjectCache.get(src);
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

    function shiftBox(box, dx = 0, dy = 0) {
        if (!box || (!dx && !dy)) return box || null;
        return { ...box, x: box.x + dx, y: box.y + dy };
    }

    function shiftGeometry(geometry, dx = 0, dy = 0) {
        if (!geometry || (!dx && !dy)) return geometry || null;
        return {
            ...geometry,
            bbox: shiftBox(geometry.bbox, dx, dy),
            corners: geometry.corners?.length
                ? geometry.corners.map((point) => ({ ...point, x: point.x + dx, y: point.y + dy }))
                : geometry.corners,
        };
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
            state.editorState.variants[templateKey] = defaultVariantState();
        }
        const variant = state.editorState.variants[templateKey];
        variant.image = variant.image || { ...defaultImageTransform() };
        variant.qr = variant.qr || { dx: 0, dy: 0, scale: 1 };
        variant.externalLogo = variant.externalLogo || { dx: 0, dy: 0, scale: 1 };
        variant.sticker = variant.sticker || { dx: 0, dy: 0, scale: 1 };
        variant.divider = variant.divider || { dx: 0, dy: 0, width: 0, height: 0 };
        variant.textStyles = variant.textStyles || {};
        variant.overlayOverrides = variant.overlayOverrides || {};
        return variant;
    }

    function getTextStyle(templateKey, field) {
        const variant = ensureVariant(templateKey);
        if (!variant.textStyles[field]) variant.textStyles[field] = defaultTextStyle();
        return variant.textStyles[field];
    }

    function setTextStyle(templateKey, field, patch) {
        const current = { ...defaultTextStyle(), ...getTextStyle(templateKey, field) };
        ensureVariant(templateKey).textStyles[field] = { ...current, ...patch };
    }

    function currentTextStyle() {
        return getTextStyle(state.selectedTemplateKey, state.activeTextField);
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

    function editableOverlayAssets(template) {
        const ignore = new Set(["image_mask", "date_title", "time_subtitle", "time_ticketlink", "title", "subtitle", "summary", "photo_credit", "ticket_link", "qr", "external_logo"]);
        const assets = [];
        for (const asset of template?.assets || []) {
            if (!asset?.role || ignore.has(asset.role)) continue;
            if (!assets.find((entry) => entry.role === asset.role)) assets.push(asset);
        }
        return assets;
    }

    function humanizeRole(role) {
        return String(role || "")
            .replace(/^static_/, "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (m) => m.toUpperCase());
    }

    function overrideAssetSrc(templateKey, asset) {
        const variant = ensureVariant(templateKey);
        const override = variant.overlayOverrides?.[asset.role];
        if (!override?.base64) return cacheBustedUrl(asset.url);
        return dataUrlFromBase64(override.base64, extensionMime(override.filename || "overlay.png", "image/png"));
    }

    function syncOverlayRoleOptions() {
        const select = document.getElementById("overlayRoleSelect");
        if (!select) return;
        const template = currentTemplate();
        const assets = editableOverlayAssets(template);
        select.innerHTML = assets.length
            ? assets.map((asset) => `<option value="${escapeHtml(asset.role)}">${escapeHtml(humanizeRole(asset.role))}</option>`).join("")
            : '<option value="">Keine austauschbaren PNG-Overlays</option>';
        if (!assets.find((asset) => asset.role === state.selectedOverlayRole)) {
            state.selectedOverlayRole = assets[0]?.role || "";
        }
        select.value = state.selectedOverlayRole || "";
        const removeBtn = document.getElementById("removeOverlayBtn");
        if (removeBtn) removeBtn.disabled = !state.selectedOverlayRole;
    }

    function syncTextStyleInputs() {
        const style = currentTextStyle();
        const fieldSelect = document.getElementById("textStyleTarget");
        const fontSelect = document.getElementById("textStyleFont");
        const alignSelect = document.getElementById("textStyleAlign");
        const sizeInput = document.getElementById("textStyleSize");
        const dxInput = document.getElementById("textStyleDx");
        const dyInput = document.getElementById("textStyleDy");
        const info = document.getElementById("textStyleInfo");
        if (fieldSelect) fieldSelect.value = state.activeTextField;
        if (fontSelect) fontSelect.value = style.font || "auto";
        if (alignSelect) alignSelect.value = style.align || "auto";
        if (sizeInput) sizeInput.value = style.size || 0;
        if (dxInput) dxInput.value = style.dx || 0;
        if (dyInput) dyInput.value = style.dy || 0;
        if (info) info.textContent = `Aktuell: ${TEXT_FIELD_LABELS[state.activeTextField] || state.activeTextField}`;
    }

    async function saveCurrentTemplateDefaultsToOdoo() {
        const templateKey = state.selectedTemplateKey;
        const defaults = deepClone(ensureVariant(templateKey));
        await fetchJson(`/groundlift_graphics/template_defaults/${encodeURIComponent(templateKey)}/save`, { defaults });
        state.odooTemplateDefaults[templateKey] = defaults;
        setStatus(`Odoo-Standard für ${templateDisplayName(templateKey)} gespeichert.`);
    }

    async function loadCurrentTemplateDefaultsFromOdoo() {
        const templateKey = state.selectedTemplateKey;
        try {
            const payload = await fetchJson(`/groundlift_graphics/template_defaults/${encodeURIComponent(templateKey)}/load`, {});
            if (!payload?.found || !payload?.defaults) {
                setStatus(`Kein Odoo-Standard für ${templateDisplayName(templateKey)} gefunden.`, true);
                return false;
            }
            const merged = { ...defaultVariantState(), ...payload.defaults };
            merged.textStyles = { ...(payload.defaults.textStyles || {}) };
            merged.overlayOverrides = { ...(payload.defaults.overlayOverrides || {}) };
            state.editorState.variants[templateKey] = merged;
            state.odooTemplateDefaults[templateKey] = deepClone(merged);
            state.templateCache.delete(templateKey);
            syncVariantInputs();
            syncTextStyleInputs();
            syncOverlayRoleOptions();
            setStatus(`Odoo-Standard für ${templateDisplayName(templateKey)} geladen.`);
            return true;
        } catch (error) {
            console.error(error);
            setStatus(`Odoo-Standard konnte nicht geladen werden: ${error.message}`, true);
            return false;
        }
    }

    function hasMeaningfulVariantData(variant) {
        if (!variant) return false;
        const hasTransform = (obj = {}, keys = []) => keys.some((key) => Math.abs(Number(obj[key] || 0)) > 0.0001) || Math.abs(Number(obj.scale || 1) - 1) > 0.0001;
        const hasTextStyle = Object.values(variant.textStyles || {}).some((style) => style && (Math.abs(Number(style.dx || 0)) > 0.0001 || Math.abs(Number(style.dy || 0)) > 0.0001 || Number(style.size || 0) > 0 || (style.font && style.font !== "auto") || (style.align && style.align !== "auto")));
        const hasDivider = hasTransform(variant.divider || {}, ["dx", "dy", "width", "height"]);
        const hasQr = hasTransform(variant.qr || {}, ["dx", "dy"]);
        const hasLogo = hasTransform(variant.externalLogo || {}, ["dx", "dy"]);
        const hasSticker = hasTransform(variant.sticker || {}, ["dx", "dy"]);
        const hasImage = Boolean(variant.imageCustom) || hasTransform(variant.image || {}, ["offsetX", "offsetY", "rotation"]);
        const hasOverlay = Object.keys(variant.overlayOverrides || {}).length > 0;
        return hasTextStyle || hasDivider || hasQr || hasLogo || hasSticker || hasImage || hasOverlay;
    }

    async function prefillVariantsFromOdooDefaults() {
        state.editorState.variants = state.editorState.variants || {};
        for (const template of state.data?.templates || []) {
            const key = template.key;
            const existing = state.editorState.variants[key];
            if (existing && hasMeaningfulVariantData(existing)) continue;
            try {
                const payload = await fetchJson(`/groundlift_graphics/template_defaults/${encodeURIComponent(key)}/load`, {});
                if (!payload?.found || !payload?.defaults) continue;
                const merged = { ...defaultVariantState(), ...payload.defaults };
                merged.textStyles = { ...(payload.defaults.textStyles || {}) };
                merged.overlayOverrides = { ...(payload.defaults.overlayOverrides || {}) };
                state.editorState.variants[key] = merged;
                state.odooTemplateDefaults[key] = deepClone(merged);
            } catch (error) {
                console.warn(`Odoo-Standard konnte für ${key} nicht geladen werden`, error);
            }
        }
    }

    function applyTextBoxStyle(box, style) {
        if (!box) return box;
        return { ...box, x: box.x + Number(style?.dx || 0), y: box.y + Number(style?.dy || 0) };
    }

    function overrideFont(baseFont, style) {
        const parsedSize = parseInt((String(baseFont).match(/(\d+)px/) || ["", "40"])[1], 10);
        const size = style?.size > 0 ? style.size : parsedSize;
        if (!style || style.font === "auto") {
            return String(baseFont).replace(/\d+px/, `${size}px`);
        }
        const familyMap = {
            regular: [400, FONT_REGULAR],
            bold: [900, FONT_BOLD],
            condensed: [600, FONT_CONDENSED],
        };
        const [weight, family] = familyMap[style.font] || [400, FONT_REGULAR];
        return `${weight} ${size}px ${family}`;
    }

    function textAlign(style, fallback = "left") {
        return style?.align && style.align !== "auto" ? style.align : fallback;
    }

    function maxFontSize(base, style) {
        return style?.size > 0 ? style.size : base;
    }

    function applyDividerVariant(bbox, dividerVariant = {}) {
        if (!bbox) return bbox;
        return {
            x: bbox.x + Number(dividerVariant.dx || 0),
            y: bbox.y + Number(dividerVariant.dy || 0),
            width: Math.max(1, dividerVariant.width > 0 ? Number(dividerVariant.width) : bbox.width),
            height: Math.max(1, dividerVariant.height > 0 ? Number(dividerVariant.height) : bbox.height),
        };
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
                const image = await loadImage(overrideAssetSrc(template.key, asset));
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
        if (template.photo_only) {
            const fullCanvasBox = {
                x: 0,
                y: 0,
                width: template.canvas_width,
                height: template.canvas_height,
            };
            bboxes.image_mask = fullCanvasBox;
            geometries.image_mask = { bbox: fullCanvasBox, corners: null };
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
                            <button class="gl-btn gl-btn-secondary w-100 mb-2" id="uploadExternalLogoBtn">Externes Logo hochladen / ersetzen</button>
                            <input type="file" accept="image/*" id="externalLogoFile" class="gl-hidden"/>
                            <button class="gl-btn gl-btn-light w-100" id="removeExternalLogoBtn">Externes Logo entfernen</button>
                            <div class="gl-small mt-2">Im Bild ziehen = verschieben, Mausrad = sanft zoomen. Seiten-Anfasser = Crop/Position, Eck-Anfasser = Drehen.</div>
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
                            ${input("admission_time_text", "Foyer Eingang – Einlass (Uhrzeit)")}
                            ${input("ticket_price_text", "Foyer Eingang – Tickets ab")}
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
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Text-Einstellungen je Element</label>
                            <div class="mb-2">
                                <label class="gl-label">Textelement</label>
                                <select class="gl-input" id="textStyleTarget">
                                    ${TEXT_FIELDS.map(([key, label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join("")}
                                </select>
                            </div>
                            <div class="gl-small mb-2" id="textStyleInfo"></div>
                            <div class="gl-grid-2">
                                <div class="gl-col"><label class="gl-label">Schriftart</label><select class="gl-input" id="textStyleFont"><option value="auto">Vorlage</option><option value="regular">Regular</option><option value="bold">Bold</option><option value="condensed">Condensed</option></select></div>
                                <div class="gl-col"><label class="gl-label">Ausrichtung</label><select class="gl-input" id="textStyleAlign"><option value="auto">Vorlage</option><option value="left">Links</option><option value="center">Zentriert</option><option value="right">Rechts</option></select></div>
                                <div class="gl-col"><label class="gl-label">Schriftgröße</label><input class="gl-input" type="number" step="1" id="textStyleSize"/></div>
                                <div class="gl-col"><label class="gl-label">Position X</label><input class="gl-input" type="number" step="1" id="textStyleDx"/></div>
                                <div class="gl-col"><label class="gl-label">Position Y</label><input class="gl-input" type="number" step="1" id="textStyleDy"/></div>
                            </div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Trennbalken</label>
                            <div class="gl-grid-2">
                                ${numberInput("divider.dx", "Balken X")}
                                ${numberInput("divider.dy", "Balken Y")}
                                ${numberInput("divider.width", "Breite px")}
                                ${numberInput("divider.height", "Länge px")}
                            </div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Externes Logo</label>
                            <div class="gl-grid-2">
                                ${numberInput("externalLogo.dx", "Logo X")}
                                ${numberInput("externalLogo.dy", "Logo Y")}
                                ${numberInput("externalLogo.scale", "Logo Größe", "0.05")}
                            </div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">QR-Code</label>
                            <div class="gl-grid-2">
                                ${numberInput("qr.dx", "QR X")}
                                ${numberInput("qr.dy", "QR Y")}
                                ${numberInput("qr.scale", "QR Größe", "0.05")}
                            </div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">PNG-Overlays im aktuellen Format ersetzen</label>
                            <div class="mb-2">
                                <label class="gl-label">Overlay</label>
                                <select class="gl-input" id="overlayRoleSelect"></select>
                            </div>
                            <button class="gl-btn gl-btn-secondary w-100 mb-2" id="uploadOverlayBtn">PNG-Overlay auswählen</button>
                            <input type="file" accept="image/png,image/webp,image/*" id="overlayFile" class="gl-hidden"/>
                            <button class="gl-btn gl-btn-light w-100" id="removeOverlayBtn">Overlay-Override entfernen</button>
                            <div class="gl-small mt-2">Ersetzt nur das ausgewählte PNG im aktuellen Ausspielformat.</div>
                        </div>
                        <div class="gl-section">
                            <label class="gl-label gl-label-strong">Standards für dieses Ausspielformat</label>
                            <button class="gl-btn gl-btn-secondary w-100 mb-2" id="saveTemplateDefaultsBtn">Aktuelles Format als Odoo-Standard speichern</button>
                            <button class="gl-btn gl-btn-light w-100" id="loadTemplateDefaultsBtn">Odoo-Standard laden</button>
                            <div class="gl-small mt-2">Speichert Text-, Divider-, QR-, Logo- und Overlay-Einstellungen global in Odoo für dieses Ausspielformat.</div>
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
        syncTextStyleInputs();
        syncOverlayRoleOptions();
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
        document.getElementById("uploadExternalLogoBtn").onclick = () => document.getElementById("externalLogoFile").click();
        document.getElementById("removeExternalLogoBtn").onclick = async () => {
            state.externalLogoBase64 = "";
            state.externalLogoFilename = "";
            await renderCanvas();
        };
        document.getElementById("uploadOverlayBtn").onclick = () => document.getElementById("overlayFile").click();
        document.getElementById("removeOverlayBtn").onclick = async () => {
            const variant = ensureVariant(state.selectedTemplateKey);
            if (!state.selectedOverlayRole) return;
            delete variant.overlayOverrides[state.selectedOverlayRole];
            state.templateCache.delete(state.selectedTemplateKey);
            await renderCanvas();
        };
        document.getElementById("saveTemplateDefaultsBtn").onclick = async () => {
            try {
                await saveCurrentTemplateDefaultsToOdoo();
            } catch (error) {
                console.error(error);
                setStatus(`Odoo-Standard konnte nicht gespeichert werden: ${error.message}`, true);
            }
        };
        document.getElementById("loadTemplateDefaultsBtn").onclick = async () => {
            if (await loadCurrentTemplateDefaultsFromOdoo()) await renderCanvas();
        };
        document.getElementById("sourceFile").onchange = async (ev) => {
            const file = ev.target.files[0];
            if (!file) return;
            state.sourceImageFilename = file.name;
            state.sourceImageBase64 = await fileToBase64(file);
            await applyPaletteFromSourceImage({ force: true });
            await renderCanvas();
        };
        document.getElementById("externalLogoFile").onchange = async (ev) => {
            const file = ev.target.files[0];
            if (!file) return;
            state.externalLogoFilename = file.name;
            state.externalLogoBase64 = await fileToBase64(file);
            await renderCanvas();
        };
        document.getElementById("overlayFile").onchange = async (ev) => {
            const file = ev.target.files[0];
            if (!file || !state.selectedOverlayRole) return;
            const variant = ensureVariant(state.selectedTemplateKey);
            variant.overlayOverrides[state.selectedOverlayRole] = {
                base64: await fileToBase64(file),
                filename: file.name,
            };
            state.templateCache.delete(state.selectedTemplateKey);
            await renderCanvas();
        };
        document.getElementById("templateSelect").onchange = async (ev) => {
            state.selectedTemplateKey = ev.target.value;
            state.editorState.selectedTemplateKey = state.selectedTemplateKey;
            syncVariantInputs();
            syncTextStyleInputs();
            syncOverlayRoleOptions();
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
        document.getElementById("overlayRoleSelect").onchange = (ev) => {
            state.selectedOverlayRole = ev.target.value || "";
        };
        document.getElementById("textStyleTarget").onchange = (ev) => {
            state.activeTextField = ev.target.value;
            syncTextStyleInputs();
        };
        [["textStyleFont", "font"], ["textStyleAlign", "align"], ["textStyleSize", "size"], ["textStyleDx", "dx"], ["textStyleDy", "dy"]].forEach(([id, field]) => {
            const node = document.getElementById(id);
            node.addEventListener("input", async (ev) => {
                const value = ["size", "dx", "dy"].includes(field) ? parseFloat(ev.target.value || 0) : ev.target.value;
                setTextStyle(state.selectedTemplateKey, state.activeTextField, { [field]: value });
                await renderCanvas();
            });
        });
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
        syncTextStyleInputs();
        syncOverlayRoleOptions();
    }

    function syncColorInputs() {
        root.querySelectorAll('.gl-field[data-field="color_1"], .gl-field[data-field="color_2"]').forEach((node) => {
            node.value = state.fields[node.dataset.field] || "#000000";
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


    function sourceImageSignature() {
        const value = state.sourceImageBase64 || "";
        if (!value) return "";
        return `${value.length}:${value.slice(0, 48)}:${value.slice(-48)}`;
    }

    function rgbToHex(color) {
        const toHex = (value) => clamp(Math.round(value || 0), 0, 255).toString(16).padStart(2, "0");
        return `#${toHex(color.r)}${toHex(color.g)}${toHex(color.b)}`;
    }

    function rgbToHsl(r, g, b) {
        r /= 255; g /= 255; b /= 255;
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        let h = 0;
        let s = 0;
        const l = (max + min) / 2;
        if (max !== min) {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            switch (max) {
                case r:
                    h = (g - b) / d + (g < b ? 6 : 0);
                    break;
                case g:
                    h = (b - r) / d + 2;
                    break;
                default:
                    h = (r - g) / d + 4;
                    break;
            }
            h /= 6;
        }
        return { h, s, l };
    }

    function hueToRgb(p, q, t) {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1 / 6) return p + (q - p) * 6 * t;
        if (t < 1 / 2) return q;
        if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
        return p;
    }

    function hslToRgb(h, s, l) {
        let r, g, b;
        if (s === 0) {
            r = g = b = l;
        } else {
            const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
            const p = 2 * l - q;
            r = hueToRgb(p, q, h + 1 / 3);
            g = hueToRgb(p, q, h);
            b = hueToRgb(p, q, h - 1 / 3);
        }
        return { r: r * 255, g: g * 255, b: b * 255 };
    }

    function colorDistance(a, b) {
        const dr = (a.r || 0) - (b.r || 0);
        const dg = (a.g || 0) - (b.g || 0);
        const db = (a.b || 0) - (b.b || 0);
        return Math.sqrt(dr * dr + dg * dg + db * db);
    }

    function normalizeGradientColor(color, index) {
        const hsl = rgbToHsl(color.r, color.g, color.b);
        const saturation = clamp(hsl.s * 1.18 + 0.08, 0.18, 0.92);
        const lightness = index === 0
            ? clamp(hsl.l * 0.58, 0.07, 0.24)
            : clamp(hsl.l * 0.72 + 0.025, 0.12, 0.36);
        return rgbToHex(hslToRgb(hsl.h, saturation, lightness));
    }

    function extractDominantPaletteFromImage(image) {
        if (!image || !image.width || !image.height) return null;
        const maxSide = 120;
        const scale = Math.min(1, maxSide / Math.max(image.width, image.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(image.width * scale));
        canvas.height = Math.max(1, Math.round(image.height * scale));
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        const buckets = new Map();

        const addPixel = (r, g, b, weight) => {
            const key = `${Math.round(r / 24)}:${Math.round(g / 24)}:${Math.round(b / 24)}`;
            const bucket = buckets.get(key) || { r: 0, g: 0, b: 0, weight: 0, score: 0 };
            bucket.r += r * weight;
            bucket.g += g * weight;
            bucket.b += b * weight;
            bucket.weight += weight;
            bucket.score += weight;
            buckets.set(key, bucket);
        };

        for (let i = 0; i < data.length; i += 4) {
            const alpha = data[i + 3];
            if (alpha < 96) continue;
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const hsl = rgbToHsl(r, g, b);
            if (hsl.l < 0.035 || hsl.l > 0.965) continue;
            if (hsl.s < 0.035 && (hsl.l < 0.12 || hsl.l > 0.88)) continue;
            const midtoneBoost = 1 - Math.abs(hsl.l - 0.48);
            const saturationBoost = Math.max(0.18, hsl.s);
            const weight = (0.35 + saturationBoost * 2.8 + midtoneBoost * 0.8) * (alpha / 255);
            addPixel(r, g, b, weight);
        }

        let candidates = Array.from(buckets.values())
            .filter((bucket) => bucket.weight > 0)
            .map((bucket) => ({
                r: bucket.r / bucket.weight,
                g: bucket.g / bucket.weight,
                b: bucket.b / bucket.weight,
                score: bucket.score,
            }))
            .sort((a, b) => b.score - a.score);

        if (!candidates.length) {
            // Fallback für sehr kontrastarme Bilder: ohne Filter erneut sammeln.
            for (let i = 0; i < data.length; i += 16) {
                if (data[i + 3] < 96) continue;
                addPixel(data[i], data[i + 1], data[i + 2], 1);
            }
            candidates = Array.from(buckets.values())
                .filter((bucket) => bucket.weight > 0)
                .map((bucket) => ({
                    r: bucket.r / bucket.weight,
                    g: bucket.g / bucket.weight,
                    b: bucket.b / bucket.weight,
                    score: bucket.score,
                }))
                .sort((a, b) => b.score - a.score);
        }

        if (!candidates.length) return null;
        const first = candidates[0];
        const second = candidates.find((color) => colorDistance(color, first) >= 72) || candidates[1] || first;

        if (second === first) {
            const hsl = rgbToHsl(first.r, first.g, first.b);
            const shifted = hslToRgb((hsl.h + 0.08) % 1, clamp(hsl.s + 0.16, 0.22, 0.9), clamp(hsl.l + 0.08, 0.16, 0.42));
            return [normalizeGradientColor(first, 0), normalizeGradientColor(shifted, 1)];
        }
        return [normalizeGradientColor(first, 0), normalizeGradientColor(second, 1)];
    }

    async function applyPaletteFromSourceImage(options = {}) {
        const signature = sourceImageSignature();
        if (!signature) return false;
        if (!options.force && state.editorState.paletteSourceImageSignature === signature) return false;
        try {
            const src = dataUrlFromBase64(state.sourceImageBase64, extensionMime(state.sourceImageFilename, "image/jpeg"));
            const image = await loadImageCached(src);
            const palette = extractDominantPaletteFromImage(image);
            if (!palette || !palette[0] || !palette[1]) return false;
            state.fields.color_1 = palette[0];
            state.fields.color_2 = palette[1];
            state.editorState.paletteSourceImageSignature = signature;
            syncColorInputs();
            return true;
        } catch (error) {
            console.warn("Automatische Farbpalette konnte nicht erzeugt werden", error);
            return false;
        }
    }

    async function refreshQr() {
        try {
            state.qrImageBase64 = await rpc("gl.graphics.poster", "generate_qr_base64", [state.fields.qr_url || state.fields.ticket_url || ""]);
        } catch (error) {
            console.warn(error);
        }
    }

    async function renderCanvas() {
        const token = ++state.renderToken;
        try {
            const template = currentTemplate();
            if (!template) return;
            const info = await ensureTemplateAssets(template);
            const visibleCanvas = document.getElementById("posterCanvas");
            const buffer = document.createElement("canvas");
            buffer.width = template.canvas_width;
            buffer.height = template.canvas_height;
            await paintTemplate(buffer.getContext("2d"), info, ensureVariant(template.key), true);
            if (token !== state.renderToken) return;
            if (visibleCanvas.width !== template.canvas_width) visibleCanvas.width = template.canvas_width;
            if (visibleCanvas.height !== template.canvas_height) visibleCanvas.height = template.canvas_height;
            const ctx = visibleCanvas.getContext("2d");
            ctx.clearRect(0, 0, visibleCanvas.width, visibleCanvas.height);
            ctx.drawImage(buffer, 0, 0);
        } catch (error) {
            console.error(error);
            setStatus(`Render-Fehler: ${error.message}`, true);
        }
    }

    async function paintTemplate(ctx, info, variant, showGuides = false) {
        if (!ctx || !info || !info.template) return;
        const template = info.template;
        const templateKey = template.key;
        ctx.clearRect(0, 0, template.canvas_width, template.canvas_height);

        if (template.photo_only) {
            await safeLayer("Veranstaltungsbild", () => drawSourceImage(ctx, info, getImageTransform(template.key)));
            if (showGuides) {
                safeLayer("Bildgriffe", () => drawImageHandles(ctx, info.geometries.image_mask));
            }
            return;
        }

        // Ebenenreihenfolge:
        // 1) Verlauf ganz hinten
        // 2) hochgeladenes Bild / Content
        // 3) feste Logos / Rahmen / Texte / QR
        // 4) Störer immer ganz oben
        drawGradient(ctx, template);

        const qrImg = state.qrImageBase64
            ? await safeLayer("QR-Code laden", () => loadImageCached(dataUrlFromBase64(state.qrImageBase64, "image/png")))
            : null;
        const img = info.imagesByRole || {};
        const box = info.bboxes || {};
        const regions = info.regions || {};
        const contentShift = resolveTemplateContentShift(template, box);

        for (const overlay of info.staticOverlays || []) {
            if (["static_admission_price", "static_begin"].includes(overlay.role)) continue;
            safeDrawImage(ctx, overlay.image, 0, 0, template.canvas_width, template.canvas_height, overlay.role || "Static Overlay");
        }

        // Feste grafische Ebenen, die nicht als "static_*" erkannt werden,
        // aber trotzdem echte sichtbare Layer sind (z. B. Kino-Claim,
        // Sudhaus-Getränkekarte und externe Partnerlogos).
        safeDrawImage(ctx, img.claim, 0, 0, template.canvas_width, template.canvas_height, "Claim");
        safeDrawImage(ctx, img.drink_card, 0, 0, template.canvas_width, template.canvas_height, "Getränkekarte");

        const adjustedText = resolveTextLayoutAdjustments(template, box, regions);
        const textBox = (role) => adjustedText.boxes[role] || box[role];
        const textRegions = (role) => adjustedText.regions[role] || regions[role] || [];
        const dateTitleLayout = textBox("date_title") ? resolveDateTitleLayout(textBox("date_title"), textRegions("date_title")) : null;
        const photoCreditBox = resolvePhotoCreditTargetBox(template, box);
        const photoCreditFont = resolvePhotoCreditFont(template);
        const qrBox = resolveQrTargetBox(template, box);
        const ticketLinkBox = resolveTicketLinkTargetBox(template, box);
        const dividerVariant = variant.divider || {};

        const drawShiftedContent = async () => {
            await safeLayer("Veranstaltungsbild", () => drawSourceImage(ctx, info, getImageTransform(template.key)));
            safeDrawImage(ctx, img.frame, 0, 0, template.canvas_width, template.canvas_height, "Rahmen");
            safeLayer("Datum/Titel", () => {
                if (templateKey === "theater_konzert") {
                    drawStandaloneDividerLeftOfBox(ctx, textBox("date_title"), template, dividerVariant);
                    drawTitleSubtitleStack(ctx, textBox("date_title"), state.fields.event_title, state.fields.event_subtitle, {
                        titleRatio: 0.66,
                        gap: Math.max(8, template.canvas_height * 0.008),
                    });
                } else {
                    drawDateTitle(ctx, textBox("date_title"), textRegions("date_title"), dateTitleLayout, template, dividerVariant);
                }
            });
            safeLayer("Uhrzeit/Untertitel", () => drawTimeSubtitle(ctx, textBox("time_subtitle"), textRegions("time_subtitle"), dateTitleLayout, template));
            safeLayer("Uhrzeit/Ticketlink", () => drawTimeTicketlink(ctx, textBox("time_ticketlink"), textRegions("time_ticketlink"), template));
            safeLayer("Titel", () => drawTitleOnly(ctx, textBox("title"), textRegions("title"), template, dividerVariant));
            safeLayer("Untertitel", () => drawSubtitleOnly(ctx, textBox("subtitle"), textRegions("subtitle"), template));
            safeLayer("Kurzzusammenfassung", () => drawParagraphBox(ctx, state.fields.summary_text, textBox("summary"), template));
            safeLayer("Fotocredit", () => drawPhotoCredit(ctx, state.fields.photo_credit, photoCreditBox, photoCreditFont, template));
            if (ticketLinkBox) {
                safeLayer("Ticketlink", () => drawSingleLine(ctx, state.fields.ticket_link_text, ticketLinkBox, "600 28px GroundliftCondensed, Arial Narrow, Arial, sans-serif", "center", template, "ticket_link_text"));
            }
            if (qrImg && qrBox) safeLayer("QR-Code zeichnen", () => drawImageBox(ctx, qrImg, applyBoxVariant(qrBox, variant.qr)));
            await safeLayer("Externes Logo", () => drawExternalLogo(ctx, img, box, variant, template));
        };

        if (contentShift.dx || contentShift.dy) {
            ctx.save();
            ctx.translate(contentShift.dx, contentShift.dy);
            await drawShiftedContent();
            ctx.restore();
        } else {
            await drawShiftedContent();
        }

        if (templateKey === "foyer_eingang") {
            safeLayer("Einlass / Ticketpreis", () => drawFoyerAdmissionPrice(ctx, box.static_admission_price, template));
        }
        if (templateKey === "theater_konzert") {
            safeLayer("Beginn", () => drawTheaterBegin(ctx, box.static_begin, template));
        }

        if (img.logo) {
            await safeLayer("Logo", () => {
                if (img.logo.width === template.canvas_width && img.logo.height === template.canvas_height) {
                    safeDrawImage(ctx, img.logo, 0, 0, template.canvas_width, template.canvas_height, "Logo");
                } else if (box.logo) {
                    drawLayerPreserveAspect(ctx, img.logo, box.logo, box.logo);
                }
            });
        }

        if (img.sticker && state.fields.sticker_mode !== "hidden" && box.sticker) {
            if (contentShift.dx || contentShift.dy) {
                ctx.save();
                ctx.translate(contentShift.dx, contentShift.dy);
                await safeLayer("Störer", () => drawCroppedLayer(ctx, img.sticker, box.sticker, applyBoxVariant(box.sticker, variant.sticker)));
                ctx.restore();
            } else {
                await safeLayer("Störer", () => drawCroppedLayer(ctx, img.sticker, box.sticker, applyBoxVariant(box.sticker, variant.sticker)));
            }
        }

        if (showGuides) {
            safeLayer("Bildgriffe", () => {
                const guideGeometry = shiftGeometry(info.geometries.image_mask || { bbox: info.bboxes.image_mask }, contentShift.dx, contentShift.dy);
                drawImageHandles(ctx, guideGeometry);
            });
        }
    }

    function resolveTemplateContentShift(template, box = {}) {
        if (!template || template.key !== "social_post") return { dx: 0, dy: 0 };
        const group = unionBoxes([box.image_mask, box.frame, box.sticker, box.date_title, box.time_subtitle, box.photo_credit, box.ticket_link].filter(Boolean));
        if (!group) return { dx: 0, dy: 0 };
        return {
            dx: Math.round(template.canvas_width / 2 - (group.x + group.width / 2)),
            dy: 0,
        };
    }

    function resolveTextLayoutAdjustments(template, box = {}, regions = {}) {
        const boxes = { ...box };
        const adjustedRegions = { ...regions };
        if (template?.key === "sudhaus_main") {
            // Sudhaus Main: Der gesamte Textblock unter dem Bild soll klar im blauen Bereich sitzen
            // und nicht in das Veranstaltungsfoto hineinragen.
            const dy = Math.round((template.canvas_height || 1080) * 0.07);
            for (const role of ["date_title", "time_subtitle"]) {
                boxes[role] = shiftBox(boxes[role], 0, dy);
                adjustedRegions[role] = shiftRegions(regions[role], 0, dy);
            }
        }
        return { boxes, regions: adjustedRegions };
    }

    function shiftRegions(regionList = [], dx = 0, dy = 0) {
        return (regionList || []).map((region) => shiftBox(region, dx, dy)).filter(Boolean);
    }

    function templateIdentity(template) {
        return [template?.key, template?.name, template?.output_suffix]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
    }

    function isFoyerTemplate(template) {
        return /foyer/.test(templateIdentity(template));
    }

    function isFoyerEingangTemplate(template) {
        return /foyer[_\s-]*eingang|eingang[_\s-]*foyer/.test(templateIdentity(template));
    }

    function isMainFoyerTemplate(template) {
        const identity = templateIdentity(template);
        if (!/foyer/.test(identity) || isFoyerEingangTemplate(template)) return false;
        const key = String(template?.key || "").trim().toLowerCase();
        const name = String(template?.name || "").trim().toLowerCase();
        const suffix = String(template?.output_suffix || "").trim().toLowerCase();
        return key === "foyer" || name === "foyer" || suffix === "foyer" || /(^|[_\s-])foyer($|[_\s-])/.test(identity);
    }

    function resolveFrameReferenceBox(box = {}) {
        const direct = box.frame || box.rahmen || box.image_frame || box.overlay_frame || box.static_frame || box.static_rahmen;
        if (direct) return direct;
        const candidates = Object.entries(box || {})
            .filter(([role, bbox]) => bbox && /(frame|rahmen)/i.test(role))
            .map(([, bbox]) => bbox)
            .sort((a, b) => (b.width * b.height) - (a.width * a.height));
        return candidates[0] || null;
    }

    function resolvePhotoCreditFont(template) {
        if (isFoyerTemplate(template)) return "400 22px GroundliftRegular, Arial, sans-serif";
        return "400 28px GroundliftRegular, Arial, sans-serif";
    }

    function resolvePhotoCreditTargetBox(template, box = {}) {
        if (!template) return box.photo_credit || null;
        if (template.key === "social_post") return box.photo_credit || null;
        const original = box.photo_credit || null;
        const frame = resolveFrameReferenceBox(box);
        if (isMainFoyerTemplate(template)) {
            // Nur Ausspielformat "Foyer" – ausdrücklich nicht "Foyer Eingang".
            // In dieser Vorlage liefert die Asset-Erkennung keinen verlässlichen Referenzrahmen
            // für die untere dünne horizontale Rahmenlinie. Deshalb wird der Fotocredit
            // template-fest direkt unter diese Linie gesetzt. Bei 1080x1920 liegt die Linie
            // bei ca. y=1110; die Textbox beginnt bei ca. y=1114.
            const height = Math.max(16, Math.min(original?.height || 22, 22));
            const width = Math.max(240, Math.min(original?.width || Math.round(template.canvas_width * 0.42), Math.round(template.canvas_width * 0.80)));
            const x = Math.max(0, Math.min(template.canvas_width - width, original?.x ?? Math.round(template.canvas_width * 0.38)));
            const y = Math.round(template.canvas_height * 0.580);
            return {
                x,
                y: Math.min(template.canvas_height - height - 6, Math.max(0, y)),
                width,
                height,
            };
        }
        if (isFoyerTemplate(template)) {
            // Foyer Eingang und sonstige Foyer-ähnliche Vorlagen behalten die rahmenbasierte Logik.
            const height = Math.max(16, Math.min(original?.height || 22, 22));
            const widthBase = original?.width || Math.round((frame?.width || template.canvas_width) * 0.78);
            const maxWidth = Math.round((frame?.width || template.canvas_width) * 0.96);
            const width = Math.max(240, Math.min(widthBase, maxWidth));
            const gap = Math.max(1, Math.round(template.canvas_height * 0.0008));
            const x = frame
                ? frame.x + (frame.width - width) / 2
                : Math.max(0, Math.min(template.canvas_width - width, original?.x ?? Math.round((template.canvas_width - width) / 2)));
            const fallbackLift = Math.round(template.canvas_height * 0.055);
            const y = frame
                ? Math.round(frame.y + frame.height + gap)
                : Math.max(0, Math.round((original?.y ?? 0) - fallbackLift));
            return {
                x,
                y: Math.min(template.canvas_height - height - 6, y),
                width,
                height,
            };
        }
        if (!frame) return original;
        const preferredWidth = original?.width || Math.round(frame.width * 0.62);
        const width = Math.max(150, Math.min(preferredWidth, Math.round(frame.width * 0.78)));
        const height = Math.max(22, Math.min(original?.height || 32, Math.round(template.canvas_height * 0.012)));
        const gap = Math.max(4, Math.round(template.canvas_height * 0.006));
        const x = frame.x + (frame.width - width) / 2;
        const y = Math.min(template.canvas_height - height - 6, frame.y + frame.height + gap);
        return { x, y, width, height };
    }

    function drawPhotoCredit(ctx, text, bbox, font, template) {
        if (!bbox || !text) return;
        const style = getTextStyle(template?.key, "photo_credit");
        drawFitText(ctx, [String(text).toUpperCase()], applyTextBoxStyle(bbox, style), overrideFont(font, style), textAlign(style, "center"), {
            allowWrap: false,
            valign: isFoyerTemplate(template) ? "top" : "middle",
            lineHeight: 1.0,
            maxSize: maxFontSize(parseInt((String(font).match(/(\d+)px/) || ["", "28"])[1], 10), style),
        });
    }

    function resolveQrTargetBox(template, box = {}) {
        if (!template) return box.qr || null;
        if (box.qr) return box.qr;
        if (template.key === "plakat") {
            const size = Math.round(Math.min(template.canvas_width, template.canvas_height) * 0.09);
            const margin = Math.round(template.canvas_width * 0.035);
            const fallbackY = template.canvas_height - size - margin;
            const y = box.ticket_link ? Math.max(margin, box.ticket_link.y - size - Math.round(template.canvas_height * 0.02)) : fallbackY;
            return { x: template.canvas_width - size - margin, y, width: size, height: size };
        }
        return null;
    }

    function resolveTicketLinkTargetBox(template, box = {}) {
        if (!template) return box.ticket_link || null;
        if (template.key === "sudhaus_main") return null;
        return box.ticket_link || null;
    }

    function resolveExternalLogoTargetBox(template, box = {}) {
        if (!template || !state.externalLogoBase64) return null;
        if (template.key === "stream_problem") return null;
        if (["foyer_eingang", "theater_konzert", "stream_start", "stream_pause", "stream_ende"].includes(template.key)) {
            return box.external_logo || null;
        }
        if (template.key === "kino") {
            const textUnion = unionBoxes([box.date_title, box.time_subtitle].filter(Boolean));
            if (!textUnion) return null;
            const width = Math.min(Math.round(template.canvas_width * 0.16), Math.round(textUnion.width * 0.56));
            const height = Math.round(width * 0.42);
            return {
                x: textUnion.x + (textUnion.width - width) / 2,
                y: Math.min(template.canvas_height - height - 18, textUnion.y + textUnion.height + Math.round(template.canvas_height * 0.028)),
                width,
                height,
            };
        }
        if (template.key === "plakat") {
            const qr = resolveQrTargetBox(template, box);
            if (!qr) return null;
            const gap = Math.max(40, Math.round(template.canvas_width * 0.025));
            const width = Math.min(Math.round(template.canvas_width * 0.12), Math.max(120, qr.x - gap * 2));
            const height = Math.max(58, Math.round(width * 0.38));
            return {
                x: Math.max(gap, qr.x - width - gap),
                y: qr.y + (qr.height - height) / 2,
                width,
                height,
            };
        }
        if (template.key === "social_post") {
            const anchor = box.time_subtitle || box.date_title || box.frame || null;
            if (!anchor) return null;
            const margin = Math.round(template.canvas_width * 0.028);
            const width = Math.round(template.canvas_width * 0.13);
            const height = Math.max(48, Math.round(width * 0.38));
            return {
                x: Math.min(template.canvas_width - width - margin, boxRight(anchor) + margin),
                y: anchor.y + (anchor.height - height) / 2,
                width,
                height,
            };
        }
        if (template.key === "social_story") {
            const anchor = box.time_subtitle || box.subtitle || null;
            if (!anchor) return null;
            const margin = Math.round(template.canvas_width * 0.03);
            const availableWidth = Math.max(80, template.canvas_width - boxRight(anchor) - margin * 1.5);
            const width = Math.min(Math.round(template.canvas_width * 0.13), availableWidth);
            const height = Math.max(48, Math.round(width * 0.38));
            return {
                x: template.canvas_width - width - margin,
                y: anchor.y + (anchor.height - height) / 2,
                width,
                height,
            };
        }
        if (template.key === "foyer_eingang") {
            const summary = box.summary;
            const ticket = box.ticket_link;
            if (!summary) return null;
            const width = Math.round(template.canvas_width * 0.18);
            const height = Math.round(width * 0.36);
            const gap = Math.max(22, Math.round(template.canvas_height * 0.008));
            const targetY = ticket
                ? Math.min(summary.y + summary.height + gap, ticket.y - height - gap)
                : summary.y + summary.height + gap;
            return {
                x: (template.canvas_width - width) / 2,
                y: Math.max(summary.y, targetY),
                width,
                height,
            };
        }
        return box.external_logo || null;
    }

    function cleanGraphicValue(value) {
        return String(value || "").trim().replace(/\s+/g, " ");
    }

    function admissionTimeFromBeginText(value) {
        const result = cleanGraphicValue(value).toUpperCase();
        const match = result.match(/(?:^|\D)([01]?\d|2[0-3])(?:[.:]([0-5]\d))?(?:\s*UHR)?(?!\d)/);
        if (!match) return "";
        const minutes = (parseInt(match[1], 10) * 60 + parseInt(match[2] || "0", 10) - 60 + 24 * 60) % (24 * 60);
        return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
    }

    function normalizeAdmissionTime(value) {
        let result = cleanGraphicValue(value).toUpperCase();
        result = result.replace(/^EINLASS\s+(?:AB\s+)?/, "").trim();
        if (!result) return "";
        if (!/\bUHR\b/.test(result)) result += " UHR";
        return result;
    }

    function normalizeTicketPrice(value) {
        return cleanGraphicValue(value)
            .replace(/^TICKETS?\s*(?:AB)?\s*:?\s*/i, "")
            .trim();
    }

    function normalizeBeginTime(value) {
        let result = cleanGraphicValue(value).toUpperCase();
        result = result.replace(/^BEGINN\s+/, "").trim();
        result = result.replace(/\bUHR\b/g, "").trim();
        const match = result.match(/^(\d{1,2})[.:](\d{2})$/);
        if (match) {
            return match[2] === "00" ? `${parseInt(match[1], 10)} UHR` : `${parseInt(match[1], 10)}:${match[2]} UHR`;
        }
        return result ? `${result} UHR` : "";
    }

    function expandedTextBox(bbox, template, xPaddingRatio = 0.035, yPadding = 8) {
        if (!bbox) return null;
        const padX = Math.round((template?.canvas_width || 1920) * xPaddingRatio);
        return {
            x: Math.max(0, bbox.x - padX),
            y: Math.max(0, bbox.y - yPadding),
            width: Math.min((template?.canvas_width || 1920) - Math.max(0, bbox.x - padX), bbox.width + padX * 2),
            height: bbox.height + yPadding * 2,
        };
    }

    function drawFoyerAdmissionPrice(ctx, bbox, template) {
        if (!bbox) return;
        const admission = normalizeAdmissionTime(state.fields.admission_time_text);
        const price = normalizeTicketPrice(state.fields.ticket_price_text);
        const parts = [];
        if (admission) parts.push(`EINLASS AB ${admission}`);
        if (price) parts.push(`TICKETS AB: ${price}`);
        if (!parts.length) return;
        drawSingleLine(
            ctx,
            parts.join(" | "),
            expandedTextBox(bbox, template, 0.055, 10),
            "600 42px GroundliftCondensed, Arial Narrow, Arial, sans-serif",
            "center",
            template,
            null,
        );
    }

    function drawTheaterBegin(ctx, bbox, template) {
        const beginTime = normalizeBeginTime(state.fields.time_text);
        if (!bbox || !beginTime) return;
        drawSingleLine(
            ctx,
            `BEGINN ${beginTime}`,
            expandedTextBox(bbox, template, 0.035, 10),
            "600 42px GroundliftCondensed, Arial Narrow, Arial, sans-serif",
            "center",
            template,
            "time_text",
        );
    }

    function drawTitleSubtitleStack(ctx, bbox, title, subtitle, options = {}) {
        if (!bbox) return;
        const ratio = options.titleRatio || 0.7;
        const gap = options.gap || 8;
        const titleBox = { x: bbox.x, y: bbox.y, width: bbox.width, height: Math.max(1, bbox.height * ratio - gap / 2) };
        const subtitleBox = { x: bbox.x, y: bbox.y + bbox.height * ratio + gap / 2, width: bbox.width, height: Math.max(1, bbox.height * (1 - ratio) - gap / 2) };
        drawFitText(ctx, title || "", titleBox, "900 72px GroundliftBold, Arial Black, Arial, sans-serif", "left", {
            allowWrap: true,
            maxLines: preferredTitleLineCount(title, titleBox),
            valign: "top",
            lineHeight: 1.0,
            maxSize: 72,
        });
        drawFitText(ctx, subtitle || "", subtitleBox, "500 34px GroundliftRegular, Arial, sans-serif", "left", {
            allowWrap: true,
            maxLines: preferredSubtitleLineCount(subtitle, subtitleBox),
            valign: "bottom",
            lineHeight: 1.08,
            maxSize: 34,
        });
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
        const image = await loadImageCached(src);
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
        const targetBox = resolveExternalLogoTargetBox(template, box);
        if (!targetBox || !state.externalLogoBase64) return;
        const logoImage = await loadImageCached(dataUrlFromBase64(
            state.externalLogoBase64,
            extensionMime(state.externalLogoFilename, "image/png")
        ));
        if (!logoImage) return;
        drawLayerPreserveAspect(ctx, logoImage, { x: 0, y: 0, width: logoImage.width, height: logoImage.height }, applyBoxVariant(targetBox, variant.externalLogo));
    }

    function drawDateTitle(ctx, bbox, regions = [], preparedLayout = null, template = null, dividerVariant = null) {
        if (!bbox) return;
        const title = state.fields.event_title || "";
        const date = state.fields.date_text || "";
        const layout = preparedLayout || resolveDateTitleLayout(bbox, regions);
        const dateStyle = getTextStyle(template?.key, "date_text");
        const titleStyle = getTextStyle(template?.key, "event_title");
        if (layout) {
            if (layout.divider) drawDivider(ctx, applyDividerVariant(layout.divider, dividerVariant));
            if (layout.left) {
                const font = overrideFont(`900 ${layout.dateFontSize || 64}px GroundliftBold, Arial Black, Arial, sans-serif`, dateStyle);
                const target = applyTextBoxStyle(layout.left, dateStyle);
                drawFitText(ctx, [date], target, font, textAlign(dateStyle, "right"), {
                    allowWrap: false,
                    valign: "top",
                    lineHeight: 1.0,
                    maxSize: maxFontSize(layout.dateFontSize || 64, dateStyle),
                });
            }
            if (layout.right) {
                const target = applyTextBoxStyle(layout.right, titleStyle);
                const font = overrideFont(`900 ${layout.titleFontSize || 64}px GroundliftBold, Arial Black, Arial, sans-serif`, titleStyle);
                drawFitText(ctx, title, target, font, textAlign(titleStyle, "left"), {
                    allowWrap: true,
                    maxLines: preferredTitleLineCount(title, target),
                    valign: "top",
                    lineHeight: 1.0,
                    maxSize: maxFontSize(layout.titleFontSize || 64, titleStyle),
                });
            }
            return;
        }
        drawSplit(ctx, bbox, [date], [title], { leftRatio: 0.42, boldRight: true }, template, dividerVariant);
    }

    function drawTimeSubtitle(ctx, bbox, regions = [], dateTitleLayout = null, template = null) {
        if (!bbox) return;
        const subtitle = state.fields.event_subtitle || "";
        const lines = String(subtitle).split(/\n+/).filter(Boolean);
        const layout = resolveTimeSubtitleLayout(bbox, regions, dateTitleLayout);
        const timeStyle = getTextStyle(template?.key, "time_text");
        const categoryStyle = getTextStyle(template?.key, "event_type_text");
        const subtitleStyle = getTextStyle(template?.key, "event_subtitle");
        if (layout) {
            const timeFontSize = layout.timeFontSize || 46;
            const categoryFontSize = layout.categoryFontSize || timeFontSize;
            const subtitleFontSize = layout.subtitleFontSize || 46;
            if (layout.leftTop) {
                drawFitText(ctx, [state.fields.time_text], applyTextBoxStyle(layout.leftTop, timeStyle), overrideFont(`900 ${timeFontSize}px GroundliftBold, Arial Black, Arial, sans-serif`, timeStyle), textAlign(timeStyle, "right"), {
                    allowWrap: false,
                    valign: "middle",
                    lineHeight: 1.0,
                    maxSize: maxFontSize(timeFontSize, timeStyle),
                });
            }
            if (layout.leftBottom) {
                drawFitText(ctx, [state.fields.event_type_text], applyTextBoxStyle(layout.leftBottom, categoryStyle), overrideFont(`900 ${categoryFontSize}px GroundliftBold, Arial Black, Arial, sans-serif`, categoryStyle), textAlign(categoryStyle, "right"), {
                    allowWrap: false,
                    valign: "middle",
                    lineHeight: 1.0,
                    maxSize: maxFontSize(categoryFontSize, categoryStyle),
                });
            }
            if (layout.right) {
                const target = applyTextBoxStyle(layout.right, subtitleStyle);
                const maxLines = Math.max(lines.length || 1, Math.min(preferredSubtitleLineCount(subtitle, target), layout.rowCount || 2));
                drawFitText(ctx, lines.length > 1 ? lines : subtitle, target, overrideFont(`500 ${subtitleFontSize}px GroundliftRegular, Arial, sans-serif`, subtitleStyle), textAlign(subtitleStyle, "left"), {
                    allowWrap: true,
                    maxLines,
                    valign: "middle",
                    lineHeight: layout.subtitleLineHeight || 1.18,
                    maxSize: maxFontSize(subtitleFontSize, subtitleStyle),
                });
            }
            return;
        }
        drawSplit(ctx, bbox, [state.fields.time_text], lines, { leftRatio: 0.38, leftBottom: state.fields.event_type_text, boldRight: false }, template);
    }

    function drawTimeTicketlink(ctx, bbox, regions = [], template = null) {
        if (!bbox) return;
        const lines = String(state.fields.ticket_link_text || "").split(/\n+/).filter(Boolean);
        const style = getTextStyle(template?.key, "ticket_link_text");
        const target = applyTextBoxStyle(regions.length ? insetBox(unionBoxes(regions), 2) : bbox, style);
        const fontSize = estimateFontSizeFromRegions(regions, 30, 1.12);
        drawFitText(ctx, lines, target, overrideFont(`600 ${fontSize}px GroundliftCondensed, Arial Narrow, Arial, sans-serif`, style), textAlign(style, "center"), {
            maxSize: maxFontSize(fontSize, style),
        });
    }

    function drawSplit(ctx, bbox, leftTopLines, rightLines, options = {}, template = null, dividerVariant = null) {
        const leftRatio = options.leftRatio || 0.4;
        const dividerGap = Math.max(18, bbox.width * 0.018);
        const dividerX = bbox.x + bbox.width * leftRatio;
        const leftBox = { x: bbox.x, y: bbox.y, width: Math.max(1, bbox.width * leftRatio - dividerGap), height: bbox.height };
        const rightBox = { x: dividerX + dividerGap, y: bbox.y, width: Math.max(1, bbox.x + bbox.width - dividerX - dividerGap), height: bbox.height };
        drawDivider(ctx, applyDividerVariant({ x: dividerX - 2, y: bbox.y + 4, width: 4, height: Math.max(1, bbox.height - 8) }, dividerVariant));
        const leftStyle = getTextStyle(template?.key, options.leftBottom ? "time_text" : "date_text");
        const rightStyle = getTextStyle(template?.key, options.boldRight === false ? "event_subtitle" : "event_title");
        drawFitText(ctx, leftTopLines, applyTextBoxStyle({ ...leftBox, height: options.leftBottom ? leftBox.height * 0.68 : leftBox.height }, leftStyle), overrideFont("900 64px GroundliftBold, Arial Black, Arial, sans-serif", leftStyle), textAlign(leftStyle, "center"));
        if (options.leftBottom) {
            const categoryStyle = getTextStyle(template?.key, "event_type_text");
            drawFitText(ctx, [options.leftBottom], applyTextBoxStyle({ x: leftBox.x, y: leftBox.y + leftBox.height * 0.66, width: leftBox.width, height: leftBox.height * 0.34 }, categoryStyle), overrideFont("900 46px GroundliftBold, Arial Black, Arial, sans-serif", categoryStyle), textAlign(categoryStyle, "center"));
        }
        drawFitText(ctx, rightLines, applyTextBoxStyle(rightBox, rightStyle), overrideFont(`${options.boldRight === false ? 500 : 900} 52px GroundliftBold, Arial Black, Arial, sans-serif`, rightStyle), textAlign(rightStyle, "left"));
    }

    function drawTitleOnly(ctx, bbox, regions = [], template = null, dividerVariant = null) {
        if (!bbox) return;
        const style = getTextStyle(template?.key, "event_title");
        if (regions.length && state.fields.event_title) {
            const layout = resolveDateTitleLayout(bbox, regions);
            if (layout?.divider) drawDivider(ctx, applyDividerVariant(layout.divider, dividerVariant));
            const target = applyTextBoxStyle(layout?.right || unionBoxes(regions) || bbox, style);
            const fontSize = layout?.titleFontSize || estimateFontSizeFromRegions(regions, 64, 1.14);
            drawFitText(ctx, state.fields.event_title, target, overrideFont(`900 ${fontSize}px GroundliftBold, Arial Black, Arial, sans-serif`, style), textAlign(style, layout?.right ? "left" : "center"), {
                allowWrap: true,
                maxLines: preferredTitleLineCount(state.fields.event_title, target),
                valign: layout?.right ? "top" : "middle",
                lineHeight: 1.0,
                maxSize: maxFontSize(fontSize, style),
            });
            return;
        }
        drawFitText(ctx, state.fields.event_title, applyTextBoxStyle(bbox, style), overrideFont("900 64px GroundliftBold, Arial Black, Arial, sans-serif", style), textAlign(style, "center"), {
            allowWrap: true,
            maxLines: preferredTitleLineCount(state.fields.event_title, bbox),
            valign: "middle",
            lineHeight: 1.0,
            maxSize: maxFontSize(64, style),
        });
    }

    function drawSubtitleOnly(ctx, bbox, regions = [], template = null) {
        if (!bbox) return;
        const subtitle = state.fields.event_subtitle || "";
        const lines = String(subtitle).split(/\n+/).filter(Boolean);
        const style = getTextStyle(template?.key, "event_subtitle");
        const target = applyTextBoxStyle(regions.length ? (unionBoxes(regions) || bbox) : bbox, style);
        const fontSize = estimateFontSizeFromRegions(regions, 46, 1.12);
        drawFitText(ctx, lines.length > 1 ? lines : subtitle, target, overrideFont(`500 ${fontSize}px GroundliftRegular, Arial, sans-serif`, style), textAlign(style, "left"), {
            allowWrap: true,
            maxLines: preferredSubtitleLineCount(subtitle, target),
            valign: "bottom",
            lineHeight: 1.12,
            maxSize: maxFontSize(fontSize, style),
        });
    }


    function boxRight(box) {
        return box ? box.x + box.width : 0;
    }

    function boxBottom(box) {
        return box ? box.y + box.height : 0;
    }

    function usefulTextRegions(regions = []) {
        return (regions || []).filter((r) => r && r.width > 3 && r.height > 3);
    }

    function maxRegionHeight(regions = [], fallback = 40) {
        const useful = usefulTextRegions(regions);
        if (!useful.length) return fallback;
        return Math.max(...useful.map((r) => r.height));
    }

    function estimateFontSizeFromRegions(regions = [], fallback = 40, factor = 1.14) {
        const height = maxRegionHeight(regions, fallback / factor);
        return Math.max(10, Math.round(height * factor));
    }

    function splitRegionsByLargestHorizontalGap(regions = []) {
        const useful = usefulTextRegions(regions).sort((a, b) => a.x - b.x);
        if (useful.length < 2) return null;
        let best = null;
        for (let i = 0; i < useful.length - 1; i++) {
            const left = useful[i];
            const right = useful[i + 1];
            const gap = right.x - boxRight(left);
            if (!best || gap > best.gap) {
                best = { gap, leftEnd: boxRight(left), rightStart: right.x };
            }
        }
        if (!best || best.gap <= 0) return null;
        return {
            splitX: (best.leftEnd + best.rightStart) / 2,
            leftEnd: best.leftEnd,
            rightStart: best.rightStart,
            gap: best.gap,
        };
    }

    function splitRegionsByRows(regions = []) {
        const useful = usefulTextRegions(regions).sort((a, b) => boxCenter(a).y - boxCenter(b).y || a.x - b.x);
        if (!useful.length) return [];
        if (useful.length === 1) return [useful];
        let best = null;
        for (let i = 0; i < useful.length - 1; i++) {
            const a = useful[i];
            const b = useful[i + 1];
            const gap = boxCenter(b).y - boxCenter(a).y;
            if (!best || gap > best.gap) best = { gap, index: i };
        }
        const threshold = Math.max(8, maxRegionHeight(useful, 30) * 0.40);
        if (!best || best.gap < threshold) return [useful];
        return [useful.slice(0, best.index + 1), useful.slice(best.index + 1)];
    }

    function findDividerBox(bbox, regions = [], fallbackRatio = 0.42) {
        const useful = usefulTextRegions(regions);
        const divider = useful
            .filter((r) => r.width < bbox.width * 0.10 && r.height > bbox.height * 0.35)
            .sort((a, b) => b.height - a.height || a.x - b.x)[0];
        if (divider) return divider;
        const centerX = bbox.x + bbox.width * fallbackRatio;
        return { x: centerX - 2, y: bbox.y + 4, width: 4, height: Math.max(1, bbox.height - 8) };
    }

    function resolveDateTitleLayout(bbox, regions) {
        const useful = usefulTextRegions(regions);
        if (!useful.length) return null;
        const divider = findDividerBox(bbox, useful, 0.42);
        const dividerCenter = divider.x + divider.width / 2;
        const leftRegions = useful.filter((r) => boxCenter(r).x < dividerCenter && r !== divider);
        const rightRegions = useful.filter((r) => boxCenter(r).x > dividerCenter && r !== divider);
        const leftUnion = unionBoxes(leftRegions);
        const rightUnion = unionBoxes(rightRegions);
        const fallbackGap = Math.max(16, bbox.width * 0.02);
        const hasLeftText = Boolean(leftUnion && boxRight(leftUnion) <= divider.x + divider.width * 0.25);
        const leftX = hasLeftText ? leftUnion.x : bbox.x;
        const leftRight = hasLeftText ? boxRight(leftUnion) : (divider.x - fallbackGap);
        const rightX = rightUnion ? rightUnion.x : (divider.x + divider.width + fallbackGap);
        const rightRight = Math.max(bbox.x + bbox.width, rightUnion ? boxRight(rightUnion) : bbox.x + bbox.width);
        const top = divider.y;
        const height = divider.height;
        return {
            divider,
            hasLeftText,
            left: hasLeftText ? { x: leftX, y: top, width: Math.max(1, leftRight - leftX), height } : null,
            right: { x: rightX, y: top, width: Math.max(1, rightRight - rightX), height },
            dateFontSize: estimateFontSizeFromRegions(leftRegions, 64, 1.14),
            titleFontSize: estimateFontSizeFromRegions(rightRegions, 64, 1.14),
            leftEnd: leftRight,
            rightStart: rightX,
        };
    }

    function resolveTimeSubtitleLayout(bbox, regions, dateTitleLayout = null) {
        const useful = usefulTextRegions(regions);
        if (!useful.length) return null;

        const inferredColumns = splitRegionsByLargestHorizontalGap(useful);
        const hasLeftGuide = Boolean(dateTitleLayout?.hasLeftText || !dateTitleLayout);
        const leftEnd = dateTitleLayout?.left ? boxRight(dateTitleLayout.left) : (inferredColumns?.leftEnd || bbox.x + bbox.width * 0.38);
        const rightStart = dateTitleLayout?.right ? dateTitleLayout.right.x : (inferredColumns?.rightStart || bbox.x + bbox.width * 0.45);
        const splitX = dateTitleLayout
            ? (dateTitleLayout.hasLeftText ? ((leftEnd + rightStart) / 2) : (dateTitleLayout.divider.x + dateTitleLayout.divider.width / 2))
            : (inferredColumns?.splitX || ((leftEnd + rightStart) / 2));

        const leftRegions = hasLeftGuide ? useful.filter((r) => boxCenter(r).x < splitX) : [];
        const rightRegions = hasLeftGuide ? useful.filter((r) => boxCenter(r).x >= splitX) : useful;
        const leftStart = Math.min(
            ...(leftRegions.length ? leftRegions.map((r) => r.x) : [bbox.x]),
            dateTitleLayout?.left?.x ?? bbox.x
        );
        const rightEnd = Math.max(bbox.x + bbox.width, ...(rightRegions.length ? rightRegions.map((r) => boxRight(r)) : [bbox.x + bbox.width]));

        const rows = splitRegionsByRows(useful);
        const topRow = unionBoxes(rows[0] || useful) || bbox;
        const bottomRow = unionBoxes(rows[1] || rows[0] || useful) || topRow;
        const rowHeight = Math.max(topRow.height, bottomRow.height, maxRegionHeight(useful, 40));
        const padY = Math.max(2, rowHeight * 0.15);
        const topBox = {
            y: Math.max(bbox.y, topRow.y - padY),
            height: topRow.height + padY * 2,
        };
        const bottomBox = {
            y: Math.max(bbox.y, bottomRow.y - padY),
            height: bottomRow.height + padY * 2,
        };
        const totalTop = Math.min(topBox.y, bottomBox.y);
        const totalBottom = Math.max(boxBottom({ x: 0, y: topBox.y, width: 1, height: topBox.height }), boxBottom({ x: 0, y: bottomBox.y, width: 1, height: bottomBox.height }));
        const rowCenterGap = Math.max(1, Math.abs(boxCenter(bottomRow).y - boxCenter(topRow).y));

        const topLeftRegions = leftRegions.filter((r) => boxCenter(r).y <= boxCenter(topRow).y + topRow.height / 2);
        const bottomLeftRegions = leftRegions.filter((r) => boxCenter(r).y > boxCenter(topRow).y + topRow.height / 2);
        const topRightRegions = rightRegions.filter((r) => boxCenter(r).y <= boxCenter(topRow).y + topRow.height / 2);
        const bottomRightRegions = rightRegions.filter((r) => boxCenter(r).y > boxCenter(topRow).y + topRow.height / 2);
        const subtitleFontSize = estimateFontSizeFromRegions(topRightRegions.concat(bottomRightRegions), 46, 1.12);

        return {
            leftTop: leftRegions.length ? { x: leftStart, y: topBox.y, width: Math.max(1, leftEnd - leftStart), height: topBox.height } : null,
            leftBottom: leftRegions.length ? { x: leftStart, y: bottomBox.y, width: Math.max(1, leftEnd - leftStart), height: bottomBox.height } : null,
            right: { x: rightStart, y: totalTop, width: Math.max(1, rightEnd - rightStart), height: Math.max(1, totalBottom - totalTop) },
            timeFontSize: estimateFontSizeFromRegions(topLeftRegions, 46, 1.12),
            categoryFontSize: estimateFontSizeFromRegions(bottomLeftRegions.length ? bottomLeftRegions : topLeftRegions, 46, 1.12),
            subtitleFontSize,
            subtitleLineHeight: clamp(rowCenterGap / Math.max(1, subtitleFontSize), 1.0, 1.35),
            rowCount: rows.length || 1,
            leftEnd,
            rightStart,
        };
    }

    function drawDivider(ctx, bbox) {
        if (!bbox) return;
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(bbox.x, bbox.y, Math.max(2, bbox.width), bbox.height);
        ctx.restore();
    }

    function drawStandaloneDividerLeftOfBox(ctx, bbox, template, dividerVariant = null) {
        if (!bbox) return;
        const width = Math.max(12, Math.round((template?.canvas_width || 1920) * 0.0066));
        const gap = Math.max(24, Math.round(bbox.width * 0.065));
        drawDivider(ctx, applyDividerVariant({
            x: bbox.x - gap,
            y: bbox.y + Math.max(4, Math.round(bbox.height * 0.02)),
            width,
            height: Math.max(1, bbox.height - Math.max(8, Math.round(bbox.height * 0.04))),
        }, dividerVariant));
    }

    function drawParagraphBox(ctx, text, bbox, template = null) {
        if (!bbox || !text) return;
        const style = getTextStyle(template?.key, "summary_text");
        drawParagraph(ctx, String(text), applyTextBoxStyle(bbox, style), overrideFont("400 34px GroundliftRegular, Arial, sans-serif", style));
    }

    function drawSingleLine(ctx, text, bbox, font, align = "left", template = null, field = null) {
        if (!bbox || !text) return;
        const style = field ? getTextStyle(template?.key, field) : defaultTextStyle();
        drawFitText(ctx, [String(text).toUpperCase()], applyTextBoxStyle(bbox, style), overrideFont(font, style), textAlign(style, align), {
            allowWrap: false,
            valign: "middle",
            lineHeight: 1.0,
            maxSize: maxFontSize(parseInt((String(font).match(/(\d+)px/) || ["", "28"])[1], 10), style),
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
        const contentShift = resolveTemplateContentShift(template, info?.bboxes || {});
        const geometry = shiftGeometry(info?.geometries?.image_mask || { bbox: info?.bboxes?.image_mask }, contentShift.dx, contentShift.dy);
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
                admission_time_text: p.admission_time_text || admissionTimeFromBeginText(p.time_text || ""),
                ticket_price_text: p.ticket_price_text || "",
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
            await prefillVariantsFromOdooDefaults();
            await applyPaletteFromSourceImage();
            buildApp();
            await renderCanvas();
        } catch (error) {
            console.error(error);
            root.innerHTML = `<div class="gl-error">Der isolierte Grafikeditor konnte nicht geladen werden:\n${escapeHtml(error.message)}</div>`;
        }
    }

    init();
})();
