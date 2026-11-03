/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

// 19.0.1.1.0 – The first click is always a PREVIEW. The server is called to
// cancel only after a *separate* explicit confirmation. In the original build,
// frontend cache cleanup / popup reopening could fail after a successful server
// cancellation and leave no reliable indication of the actual outcome.
patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.glDraftCleanupState = useState({ busy: false });
    },

    glDraftAlert(title, body) {
        this.dialog.add(AlertDialog, { title, body });
    },

    async glDeleteDrafts() {
        if (this.glDraftCleanupState.busy) {
            return;
        }
        this.glDraftCleanupState.busy = true;
        let serverHasCanceled = false;

        try {
            const sessionId = this.pos.session.id;
            // Never classify server-side drafts before uploading pending local
            // changes. Never continue when an offline sync explicitly fails.
            const synced = await this.pos.syncAllOrders({ throw: true });
            if (synced === false) {
                throw new Error("Synchronisierung fehlgeschlagen. Bitte Verbindung prüfen und erneut versuchen.");
            }

            const preview = await this.pos.data.call(
                "pos.session", "gl_preview_draft_cleanup", [sessionId]
            );
            if (preview.too_many) {
                this.glDraftAlert(
                    "Drafts löschen – zu viele Einträge",
                    "Mehr als 200 geeignete Drafts vorhanden. Bitte einen POS-Manager hinzuziehen."
                );
                return;
            }

            const ordersModel = this.pos.models["pos.order"];
            const eligible = preview.candidates.filter((item) => {
                const local = ordersModel.find((o) => o.id === item.id);
                // Stale server orders not present locally are okay; orders being
                // edited on THIS device are excluded from the batch.
                return !local || (
                    local.state === "draft" &&
                    !local.isUnsyncedPaid &&
                    !(local.isDirty?.() ?? true) &&
                    !this.pos.pendingOrder?.create?.has(local.id) &&
                    !this.pos.pendingOrder?.write?.has(local.id)
                );
            });
            const protectedLocally = preview.candidates.length - eligible.length;
            if (!eligible.length) {
                this.glDraftAlert(
                    "Keine sicheren Drafts gefunden",
                    `${preview.draft_count} Draft(s) auf dem Server; aktuell keiner sicher stornierbar. ` +
                        `Aktive, geänderte oder junge Bestellungen bleiben geschützt. ` +
                        `Es wurde NICHTS gelöscht.`
                );
                return;
            }

            const refs = eligible.slice(0, 15).map(
                (o) => `${o.reference}: ${o.kind === "empty" ? "leer" : "vollständig gegengebucht"}`
            );
            const more = eligible.length - refs.length;
            const confirmed = await ask(this.dialog, {
                title: "VORSCHAU – noch nichts storniert",
                body: [
                    `Kasse: ${preview.session_name}`,
                    `Zur Stornierung ausgewählt: ${eligible.length}`,
                    ...refs,
                    ...(more ? [`… und ${more} weitere`] : []),
                    `Nicht ausgewählte Drafts: ${preview.skipped_count + protectedLocally}`,
                    "ACHTUNG: Bis jetzt wurde nur geprüft. Erst der folgende Bestätigungsbutton storniert diese Bestellungen auf dem Odoo-Server.",
                    "Vorher sicherstellen, dass niemand diese Aufträge auf einem anderen Gerät bearbeitet.",
                ].join("\n"),
                confirmLabel: "Jetzt verbindlich stornieren",
                cancelLabel: "Nur anzeigen / Abbrechen",
            });
            if (!confirmed) {
                return;
            }

            const result = await this.pos.data.call(
                "pos.session", "gl_cancel_draft_cleanup",
                [sessionId, eligible.map(({ id, version }) => ({ id, version }))],
                { context: { device_identifier: this.pos.device?.identifier || 0 } }
            );
            // The successful RPC guarantees a COMMITTED server transaction
            // (Odoo's HTTP handler commits it on successful completion).
            serverHasCanceled = true;
            const cancelledIds = new Set(result.ids);

            // Best-effort LOCAL cache cleanup. This must NEVER mask a successful
            // server cancellation. It is safe to continue even if this frontend
            // operation cannot run due to a custom POS patch or active device.
            let localRemoved = 0;
            let localCleanupWarning = "";
            try {
                for (const order of ordersModel.filter((o) =>
                    cancelledIds.has(o.id) && o.session_id?.id === sessionId
                )) {
                    if (order.state !== "draft" || order.isUnsyncedPaid || order.isDirty?.()) {
                        continue;
                    }
                    await this.pos.removeOrder(order, false);
                    this.pos.removePendingOrder(order);
                    localRemoved++;
                }
                if (localRemoved) {
                    await this.pos.afterOrderDeletion();
                }
            } catch (cacheError) {
                console.warn("Groundlift draft cleanup: server succeeded, local cache refresh failed", cacheError);
                localCleanupWarning = " Die lokale Anzeige konnte nicht vollständig aktualisiert werden.";
            }

            // NO automatic this.pos.closeSession() and NO props.close(): those
            // could throw/reinitialize a closing popup after the server commit,
            // hiding the success state and making the user believe nothing was
            // canceled. Require the cashier to close normally, separately.
            const remaining = result.remaining_drafts;
            this.glDraftAlert(
                `${result.count} Draft(s) STORNIERT – bestätigt`,
                `${result.count} Bestellungen wurden auf dem Odoo-Server nachweislich auf "cancel" gesetzt. ` +
                    `Noch offene Server-Drafts in ${preview.session_name}: ${remaining}.` +
                    (remaining
                        ? " Diese übrigen Entwürfe wurden bewusst nicht angetastet."
                        : " Damit blockieren keine Server-Drafts dieser Sitzung mehr den Abschluss.") +
                    localCleanupWarning +
                    " Bitte den Kassenschluss-Dialog schließen, ggf. nach vollständiger POS-Synchronisierung erneut öffnen, und die Kasse REGULÄR schließen."
            );
        } catch (error) {
            const message = error?.data?.message || error?.message || String(error);
            this.glDraftAlert(
                serverHasCanceled ? "Server-Bereinigung erfolgt" : "Drafts NICHT storniert",
                serverHasCanceled
                    ? "Die Server-Stornierung war erfolgreich; nur die lokale Verarbeitung schlug fehl: " + message
                    : "Es wurde keine erfolgreiche Stornierung bestätigt: " + message
            );
        } finally {
            this.glDraftCleanupState.busy = false;
        }
    },
});
