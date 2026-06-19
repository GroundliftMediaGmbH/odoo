/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function hexToRgb(hex) {
    const value = (hex || "").replace("#", "").trim();
    if (!/^[0-9a-fA-F]{6}$/.test(value)) return { r: 0, g: 0, b: 0 };
    return {
        r: parseInt(value.slice(0, 2), 16),
        g: parseInt(value.slice(2, 4), 16),
        b: parseInt(value.slice(4, 6), 16),
    };
}

function rgbToHex({ r, g, b }) {
    return `#${[r, g, b]
        .map((value) => clamp(Math.round(value), 0, 255).toString(16).padStart(2, "0"))
        .join("")}`.toUpperCase();
}

function rgbToHsl({ r, g, b }) {
    r /= 255;
    g /= 255;
    b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h = 0;
    let s = 0;
    const l = (max + min) / 2;
    const d = max - min;
    if (d !== 0) {
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        if (max === g) h = ((b - r) / d + 2) / 6;
        if (max === b) h = ((r - g) / d + 4) / 6;
    }
    return { h, s, l };
}

function hslToRgb({ h, s, l }) {
    if (s === 0) {
        const gray = Math.round(l * 255);
        return { r: gray, g: gray, b: gray };
    }
    const hue2rgb = (p, q, t) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1 / 6) return p + (q - p) * 6 * t;
        if (t < 1 / 2) return q;
        if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
        return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    return {
        r: Math.round(hue2rgb(p, q, h + 1 / 3) * 255),
        g: Math.round(hue2rgb(p, q, h) * 255),
        b: Math.round(hue2rgb(p, q, h - 1 / 3) * 255),
    };
}

function contrastingColor(hex) {
    const hsl = rgbToHsl(hexToRgb(hex));
    hsl.h = (hsl.h + 0.5) % 1;
    hsl.s = clamp(Math.max(hsl.s, 0.68), 0, 1);
    hsl.l = hsl.l > 0.48 ? 0.13 : 0.86;
    return rgbToHex(hslToRgb(hsl));
}

function dataUrlFromBase64(base64, mime = "image/png") {
    return base64 ? `data:${mime};base64,${base64}` : "";
}

function extensionMime(filename, fallback = "image/png") {
    const extension = (filename || "").split(".").pop().toLowerCase();
    const mapping = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };
    return mapping[extension] || fallback;
}

function defaultDrinkCard() {
    return {
        profileName: "",
        sections: [
            { title: "Biere", product_ids: [] },
            { title: "Weine", product_ids: [] },
            { title: "Longdrinks", product_ids: [] },
            { title: "Alkoholfrei", product_ids: [] },
        ],
        footer: "",
    };
}

async function loadImage(src) {
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

function alphaBBox(image) {
    if (!image) return null;
    const geometry = alphaGeometry(image);
    return geometry ? geometry.bbox : null;
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
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
            const sum = x + y;
            const diff = x - y;
            if (sum < tlScore) {
                tlScore = sum;
                tl = { x, y };
            }
            if (diff > trScore) {
                trScore = diff;
                tr = { x, y };
            }
            if (sum > brScore) {
                brScore = sum;
                br = { x, y };
            }
            if (diff < blScore) {
                blScore = diff;
                bl = { x, y };
            }
        }
    }
    if (maxX < minX || maxY < minY) return null;
    const bbox = { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
    const corners = tl && tr && br && bl ? [tl, tr, br, bl] : null;
    return { bbox, corners };
}

function drawPolygonPath(ctx, points) {
    if (!ctx || !points || !points.length) return;
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y);
    }
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

