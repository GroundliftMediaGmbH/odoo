/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { EventRegistrationPopup } from "@pos_event/app/components/popup/event_registration_popup/event_registration_popup";

/**
 * Groundlift / Odoo 19: selectively fast-forward Odoo's existing registration dialog.
 *
 * The standard pos_event ProductScreen remains fully responsible for creating
 * pos.order.line and event.registration records, prices, seat checks, answers,
 * payment, refunds and POS sync. No sale or server-side registration is fabricated.
 *
 * Offline caveat: Odoo's existing POS offline availability rules still apply.
 * This opt-in only removes manual attendee identification from a narrow case.
 */
const IDENTIFICATION_TYPES = new Set(["name", "email", "phone", "company_name"]);

let anonymousSerial = 0;

function anonymousAttendeeName() {
    // No real personal data, no fake e-mail. The event registration itself also
    // receives Odoo's unique barcode once synchronised on the server.
    anonymousSerial += 1;
    const timestamp = Date.now().toString(36).toUpperCase();
    const randomPart = Math.random().toString(36).slice(2, 8).toUpperCase();
    return `Abendkasse ${timestamp}-${randomPart}-${anonymousSerial}`;
}

patch(EventRegistrationPopup.prototype, {
    _glCanSellWithoutAttendeeData() {
        if (this.pos?.config?.gl_anonymous_event_tickets !== true) {
            return false;
        }

        // A customer may have been explicitly chosen for an invoice or for
        // customer tickets: in that case do not silently discard their details.
        const order = this.pos.getOrder();
        if (!order || order.partner_id) {
            return false;
        }

        const questions = this.props.event?.question_ids;
        // Zero questions: native Odoo already auto-confirms these tickets.
        // Any custom question: keep the FULL native dialog and validations.
        return (
            Array.isArray(questions) &&
            questions.length > 0 &&
            questions.every((question) => IDENTIFICATION_TYPES.has(question.question_type))
        );
    },

    setup() {
        super.setup(...arguments);
        if (!this._glCanSellWithoutAttendeeData()) {
            return;
        }

        // Supply a neutral label in place of an actual visitor's name; keep
        // email, phone and company empty. Odoo will write a separate registration
        // and barcode for each ticket, with no CRM customer creation.
        const perTicketName = this.questionsByRegistration.find(
            (question) => question.question_type === "name"
        );
        if (perTicketName) {
            for (const registration of this.state.byRegistration) {
                registration.questions[perTicketName.id] = anonymousAttendeeName();
            }
        }

        const oncePerOrderName = this.questionsOncePerOrder.find(
            (question) => question.question_type === "name"
        );
        if (oncePerOrderName) {
            // For an "ask once" name question Odoo intentionally uses one
            // answer per order. Its generated barcodes remain unique per ticket.
            this.state.byOrder[oncePerOrderName.id] = anonymousAttendeeName();
        }

        // Uses Odoo's OWN standard payload builder. This is safe to invoke
        // in setup: upstream does likewise if an event has no questions.
        this.confirm();
    },

    isQuestionMissingMandatoryAnswer(id, value) {
        if (this._glCanSellWithoutAttendeeData()) {
            const question = this.pos.models["event.question"].get(Number(id));
            if (question && IDENTIFICATION_TYPES.has(question.question_type)) {
                return false;
            }
        }
        return super.isQuestionMissingMandatoryAnswer(id, value);
    },
});
