/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const STORAGE_KEY = "gl_meta_pixel_seen_events";
let bootPromise = null;

function readStore() {
    try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}"); }
    catch { return {}; }
}
function writeStore(data) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch {}
}
function uid(prefix, eventId) {
    return `${prefix}_${eventId}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}
function loadPixel(pixelId) {
    window.glMetaPixels = window.glMetaPixels || {};
    if (window.glMetaPixels[pixelId]) return;
    if (!window.fbq) {
        const fbq = window.fbq = function() {
            fbq.callMethod ? fbq.callMethod.apply(fbq, arguments) : fbq.queue.push(arguments);
        };
        if (!window._fbq) window._fbq = fbq;
        fbq.push = fbq;
        fbq.loaded = true;
        fbq.version = "2.0";
        fbq.queue = [];
        const script = document.createElement("script");
        script.async = true;
        script.src = "https://connect.facebook.net/en_US/fbevents.js";
        document.head.appendChild(script);
    }
    window.fbq("init", pixelId);
    window.glMetaPixels[pixelId] = true;
}
async function sendBrowserEvent(ctx, eventName, value=0, currency="EUR", options={}) {
    if (!ctx?.consent || !ctx?.pixel_id) return false;
    loadPixel(ctx.pixel_id);
    const eventUid = options.eventUid || ctx.event_uid || uid(eventName.toLowerCase(), ctx.event_id);
    const params = eventName === "PageView" ? {} : {
        content_ids: [`event_${ctx.event_id}`],
        content_type: "product",
        content_name: ctx.event_name,
        value: Number(value || 0),
        currency: currency || "EUR",
    };
    window.fbq("trackSingle", ctx.pixel_id, eventName, params, { eventID: eventUid });

    // Internal reporting is best-effort only. The request is intentionally NOT
    // awaited, so a reporting failure can never block or roll back Odoo checkout.
    rpc("/meta_pixel/log_browser_event", {
        event_id: ctx.event_id,
        event_name: eventName,
        event_uid: eventUid,
        value: Number(value || 0),
        currency: currency || "EUR",
        page_url: window.location.href,
        sale_order_id: ctx.order_id || null,
    }).catch((error) => console.warn("Meta Pixel reporting log error", error));
    return true;
}
async function onEventPage() {
    const marker = document.getElementById("gl_meta_pixel_event_context");
    if (!marker) return false;
    const eventId = Number(marker.dataset.eventId);
    if (!eventId) return true;

    const ctx = await rpc("/meta_pixel/event_context", { event_id: eventId });
    if (!ctx?.enabled) return true;

    const store = readStore();
    store[eventId] = { pixel_id: ctx.pixel_id, ts: Date.now() };
    writeStore(store);

    if (!ctx.consent) return true;

    const pageKey = `eventpage:${eventId}:${window.location.pathname}`;
    if (store[pageKey]) return true;

    loadPixel(ctx.pixel_id);
    await sendBrowserEvent(ctx, "PageView");
    if (ctx.events?.ViewContent) {
        await sendBrowserEvent(ctx, "ViewContent");
    }
    store[pageKey] = true;
    writeStore(store);
    return true;
}
async function onCommercePage() {
    const path = window.location.pathname;
    // Do NOT run on generic /payment/* routes. Those include Odoo payment status,
    // polling and provider return pages. Tracking must never touch those routes.
    const interesting = path.startsWith("/shop/cart") || path.startsWith("/shop/checkout") || path.startsWith("/shop/payment");
    if (!interesting) return;
    const data = await rpc("/meta_pixel/cart_context", {});
    if (!data?.consent) return;
    for (const ctx of (data.events || [])) {
        ctx.consent = true;
        // Scope de-duplication to the current sale order. A second purchase of the
        // same event in the same browser session must generate fresh funnel events.
        const onceKey = `${path}:${ctx.event_id}:${ctx.order_id || "no_order"}`;
        const store = readStore();
        if (store[onceKey]) continue;
        if (path.startsWith("/shop/cart") && ctx.events?.AddToCart) {
            await sendBrowserEvent(ctx, "AddToCart", ctx.value, ctx.currency);
        } else if (path.startsWith("/shop/checkout") && ctx.events?.InitiateCheckout) {
            await sendBrowserEvent(ctx, "InitiateCheckout", ctx.value, ctx.currency);
        } else if (path.startsWith("/shop/payment") && ctx.events?.AddPaymentInfo) {
            await sendBrowserEvent(ctx, "AddPaymentInfo", ctx.value, ctx.currency);
        }
        store[onceKey] = true;
        writeStore(store);
    }
}

function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function onPurchaseConfirmationPage() {
    const path = window.location.pathname;
    if (!path.startsWith("/shop/confirmation")) return;

    // Some payment providers return the customer before the final transaction state
    // has reached Odoo. Poll read-only for a short period so browser-only Purchase
    // still has a chance to fire once Odoo marks the payment done/authorized.
    for (let attempt = 0; attempt < 30; attempt++) {
        const data = await rpc("/meta_pixel/purchase_context", {});
        if (!data?.consent) return;
        if (data?.ready) {
            const store = readStore();
            for (const ctx of (data.events || [])) {
                ctx.consent = true;
                const onceKey = `purchase:${ctx.event_uid}`;
                if (store[onceKey]) continue;
                await sendBrowserEvent(
                    ctx,
                    "Purchase",
                    ctx.value,
                    ctx.currency,
                    { eventUid: ctx.event_uid },
                );
                store[onceKey] = true;
            }
            writeStore(store);
            return;
        }
        if (!data?.pending) return;
        await delay(1500);
    }
}

async function boot() {
    if (bootPromise) return bootPromise;
    bootPromise = (async () => {
        try {
            await onEventPage();
            await onCommercePage();
            await onPurchaseConfirmationPage();
        } catch (error) {
            console.warn("Meta Pixel tracking error", error);
        } finally {
            bootPromise = null;
        }
    })();
    return bootPromise;
}

// Odoo 19 loads frontend assets lazily. If this module is evaluated after
// DOMContentLoaded, registering only a DOMContentLoaded handler means the
// tracking bootstrap would never run. Start immediately when the DOM is ready.
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
    boot();
}

// Odoo emits this event when the visitor accepts optional cookies. This makes
// the pixel start immediately after consent instead of requiring a page reload.
document.addEventListener("optionalCookiesAccepted", boot);
