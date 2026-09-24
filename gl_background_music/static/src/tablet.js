"use strict";
/* Standalone tablet controller. Only requests the authenticated Odoo endpoint.
 * No Spotify secrets or music are sent to this browser. */
(() => {
    const app = document.getElementById("gl-tablet");
    if (!app) return;
    const csrf = app.dataset.csrf;
    const $ = (id) => document.getElementById(id);
    let state = {playing: false, target_active: false, target_available: false,
                 progress_ms: 0, duration_ms: 0, volume: 0, restore_volume: 0, playlists: []};
    let observedAt = Date.now();
    let seeking = false;
    let busy = false;
    let polling = false;
    let searchBusy = false;
    let searchQuery = "";
    let searchNext = null;
    let searchVersion = 0;
    let searchTimer = null;
    let volumeTimer = null;
    let volumeInFlight = false;
    let volumeWanted = null;
    let volumeLastSentAt = 0;
    let volumeLastSent = null;
    let volumeLocalUntil = 0;
    let fadeTimer = null;
    let fadeGeneration = 0;
    let fadeMode = "";
    let nextFadeSendAt = 0;

    async function api(action, fields = {}) {
        const form = new URLSearchParams({ csrf_token: csrf, action, ...fields });
        const response = await fetch("/hintergrundmusik/api", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
            body: form.toString(), cache: "no-store",
        });
        let payload;
        try { payload = await response.json(); }
        catch (_error) { throw Error("Sitzung abgelaufen oder Server nicht erreichbar. Seite neu laden und in Odoo anmelden."); }
        if (!response.ok || !payload.ok) throw Error(payload.error || "Aktion fehlgeschlagen.");
        return payload.result;
    }
    function banner(message) {
        $("banner").textContent = message || "";
        $("banner").hidden = !message;
    }
    function format(ms) {
        const sec = Math.floor(Math.max(0, ms || 0) / 1000);
        return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    }
    function currentPosition() {
        const elapsed = state.playing && state.target_active ? Date.now() - observedAt : 0;
        return Math.min(state.duration_ms || 0, (state.progress_ms || 0) + elapsed);
    }
    function drawProgress() {
        const ms = seeking ? Number($("position").value) : currentPosition();
        $("position").max = Math.max(1, state.duration_ms || 0);
        if (!seeking) $("position").value = ms;
        $("time").textContent = `${format(ms)} / ${format(state.duration_ms)}`;
    }
    function draw() {
        $("connection").textContent = state.agent_online ? "● Windows verbunden" : "○ Windows offline";
        $("connection").classList.toggle("online", Boolean(state.agent_online));
        const available = Boolean(state.target_available);
        let deviceLabel = state.target_name ? `Musik-PC: ${state.target_name}` : "Kein Spotify-Zielgerät eingerichtet";
        if (state.active_device && !state.target_active) deviceLabel += ` · Spotify ist derzeit auf ${state.active_device} aktiv`;
        if (!available) deviceLabel += " · Bitte Spotify auf dem Musik-PC starten";
        $("device").textContent = deviceLabel;
        $("device").classList.toggle("offline", !available);
        $("title").textContent = state.track || "Keine Wiedergabe";
        $("artist").textContent = state.artist || "Spotify Connect";
        const coverUrl = state.image || "";
        $("cover").hidden = !coverUrl;
        $("cover-placeholder").hidden = Boolean(coverUrl);
        if (coverUrl && $("cover").getAttribute("src") !== coverUrl) $("cover").src = coverUrl;
        $("spotify-link").hidden = !state.track_url;
        if (state.track_url) $("spotify-link").href = state.track_url;
        $("play").textContent = state.playing && state.target_active ? "Ⅱ" : "▶";
        $("shuffle").classList.toggle("active", Boolean(state.shuffle));
        $("repeat").classList.toggle("active", state.repeat !== "off");
        $("repeat").title = {off:"Wiederholen aus",context:"Playlist wiederholen",track:"Titel wiederholen"}[state.repeat] || "Wiederholen";
        for (const id of ["play", "previous", "next", "shuffle", "repeat", "position"])
            $(id).disabled = !available || busy;
        $("position").disabled = !available || busy || !state.duration_ms;
        drawVolume();
        drawProgress();
        document.querySelectorAll("button[data-playlist]").forEach((button) => button.disabled = !available || busy);
    }
    async function refresh() {
        if (busy || polling || document.hidden) return;
        polling = true;
        try {
            const next = await api("status");
            const keepLocalVolume = fadeMode || volumeInFlight || volumeWanted !== null || Date.now() < volumeLocalUntil;
            const localVolume = state.volume;
            state = {...state, ...next};
            if (keepLocalVolume) state.volume = localVolume;
            observedAt = Date.now();
            draw();
            banner("");
        } catch (error) { banner(error.message); }
        finally { polling = false; }
    }
    async function command(action, fields = {}) {
        if (busy) return;
        busy = true; draw();
        try {
            await api(action, fields);
            // Spotify Connect can take a short while to publish a command's new state.
            await new Promise((resolve) => setTimeout(resolve, 550));
            banner("");
        } catch (error) { banner(error.message); }
        finally { busy = false; }
        await refresh(); draw();
    }
    function makeCard(item) {
        const row = document.createElement("div"); row.className = "list-row";
        if (item.image) {
            const image = document.createElement("img");
            image.src = item.image; image.alt = "Playlistcover"; image.loading = "lazy";
            row.appendChild(image);
        }
        const description = document.createElement("div"); description.className = "list-text";
        const name = document.createElement("strong"); name.textContent = item.name || "Playlist";
        description.appendChild(name);
        if (item.owner) {
            const owner = document.createElement("small"); owner.textContent = item.owner;
            description.appendChild(owner);
        }
        row.appendChild(description);
        const button = document.createElement("button"); button.type = "button";
        button.className = "primary"; button.textContent = "▶ Spielen";
        button.dataset.playlist = item.url;
        button.disabled = !state.target_available || busy;
        button.addEventListener("click", () => command("play_playlist", {value: item.url}));
        row.appendChild(button);
        return row;
    }
    function showSaved(items) {
        const container = $("saved"); container.replaceChildren();
        if (!items.length) { const p = document.createElement("p"); p.className="muted";
            p.textContent="Noch keine festen Playlists gespeichert."; container.appendChild(p); return; }
        for (const item of items) container.appendChild(makeCard(item));
    }
    // Live search: debounce API calls, discard responses for older query versions.
    function onSearchInput() {
        if (searchTimer) clearTimeout(searchTimer);
        const query = $("query").value.trim();
        const version = ++searchVersion;
        searchBusy = false;
        searchNext = null;
        $("more").hidden = true;
        $("results").replaceChildren();
        if (query.length < 2) {
            $("search-info").textContent = "Ab zwei Zeichen erscheinen passende Playlists automatisch.";
            return;
        }
        $("search-info").textContent = "Suche startet gleich …";
        searchTimer = setTimeout(() => {
            searchTimer = null;
            void search(false, query, version);
        }, 400);
    }
    async function search(more = false, typedQuery = null, typedVersion = null) {
        if (more && (searchBusy || searchNext == null)) return;
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = null;
        const query = more ? searchQuery : (typedQuery ?? $("query").value.trim());
        if (query.length < 2) {
            $("search-info").textContent = "Bitte mindestens zwei Zeichen eingeben.";
            return;
        }
        const version = more ? searchVersion : (typedVersion ?? ++searchVersion);
        if (!more) {
            searchQuery = query;
            searchNext = null;
            $("results").replaceChildren();
        }
        searchBusy = true;
        $("more").disabled = true;
        $("search-info").textContent = "Passende Spotify-Playlists werden gesucht …";
        try {
            const page = await api("search", {value: query, offset: String(more ? searchNext : 0)});
            if (version !== searchVersion) return;
            for (const item of page.items) $("results").appendChild(makeCard(item));
            searchNext = page.next_offset;
            $("more").hidden = searchNext == null;
            $("search-info").textContent = $("results").children.length
                ? "Playlist antippen, um sie am Musik-PC abzuspielen." : "Keine Playlists gefunden.";
            banner("");
        } catch (error) {
            if (version === searchVersion) {
                $("search-info").textContent = "Suche fehlgeschlagen.";
                banner(error.message);
            }
        } finally {
            if (version === searchVersion) {searchBusy = false; $("more").disabled = false;}
        }
    }
    // Browser drives the short ramp; only the latest value is sent if the network lags.
    function drawVolume() {
        const volume = Math.min(100, Math.max(0, Number(state.volume) || 0));
        $("volume-value").textContent = `${Math.round(volume)}%`;
        $("volume-minus").disabled = !state.target_available || busy || volume <= 0;
        $("volume-plus").disabled = !state.target_available || busy || volume >= 100;
        $("fade-in").disabled = !state.target_available || busy || !state.restore_volume;
        $("fade-out").disabled = !state.target_available || busy || volume <= 0;
        $("fade-status").textContent = fadeMode ? `Fade ${fadeMode === "in" ? "In" : "Out"} läuft …` : "";
    }
    function stopFade() {
        fadeGeneration++;
        if (fadeTimer) clearInterval(fadeTimer);
        fadeTimer = null;
        fadeMode = "";
        drawVolume();
    }
    function setLocalVolume(value, send = true, final = false) {
        const volume = Math.min(100, Math.max(0, Math.round(value)));
        state.volume = volume;
        volumeLocalUntil = Date.now() + 3500;
        drawVolume();
        if (send && state.target_available) {
            volumeWanted = volume;
            scheduleVolume(final);
        }
    }
    function changeVolume(delta) {
        if (!state.target_available || busy) return;
        stopFade();
        setLocalVolume(state.volume + delta, true, true);
    }
    async function startFade(direction) {
        if (!state.target_available || busy) return;
        stopFade();
        const generation = fadeGeneration;
        const from = Math.min(100, Math.max(0, Number(state.volume) || 0));
        let to;
        if (direction === "out") {
            if (from === 0) return;
            fadeMode = "out"; drawVolume();
            try {
                const remembered = await api("remember_fade_volume", {value: String(from)});
                if (generation !== fadeGeneration) return;
                state.restore_volume = remembered;
            } catch (error) {
                if (generation === fadeGeneration) {stopFade(); banner(error.message);}
                return;
            }
            to = 0;
        } else {
            to = Number(state.restore_volume) || 0;
            if (!to) {
                banner("Keine vorherige Lautstärke gespeichert. Erst mit +/- einstellen und Fade Out verwenden.");
                return;
            }
            if (from === to) return;
            fadeMode = "in"; drawVolume();
        }
        const started = Date.now();
        nextFadeSendAt = started;
        const tick = () => {
            if (generation !== fadeGeneration) return;
            const elapsed = Math.min(3000, Math.max(0, Date.now() - started));
            const value = Math.round(from + (to - from) * elapsed / 3000);
            const send = elapsed === 3000 || Date.now() >= nextFadeSendAt;
            setLocalVolume(value, send, elapsed === 3000);
            if (send) nextFadeSendAt = Date.now() + 350;
            if (elapsed === 3000) {
                if (fadeTimer) clearInterval(fadeTimer);
                fadeTimer = null;
                fadeMode = "";
                drawVolume();
            }
        };
        tick();
        fadeTimer = setInterval(tick, 75);
    }
    function scheduleVolume(final = false) {
        if (volumeInFlight || volumeWanted === null) return;
        if (volumeTimer) clearTimeout(volumeTimer);
        const wait = final ? 0 : Math.max(0, 320 - (Date.now() - volumeLastSentAt));
        volumeTimer = setTimeout(() => {
            volumeTimer = null;
            void flushVolume();
        }, wait);
    }
    async function flushVolume() {
        if (volumeInFlight || volumeWanted === null) return;
        const volume = volumeWanted;
        volumeWanted = null;
        if (volume === volumeLastSent && Date.now() - volumeLastSentAt < 800) return;
        volumeInFlight = true;
        volumeLastSentAt = Date.now();
        try {
            await api("transport", {command: "volume", value: JSON.stringify(volume)});
            volumeLastSent = volume;
            volumeLocalUntil = Date.now() + 2500;
            banner("");
        } catch (error) {
            volumeWanted = null; // Do not retry indefinitely on 429/offline.
            volumeLastSent = null;
            stopFade();
            volumeLocalUntil = 0;
            banner(error.message);
            void refresh();
        } finally {
            volumeInFlight = false;
            if (volumeWanted !== null) scheduleVolume();
        }
    }
    async function boot() {
        try {
            const initial = await api("bootstrap");
            state = {...state, ...initial};
            showSaved(initial.playlists || []);
            await refresh();
        } catch (error) { banner(error.message); }
    }
    $("refresh").addEventListener("click", () => refresh());
    $("play").addEventListener("click", () => command("transport", {command: state.playing && state.target_active ? "pause" : "play"}));
    $("next").addEventListener("click", () => command("transport", {command: "next"}));
    $("previous").addEventListener("click", () => command("transport", {command: "previous"}));
    $("shuffle").addEventListener("click", () => command("transport", {command: "shuffle",value:JSON.stringify(!state.shuffle)}));
    $("repeat").addEventListener("click", () => command("transport", {command: "repeat",value:JSON.stringify(state.repeat === "off" ? "context" : state.repeat === "context" ? "track" : "off")}));
    $("open-spotify").addEventListener("click", () => command("windows_start"));
    $("position").addEventListener("input", () => {seeking = true; drawProgress();});
    $("position").addEventListener("change", async () => {
        const ms = Number($("position").value);
        await command("transport", {command: "seek", value: JSON.stringify(ms)});
        seeking = false; drawProgress();
    });
    $("volume-minus").addEventListener("click", () => changeVolume(-5));
    $("volume-plus").addEventListener("click", () => changeVolume(5));
    $("fade-in").addEventListener("click", () => {void startFade("in");});
    $("fade-out").addEventListener("click", () => {void startFade("out");});
    $("query").addEventListener("input", onSearchInput);
    $("search-form").addEventListener("submit", (event) => {event.preventDefault(); void search();});
    $("more").addEventListener("click", () => {void search(true);});
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
    setInterval(drawProgress, 1000);
    setInterval(refresh, 25000);
    boot();
})();
