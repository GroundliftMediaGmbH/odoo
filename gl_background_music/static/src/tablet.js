"use strict";
/* Standalone tablet controller. Only requests the authenticated Odoo endpoint.
 * No Spotify secrets or music are sent to this browser. */
(() => {
    const app = document.getElementById("gl-tablet");
    if (!app) return;
    const csrf = app.dataset.csrf;
    const $ = (id) => document.getElementById(id);
    let state = {playing: false, target_active: false, target_available: false,
                 progress_ms: 0, duration_ms: 0, volume: 0, playlists: []};
    let observedAt = Date.now();
    let seeking = false;
    let changingVolume = false;
    let busy = false;
    let polling = false;
    let searchBusy = false;
    let searchQuery = "";
    let searchNext = null;

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
        for (const id of ["play", "previous", "next", "shuffle", "repeat", "position", "volume"])
            $(id).disabled = !available || busy;
        $("position").disabled = !available || busy || !state.duration_ms;
        if (!changingVolume) $("volume").value = state.volume || 0;
        $("volume-value").textContent = `${$("volume").value}%`;
        drawProgress();
        document.querySelectorAll("button[data-playlist]").forEach((button) => button.disabled = !available || busy);
    }
    async function refresh() {
        if (busy || polling || document.hidden) return;
        polling = true;
        try {
            const next = await api("status");
            state = {...state, ...next};
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
    async function search(more = false) {
        if (searchBusy) return;
        const query = more ? searchQuery : $("query").value.trim();
        if (query.length < 2) { $("search-info").textContent = "Bitte mindestens zwei Zeichen eingeben."; return; }
        if (!more) { searchQuery = query; searchNext = null; $("results").replaceChildren(); }
        searchBusy = true;
        $("search-button").disabled = true; $("more").disabled = true;
        $("search-info").textContent = "Spotify-Playlists werden gesucht …";
        try {
            const page = await api("search", {value: searchQuery, offset: String(more ? searchNext : 0)});
            for (const item of page.items) $("results").appendChild(makeCard(item));
            searchNext = page.next_offset;
            $("more").hidden = searchNext == null;
            $("search-info").textContent = $("results").children.length ? "Playlist antippen, um sie am Musik-PC abzuspielen." : "Keine Playlists gefunden.";
            banner("");
        } catch (error) { $("search-info").textContent = "Suche fehlgeschlagen."; banner(error.message); }
        finally { searchBusy = false; $("search-button").disabled = false; $("more").disabled = false; }
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
    $("volume").addEventListener("input", () => { changingVolume=true; $("volume-value").textContent=`${$("volume").value}%`; });
    $("volume").addEventListener("change", async () => {
        const v = Number($("volume").value);
        await command("transport", {command: "volume",value:JSON.stringify(v)});
        changingVolume = false; draw();
    });
    $("search-form").addEventListener("submit", (event) => {event.preventDefault(); search();});
    $("more").addEventListener("click", () => search(true));
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
    setInterval(drawProgress, 1000);
    setInterval(refresh, 25000);
    boot();
})();
