/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.glDraftCleanupState = useState({ busy: false });
    },

    async glDeleteDrafts() {
        if (this.glDraftCleanupState.busy) {
            return;
        }
        this.glDraftCleanupState.busy = true;
        try {
            const sessionId = this.pos.session.id;
            // Upload any locally pending updates before deciding which SERVER drafts
            // are stale. If this device is offline, never continue with cleanup.
            await this.pos.syncAllOrders({ throw: true });
            const preview = await this.pos.data.call(
                "pos.session", "gl_preview_draft_cleanup", [sessionId]
            );
            if (preview.too_many) {
                this.dialog.add(AlertDialog, {
                    title: "Drafts löschen",
                    body: "Zu viele Entwürfe für die sichere Bereinigung. Bitte einen POS-Manager kontaktieren.",
                });
                return;
            }
            const candidates = preview.candidates.filter((item) => {
                const local = this.pos.models["pos.order"].find((o) => o.id === item.id);
                return !local || (
                    local.state === "draft" &&
                    !local.isUnsyncedPaid &&
                    !local.isDirty() &&
                    !this.pos.pendingOrder.create.has(local.id) &&
                    !this.pos.pendingOrder.write.has(local.id)
                );
            });
            const locallyProtected = preview.candidates.length - candidates.length;
            if (!candidates.length) {
                this.dialog.add(AlertDialog, {
                    title: "Keine bereinigbaren Drafts",
                    body: `${preview.draft_count} offene Entwürfe gefunden, aber keine sicher bereinigbaren. ` +
                        `Geschützt bleiben aktive Verkäufe, Zahlungen und Aufträge, die in den letzten ` +
                        `${preview.min_age_seconds} Sekunden geändert wurden.`,
                });
                return;
            }

            const refs = candidates.slice(0, 12).map(
                (item) => `${item.reference} (${item.kind === "empty" ? "leer" : "ausgeglichen"})`
            );
            const remaining = candidates.length - refs.length;
            const prompt = [
                `Kasse: ${preview.session_name}`,
                `Sicher stornierbare 0-Euro-Entwürfe: ${candidates.length}`,
                ...refs,
                ...(remaining ? [`... sowie ${remaining} weitere`] : []),
                `Andere, weiterhin offene Entwürfe: ${preview.skipped_count + locallyProtected}.`,
                "Es werden ausschließlich diese Entwürfe STORNIERT (nicht physisch gelöscht).",
                "Bezahlte und reguläre offene Bestellungen bleiben erhalten.",
                "Bitte sicherstellen, dass diese Bestellungen nicht gerade an einer anderen Kasse bearbeitet werden.",
            ].join("\n");

            const confirmed = await ask(this.dialog, {
                title: "Drafts löschen?",
                body: prompt,
                confirmLabel: "Entwürfe stornieren",
                cancelLabel: "Abbrechen",
            });
            if (!confirmed) {
                return;
            }
            const result = await this.pos.data.call(
                "pos.session", "gl_cancel_draft_cleanup",
                [sessionId, candidates.map(({ id, version }) => ({ id, version }))],
                { context: { device_identifier: this.pos.device?.identifier || 0 } }
            );
            const canceledIds = new Set(result.ids);
            let localRemoved = 0;
            // Remove *only* the just-cancelled draft orders from this device's POS cache;
            // otherwise Odoo could sync a stale local draft again on closing.
            for (const order of this.pos.models["pos.order"].filter(
                (order) => canceledIds.has(order.id) && order.session_id?.id === sessionId
            )) {
                if (order.state !== "draft" || order.isUnsyncedPaid || order.isDirty()) {
                    continue;
                }
                await this.pos.removeOrder(order, false);
                this.pos.removePendingOrder(order);
                localRemoved++;
            }
            if (localRemoved) {
                await this.pos.afterOrderDeletion();
            }
            this.pos.notification.add(
                `${result.count} Entwurf/Entwürfe storniert. Die Abschlussansicht wird aktualisiert.`,
                { type: "success" }
            );
            this.props.close();
            await this.pos.closeSession();
        } catch (error) {
            const message = error?.data?.message || error?.message || String(error);
            this.dialog.add(AlertDialog, {
                title: "Drafts konnten nicht bereinigt werden",
                body: message,
            });
        } finally {
            this.glDraftCleanupState.busy = false;
        }
    },
});
