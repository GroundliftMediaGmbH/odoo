/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

let saving = null;

function errorBox(message) {
    const box = document.getElementById("gl_customer_error");
    if (!box) return;
    if (message) {
        box.textContent = message;
        box.classList.remove("d-none");
        box.scrollIntoView({behavior: "smooth", block: "center"});
    } else {
        box.textContent = "";
        box.classList.add("d-none");
    }
}

async function saveCustomer() {
    if (saving) return saving;
    saving = (async () => {
        const form = document.getElementById("gl_customer_form");
        if (!form) return true;
        errorBox("");
        if (!form.reportValidity()) return false;
        const values = Object.fromEntries(new FormData(form).entries());
        try {
            const result = await rpc("/groundlift/checkout/customer", values);
            if (!result?.ok) {
                errorBox(result?.error || "Die persönlichen Daten konnten nicht gespeichert werden.");
                return false;
            }
            document.documentElement.dataset.glCustomerSaved = "1";
            return true;
        } catch (error) {
            console.warn("Groundlift customer save failed", error);
            errorBox("Die persönlichen Daten konnten nicht gespeichert werden. Bitte versuche es erneut.");
            return false;
        } finally {
            saving = null;
        }
    })();
    return saving;
}

window.glGroundliftSaveCustomer = saveCustomer;

function boot() {
    if (!document.querySelector("[data-gl-groundlift-checkout='1']")) return;

    // Always persist customer data before Odoo's payment interaction creates a transaction.
    document.addEventListener("click", async (ev) => {
        const button = ev.target.closest("#o_payment_submit_button, button[name='o_payment_submit_button'], .o_payment_submit_button");
        if (!button || button.dataset.glCustomerReleased === "1") return;
        ev.preventDefault();
        ev.stopImmediatePropagation();
        const ok = await saveCustomer();
        if (!ok) return;
        button.dataset.glCustomerReleased = "1";
        button.click();
    }, true);

    const freeForm = document.getElementById("gl_free_confirm_form");
    if (freeForm) {
        freeForm.addEventListener("submit", async (ev) => {
            if (freeForm.dataset.glReleased === "1") return;
            ev.preventDefault();
            const ok = await saveCustomer();
            if (!ok) return;
            freeForm.dataset.glReleased = "1";
            freeForm.submit();
        });
    }
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
else boot();
