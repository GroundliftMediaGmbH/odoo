/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const STORAGE_KEY = "gl_meta_pixel_seen_events";

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
async function sendBrowserEvent(ctx, eventName, value=0, currency="EUR") {
    if (!ctx?.consent || !ctx?.pixel_id) return;
    loadPixel(ctx.pixel_id);
    const eventUid = uid(eventName.toLowerCase(), ctx.event_id);
    const params = {
        content_ids: [`event_${ctx.event_id}`],
        content_type: "product",
        content_name: ctx.event_name,
        value: Number(value || 0),
        currency: currency || "EUR",
    };
    window.fbq("trackSingle", ctx.pixel_id, eventName, params, { eventID: eventUid });
    await rpc("/meta_pixel/log_browser_event", {
        event_id: ctx.event_id,
        event_name: eventName,
        event_uid: eventUid,
        value: params.value,
        currency: params.currency,
        page_url: window.location.href,
    });
}
async function onEventPage() {
    const marker = document.getElementById("gl_meta_pixel_event_context");
    if (!marker) return false;
    const eventId = Number(marker.dataset.eventId);
    const ctx = await rpc("/meta_pixel/event_context", { event_id: eventId });
    if (!ctx?.enabled) return true;
    const store = readStore();
    store[eventId] = { pixel_id: ctx.pixel_id, ts: Date.now() };
    writeStore(store);
    if (ctx.consent) {
        loadPixel(ctx.pixel_id);
        window.fbq("trackSingle", ctx.pixel_id, "PageView");
        if (ctx.events?.ViewContent) await sendBrowserEvent(ctx, "ViewContent");
    }
    return true;
}
async function onCommercePage() {
    const path = window.location.pathname;
    const interesting = path.startsWith("/shop/cart") || path.startsWith("/shop/checkout") || path.startsWith("/shop/payment") || path.startsWith("/payment");
    if (!interesting) return;
    const data = await rpc("/meta_pixel/cart_context", {});
    if (!data?.consent) return;
    for (const ctx of (data.events || [])) {
        ctx.consent = true;
        const onceKey = `${path}:${ctx.event_id}`;
        const store = readStore();
        if (store[onceKey]) continue;
        if (path.startsWith("/shop/cart") && ctx.events?.AddToCart) {
            await sendBrowserEvent(ctx, "AddToCart", ctx.value, ctx.currency);
        } else if (path.startsWith("/shop/checkout") && ctx.events?.InitiateCheckout) {
            await sendBrowserEvent(ctx, "InitiateCheckout", ctx.value, ctx.currency);
        } else if ((path.startsWith("/shop/payment") || path.startsWith("/payment")) && ctx.events?.AddPaymentInfo) {
            await sendBrowserEvent(ctx, "AddPaymentInfo", ctx.value, ctx.currency);
        }
        store[onceKey] = true;
        writeStore(store);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    try {
        await onEventPage();
        await onCommercePage();
    } catch (error) {
        console.warn("Meta Pixel tracking error", error);
    }
});