class GraphicsEditor extends Component {
    static template = "groundlift_graphics.GraphicsEditor";
    static props = ["action"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.canvasRef = useRef("posterCanvas");
        this.sourceFileRef = useRef("sourceFile");
        this.externalLogoFileRef = useRef("externalLogoFile");

        this.posterId = this.props.action.params.poster_id;
        this.state = useState({
            loading: true,
            saving: false,
            eventName: "",
            sidebarTab: "overview",
            selectedTemplateKey: "",
            templates: [],
            products: [],
            drinkProfiles: [],
            outputs: {},
            sourceImageBase64: "",
            sourceImageFilename: "",
            externalLogoBase64: "",
            externalLogoFilename: "",
            claim: "",
            event_title: "",
            event_subtitle: "",
            date_text: "",
            time_text: "",
            event_type_text: "",
            summary_text: "",
            photo_credit: "",
            ticket_url: "",
            ticket_link_text: "",
            qr_url: "",
            color_contrast: false,
            color_1: "#000033",
            color_2: "#002E59",
            sticker_mode: "original",
            sticker_text: "LIVE\nON\nSTAGE",
            sticker_color: "#D6331F",
            output_filename: "",
            drink_card_profile_id: false,
            qrImageBase64: "",
            editor_state: {},
        });

        this.templateCache = new Map();
        this.fontFaces = [];
        this.pointerDrag = null;
        onMounted(async () => {
            try {
                await this.loadData();
            } catch (error) {
                console.error("Groundlift graphics editor could not be loaded", error);
                this.state.loading = false;
                this.notification.add("Der Grafikeditor konnte nicht geladen werden. Bitte Seite neu laden oder das letzte Update prüfen.", { type: "danger" });
            }
        });
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call("gl.graphics.poster", "get_editor_data", [[this.posterId]]);
        const poster = data.poster;
        this.state.eventName = poster.event_name;
        this.state.sourceImageBase64 = poster.source_image;
        this.state.sourceImageFilename = poster.source_image_filename;
        this.state.externalLogoBase64 = poster.external_logo_image;
        this.state.externalLogoFilename = poster.external_logo_filename;
        this.state.claim = poster.claim;
        this.state.event_title = poster.event_title;
        this.state.event_subtitle = poster.event_subtitle;
        this.state.date_text = poster.date_text;
        this.state.time_text = poster.time_text;
        this.state.event_type_text = poster.event_type_text;
        this.state.summary_text = poster.summary_text;
        this.state.photo_credit = poster.photo_credit;
        this.state.ticket_url = poster.ticket_url;
        this.state.ticket_link_text = poster.ticket_link_text;
        this.state.qr_url = poster.qr_url;
        this.state.color_contrast = poster.color_contrast;
        this.state.color_1 = poster.color_1;
        this.state.color_2 = poster.color_2;
        this.state.sticker_mode = poster.sticker_mode;
        this.state.sticker_text = poster.sticker_text;
        this.state.sticker_color = poster.sticker_color;
        this.state.output_filename = poster.output_filename;
        this.state.drink_card_profile_id = poster.drink_card_profile_id;
        this.state.editor_state = poster.editor_state || {};
        this.state.qrImageBase64 = data.qr_image || "";
        this.state.templates = data.templates || [];
        this.state.products = data.products || [];
        this.state.drinkProfiles = data.drink_profiles || [];
        this.state.outputs = data.outputs || {};
        this.state.selectedTemplateKey = this.state.editor_state.selectedTemplateKey || (this.state.templates[0] && this.state.templates[0].key) || "";

        if (!this.state.editor_state.variants) this.state.editor_state.variants = {};
        if (!this.state.editor_state.drink_card) {
            const activeProfile = this.state.drinkProfiles.find((p) => p.id === this.state.drink_card_profile_id);
            this.state.editor_state.drink_card = activeProfile ? JSON.parse(JSON.stringify(activeProfile.config || defaultDrinkCard())) : defaultDrinkCard();
        }

        await this.registerFonts(data.template || {});
        await this.ensureAllTemplateAssets();
        this.state.loading = false;
        this.renderCanvas();
    }

    async registerFonts(templateInfo) {
        const fonts = [
            [templateInfo.font_regular_file, templateInfo.font_regular_filename, "GroundliftRegular"],
            [templateInfo.font_bold_file, templateInfo.font_bold_filename, "GroundliftBold"],
            [templateInfo.font_condensed_file, templateInfo.font_condensed_filename, "GroundliftCondensed"],
        ];
        for (const [base64, filename, family] of fonts) {
            if (!base64) continue;
            const mime = extensionMime(filename, "font/ttf");
            try {
                const face = new FontFace(family, `url(${dataUrlFromBase64(base64, mime)})`);
                await face.load();
                document.fonts.add(face);
                this.fontFaces.push(face);
            } catch {
                // ignore font load failures
            }
        }
    }

    get currentTemplate() {
        return this.state.templates.find((t) => t.key === this.state.selectedTemplateKey) || this.state.templates[0];
    }

    get currentVariant() {
        return this.ensureVariant(this.state.selectedTemplateKey);
    }

    ensureVariant(templateKey) {
        if (!this.state.editor_state.variants) this.state.editor_state.variants = {};
        if (!this.state.editor_state.variants[templateKey]) {
            this.state.editor_state.variants[templateKey] = {
                image: { offsetX: 0, offsetY: 0, scale: 1, rotation: 0 },
                qr: { dx: 0, dy: 0, scale: 1 },
                externalLogo: { dx: 0, dy: 0, scale: 1 },
                sticker: { dx: 0, dy: 0, scale: 1 },
            };
        }
        return this.state.editor_state.variants[templateKey];
    }

