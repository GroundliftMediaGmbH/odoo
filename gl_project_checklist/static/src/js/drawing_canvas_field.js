/** @odoo-module **/

import { Component, onMounted, onPatched, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class GroundliftDrawingCanvasField extends Component {
    static template = "gl_project_checklist.DrawingCanvasField";
    static props = {
        ...standardFieldProps,
        backgroundUrl: { type: String, optional: true },
        canvasWidth: { type: Number, optional: true },
        canvasHeight: { type: Number, optional: true },
        title: { type: String, optional: true },
        rotationField: { type: String, optional: true },
    };

    setup() {
        this.bgCanvasRef = useRef("bgCanvas");
        this.canvasRef = useRef("canvas");
        this.scrollerRef = useRef("scroller");
        this.holderRef = useRef("holder");
        this.bgCtx = null;
        this.ctx = null;
        this.backgroundImage = null;
        this.backgroundImageUrl = null;
        this.drawing = false;
        this.lastX = 0;
        this.lastY = 0;
        this.saveTimer = null;
        this.lastLoadedValue = null;
        this.state = useState({
            size: 4,
            color: "#0a84ff",
            eraser: false,
            zoom: 100,
            status: "",
            rotation: this.getRecordRotation(),
        });

        onMounted(() => {
            this.initContexts();
            this.resizeCanvases();
            this.loadBackground();
            this.loadOverlay(true);
            this.fitToWidth();
        });

        onPatched(() => {
            this.initContexts();
            this.resizeCanvases(false);
            this.loadBackground();
            this.loadOverlay(false);
        });
    }

    normalizeRotation(value) {
        let rotation = Number(value || 0);
        if (!Number.isFinite(rotation)) {
            rotation = 0;
        }
        rotation = ((rotation % 360) + 360) % 360;
        return [0, 90, 180, 270].includes(rotation) ? rotation : 0;
    }

    getRecordRotation() {
        if (!this.props.rotationField) {
            return 0;
        }
        return this.normalizeRotation(this.props.record.data[this.props.rotationField]);
    }

    get baseCanvasWidth() {
        return this.props.canvasWidth || 980;
    }

    get baseCanvasHeight() {
        return this.props.canvasHeight || 1400;
    }

    get rotation() {
        return this.normalizeRotation(this.state.rotation);
    }

    get isQuarterTurn() {
        return this.rotation === 90 || this.rotation === 270;
    }

    get canvasWidth() {
        return this.isQuarterTurn ? this.baseCanvasHeight : this.baseCanvasWidth;
    }

    get canvasHeight() {
        return this.isQuarterTurn ? this.baseCanvasWidth : this.baseCanvasHeight;
    }

    get title() {
        return this.props.title || "Plan";
    }

    get rotationLabel() {
        return `${this.rotation}°`;
    }

    get canvasStyle() {
        return `width:${this.canvasWidth}px; height:${this.canvasHeight}px;`;
    }

    get holderStyle() {
        const zoom = this.state.zoom / 100;
        return `width:${this.canvasWidth}px; height:${this.canvasHeight}px; transform:scale(${zoom});`;
    }

    get wrapperStyle() {
        const zoom = this.state.zoom / 100;
        return `width:${this.canvasWidth * zoom}px; height:${this.canvasHeight * zoom}px;`;
    }

    get currentValue() {
        return this.props.record.data[this.props.name] || false;
    }

    initContexts() {
        if (this.bgCanvasRef.el && !this.bgCtx) {
            this.bgCtx = this.bgCanvasRef.el.getContext("2d");
        }
        if (this.canvasRef.el && !this.ctx) {
            this.ctx = this.canvasRef.el.getContext("2d");
        }
    }

    resizeCanvases(clearOverlay = true) {
        for (const canvas of [this.bgCanvasRef.el, this.canvasRef.el]) {
            if (!canvas) {
                continue;
            }
            if (canvas.width !== this.canvasWidth) {
                canvas.width = this.canvasWidth;
            }
            if (canvas.height !== this.canvasHeight) {
                canvas.height = this.canvasHeight;
            }
            canvas.style.width = `${this.canvasWidth}px`;
            canvas.style.height = `${this.canvasHeight}px`;
        }
        if (clearOverlay && this.ctx) {
            this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
        }
        this.drawBackground();
    }

    loadBackground() {
        if (!this.props.backgroundUrl) {
            return;
        }
        if (this.backgroundImage && this.backgroundImageUrl === this.props.backgroundUrl) {
            this.drawBackground();
            return;
        }
        this.backgroundImageUrl = this.props.backgroundUrl;
        const img = new Image();
        img.onload = () => {
            this.backgroundImage = img;
            this.drawBackground();
        };
        img.src = this.props.backgroundUrl;
    }

    drawBackground() {
        if (!this.bgCtx || !this.backgroundImage) {
            return;
        }
        const ctx = this.bgCtx;
        const bw = this.baseCanvasWidth;
        const bh = this.baseCanvasHeight;
        const cw = this.canvasWidth;
        const ch = this.canvasHeight;
        ctx.clearRect(0, 0, cw, ch);
        ctx.save();
        if (this.rotation === 90) {
            ctx.translate(cw, 0);
            ctx.rotate(Math.PI / 2);
        } else if (this.rotation === 180) {
            ctx.translate(cw, ch);
            ctx.rotate(Math.PI);
        } else if (this.rotation === 270) {
            ctx.translate(0, ch);
            ctx.rotate(-Math.PI / 2);
        }
        ctx.drawImage(this.backgroundImage, 0, 0, bw, bh);
        ctx.restore();
    }

    normalizeBinaryValue(value) {
        if (!value || typeof value !== "string") {
            return false;
        }
        if (value.startsWith("data:image")) {
            return value;
        }
        return `data:image/png;base64,${value}`;
    }

    loadOverlay(force = false) {
        if (!this.ctx) {
            return;
        }
        const value = this.currentValue;
        if (!force && value === this.lastLoadedValue) {
            return;
        }
        this.lastLoadedValue = value;
        this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
        const src = this.normalizeBinaryValue(value);
        if (!src) {
            return;
        }
        const img = new Image();
        img.onload = () => {
            this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
            this.ctx.drawImage(img, 0, 0, this.canvasWidth, this.canvasHeight);
        };
        img.src = src;
    }

    fitToWidth() {
        const scroller = this.scrollerRef.el;
        if (!scroller) {
            return;
        }
        const fit = Math.min(100, Math.floor(((scroller.clientWidth || 0) - 24) / this.canvasWidth * 100));
        if (Number.isFinite(fit) && fit > 10) {
            this.state.zoom = fit;
        }
    }

    setColor(color) {
        this.state.color = color;
        this.state.eraser = false;
    }

    setRed() {
        this.setColor("#ff3b30");
    }

    setGreen() {
        this.setColor("#34c759");
    }

    setBlue() {
        this.setColor("#0a84ff");
    }

    setYellow() {
        this.setColor("#ffd60a");
    }

    getCanvasPoint(ev) {
        const canvas = this.canvasRef.el;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        return {
            x: (ev.clientX - rect.left) * scaleX,
            y: (ev.clientY - rect.top) * scaleY,
        };
    }

    startDraw(ev) {
        if (this.props.readonly) {
            return;
        }
        ev.preventDefault();
        this.loadOverlay(false);
        const pos = this.getCanvasPoint(ev);
        this.drawing = true;
        this.lastX = pos.x;
        this.lastY = pos.y;
        try {
            this.canvasRef.el.setPointerCapture(ev.pointerId);
        } catch (_) {
            // Pointer capture is a convenience only.
        }
    }

    moveDraw(ev) {
        if (!this.drawing || this.props.readonly) {
            return;
        }
        ev.preventDefault();
        const pos = this.getCanvasPoint(ev);
        this.ctx.lineJoin = "round";
        this.ctx.lineCap = "round";
        this.ctx.lineWidth = Number(this.state.size || 4);
        this.ctx.globalCompositeOperation = this.state.eraser ? "destination-out" : "source-over";
        this.ctx.strokeStyle = this.state.color || "#0a84ff";
        this.ctx.beginPath();
        this.ctx.moveTo(this.lastX, this.lastY);
        this.ctx.lineTo(pos.x, pos.y);
        this.ctx.stroke();
        this.lastX = pos.x;
        this.lastY = pos.y;
        this.state.status = "Änderungen ...";
    }

    endDraw(ev) {
        if (!this.drawing) {
            return;
        }
        ev.preventDefault();
        this.drawing = false;
        this.scheduleSave();
    }

    scheduleSave() {
        clearTimeout(this.saveTimer);
        this.saveTimer = setTimeout(() => this.saveCanvas(), 600);
    }

    buildUpdateData(base64) {
        const values = { [this.props.name]: base64 };
        if (this.props.rotationField) {
            values[this.props.rotationField] = this.rotation;
        }
        return values;
    }

    async saveCanvas(statusText = null) {
        if (this.props.readonly) {
            return;
        }
        const dataUrl = this.canvasRef.el.toDataURL("image/png");
        const base64 = dataUrl.split(",", 2)[1];
        this.lastLoadedValue = base64;
        await this.props.record.update(this.buildUpdateData(base64));
        this.state.status = statusText || `In das Projekt übernommen ${new Date().toLocaleTimeString()}`;
    }

    async clearCanvas() {
        if (this.props.readonly) {
            return;
        }
        this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
        this.lastLoadedValue = false;
        const values = { [this.props.name]: false };
        if (this.props.rotationField) {
            values[this.props.rotationField] = this.rotation;
        }
        await this.props.record.update(values);
        this.state.status = "Zeichnung zurückgesetzt";
    }

    rotateOverlayClockwise(oldCanvas, oldWidth, oldHeight) {
        if (!this.ctx) {
            return;
        }
        this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
        this.ctx.save();
        this.ctx.translate(this.canvasWidth, 0);
        this.ctx.rotate(Math.PI / 2);
        this.ctx.drawImage(oldCanvas, 0, 0, oldWidth, oldHeight);
        this.ctx.restore();
    }

    async rotateClockwise() {
        if (this.props.readonly) {
            return;
        }
        this.loadOverlay(false);
        const oldWidth = this.canvasWidth;
        const oldHeight = this.canvasHeight;
        const oldCanvas = document.createElement("canvas");
        oldCanvas.width = oldWidth;
        oldCanvas.height = oldHeight;
        oldCanvas.getContext("2d").drawImage(this.canvasRef.el, 0, 0, oldWidth, oldHeight);

        this.state.rotation = this.normalizeRotation(this.rotation + 90);
        this.resizeCanvases(true);
        this.drawBackground();
        this.rotateOverlayClockwise(oldCanvas, oldWidth, oldHeight);
        await this.saveCanvas(`Plan rotiert auf ${this.rotationLabel}`);
    }
}

const groundliftDrawingCanvasField = {
    component: GroundliftDrawingCanvasField,
    supportedTypes: ["binary"],
    extractProps: ({ options }) => ({
        backgroundUrl: options.background_url || "",
        canvasWidth: Number(options.canvas_width || 980),
        canvasHeight: Number(options.canvas_height || 1400),
        title: options.title || "Plan",
        rotationField: options.rotation_field || "",
    }),
};

registry.category("fields").add("gl_drawing_canvas", groundliftDrawingCanvasField);
