/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class InboxFilterBatchProgress extends Component {
    static template = "inbox_filter.BatchProgress";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.batchId = this.props.action?.params?.batch_id;
        this.busy = false;
        this.state = useState({
            exists: true,
            name: "Inbox Filter",
            state: "queued",
            state_label: "Vorbereitet",
            total_count: 0,
            processed_count: 0,
            success_count: 0,
            error_count: 0,
            skipped_count: 0,
            progress: 0,
            last_message: "Stapelverarbeitung wird vorbereitet …",
            current_history: "",
            wait_seconds: 0,
            done: false,
        });
        onMounted(async () => {
            await this._load();
            this.timer = setInterval(() => this._tick(), 1800);
            await this._tick();
        });
        onWillUnmount(() => {
            if (this.timer) {
                clearInterval(this.timer);
            }
        });
    }

    async _load() {
        if (!this.batchId) {
            this.state.exists = false;
            return;
        }
        const data = await this.orm.call("inbox.filter.batch", "get_progress", [this.batchId]);
        Object.assign(this.state, data || {});
    }

    async _tick() {
        if (this.busy || !this.batchId || this.state.done || !this.state.exists) {
            return;
        }
        this.busy = true;
        try {
            if (!this.state.wait_seconds || this.state.wait_seconds <= 1) {
                const data = await this.orm.call("inbox.filter.batch", "process_next_item", [this.batchId]);
                Object.assign(this.state, data || {});
            } else {
                await this._load();
            }
        } catch (error) {
            this.state.last_message = error?.message || "Fortschritt konnte kurzzeitig nicht aktualisiert werden.";
            await this._load();
        } finally {
            this.busy = false;
        }
    }

    async refreshNow() {
        await this._load();
        await this._tick();
    }

    openHistory() {
        return this.actionService.doAction("inbox_filter.action_inbox_filter_history");
    }

    openWorkspace() {
        return this.actionService.doAction("inbox_filter.action_inbox_filter_workspace");
    }
}

registry.category("actions").add("inbox_filter.batch_progress", InboxFilterBatchProgress);