    async ensureAllTemplateAssets() {
        for (const template of this.state.templates) {
            await this.ensureTemplateAssets(template);
        }
    }

    async ensureTemplateAssets(template) {
        if (!template || this.templateCache.has(template.key)) return this.templateCache.get(template.key);
        const imagesByRole = {};
        const bboxes = {};
        const geometries = {};
        const staticOverlays = [];
        for (const asset of template.assets) {
            try {
                const image = await loadImage(asset.url);
                if (!image) continue;
                if (!imagesByRole[asset.role]) imagesByRole[asset.role] = image;
                if (asset.role.startsWith("static_")) staticOverlays.push({ role: asset.role, image });
                const geometry = alphaGeometry(image);
                geometries[asset.role] = geometry;
                bboxes[asset.role] = geometry ? geometry.bbox : null;
            } catch {
                // ignore missing asset
            }
        }
        const info = { template, imagesByRole, bboxes, geometries, staticOverlays };
        this.templateCache.set(template.key, info);
        return info;
    }

    openFilePicker() {
        this.sourceFileRef.el.click();
    }

    openExternalLogoPicker() {
        this.externalLogoFileRef.el.click();
    }

    async onSourceFile(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        this.state.sourceImageBase64 = await this.fileToBase64(file);
        this.state.sourceImageFilename = file.name;
        this.extractPalette();
        this.renderCanvas();
    }

    async onExternalLogoFile(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        this.state.externalLogoBase64 = await this.fileToBase64(file);
        this.state.externalLogoFilename = file.name;
        this.renderCanvas();
    }

    async fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const value = reader.result.split(",", 2)[1];
                resolve(value);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    backToRecord() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "gl.graphics.poster",
            res_id: this.posterId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onFieldInput(ev) {
        const field = ev.target.dataset.field;
        if (!field) return;
        this.state[field] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
        if (field === "ticket_url" && !this.state.qr_url) {
            this.state.qr_url = this.state.ticket_url;
            this.refreshQrCode();
        }
        this.renderCanvas();
    }

    onContrastChange(ev) {
        this.state.color_contrast = ev.target.checked;
        if (this.state.color_contrast) {
            this.state.color_1 = contrastingColor(this.state.color_1 || "#000033");
            this.state.color_2 = contrastingColor(this.state.color_2 || "#002E59");
        }
        this.renderCanvas();
    }

    onTemplateChange(ev) {
        this.state.selectedTemplateKey = ev.target.value;
        this.state.editor_state.selectedTemplateKey = this.state.selectedTemplateKey;
        const template = this.currentTemplate;
        if (template) {
            this.state.output_filename = this.buildOutputFilename(template.output_suffix);
        }
        this.renderCanvas();
    }

    buildOutputFilename(suffix) {
        const original = this.state.output_filename || "";
        if (!original.includes("_")) return original;
        return original.replace(/_[^_]+\.jpg$/i, `_${suffix}.jpg`);
    }

    onVariantNumberInput(ev) {
        const variant = this.currentVariant;
        const [group, field] = ev.target.dataset.path.split(".");
        variant[group][field] = parseFloat(ev.target.value || 0);
        this.renderCanvas();
    }

    onQrUrlChange(ev) {
        this.state.qr_url = ev.target.value;
        this.refreshQrCode();
    }

    async refreshQrCode() {
        this.state.qrImageBase64 = await this.orm.call("gl.graphics.poster", "generate_qr_base64", [this.state.qr_url || this.state.ticket_url || ""]);
        this.renderCanvas();
    }

    applyDrinkProfile(ev) {
        const profileId = parseInt(ev.target.value || "0", 10) || false;
        this.state.drink_card_profile_id = profileId;
        const profile = this.state.drinkProfiles.find((p) => p.id === profileId);
        this.state.editor_state.drink_card = profile ? JSON.parse(JSON.stringify(profile.config || defaultDrinkCard())) : defaultDrinkCard();
        this.renderCanvas();
    }

    onDrinkFieldInput(ev, sectionIndex = null) {
        const cfg = this.state.editor_state.drink_card;
        if (!cfg) return;
        if (sectionIndex === null) {
            cfg[ev.target.dataset.field] = ev.target.value;
        } else {
            cfg.sections[sectionIndex][ev.target.dataset.field] = ev.target.value;
        }
        this.renderCanvas();
    }

