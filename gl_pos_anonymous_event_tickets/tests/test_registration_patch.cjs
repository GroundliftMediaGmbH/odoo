// Node-only regression harness for the isolated Groundlift patch.
// Run: node tests/test_registration_patch.cjs
// This is NOT a substitute for Odoo staging integration tests.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class EventRegistrationPopup {
    setup() {
        this.pos = this.fixturePos;
        this.props = this.fixtureProps;
        this.questionsByRegistration = this.props.event.question_ids.filter((q) => !q.once_per_order);
        this.questionsOncePerOrder = this.props.event.question_ids.filter((q) => q.once_per_order);
        this.state = { byRegistration: [], byOrder: {} };
        for (const data of this.props.data) {
            for (let i = 0; i < data.qty; i++) {
                const answers = {};
                for (const question of this.questionsByRegistration) answers[question.id] = "";
                this.state.byRegistration.push({ ticket_id: data.ticket_id, questions: answers });
            }
        }
        for (const question of this.questionsOncePerOrder) this.state.byOrder[question.id] = "";
        if (this.props.event.question_ids.length === 0) this.confirm();
    }
    isQuestionMissingMandatoryAnswer(id, value) {
        const question = this.pos.models["event.question"].get(Number(id));
        return Boolean(question && question.is_mandatory_answer && !value);
    }
    confirm() {
        for (const item of this.state.byRegistration) {
            for (const [id, value] of Object.entries(item.questions)) {
                if (this.isQuestionMissingMandatoryAnswer(id, value)) return;
            }
        }
        for (const [id, value] of Object.entries(this.state.byOrder)) {
            if (this.isQuestionMissingMandatoryAnswer(id, value)) return;
        }
        const byRegistration = {};
        for (const item of this.state.byRegistration) {
            (byRegistration[item.ticket_id.id] ||= []).push(item.questions);
        }
        this.props.getPayload({ byRegistration, byOrder: this.state.byOrder });
        this.props.close();
    }
}

const original = { ...Object.getOwnPropertyDescriptors(EventRegistrationPopup.prototype) };
const superMethods = Object.create(Object.getPrototypeOf(EventRegistrationPopup.prototype));
Object.defineProperties(superMethods, original);
const patch = (prototype, extension) => {
    Object.setPrototypeOf(extension, superMethods);
    Object.defineProperties(prototype, Object.getOwnPropertyDescriptors(extension));
};
const file = path.join(__dirname, "../static/src/js/anonymous_event_registration.js");
const source = fs.readFileSync(file, "utf8").replace(/^import .*;\s*$/gm, "");
vm.runInNewContext(source, { patch, EventRegistrationPopup, Set, Date, Math });

function run({ enabled = true, partner = false, questions = [], qty = 2 }) {
    let payload = null;
    let closes = 0;
    const pos = {
        config: { gl_anonymous_event_tickets: enabled },
        getOrder: () => ({ partner_id: partner }),
        models: { "event.question": { get: (id) => questions.find((q) => q.id === id) } },
    };
    const popup = new EventRegistrationPopup();
    popup.fixturePos = pos;
    popup.fixtureProps = {
        event: { question_ids: questions },
        data: [{ ticket_id: { id: 101 }, qty }],
        getPayload: (data) => { payload = data; },
        close: () => { closes++; },
    };
    popup.setup();
    return { payload, closes, popup };
}

const q = (id, type, once = false, mandatory = true) => ({
    id, question_type: type, once_per_order: once, is_mandatory_answer: mandatory,
});

// Given the specific Groundlift event example: no typing, 2 separate attendees,
// pseudonymous names, and critically NO invented email answers.
let test = run({ questions: [q(1, "name"), q(2, "email"), q(3, "phone", false, false)] });
assert.equal(test.closes, 1);
assert.equal(test.payload.byRegistration[101].length, 2);
assert.match(test.payload.byRegistration[101][0][1], /^Abendkasse /);
assert.notEqual(test.payload.byRegistration[101][0][1], test.payload.byRegistration[101][1][1]);
assert.equal(test.payload.byRegistration[101][0][2], "");
assert.equal(test.payload.byRegistration[101][0][3], "");

// Fail closed for non-identification questions; no bypass of legal/custom questions.
test = run({ questions: [q(1, "name"), q(2, "email"), q(4, "text_box")] });
assert.equal(test.closes, 0);
assert.equal(test.payload, null);

// For regular checkout and POS invoices with selected customer, stock dialog stays.
test = run({ enabled: false, questions: [q(1, "name"), q(2, "email")] });
assert.equal(test.closes, 0);
test = run({ partner: { id: 300 }, questions: [q(1, "name"), q(2, "email")] });
assert.equal(test.closes, 0);

// "Ask once per order" is also handled and still has 2 separate registrations.
test = run({ questions: [q(1, "name", true), q(2, "email", true)] });
assert.equal(test.closes, 1);
assert.equal(test.payload.byRegistration[101].length, 2);
assert.match(test.payload.byOrder[1], /^Abendkasse /);
assert.equal(test.payload.byOrder[2], "");

// Native Odoo behavior with no event questions: auto-confirm normally.
test = run({ questions: [] });
assert.equal(test.closes, 1);

console.log("6 mock POS popup regression scenarios passed.");
