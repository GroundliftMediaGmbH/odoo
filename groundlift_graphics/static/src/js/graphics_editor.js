/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

const CANVAS_WIDTH = 2048;
const CANVAS_HEIGHT = 1045;
const IMAGE_POLYGON = [
    { x: 185, y: 74 },
    { x: 906, y: 214 },
    { x: 766, y: 942 },
    { x: 45, y: 803 },
];
const IMAGE_BBOX = { x: 45, y: 74, width: 861, height: 868 };

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function midpoint(a, b) {
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function distance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointInPolygon(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const xi = polygon[i].x;
        const yi = polygon[i].y;
        const xj = polygon[j].x;
        const yj = polygon[j].y;
        const intersects =
            yi > point.y !== yj > point.y &&
            point.x < ((xj - xi) * (point.y - yi)) / (yj - yi || 1) + xi;
        if (intersects) inside = !inside;
    }
    return inside;
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

function extensionMime(filename, fallback = "image/png") {
    const extension = (filename || "").split(".").pop().toLowerCase();
    const mapping = {
        png: "image/png",
        jpg: "image/jpeg",
        jpeg: "image/jpeg",
        webp: "image/webp",
        gif: "image/gif",
        svg: "image/svg+xml",
        ttf: "font/ttf",
        otf: "font/otf",
        woff: "font/woff",
        woff2: "font/woff2",
    };
    return mapping[extension] || fallback;
}

function dataUrl(base64Value, mime = "image/png") {
    return base64Value ? `data:${mime};base64,${base64Value}` : "";
}

function stripDataUrl(value) {
    return value && value.includes(",") ? value.split(",", 2)[1] : value || "";
}

export class GraphicsEditor extends Component {
    static template = "groundlift_graphics.GraphicsEditor";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.canvasRef = useRef("posterCanvas");
        this.fileRef = useRef("sourceFile");
        this.state = useState({
            loading: true,
            saving: false,
            posterId: 0,
            eventName: "",
            sourceImageBase64: "",
            sourceImageFilename: "veranstaltungsbild.jpg",
            claim: "",
            event_title: "",
            event_subtitle: "",
            date_text: "",
            time_text: "",
            event_type_text: "",
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
            output_filename: "veranstaltungsplakat.png",
            transform: { x: 475.5, y: 508, scale: 1, rotation: 0 },
        });
        this.templateData = {};
        this.images = {};
        this.paletteBase = null;
        this.drag = null;
        this.renderFrame = null;
        this._wheelHandler = (event) => this.onWheel(event);
        this._pointerMoveHandler = (event) => this.onPointerMove(event);
        this._pointerUpHandler = (event) => this.onPointerUp(event);

        onMounted(async () => {
            await this.loadEditor();
            await new Promise((resolve) => requestAnimationFrame(resolve));
            const canvas = this.canvasRef.el;
            if (canvas) {
                canvas.addEventListener("wheel", this._wheelHandler, { passive: false });
                this.renderPoster(true);
            }
            window.addEventListener("pointermove", this._pointerMoveHandler);
            window.addEventListener("pointerup", this._pointerUpHandler);
        });
        onWillUnmount(() => {
            const canvas = this.canvasRef.el;
            if (canvas) canvas.removeEventListener("wheel", this._wheelHandler);
            window.removeEventListener("pointermove", this._pointerMoveHandler);
            window.removeEventListener("pointerup", this._pointerUpHandler);
            if (this.renderFrame) cancelAnimationFrame(this.renderFrame);
        });
    }

    async loadEditor() {
        const posterId = Number(
            this.props.action?.params?.poster_id ||
                this.props.action?.context?.active_id ||
                this.props.action?.context?.params?.poster_id
        );
        if (!posterId) {
            this.notification.add("Keine Grafik-ID übergeben.", { type: "danger" });
            return;
        }
        try {
            const data = await this.orm.call("gl.graphics.poster", "get_editor_data", [[posterId]]);
            const poster = data.poster;
            const savedState = poster.editor_state || {};
            Object.assign(this.state, {
                loading: false,
                posterId: poster.id,
                eventName: poster.event_name,
                sourceImageBase64: poster.source_image || "",
                sourceImageFilename: poster.source_image_filename || "veranstaltungsbild.jpg",
                claim: poster.claim,
                event_title: poster.event_title,
                event_subtitle: poster.event_subtitle,
                date_text: poster.date_text,
                time_text: poster.time_text,
                event_type_text: poster.event_type_text,
                photo_credit: poster.photo_credit,
                ticket_url: poster.ticket_url,
                ticket_link_text: poster.ticket_link_text,
                qr_url: poster.qr_url,
                color_contrast: poster.color_contrast,
                color_1: poster.color_1,
                color_2: poster.color_2,
                sticker_mode: poster.sticker_mode,
                sticker_text: poster.sticker_text,
                sticker_color: poster.sticker_color,
                output_filename: poster.output_filename,
                transform: savedState.transform || this.state.transform,
            });
            this.paletteBase = savedState.paletteBase || null;
            this.templateData = data.template || {};
            await this.registerFonts();
            await this.loadImages(data.qr_image || "");
            if (this.images.source && !savedState.transform) this.resetTransform(false);
            if (this.images.source && !this.paletteBase) this.extractPalette(true);
            this.renderSoon();
        } catch (error) {
            console.error(error);
            this.state.loading = false;
            this.notification.add("Der Grafik-Editor konnte nicht geladen werden.", { type: "danger" });
        }
    }

    async registerFonts() {
        const definitions = [
            ["GLGraphicsRegular", this.templateData.font_regular_file, this.templateData.font_regular_filename],
            ["GLGraphicsBold", this.templateData.font_bold_file, this.templateData.font_bold_filename],
            ["GLGraphicsCondensed", this.templateData.font_condensed_file, this.templateData.font_condensed_filename],
        ];
        for (const [family, file, filename] of definitions) {
            if (!file) continue;
            try {
                const face = new FontFace(family, `url(${dataUrl(file, extensionMime(filename, "font/ttf"))})`);
                await face.load();
                document.fonts.add(face);
            } catch (error) {
                console.warn(`Schrift ${family} konnte nicht geladen werden`, error);
            }
        }
    }

    fontFamily(kind) {
        const customMap = {
            regular: this.templateData.font_regular_file ? "GLGraphicsRegular" : null,
            bold: this.templateData.font_bold_file ? "GLGraphicsBold" : null,
            condensed: this.templateData.font_condensed_file ? "GLGraphicsCondensed" : null,
        };
        const configuredMap = {
            regular: this.templateData.font_regular_name || "Arial",
            bold: this.templateData.font_bold_name || "Arial Black",
            condensed: this.templateData.font_condensed_name || "Arial Narrow",
        };
        return customMap[kind] || configuredMap[kind];
    }

    async loadImages(qrBase64 = "") {
        const loads = [
            ["logo", this.templateData.logo_image, "image/png"],
            ["frame", this.templateData.frame_image, "image/png"],
            ["sticker", this.templateData.sticker_image, "image/png"],
            ["qr", qrBase64, "image/png"],
        ];
        if (this.state.sourceImageBase64) {
            loads.push([
                "source",
                this.state.sourceImageBase64,
                extensionMime(this.state.sourceImageFilename, "image/jpeg"),
            ]);
        }
        await Promise.all(
            loads.map(async ([key, value, mime]) => {
                this.images[key] = value ? await this.loadImage(dataUrl(value, mime)) : null;
            })
        );
    }

    loadImage(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = reject;
            image.src = url;
        });
    }

    renderSoon() {
        if (this.renderFrame) cancelAnimationFrame(this.renderFrame);
        this.renderFrame = requestAnimationFrame(() => {
            this.renderFrame = null;
            this.renderPoster(true);
        });
    }

    renderPoster(showGuides = true) {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        const ctx = canvas.getContext("2d", { alpha: false });
        ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
        this.drawGradient(ctx);
        this.drawSourceImage(ctx);
        this.drawLayer(ctx, this.images.frame, { x: 140, y: 156, width: 665, height: 677 });
        this.drawSticker(ctx);
        this.drawLogo(ctx);
        this.drawClaim(ctx);
        this.drawEventText(ctx);
        this.drawPhotoCredit(ctx);
        this.drawTicketLink(ctx);
        this.drawQr(ctx);
        if (showGuides) this.drawImageHandles(ctx);
    }

    drawGradient(ctx) {
        const gradient = ctx.createLinearGradient(0, 0, 0, CANVAS_HEIGHT);
        gradient.addColorStop(0, this.state.color_1 || "#000033");
        gradient.addColorStop(0.48, this.state.color_2 || "#002E59");
        gradient.addColorStop(1, "#000000");
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    }

    drawSourceImage(ctx) {
        ctx.save();
        ctx.beginPath();
        IMAGE_POLYGON.forEach((point, index) => {
            if (index === 0) ctx.moveTo(point.x, point.y);
            else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.clip();
        if (!this.images.source) {
            ctx.fillStyle = "rgba(255,255,255,0.08)";
            ctx.fillRect(IMAGE_BBOX.x, IMAGE_BBOX.y, IMAGE_BBOX.width, IMAGE_BBOX.height);
            ctx.fillStyle = "rgba(255,255,255,0.65)";
            ctx.font = `600 28px ${this.fontFamily("regular")}`;
            ctx.textAlign = "center";
            ctx.fillText("BILD HOCHLADEN", 475, 510);
            ctx.restore();
            return;
        }
        const transform = this.state.transform;
        ctx.translate(transform.x, transform.y);
        ctx.rotate(transform.rotation);
        ctx.scale(transform.scale, transform.scale);
        ctx.drawImage(
            this.images.source,
            -this.images.source.naturalWidth / 2,
            -this.images.source.naturalHeight / 2
        );
        ctx.restore();
    }

    drawLayer(ctx, image, fallbackBox) {
        if (!image) return;
        if (image.naturalWidth === CANVAS_WIDTH && image.naturalHeight === CANVAS_HEIGHT) {
            ctx.drawImage(image, 0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
            return;
        }
        const scale = Math.min(
            fallbackBox.width / image.naturalWidth,
            fallbackBox.height / image.naturalHeight
        );
        const width = image.naturalWidth * scale;
        const height = image.naturalHeight * scale;
        const x = fallbackBox.x + (fallbackBox.width - width) / 2;
        const y = fallbackBox.y + (fallbackBox.height - height) / 2;
        ctx.drawImage(image, x, y, width, height);
    }

    drawLogo(ctx) {
        this.drawLayer(ctx, this.images.logo, { x: 1267, y: 174, width: 356, height: 120 });
    }

    drawSticker(ctx) {
        if (this.state.sticker_mode === "hidden") return;
        if (this.state.sticker_mode === "original" && this.images.sticker) {
            this.drawLayer(ctx, this.images.sticker, { x: 801, y: 7, width: 336, height: 337 });
            return;
        }
        const center = { x: 969, y: 175 };
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.32)";
        ctx.shadowBlur = 8;
        ctx.shadowOffsetY = 4;
        ctx.fillStyle = this.state.sticker_color || "#D6331F";
        ctx.beginPath();
        ctx.arc(center.x, center.y, 167, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowColor = "transparent";
        ctx.translate(center.x, center.y);
        ctx.rotate((-10 * Math.PI) / 180);
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = `900 48px ${this.fontFamily("bold")}`;
        const lines = (this.state.sticker_text || "").split(/\r?\n/).slice(0, 4);
        const lineHeight = 57;
        const startY = -((lines.length - 1) * lineHeight) / 2;
        lines.forEach((line, index) => ctx.fillText(line.toUpperCase(), 0, startY + index * lineHeight));
        ctx.restore();
    }

    drawClaim(ctx) {
        const lines = (this.state.claim || "").split(/\r?\n/).slice(0, 3);
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.font = `400 31px ${this.fontFamily("regular")}`;
        const x = 1444;
        const lineHeight = 45;
        const startY = 387 - ((lines.length - 2) * lineHeight) / 2;
        lines.forEach((line, index) => this.drawTrackedText(ctx, line.toUpperCase(), x, startY + index * lineHeight, 0.25, "center"));
        ctx.restore();
    }

    drawEventText(ctx) {
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        ctx.textBaseline = "alphabetic";

        ctx.fillRect(1266, 566, 13, 197);

        const boldFamily = this.fontFamily("bold");
        const regularFamily = this.fontFamily("regular");

        ctx.textAlign = "right";
        ctx.font = `900 ${this.fitFontSize(ctx, this.state.date_text, 303, 52, 32, "900", boldFamily)}px ${boldFamily}`;
        ctx.fillText((this.state.date_text || "").toUpperCase(), 1227, 620);

        ctx.textAlign = "left";
        ctx.font = `900 ${this.fitFontSize(ctx, this.state.event_title, 585, 51, 28, "900", boldFamily)}px ${boldFamily}`;
        ctx.fillText((this.state.event_title || "").toUpperCase(), 1318, 620);

        ctx.textAlign = "right";
        ctx.font = `900 ${this.fitFontSize(ctx, this.state.time_text, 300, 39, 27, "900", boldFamily)}px ${boldFamily}`;
        ctx.fillText((this.state.time_text || "").toUpperCase(), 1227, 690);

        ctx.font = `400 ${this.fitFontSize(ctx, this.state.event_type_text, 300, 36, 25, "400", regularFamily)}px ${regularFamily}`;
        ctx.fillText((this.state.event_type_text || "").toUpperCase(), 1227, 746);

        ctx.textAlign = "left";
        ctx.font = `400 36px ${this.fontFamily("regular")}`;
        this.drawWrappedText(
            ctx,
            (this.state.event_subtitle || "").toUpperCase(),
            1318,
            690,
            590,
            54,
            2,
            26,
            "400",
            regularFamily
        );
        ctx.restore();
    }

    fitFontSize(ctx, text, maxWidth, startSize, minSize, weight, family) {
        let size = startSize;
        while (size > minSize) {
            ctx.font = `${weight} ${size}px ${family}`;
            if (ctx.measureText((text || "").toUpperCase()).width <= maxWidth) break;
            size -= 1;
        }
        return size;
    }

    drawWrappedText(
        ctx,
        text,
        x,
        y,
        maxWidth,
        lineHeight,
        maxLines = 2,
        minFontSize = 24,
        weight = "400",
        family = "Arial"
    ) {
        let fontSize = parseFloat(ctx.font.match(/([0-9.]+)px/)?.[1] || "36");
        let lines = [];
        while (fontSize >= minFontSize) {
            ctx.font = `${weight} ${fontSize}px ${family}`;
            const words = (text || "").split(/\s+/).filter(Boolean);
            lines = [];
            let line = "";
            for (const word of words) {
                const candidate = line ? `${line} ${word}` : word;
                if (ctx.measureText(candidate).width <= maxWidth || !line) line = candidate;
                else {
                    lines.push(line);
                    line = word;
                }
            }
            if (line) lines.push(line);
            if (lines.length <= maxLines) break;
            fontSize -= 1;
        }
        lines.slice(0, maxLines).forEach((line, index) => ctx.fillText(line, x, y + index * lineHeight));
    }

    drawPhotoCredit(ctx) {
        if (!this.state.photo_credit) return;
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.font = `400 17px ${this.fontFamily("condensed")}`;
        this.drawTrackedText(ctx, this.state.photo_credit.toUpperCase(), 475, 866, 0.5, "center");
        ctx.restore();
    }

    drawTicketLink(ctx) {
        if (!this.state.ticket_link_text) return;
        ctx.save();
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        let size = 15;
        ctx.font = `700 ${size}px ${this.fontFamily("condensed")}`;
        while (ctx.measureText(this.state.ticket_link_text.toUpperCase()).width > 900 && size > 10) {
            size -= 0.5;
            ctx.font = `700 ${size}px ${this.fontFamily("condensed")}`;
        }
        this.drawTrackedText(ctx, this.state.ticket_link_text.toUpperCase(), 1165, 1002, 0.15, "center");
        ctx.restore();
    }

    drawQr(ctx) {
        if (!this.images.qr) return;
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(1719, 816, 191, 191);
        ctx.drawImage(this.images.qr, 1719, 816, 191, 191);
        ctx.restore();
    }

    drawTrackedText(ctx, text, x, y, tracking = 0, align = "left") {
        if (!text) return;
        if (!tracking) {
            ctx.textAlign = align;
            ctx.fillText(text, x, y);
            return;
        }
        const widths = [...text].map((character) => ctx.measureText(character).width);
        const total = widths.reduce((sum, width) => sum + width, 0) + tracking * Math.max(0, text.length - 1);
        let cursor = x;
        if (align === "center") cursor -= total / 2;
        if (align === "right") cursor -= total;
        ctx.textAlign = "left";
        [...text].forEach((character, index) => {
            ctx.fillText(character, cursor, y);
            cursor += widths[index] + tracking;
        });
    }

    drawImageHandles(ctx) {
        const edgeHandles = IMAGE_POLYGON.map((point, index) => midpoint(point, IMAGE_POLYGON[(index + 1) % IMAGE_POLYGON.length]));
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,0.72)";
        ctx.lineWidth = 2;
        ctx.setLineDash([12, 10]);
        ctx.beginPath();
        IMAGE_POLYGON.forEach((point, index) => {
            if (index === 0) ctx.moveTo(point.x, point.y);
            else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.stroke();
        ctx.setLineDash([]);
        for (const point of edgeHandles) this.drawHandle(ctx, point, false);
        for (const point of IMAGE_POLYGON) this.drawHandle(ctx, point, true);
        ctx.restore();
    }

    drawHandle(ctx, point, corner) {
        ctx.fillStyle = corner ? "#0D6EFD" : "#FFFFFF";
        ctx.strokeStyle = corner ? "#FFFFFF" : "#0D6EFD";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(point.x, point.y, corner ? 11 : 9, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
    }

    canvasPoint(event) {
        const rect = this.canvasRef.el.getBoundingClientRect();
        return {
            x: ((event.clientX - rect.left) / rect.width) * CANVAS_WIDTH,
            y: ((event.clientY - rect.top) / rect.height) * CANVAS_HEIGHT,
        };
    }

    onPointerDown(event) {
        if (!this.images.source) return;
        const point = this.canvasPoint(event);
        const cornerIndex = IMAGE_POLYGON.findIndex((handle) => distance(point, handle) <= 24);
        const edgeHandles = IMAGE_POLYGON.map((handle, index) => midpoint(handle, IMAGE_POLYGON[(index + 1) % IMAGE_POLYGON.length]));
        const edgeIndex = edgeHandles.findIndex((handle) => distance(point, handle) <= 24);
        const transform = { ...this.state.transform };
        const center = { x: IMAGE_BBOX.x + IMAGE_BBOX.width / 2, y: IMAGE_BBOX.y + IMAGE_BBOX.height / 2 };
        if (cornerIndex >= 0) {
            this.drag = {
                mode: "rotate",
                startPoint: point,
                startTransform: transform,
                startAngle: Math.atan2(point.y - center.y, point.x - center.x),
                center,
            };
        } else if (edgeIndex >= 0) {
            const a = IMAGE_POLYGON[edgeIndex];
            const b = IMAGE_POLYGON[(edgeIndex + 1) % IMAGE_POLYGON.length];
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const length = Math.hypot(dx, dy) || 1;
            this.drag = {
                mode: "edge",
                startPoint: point,
                startTransform: transform,
                normal: { x: -dy / length, y: dx / length },
            };
        } else if (pointInPolygon(point, IMAGE_POLYGON)) {
            this.drag = { mode: "pan", startPoint: point, startTransform: transform };
        }
        if (this.drag) {
            event.preventDefault();
            this.canvasRef.el.setPointerCapture?.(event.pointerId);
        }
    }

    onPointerMove(event) {
        if (!this.drag) return;
        const point = this.canvasPoint(event);
        const start = this.drag.startPoint;
        const transform = { ...this.drag.startTransform };
        if (this.drag.mode === "pan") {
            transform.x += point.x - start.x;
            transform.y += point.y - start.y;
        } else if (this.drag.mode === "edge") {
            const delta = { x: point.x - start.x, y: point.y - start.y };
            const projection = delta.x * this.drag.normal.x + delta.y * this.drag.normal.y;
            transform.x += this.drag.normal.x * projection;
            transform.y += this.drag.normal.y * projection;
        } else if (this.drag.mode === "rotate") {
            const angle = Math.atan2(point.y - this.drag.center.y, point.x - this.drag.center.x);
            transform.rotation += angle - this.drag.startAngle;
        }
        this.state.transform = transform;
        this.renderSoon();
    }

    onPointerUp() {
        this.drag = null;
    }

    onWheel(event) {
        if (!this.images.source) return;
        event.preventDefault();
        const point = this.canvasPoint(event);
        const transform = { ...this.state.transform };
        const oldScale = transform.scale;
        const factor = Math.exp(-event.deltaY * 0.0015);
        const newScale = clamp(oldScale * factor, 0.03, 12);
        const cos = Math.cos(-transform.rotation);
        const sin = Math.sin(-transform.rotation);
        const dx = point.x - transform.x;
        const dy = point.y - transform.y;
        const localX = (dx * cos - dy * sin) / oldScale;
        const localY = (dx * sin + dy * cos) / oldScale;
        const rcos = Math.cos(transform.rotation);
        const rsin = Math.sin(transform.rotation);
        transform.x = point.x - (localX * rcos - localY * rsin) * newScale;
        transform.y = point.y - (localX * rsin + localY * rcos) * newScale;
        transform.scale = newScale;
        this.state.transform = transform;
        this.renderSoon();
    }

    resetTransform(notify = true) {
        if (!this.images.source) return;
        const scale = Math.max(
            IMAGE_BBOX.width / this.images.source.naturalWidth,
            IMAGE_BBOX.height / this.images.source.naturalHeight
        );
        this.state.transform = {
            x: IMAGE_BBOX.x + IMAGE_BBOX.width / 2,
            y: IMAGE_BBOX.y + IMAGE_BBOX.height / 2,
            scale,
            rotation: 0,
        };
        if (notify) this.notification.add("Bildausschnitt zurückgesetzt.", { type: "info" });
        this.renderSoon();
    }

    openFilePicker() {
        this.fileRef.el.click();
    }

    async onSourceFile(event) {
        const file = event.target.files?.[0];
        if (!file) return;
        if (!file.type.startsWith("image/")) {
            this.notification.add("Bitte eine Bilddatei auswählen.", { type: "warning" });
            return;
        }
        const value = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        this.state.sourceImageBase64 = stripDataUrl(value);
        this.state.sourceImageFilename = file.name;
        this.images.source = await this.loadImage(value);
        this.paletteBase = null;
        this.resetTransform(false);
        this.extractPalette(true);
        event.target.value = "";
        this.renderSoon();
    }

    extractPalette(apply = true) {
        const image = this.images.source;
        if (!image) return;
        const sampleCanvas = document.createElement("canvas");
        sampleCanvas.width = 96;
        sampleCanvas.height = 96;
        const sampleCtx = sampleCanvas.getContext("2d", { willReadFrequently: true });
        sampleCtx.drawImage(image, 0, 0, 96, 96);
        const data = sampleCtx.getImageData(0, 0, 96, 96).data;
        const pixels = [];
        for (let index = 0; index < data.length; index += 16) {
            const r = data[index];
            const g = data[index + 1];
            const b = data[index + 2];
            const alpha = data[index + 3];
            if (alpha < 180) continue;
            const max = Math.max(r, g, b);
            const min = Math.min(r, g, b);
            if (max < 12 || min > 245) continue;
            pixels.push([r, g, b]);
        }
        if (!pixels.length) return;
        let centers = [pixels[Math.floor(pixels.length * 0.25)], pixels[Math.floor(pixels.length * 0.75)]];
        for (let iteration = 0; iteration < 12; iteration++) {
            const groups = [[], []];
            for (const pixel of pixels) {
                const distances = centers.map((center) =>
                    (pixel[0] - center[0]) ** 2 + (pixel[1] - center[1]) ** 2 + (pixel[2] - center[2]) ** 2
                );
                groups[distances[0] <= distances[1] ? 0 : 1].push(pixel);
            }
            centers = groups.map((group, index) => {
                if (!group.length) return centers[index];
                return [0, 1, 2].map((channel) =>
                    group.reduce((sum, pixel) => sum + pixel[channel], 0) / group.length
                );
            });
        }
        this.paletteBase = centers.map((center) => rgbToHex({ r: center[0], g: center[1], b: center[2] }));
        if (apply) this.applyPalette();
    }

    applyPalette() {
        if (!this.paletteBase) return;
        const colors = this.state.color_contrast
            ? this.paletteBase.map((color) => contrastingColor(color))
            : this.paletteBase;
        this.state.color_1 = colors[0];
        this.state.color_2 = colors[1];
        this.renderSoon();
    }

    onFieldInput(event) {
        const field = event.currentTarget.dataset.field;
        this.state[field] = event.currentTarget.value;
        if (field === "color_1" || field === "color_2") this.state.color_contrast = false;
        this.renderSoon();
    }

    async onQrUrlChange(event) {
        this.state.qr_url = event.currentTarget.value;
        try {
            const qrBase64 = await this.orm.call("gl.graphics.poster", "generate_qr_base64", [this.state.qr_url]);
            this.images.qr = qrBase64 ? await this.loadImage(dataUrl(qrBase64, "image/png")) : null;
            this.renderSoon();
        } catch (error) {
            console.error(error);
            this.notification.add("QR-Code konnte nicht erzeugt werden.", { type: "warning" });
        }
    }

    onContrastChange(event) {
        this.state.color_contrast = event.currentTarget.checked;
        if (!this.paletteBase && this.images.source) this.extractPalette(false);
        this.applyPalette();
    }

    async save() {
        return this._save(false);
    }

    async saveAndDownload() {
        return this._save(true);
    }

    async _save(download) {
        if (this.state.saving) return;
        if (!this.state.sourceImageBase64 || !this.images.source) {
            this.notification.add("Bitte zuerst ein Veranstaltungsbild hochladen.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            this.renderPoster(false);
            const rendered = this.canvasRef.el.toDataURL("image/png");
            const values = {
                source_image: this.state.sourceImageBase64,
                source_image_filename: this.state.sourceImageFilename,
                claim: this.state.claim,
                event_title: this.state.event_title,
                event_subtitle: this.state.event_subtitle,
                date_text: this.state.date_text,
                time_text: this.state.time_text,
                event_type_text: this.state.event_type_text,
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
                output_filename: this.state.output_filename,
                editor_state: {
                    transform: { ...this.state.transform },
                    paletteBase: this.paletteBase,
                },
            };
            await this.orm.call("gl.graphics.poster", "save_editor_data", [
                [this.state.posterId],
                values,
                rendered,
            ]);
            this.notification.add("Grafik wurde gespeichert.", { type: "success" });
            if (download) {
                window.location.href = `/web/content?model=gl.graphics.poster&id=${this.state.posterId}&field=output_image&filename_field=output_filename&download=true`;
            }
        } catch (error) {
            console.error(error);
            this.notification.add("Die Grafik konnte nicht gespeichert werden.", { type: "danger" });
        } finally {
            this.state.saving = false;
            this.renderSoon();
        }
    }

    backToRecord() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "gl.graphics.poster",
            res_id: this.state.posterId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("groundlift_graphics.GraphicsEditor", GraphicsEditor);
