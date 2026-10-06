(function () {
    "use strict";

    const app = document.getElementById("gl-ha-device-setup");
    if (!app) return;

    const publicId = app.dataset.publicId || "";
    const setupToken = app.dataset.setupToken || "";
    const button = document.getElementById("gl-ha-device-enroll");
    const statusEl = document.getElementById("gl-ha-device-setup-status");

    function setStatus(message, type) {
        statusEl.textContent = message;
        statusEl.classList.remove("success", "error");
        if (type) statusEl.classList.add(type);
    }

    function openDb() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open("gl_ha_device_keys", 1);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains("keys")) db.createObjectStore("keys");
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error || new Error("Der lokale Geräteschlüsselspeicher konnte nicht geöffnet werden."));
        });
    }

    async function savePrivateKey(key) {
        const db = await openDb();
        try {
            await new Promise((resolve, reject) => {
                const tx = db.transaction("keys", "readwrite");
                tx.objectStore("keys").put(key, publicId);
                tx.oncomplete = () => resolve();
                tx.onerror = () => reject(tx.error || new Error("Der Geräteschlüssel konnte nicht gespeichert werden."));
                tx.onabort = () => reject(tx.error || new Error("Der Geräteschlüssel konnte nicht gespeichert werden."));
            });
        } finally {
            db.close();
        }
    }

    async function createDeviceKey() {
        if (!window.crypto?.subtle || !window.indexedDB) {
            throw new Error("Dieser Browser unterstützt die sichere Gerätebindung nicht. Bitte einen aktuellen Chrome-, Edge- oder Safari-Browser verwenden.");
        }

        // Zum Übertragen des öffentlichen Schlüssels wird das Paar einmal exportierbar
        // erzeugt. Der lokal gespeicherte private Schlüssel wird anschließend erneut
        // als NICHT exportierbarer CryptoKey importiert.
        const generated = await crypto.subtle.generateKey(
            {name: "ECDSA", namedCurve: "P-256"},
            true,
            ["sign", "verify"]
        );
        const publicJwk = await crypto.subtle.exportKey("jwk", generated.publicKey);
        const privateJwk = await crypto.subtle.exportKey("jwk", generated.privateKey);
        const privateKey = await crypto.subtle.importKey(
            "jwk",
            privateJwk,
            {name: "ECDSA", namedCurve: "P-256"},
            false,
            ["sign"]
        );
        return {publicJwk, privateKey};
    }

    async function enroll() {
        button.disabled = true;
        setStatus("Sicherer Geräteschlüssel wird erzeugt …");
        try {
            const {publicJwk, privateKey} = await createDeviceKey();
            await savePrivateKey(privateKey);
            setStatus("Geräteschlüssel gespeichert. Odoo registriert diesen Rechner …");

            const response = await fetch("/groundlift/ha/device/enroll", {
                method: "POST",
                credentials: "same-origin",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    token: setupToken,
                    public_id: publicId,
                    public_jwk: publicJwk,
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Die Gerätebindung konnte nicht abgeschlossen werden.");
            }

            setStatus("Gerät erfolgreich gebunden. Dashboard wird geöffnet …", "success");
            window.setTimeout(() => {
                window.location.replace(payload.redirect_url);
            }, 500);
        } catch (error) {
            console.error(error);
            setStatus(error?.message || "Die Gerätebindung ist fehlgeschlagen.", "error");
            button.disabled = false;
        }
    }

    button.addEventListener("click", enroll);
})();