    onDrinkProductSelect(ev, sectionIndex) {
        const values = Array.from(ev.target.selectedOptions).map((o) => parseInt(o.value, 10));
        this.state.editor_state.drink_card.sections[sectionIndex].product_ids = values;
        this.renderCanvas();
    }

    async saveDrinkProfile() {
        const name = prompt("Name des Getränkekarten-Setups:", this.state.editor_state.drink_card.profileName || "Getränkekarte");
        if (!name) return;
        const profile = await this.orm.call("gl.graphics.poster", "save_drink_profile", [[this.posterId], name, this.state.editor_state.drink_card]);
        this.state.drinkProfiles.push(profile);
        this.state.drink_card_profile_id = profile.id;
        this.notification.add("Getränkekarten-Profil gespeichert.", { type: "success" });
    }

    async save() {
        await this.saveAll(false);
    }

    async saveAndDownload() {
        await this.saveAll("current");
    }

    async saveAndDownloadZip() {
        await this.saveAll("zip");
    }

    async saveAll(downloadMode = false) {
        this.state.saving = true;
        try {
            const renderedOutputs = await this.renderAllOutputs();
            const current = renderedOutputs[this.state.selectedTemplateKey];
            const values = {
                source_image: this.state.sourceImageBase64,
                source_image_filename: this.state.sourceImageFilename,
                external_logo_image: this.state.externalLogoBase64,
                external_logo_filename: this.state.externalLogoFilename,
                claim: this.state.claim,
                event_title: this.state.event_title,
                event_subtitle: this.state.event_subtitle,
                date_text: this.state.date_text,
                time_text: this.state.time_text,
                event_type_text: this.state.event_type_text,
                summary_text: this.state.summary_text,
                photo_credit: this.state.photo_credit,
                ticket_url: this.state.ticket_url,
                ticket_link_text: this.state.ticket_link_text,
                qr_url: this.state.qr_url,
                color_contrast: this.state.color_contrast,
                color_1: this.state.color_1,
                color_2: this.state.color_2,
                sticker_mode: this.state.sticker_mode,
                sticker_text: this.state.sticker_text,
                sticker_color: this.state.sticker_color,
                drink_card_profile_id: this.state.drink_card_profile_id,
                editor_state: this.state.editor_state,
                output_filename: current ? current.filename : this.state.output_filename,
            };
            await this.orm.call("gl.graphics.poster", "save_editor_data", [[this.posterId], values, current ? current.data : false, renderedOutputs]);
            if (downloadMode === "current") {
                const action = await this.orm.call("gl.graphics.poster", "action_download_specific_output", [[this.posterId], this.state.selectedTemplateKey]);
                this.actionService.doAction(action);
            } else if (downloadMode === "zip") {
                const action = await this.orm.call("gl.graphics.poster", "action_download_outputs_zip", [[this.posterId]]);
                this.actionService.doAction(action);
            } else {
                this.notification.add("Grafiken gespeichert.", { type: "success" });
            }
        } finally {
            this.state.saving = false;
        }
    }

    async renderAllOutputs() {
        const result = {};
        for (const template of this.state.templates) {
            const data = await this.renderTemplateToDataUrl(template.key);
            result[template.key] = {
                data,
                filename: this.buildOutputFilename(template.output_suffix),
                template_name: template.name,
            };
        }
        return result;
    }

    async renderTemplateToDataUrl(templateKey) {
        const template = this.state.templates.find((t) => t.key === templateKey);
        const info = await this.ensureTemplateAssets(template);
        const offscreen = document.createElement("canvas");
        offscreen.width = template.canvas_width;
        offscreen.height = template.canvas_height;
        const ctx = offscreen.getContext("2d");
        await this.paintTemplate(ctx, info, this.ensureVariant(templateKey));
        return offscreen.toDataURL("image/jpeg", 0.96);
    }

    async renderCanvas() {
        if (this.state.loading || !this.canvasRef.el || !this.currentTemplate) return;
        try {
            const info = await this.ensureTemplateAssets(this.currentTemplate);
            const canvas = this.canvasRef.el;
            canvas.width = this.currentTemplate.canvas_width;
            canvas.height = this.currentTemplate.canvas_height;
            await this.paintTemplate(canvas.getContext("2d"), info, this.currentVariant, true);
        } catch (error) {
            console.error("Groundlift graphics preview render failed", error);
        }
    }

