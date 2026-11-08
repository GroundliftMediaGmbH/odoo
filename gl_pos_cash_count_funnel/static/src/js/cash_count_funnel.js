/** @odoo-module **/
/**
 * Groundlift POS cash-control funnel for Odoo 19.
 * Patches only the native opening/closing popup OWL classes. No POS accounting
 * overrides, no monkey-patching of DOM nodes, and no changes to other modules.
 */
import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

const DENOMS = [
    50000, 20000, 10000, 5000, 2000, 1000, 500,
    200, 100, 50, 20, 10, 5, 2, 1,
].map((cents) => ({ cents, filename: `${cents}.png`, label: (cents / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €" }));

const blankCounts = () => Object.fromEntries(DENOMS.map(({ cents }) => [String(cents), "0"]));
function sumCents(counts) {
    let total = 0;
    for (const item of DENOMS) {
        const value = Number(counts[String(item.cents)] ?? "0");
        if (!Number.isSafeInteger(value) || value < 0 || value > 10000) {
            return null;
        }
        total += item.cents * value;
    }
    return Number.isSafeInteger(total) ? total : null;
}
// One-piece touch adjustment, clamped to the same limits as manual entry and
// server validation. Update the active input too (its DOM value can be "dirty"
// after manual typing and would not necessarily follow a value-attribute patch).
function stepQuantity(quantities, cents, delta, event, update) {
    const current = quantities[String(cents)];
    const parsed = Number(current);
    const safe = Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= 10000 ? parsed : 0;
    const next = String(Math.max(0, Math.min(10000, safe + delta)));
    if (next !== current) {
        update(cents, next);
        const input = event?.currentTarget?.parentElement?.querySelector("input");
        if (input) input.value = next;
    }
}
function errorText(error) {
    return error?.data?.message || error?.message || String(error);
}
function euroValue(env, n) {
    return env.utils.formatCurrency(n);
}

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.glOpening = useState({ quantities: blankCounts(), confirmed: false });
    },
    get glEuroDenoms() { return DENOMS; },
    get glEuroEnabled() { return this.pos.currency?.name === "EUR" && Boolean(this.cashMethodCount); },
    glMoneyFormat(value) { return euroValue(this.env, value); },
    glOpeningCents() { return sumCents(this.glOpening.quantities); },
    glSetOpeningQty(cents, value) {
        this.glOpening.quantities[String(cents)] = value === "" ? "0" : value;
        this.glOpening.confirmed = false;
    },
    glAdjustOpeningQty(cents, delta, event) {
        stepQuantity(this.glOpening.quantities, cents, delta, event,
            (denom, qty) => this.glSetOpeningQty(denom, qty));
    },
    glConfirmOpeningCount() {
        const cents = this.glOpeningCents();
        if (cents === null) {
            this.dialog.add(AlertDialog, {title: "Ungültige Stückzahl", body: "Bitte nur ganze, nichtnegative Stückzahlen bis 10.000 eingeben."});
            return;
        }
        this.state.openingCash = this.env.utils.formatCurrency(cents / 100, false);
        // Keep the denomination record in standard Odoo opening notes.
        const items = DENOMS.filter((d) => Number(this.glOpening.quantities[String(d.cents)]) > 0)
            .map((d) => `${this.glOpening.quantities[String(d.cents)]} × ${d.label}`);
        const prefix = "[Groundlift Kassenbeginn – Stückelzählung]";
        const notes = (this.state.notes || "").split(prefix)[0].trim();
        this.state.notes = `${notes}${notes ? "\n" : ""}${prefix}\n${items.join("; ") || "Leere Kasse (0,00 €)"}\nGesamt: ${euroValue(this.env, cents / 100)}`;
        this.glOpening.confirmed = true;
    },
    async confirm(...args) {
        if (this.glEuroEnabled && !this.glOpening.confirmed) {
            this.dialog.add(AlertDialog, {
                title: "Kassenzählung erforderlich",
                body: "Bitte alle Scheine und Münzen zählen und auf „Zählung übernehmen“ klicken.",
            });
            return;
        }
        return super.confirm(...args);
    },
});

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.glClosing = useState({
            stage: "loading", busy: false, error: "", quantities: blankCounts(),
            recount: blankCounts(), plan: null, finalCents: null,
        });
        onWillStart(async () => {
            if (!this.glEuroEnabled) {
                this.glClosing.stage = "disabled";
                return;
            }
            await this.glRefreshStatus();
        });
    },
    get glEuroDenoms() { return DENOMS; },
    get glEuroEnabled() {
        return this.pos.currency?.name === "EUR" && Boolean(this.pos.config.cash_control) &&
            Boolean(this.props.default_cash_details?.id);
    },
    glMoneyFormat(value) { return euroValue(this.env, value); },
    glClosingCents() { return sumCents(this.glClosing.quantities); },
    glRecountCents() { return sumCents(this.glClosing.recount); },
    glSetClosingQty(cents, value) {
        this.glClosing.quantities[String(cents)] = value === "" ? "0" : value;
        this.glClosing.error = "";
    },
    glSetRecountQty(cents, value) {
        this.glClosing.recount[String(cents)] = value === "" ? "0" : value;
        this.glClosing.finalCents = null;
    },
    glAdjustClosingQty(cents, delta, event) {
        stepQuantity(this.glClosing.quantities, cents, delta, event,
            (denom, qty) => this.glSetClosingQty(denom, qty));
    },
    glAdjustRecountQty(cents, delta, event) {
        stepQuantity(this.glClosing.recount, cents, delta, event,
            (denom, qty) => this.glSetRecountQty(denom, qty));
    },
    async glRefreshStatus() {
        this.glClosing.busy = true;
        this.glClosing.error = "";
        try {
            const status = await this.pos.data.call("pos.session", "gl_cash_helper_status", [this.pos.session.id]);
            if (status.posted) {
                this.glClosing.plan = status.plan;
                await this.glRefreshNativeExpected(status.expected_now);
                this.glClosing.stage = "recount";
            } else {
                this.glClosing.stage = "count";
            }
        } catch (error) {
            this.glClosing.error = "Status der Kassenentnahmen konnte nicht abgefragt werden: " + errorText(error);
            this.glClosing.stage = "error";
        } finally {
            this.glClosing.busy = false;
        }
    },
    async glRefreshNativeExpected(fallback) {
        // Native closing popup props are a snapshot from before cash-out.
        // Refresh them after posting, or Odoo would show a *false* difference.
        if (Number.isFinite(Number(fallback))) {
            this.props.default_cash_details.amount = Number(fallback);
        }
        try {
            const closing = await this.pos.data.call("pos.session", "get_closing_control_data", [this.pos.session.id]);
            if (closing?.default_cash_details?.id === this.props.default_cash_details.id) {
                this.props.default_cash_details.amount = closing.default_cash_details.amount;
                this.props.default_cash_details.moves = closing.default_cash_details.moves;
            }
        } catch (error) {
            console.warn("Groundlift cash helper: expected amount fallback used", error);
        }
    },
    async glComputePreview() {
        if (this.glClosing.busy) return;
        const cents = this.glClosingCents();
        if (cents === null) {
            this.glClosing.error = "Ungültige Stückzahl. Bitte nur ganze Zahlen von 0 bis 10.000 eingeben.";
            return;
        }
        this.glClosing.busy = true;
        this.glClosing.error = "";
        try {
            const synced = await this.pos.syncAllOrders({ throw: true });
            if (synced === false) throw new Error("Bestellungen konnten nicht synchronisiert werden.");
            const response = await this.pos.data.call(
                "pos.session", "gl_cash_helper_preview", [this.pos.session.id, this.glClosing.quantities]
            );
            if (response.already_posted) {
                this.glClosing.plan = response.plan;
                await this.glRefreshNativeExpected(response.expected_now);
                this.glClosing.stage = "recount";
                return;
            }
            this.glClosing.plan = response;
            this.glClosing.stage = "preview";
        } catch (error) {
            this.glClosing.error = "Berechnung nicht möglich: " + errorText(error);
        } finally {
            this.glClosing.busy = false;
        }
    },
    async glPostWithdrawals() {
        if (this.glClosing.busy || this.glClosing.stage !== "preview") return;
        const p = this.glClosing.plan;
        const confirmed = await ask(this.dialog, {
            title: "Barentnahmen verbindlich buchen?",
            body: [
                `Gezählter Bestand vor Entnahme: ${euroValue(this.env, p.counted_before)}`,
                `Tagesüberschuss (nur Bar) – in den Umschlag!: ${euroValue(this.env, p.daily_out)}`,
                `Gesamtes Trinkgeld: ${euroValue(this.env, p.tip_total)}`,
                `Insgesamt BAR entnehmen: ${euroValue(this.env, p.total_out)}`,
                `Trinkgelddefizit auffüllen (sicher unbar): ${euroValue(this.env, p.known_card_shortfall)}`,
                `Danach soll in der Schublade sein: ${euroValue(this.env, p.remaining)}`,
                "Durch die Bestätigung werden die Entnahmen als echte Cash-Out-Vorgänge in Odoo gebucht. Bitte erst danach das Bargeld tatsächlich herausnehmen und erneut zählen.",
            ].join("\n"),
            confirmLabel: "Verbindlich als Cash Out buchen",
            cancelLabel: "Abbrechen",
        });
        if (!confirmed) return;
        this.glClosing.busy = true;
        this.glClosing.error = "";
        try {
            const res = await this.pos.data.call(
                "pos.session", "gl_cash_helper_post", [this.pos.session.id, this.glClosing.quantities, p.signature]
            );
            this.glClosing.plan = res.plan;
            await this.glRefreshNativeExpected(res.expected_now);
            this.glClosing.recount = blankCounts();
            this.glClosing.finalCents = null;
            this.glClosing.stage = "recount";
        } catch (error) {
            // On network loss the server may have posted already! Never retry
            // blindly: force a status read before showing the booking screen.
            this.glClosing.stage = "error";
            this.glClosing.error = "Buchungsstatus unklar: " + errorText(error) + " Bitte Status erneut prüfen; keinesfalls ein zweites Mal auszahlen.";
        } finally {
            this.glClosing.busy = false;
        }
    },
    glConfirmFinalCount() {
        const cents = this.glRecountCents();
        if (cents === null) {
            this.glClosing.error = "Ungültige Stückzahl beim Nachzählen.";
            return;
        }
        this.glClosing.finalCents = cents;
        const amount = cents / 100;
        const cashId = this.props.default_cash_details.id;
        this.state.payments[cashId].counted = this.env.utils.formatCurrency(amount, false);
        // No Odoo cash details note is set here, so native manually entered
        // cash amount is kept. Explain the two counts in the closing note.
        const plan = this.glClosing.plan;
        const prefix = "[Groundlift Kassenabschluss – Entnahmebericht]";
        const existing = (this.state.notes || "").split(prefix)[0].trim();
        const cashNotes = DENOMS.filter((d) => Number(this.glClosing.recount[String(d.cents)]) > 0)
            .map((d) => `${this.glClosing.recount[String(d.cents)]} × ${d.label}`);
        this.state.notes = `${existing}${existing ? "\n" : ""}${prefix}\n` +
            `Vor Entnahmen: ${euroValue(this.env, plan.counted_before)}; ` +
            `Tagesüberschuss (nur Bar; in den Umschlag!): ${euroValue(this.env, plan.daily_out)}; ` +
            `Trinkgeld: ${euroValue(this.env, plan.tip_total)}; ` +
            `Trinkgelddefizit auffüllen (sicher unbar): ${euroValue(this.env, plan.known_card_shortfall)}; ` +
            `Soll nach Entnahme: ${euroValue(this.env, plan.remaining)}; ` +
            `IST nach Entnahme: ${euroValue(this.env, amount)}.\n` +
            `Nachgezählt: ${cashNotes.join("; ") || "Kasse leer"}`;
        this.glClosing.stage = "done";
    },
    glCanClose() {
        if (!this.glEuroEnabled) return true;
        if (this.glClosing.stage !== "done" || this.glClosing.finalCents === null) return false;
        const nativeCount = this.state.payments[this.props.default_cash_details.id]?.counted;
        const parsed = this.env.utils.parseValidFloat(nativeCount || "");
        return Number.isFinite(parsed) && Math.round(parsed * 100) === this.glClosing.finalCents;
    },
    async confirm(...args) {
        if (!this.glCanClose()) {
            this.dialog.add(AlertDialog, {
                title: "Kassenzähl-Helfer noch nicht abgeschlossen",
                body: "Bitte alle Schritte durchführen, Entnahmen buchen und den Bargeldbestand danach erneut zählen und übernehmen.",
            });
            return;
        }
        if (this.glEuroEnabled) {
            try {
                const status = await this.pos.data.call(
                    "pos.session", "gl_cash_helper_status", [this.pos.session.id]
                );
                if (!status.posted) throw new Error("Entnahme wurde serverseitig nicht bestätigt.");
                await this.glRefreshNativeExpected(status.expected_now);
            } catch (error) {
                this.dialog.add(AlertDialog, {
                    title: "Kassenabschluss zur Sicherheit angehalten",
                    body: "Buchungsstatus konnte nicht geprüft werden: " + errorText(error),
                });
                return;
            }
        }
        return super.confirm(...args);
    },
});
