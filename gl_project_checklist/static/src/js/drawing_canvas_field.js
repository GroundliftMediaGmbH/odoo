/** @odoo-module **/

import { Component, onMounted, useRef, useState } from "@odoo/owl";
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
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.scrollerRef = useRef("scroller");
        this.holderRef = useRef("holder");
        this.ctx = null;
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
        });
        onMounted(() => {
            this.ctx = this.canvasRef.el.getContext("2d");
            this.loadOverlay();
            this.fitToWidth();
        });
    }

    get canvasWidth() {
        return this.props.canvasWidth || 980;
    }

    get canvasHeight() {
        return this.props.canvasHeight || 1400;
    }

    get title() {
        return this.props.title || "Plan";
    }

    get canvasStyle() {
        const bg = this.props.backgroundUrl ? `background-image:url('${this.props.backgroundUrl}');` : "";
        return `${bg} width:${this.canvasWidth}px; height:${this.canvasHeight}px;`;
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

    normalizeBinaryValue(value) {
        if (!value || typeof value !== "string") {
            return false;
        }
        if (value.startsWith("data:image")) {
            return value;
        }
        return `data:image/png;base64,${value}`;
    }

    loadOverlay() {
        if (!this.ctx) {
            return;
        }
        const value = this.currentValue;
        if (value === this.lastLoadedValue) {
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
        const fit = Math.min(100, Math.floor((scroller.clientWidth - 24) / this.canvasWidth * 100));
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
        this.loadOverlay();
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

    async saveCanvas() {
        if (this.props.readonly) {
            return;
        }
        const dataUrl = this.canvasRef.el.toDataURL("image/png");
        const base64 = dataUrl.split(",", 2)[1];
        this.lastLoadedValue = base64;
        await this.props.record.update({ [this.props.name]: base64 });
        this.state.status = `In das Projekt übernommen ${new Date().toLocaleTimeString()}`;
    }

    async clearCanvas() {
        if (this.props.readonly) {
            return;
        }
        this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
        this.lastLoadedValue = false;
        await this.props.record.update({ [this.props.name]: false });
        this.state.status = "Zeichnung zurückgesetzt";
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
    }),
};

registry.category("fields").add("gl_drawing_canvas", groundliftDrawingCanvasField);
