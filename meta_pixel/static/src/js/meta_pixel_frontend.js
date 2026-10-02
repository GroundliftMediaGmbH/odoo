/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const STORAGE_KEY = "gl_meta_pixel_seen_events";
let bootPromise = null;
let paymentGuardInstalled = false;

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
function cookie(name) {
    const needle = `${name}=`;
    for (const chunk of document.cookie.split(";")) {
        const item = chunk.trim();
        if (item.startsWith(needle)) return decodeURIComponent(item.slice(needle.length));
    }
    return null;
}
function browserContext() {
    const url = new URL(window.location.href);
    const fbclid = url.searchParams.get("fbclid");
    let fbc = cookie("_fbc");
    if (!fbc && fbclid) fbc = `fb.1.${Date.now()}.${fbclid}`;
    return {
        fbp: cookie("_fbp"),
        fbc,
        fbclid,
        page_url: window.location.href,
    };
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
async function getCartContexts() {
    const data = await rpc("/meta_pixel/cart_context", browserContext());
    if (!data?.consent) return [];
    return (data.events || []).map((ctx) => ({...ctx, consent: true}));
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
    // Groundlift funnel: the public-events.php overview owns PageView. The Odoo
    // event detail page therefore emits ViewContent only, never an extra PageView.
    if (ctx.events?.ViewContent) await sendBrowserEvent(ctx, "ViewContent");
    store[pageKey] = true;
    writeStore(store);
    return true;
}
async function onCommercePage() {
    const path = window.location.pathname;
    const isGroundliftCheckout = path.startsWith("/groundlift/checkout");
    const isLegacy = path.startsWith("/shop/cart") || path.startsWith("/shop/checkout") || path.startsWith("/shop/payment");
    if (!isGroundliftCheckout && !isLegacy) return;
    const contexts = await getCartContexts();
    const store = readStore();
    for (const ctx of contexts) {
        if (isGroundliftCheckout) {
            // Successful add-to-cart is represented by arriving at our checkout
            // after the server accepted the ticket quantities.
            const addKey = `addtocart:${ctx.event_id}:${ctx.order_id}`;
            if (!store[addKey] && ctx.events?.AddToCart) {
                await sendBrowserEvent(ctx, "AddToCart", ctx.value, ctx.currency);
                store[addKey] = true;
            }
            continue;
        }
        // Preserve legacy Odoo behaviour for other checkout entry points / older
        // custom pixel setups. Groundlift's new flow does not need InitiateCheckout.
        const onceKey = `${path}:${ctx.event_id}:${ctx.order_id || "no_order"}`;
        if (store[onceKey]) continue;
        if (path.startsWith("/shop/cart") && ctx.events?.AddToCart) {
            await sendBrowserEvent(ctx, "AddToCart", ctx.value, ctx.currency);
        } else if (path.startsWith("/shop/checkout") && ctx.events?.InitiateCheckout) {
            await sendBrowserEvent(ctx, "InitiateCheckout", ctx.value, ctx.currency);
        }
        store[onceKey] = true;
    }
    writeStore(store);
}

async function fireAddPaymentInfo() {
    const contexts = await getCartContexts();
    const store = readStore();
    for (const ctx of contexts) {
        const key = `paymentinfo:${ctx.event_id}:${ctx.order_id}`;
        if (store[key] || !ctx.events?.AddPaymentInfo) continue;
        await sendBrowserEvent(ctx, "AddPaymentInfo", ctx.value, ctx.currency);
        store[key] = true;
    }
    writeStore(store);
}

function installPaymentGuard() {
    if (paymentGuardInstalled || !window.location.pathname.startsWith("/groundlift/checkout")) return;
    paymentGuardInstalled = true;
    document.addEventListener("click", async (ev) => {
        const button = ev.target.closest("#o_payment_submit_button, button[name='o_payment_submit_button'], .o_payment_submit_button");
        if (!button || button.dataset.glMetaReleased === "1") return;
        ev.preventDefault();
        ev.stopImmediatePropagation();
        try {
            // Save/validate the Groundlift customer form first.  This endpoint also
            // writes exact first/last name to the sale order for CAPI matching.
            if (window.glGroundliftSaveCustomer) {
                const ok = await window.glGroundliftSaveCustomer();
                if (!ok) return;
            }
            await fireAddPaymentInfo();
            button.dataset.glMetaReleased = "1";
            button.click();
        } catch (error) {
            console.warn("Meta AddPaymentInfo guard error", error);
        }
    }, true);
}

function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
async function onPurchaseConfirmationPage() {
    if (!window.location.pathname.startsWith("/shop/confirmation")) return;
    for (let attempt = 0; attempt < 30; attempt++) {
        const data = await rpc("/meta_pixel/purchase_context", browserContext());
        if (!data?.consent) return;
        if (data?.ready) {
            const store = readStore();
            for (const ctx of (data.events || [])) {
                ctx.consent = true;
                const onceKey = `purchase:${ctx.event_uid}`;
                if (store[onceKey]) continue;
                await sendBrowserEvent(ctx, "Purchase", ctx.value, ctx.currency, { eventUid: ctx.event_uid });
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
            installPaymentGuard();
            await onPurchaseConfirmationPage();
        } catch (error) {
            console.warn("Meta Pixel tracking error", error);
        } finally {
            bootPromise = null;
        }
    })();
    return bootPromise;
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
else boot();
document.addEventListener("optionalCookiesAccepted", boot);