    async paintTemplate(ctx, info, variant, showGuides = false) {
        const template = info.template;
        ctx.clearRect(0, 0, template.canvas_width, template.canvas_height);
        this.drawGradient(ctx, template);
        await this.drawSourceImage(ctx, info, variant);
        const dynamicImages = {
            qr: this.state.qrImageBase64 ? await loadImage(dataUrlFromBase64(this.state.qrImageBase64, "image/png")) : null,
            external: this.state.externalLogoBase64 ? await loadImage(dataUrlFromBase64(this.state.externalLogoBase64, extensionMime(this.state.externalLogoFilename, "image/png"))) : info.imagesByRole.external_logo,
        };
        for (const overlay of info.staticOverlays) {
            ctx.drawImage(overlay.image, 0, 0, template.canvas_width, template.canvas_height);
        }
        this.drawMainLayers(ctx, info, variant, dynamicImages);
        if (showGuides) this.drawMaskOutline(ctx, info.bboxes.image_mask, info.geometries?.image_mask);
    }

    drawGradient(ctx, template) {
        const gradient = ctx.createLinearGradient(0, 0, template.canvas_width, template.canvas_height);
        gradient.addColorStop(0, this.state.color_1 || "#000033");
        gradient.addColorStop(1, this.state.color_2 || "#002E59");
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, template.canvas_width, template.canvas_height);
    }

    async drawSourceImage(ctx, info, variant) {
        const maskGeometry = info.geometries?.image_mask;
        const box = maskGeometry?.bbox || info.bboxes.image_mask;
        if (!this.state.sourceImageBase64 || !box) return;
        const src = dataUrlFromBase64(this.state.sourceImageBase64, extensionMime(this.state.sourceImageFilename, "image/jpeg"));
        const image = await loadImage(src);
        if (!image) return;
        const tr = variant.image;
        const coverScale = Math.max(box.width / image.width, box.height / image.height);
        const scale = coverScale * (tr.scale || 1);
        const drawW = image.width * scale;
        const drawH = image.height * scale;
        const cx = box.x + box.width / 2 + (tr.offsetX || 0);
        const cy = box.y + box.height / 2 + (tr.offsetY || 0);
        ctx.save();
        ctx.beginPath();
        if (maskGeometry?.corners?.length === 4) drawPolygonPath(ctx, maskGeometry.corners);
        else ctx.rect(box.x, box.y, box.width, box.height);
        ctx.clip();
        ctx.translate(cx, cy);
        ctx.rotate((tr.rotation || 0) * Math.PI / 180);
        ctx.drawImage(image, -drawW / 2, -drawH / 2, drawW, drawH);
        ctx.restore();
    }

    drawMainLayers(ctx, info, variant, dynamicImages = {}) {
        const img = info.imagesByRole;
        const box = info.bboxes;
        if (img.frame) ctx.drawImage(img.frame, 0, 0, info.template.canvas_width, info.template.canvas_height);
        if (this.state.sticker_mode !== "hidden") this.drawSticker(ctx, img.sticker, box.sticker, variant.sticker);
        if (img.logo) ctx.drawImage(img.logo, 0, 0, info.template.canvas_width, info.template.canvas_height);
        this.drawTextByRole(ctx, "claim", box.claim);
        this.drawDateTitle(ctx, box.date_title || box.title);
        this.drawTimeSubtitle(ctx, box.time_subtitle);
        this.drawTimeTicketlink(ctx, box.time_ticketlink);
        this.drawTitleOnly(ctx, box.title);
        this.drawSubtitleOnly(ctx, box.subtitle);
        this.drawSummary(ctx, box.summary);
        this.drawPhotoCredit(ctx, box.photo_credit);
        this.drawTicketLink(ctx, box.ticket_link);
        this.drawQr(ctx, dynamicImages.qr, box.qr, variant.qr);
        this.drawExternalLogo(ctx, dynamicImages.external || img.external_logo, box.external_logo, variant.externalLogo);
        this.drawDrinkCard(ctx, box.drink_card);
    }

    drawSticker(ctx, stickerImage, bbox, variantBox) {
        if (!bbox) return;
        const box = this.applyBoxVariant(bbox, variantBox);
        if (this.state.sticker_mode === "original" && stickerImage) {
            ctx.drawImage(stickerImage, box.x, box.y, box.width, box.height);
            return;
        }
        ctx.save();
        ctx.fillStyle = this.state.sticker_color || "#D6331F";
        const radius = Math.min(box.width, box.height) / 2;
        ctx.beginPath();
        ctx.arc(box.x + box.width / 2, box.y + box.height / 2, radius, 0, Math.PI * 2);
        ctx.fill();
        this.drawFitText(ctx, (this.state.sticker_text || "LIVE\nON\nSTAGE").toUpperCase().split(/\n+/), box, { font: "900 48px GroundliftBold, Arial Black, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.08 });
        ctx.restore();
    }

    drawTextByRole(ctx, role, bbox) {
        if (!bbox) return;
        if (role === "claim") {
            const lines = (this.state.claim || "").split(/\n+/).filter(Boolean).map((l) => l.toUpperCase());
            this.drawFitText(ctx, lines, bbox, { font: "500 54px GroundliftRegular, Arial, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.12 });
        }
    }

    drawDateTitle(ctx, bbox) {
        if (!bbox) return;
        const title = (this.state.event_title || "").toUpperCase();
        const date = (this.state.date_text || "").toUpperCase();
        this.drawSplitInfo(ctx, bbox, [date], [title], { leftRatio: 0.42 });
    }

    drawTimeSubtitle(ctx, bbox) {
        if (!bbox) return;
        const lines = (this.state.event_subtitle || "").split(/\n+/).filter(Boolean).map((l) => l.toUpperCase());
        this.drawSplitInfo(ctx, bbox, [(this.state.time_text || "").toUpperCase()], lines, { leftRatio: 0.38, leftBottom: (this.state.event_type_text || "").toUpperCase() });
    }

    drawTimeTicketlink(ctx, bbox) {
        if (!bbox) return;
        const lines = (this.state.ticket_link_text || "").split(/
+/).filter(Boolean).map((l) => l.toUpperCase());
        this.drawSplitInfo(ctx, bbox, [(this.state.time_text || "").toUpperCase()], lines, { leftRatio: 0.42, leftBottom: (this.state.event_type_text || "").toUpperCase(), compactRight: true });
    }

    drawSplitInfo(ctx, bbox, leftTopLines, rightLines, options = {}) {
        const leftRatio = options.leftRatio || 0.4;
        const dividerGap = Math.max(20, Math.round(bbox.width * 0.018));
        const dividerX = bbox.x + bbox.width * leftRatio;
        const leftBox = { x: bbox.x, y: bbox.y, width: Math.max(0, bbox.width * leftRatio - dividerGap), height: bbox.height };
        const rightBox = { x: dividerX + dividerGap, y: bbox.y, width: Math.max(0, bbox.x + bbox.width - (dividerX + dividerGap)), height: bbox.height };
        const leftTopBox = { ...leftBox, height: leftBox.height * (options.leftBottom ? 0.68 : 1) };
        ctx.save();
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = Math.max(4, Math.round(bbox.height * 0.018));
        ctx.beginPath();
        ctx.moveTo(dividerX, bbox.y + 6);
        ctx.lineTo(dividerX, bbox.y + bbox.height - 6);
        ctx.stroke();
        ctx.restore();
        this.drawFitText(ctx, leftTopLines.filter(Boolean), leftTopBox, { font: "900 64px GroundliftBold, Arial Black, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.0 });
        if (options.leftBottom) {
            const bottomBox = { x: leftBox.x, y: leftBox.y + leftBox.height * 0.66, width: leftBox.width, height: leftBox.height * 0.34 };
            this.drawFitText(ctx, [options.leftBottom], bottomBox, { font: "500 34px GroundliftRegular, Arial, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.0 });
        }
        this.drawFitText(ctx, rightLines.filter(Boolean), rightBox, { font: `${options.compactRight ? 500 : 800} 52px GroundliftBold, Arial Black, sans-serif`, color: "#FFFFFF", align: "left", valign: "middle", lineHeight: 1.05 });
    }

    drawTitleOnly(ctx, bbox) {
        if (!bbox) return;
        this.drawFitText(ctx, [(this.state.event_title || "").toUpperCase()], bbox, { font: "900 64px GroundliftBold, Arial Black, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.0 });
    }

    drawSubtitleOnly(ctx, bbox) {
        if (!bbox) return;
        const lines = (this.state.event_subtitle || "").split(/\n+/).filter(Boolean).map((l) => l.toUpperCase());
        this.drawFitText(ctx, lines, bbox, { font: "500 46px GroundliftRegular, Arial, sans-serif", color: "#FFFFFF", align: "left", valign: "middle", lineHeight: 1.08 });
    }

    drawSummary(ctx, bbox) {
        if (!bbox) return;
        const text = (this.state.summary_text || "").trim();
        if (!text) return;
        this.drawParagraph(ctx, text, bbox, { font: "500 34px GroundliftRegular, Arial, sans-serif", color: "#FFFFFF", align: "left", lineHeight: 1.25 });
    }

    drawPhotoCredit(ctx, bbox) {
        if (!bbox || !this.state.photo_credit) return;
        this.drawFitText(ctx, [(this.state.photo_credit || "").toUpperCase()], bbox, { font: "400 28px GroundliftRegular, Arial, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.0 });
    }

    drawTicketLink(ctx, bbox) {
        if (!bbox || !this.state.ticket_link_text) return;
        this.drawFitText(ctx, [(this.state.ticket_link_text || "").toUpperCase()], bbox, { font: "600 28px GroundliftCondensed, Arial Narrow, sans-serif", color: "#FFFFFF", align: "center", valign: "middle", lineHeight: 1.0 });
    }

    drawQr(ctx, image, bbox, variant) {
        if (!bbox || !image) return;
        const box = this.applyBoxVariant(bbox, variant);
        ctx.drawImage(image, box.x, box.y, box.width, box.height);
    }

    drawExternalLogo(ctx, image, bbox, variant) {
        if (!bbox || !image) return;
        const box = this.applyBoxVariant(bbox, variant);
        ctx.drawImage(image, box.x, box.y, box.width, box.height);
    }

    drawDrinkCard(ctx, bbox) {
        if (!bbox || !this.currentTemplate?.is_drink_card) return;
        const config = this.state.editor_state.drink_card || defaultDrinkCard();
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        let cursorY = bbox.y + 40;
        const maxX = bbox.x + bbox.width - 24;
        const lineGap = 8;
        for (const section of config.sections || []) {
            if (!section.title) continue;
            ctx.font = "700 30px GroundliftBold, Arial Black, sans-serif";
            ctx.fillText(section.title.toUpperCase(), bbox.x + 24, cursorY);
            cursorY += 42;
            const products = this.state.products.filter((p) => (section.product_ids || []).includes(p.id));
            ctx.font = "400 23px GroundliftRegular, Arial, sans-serif";
            for (const product of products) {
                const line = `${product.name}`;
                const price = `${Number(product.price || 0).toFixed(2).replace('.', ',')} €`;
                ctx.fillText(line, bbox.x + 24, cursorY);
                const priceWidth = ctx.measureText(price).width;
                ctx.fillText(price, maxX - priceWidth, cursorY);
                cursorY += 29;
            }
            cursorY += lineGap + 12;
            if (cursorY > bbox.y + bbox.height - 80) break;
        }
        if (config.footer) {
            this.drawParagraph(ctx, config.footer, { x: bbox.x + 24, y: bbox.y + bbox.height - 120, width: bbox.width - 48, height: 96 }, { font: "400 20px GroundliftRegular, Arial, sans-serif", color: "#FFFFFF", align: "left", lineHeight: 1.2 });
        }
        ctx.restore();
    }

    drawFitText(ctx, lines, bbox, options = {}) {
        if (!bbox || !lines?.length) return;
        let size = parseInt((options.font || "500 40px Arial").match(/(\d+)px/)?.[1] || "40", 10);
        const fontTemplate = options.font || "500 SIZEpx Arial";
        const cleanLines = lines.filter((l) => l && String(l).trim());
        if (!cleanLines.length) return;
        while (size > 8) {
            ctx.font = fontTemplate.replace(/\d+px/, `${size}px`);
            const maxWidth = Math.max(...cleanLines.map((line) => ctx.measureText(line).width));
            const lineHeight = size * (options.lineHeight || 1.1);
            const totalHeight = cleanLines.length * lineHeight;
            if (maxWidth <= bbox.width && totalHeight <= bbox.height) break;
            size -= 2;
        }
        ctx.save();
        ctx.font = fontTemplate.replace(/\d+px/, `${size}px`);
        ctx.fillStyle = options.color || "#FFFFFF";
        ctx.textAlign = options.align || "left";
        ctx.textBaseline = "middle";
        const lineHeight = size * (options.lineHeight || 1.1);
        const totalHeight = cleanLines.length * lineHeight;
        let y = bbox.y + (options.valign === "middle" ? (bbox.height - totalHeight) / 2 + lineHeight / 2 : lineHeight / 2);
        for (const line of cleanLines) {
            const x = options.align === "center" ? bbox.x + bbox.width / 2 : options.align === "right" ? bbox.x + bbox.width : bbox.x;
            ctx.fillText(line, x, y);
            y += lineHeight;
        }
        ctx.restore();
    }

    drawParagraph(ctx, text, bbox, options = {}) {
        if (!text || !bbox) return;
        const words = text.split(/\s+/).filter(Boolean);
        let size = parseInt((options.font || "400 32px Arial").match(/(\d+)px/)?.[1] || "32", 10);
        const fontTemplate = options.font || "400 SIZEpx Arial";
        let lines = [];
        while (size > 8) {
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
            const totalHeight = lines.length * size * (options.lineHeight || 1.2);
            if (totalHeight <= bbox.height) break;
            size -= 2;
        }
        this.drawFitText(ctx, lines, bbox, { ...options, font: fontTemplate.replace(/\d+px/, `${size}px`), valign: "top" });
    }

    applyBoxVariant(bbox, variantBox = { dx: 0, dy: 0, scale: 1 }) {
        const scale = variantBox.scale || 1;
        const width = bbox.width * scale;
        const height = bbox.height * scale;
        return {
            x: bbox.x + (variantBox.dx || 0),
            y: bbox.y + (variantBox.dy || 0),
            width,
            height,
        };
    }

    drawMaskOutline(ctx, bbox, geometry = null) {
        if (!bbox) return;
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,0.9)";
        ctx.lineWidth = 2;
        if (geometry?.corners?.length === 4) {
            ctx.beginPath();
            drawPolygonPath(ctx, geometry.corners);
            ctx.stroke();
        } else {
            ctx.strokeRect(bbox.x, bbox.y, bbox.width, bbox.height);
        }
        ctx.restore();
    }

    async extractPalette() {
        if (!this.state.sourceImageBase64) return;
        const image = await loadImage(dataUrlFromBase64(this.state.sourceImageBase64, extensionMime(this.state.sourceImageFilename, "image/jpeg")));
        if (!image) return;
        const sample = document.createElement("canvas");
        sample.width = 48;
        sample.height = 48;
        const sctx = sample.getContext("2d");
        sctx.drawImage(image, 0, 0, sample.width, sample.height);
        const { data } = sctx.getImageData(0, 0, sample.width, sample.height);
        let dark = { r: 0, g: 0, b: 0, c: 0 };
        let bright = { r: 0, g: 0, b: 0, c: 0 };
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i + 1], b = data[i + 2];
            const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
            if (lum < 128) {
                dark.r += r; dark.g += g; dark.b += b; dark.c += 1;
            } else {
                bright.r += r; bright.g += g; bright.b += b; bright.c += 1;
            }
        }
        const first = dark.c ? { r: dark.r / dark.c, g: dark.g / dark.c, b: dark.b / dark.c } : { r: 0, g: 0, b: 40 };
        const second = bright.c ? { r: bright.r / bright.c, g: bright.g / bright.c, b: bright.b / bright.c } : { r: 0, g: 46, b: 89 };
        this.state.color_1 = rgbToHex(first);
        this.state.color_2 = this.state.color_contrast ? contrastingColor(this.state.color_1) : rgbToHex(second);
        this.renderCanvas();
    }

    onPointerDown(ev) {
        const templateInfo = this.templateCache.get(this.currentTemplate.key);
        const geometry = templateInfo?.geometries?.image_mask;
        const bbox = geometry?.bbox || templateInfo?.bboxes.image_mask;
        if (!bbox) return;
        const canvasRect = this.canvasRef.el.getBoundingClientRect();
        const x = ((ev.clientX - canvasRect.left) / canvasRect.width) * this.canvasRef.el.width;
        const y = ((ev.clientY - canvasRect.top) / canvasRect.height) * this.canvasRef.el.height;
        const inside = geometry?.corners?.length === 4
            ? pointInPolygon(x, y, geometry.corners)
            : (x >= bbox.x && x <= bbox.x + bbox.width && y >= bbox.y && y <= bbox.y + bbox.height);
        if (!inside) return;
        ev.preventDefault();
        const variant = this.currentVariant;
        const start = { x: ev.clientX, y: ev.clientY, offsetX: variant.image.offsetX || 0, offsetY: variant.image.offsetY || 0 };
        const move = (moveEv) => {
            variant.image.offsetX = start.offsetX + (moveEv.clientX - start.x) * (this.canvasRef.el.width / canvasRect.width);
            variant.image.offsetY = start.offsetY + (moveEv.clientY - start.y) * (this.canvasRef.el.height / canvasRect.height);
            this.renderCanvas();
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    onCanvasWheel(ev) {
        ev.preventDefault();
        const variant = this.currentVariant;
        const factor = ev.deltaY < 0 ? 1.03 : 0.97;
        variant.image.scale = clamp((variant.image.scale || 1) * factor, 0.2, 5);
        this.renderCanvas();
    }
}

registry.category("actions").add("groundlift_graphics.GraphicsEditor", GraphicsEditor);
