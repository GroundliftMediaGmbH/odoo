/** @odoo-module **/
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class GroundliftMusic extends Component {
    static template = "gl_background_music.Player";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            ready: false, busy: false, is_admin: false, connected: false,
            configured: false, agent_online: false, agent_running: false, agent_pc: "", target_name: "", target_available: false,
            active_device: "", target_active: false, playing: false, track: "", artist: "",
            image: "", track_url: "", volume: 40, volumeInput: 40, shuffle: false,
            repeat: "off", progress_ms: 0, duration_ms: 0, progressInput: 0,
            playlists: [], owned: [], devices: [], showOwned: false, showDevices: false,
            playlistName: "", playlistUrl: "", embedUrl: "", currentUrl: "",
            searchQuery: "", searchedQuery: "", searchItems: [], searchNext: null,
            searchLoading: false, searchDone: false,
        });
        this.timer = null;
        this.progressTimer = null;
        this.refreshing = false;
        this.seekDragging = false;
        this.volumeDragging = false;
        this.progressAnchorAt = Date.now();
        this.progressAnchorValue = 0;
        this.lastErrorMessage = "";
        this.lastErrorAt = 0;
        onMounted(async () => {
            await this.initialize();
            this.timer = setInterval(() => this.refresh(false), 30000);
            this.progressTimer = setInterval(() => this.advanceProgress(), 1000);
        });
        onWillUnmount(() => {
            if (this.timer) clearInterval(this.timer);
            if (this.progressTimer) clearInterval(this.progressTimer);
        });
    }

    message(error) {
        return error?.data?.message || error?.data?.arguments?.[0] || error?.message || "Aktion fehlgeschlagen";
    }
    alert(error) {
        const message = this.message(error);
        // Prevent several identical sticky errors obscuring the device selector.
        if (message === this.lastErrorMessage && Date.now() - this.lastErrorAt < 8000) return;
        this.lastErrorMessage = message;
        this.lastErrorAt = Date.now();
        this.notification.add(message, { type: "danger" });
    }
    async initialize() {
        try {
            const data = await this.orm.call("gl.music.player", "bootstrap", []);
            Object.assign(this.state, data);
            this.state.ready = true;
            if (data.connected) await this.refresh(false);
            if (this.state.is_admin && this.state.connected && !this.state.target_available) {
                await this.loadDevices();
            }
        } catch (error) {
            this.state.ready = true;
            this.alert(error);
        }
    }
    async refresh(showError = true) {
        if (!this.state.connected || this.state.busy || this.refreshing) return;
        this.refreshing = true;
        try {
            const data = await this.orm.call("gl.music.player", "status", []);
            // Do not jump the seek thumb back while someone is dragging it.
            const draggedPosition = this.state.progressInput;
            Object.assign(this.state, data);
            if (!this.volumeDragging) this.state.volumeInput = this.state.volume || 0;
            this.state.progressInput = this.seekDragging ? draggedPosition : (this.state.progress_ms || 0);
            this.progressAnchorAt = Date.now();
            this.progressAnchorValue = this.state.progress_ms || 0;
        } catch (error) {
            if (showError) this.alert(error);
        } finally {
            this.refreshing = false;
        }
    }
    advanceProgress() {
        if (!this.state.playing || !this.state.target_active || this.seekDragging || !this.state.duration_ms) return;
        const next = Math.min(this.state.duration_ms,
            this.progressAnchorValue + Math.max(0, Date.now() - this.progressAnchorAt));
        this.state.progress_ms = next;
        this.state.progressInput = next;
    }
    onProgressInput(event) {
        this.seekDragging = true;
        this.state.progressInput = Number(event.target.value);
    }
    async commitSeek() {
        const position = this.state.progressInput;
        await this.run("seek", position);
        this.seekDragging = false;
        await this.refresh(false);
    }
    onVolumeInput(event) {
        this.volumeDragging = true;
        this.state.volumeInput = Number(event.target.value);
    }
    async commitVolume() {
        const volume = this.state.volumeInput;
        await this.run("volume", volume);
        this.volumeDragging = false;
    }
    async run(command, value = null) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            await this.orm.call("gl.music.player", "transport", [command, value]);
            await this.delay(650);
            this.notification.add("Befehl an den Musik-PC gesendet", { type: "success" });
        } catch (error) {
            this.alert(error);
        } finally {
            this.state.busy = false;
        }
        await this.refresh(false);
    }
    delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
    async playPlaylist(url) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            await this.orm.call("gl.music.player", "play_playlist", [url]);
            this.state.currentUrl = url;
            const match = url.match(/(?:playlist\/|spotify:playlist:)([A-Za-z0-9]{22})/);
            this.state.embedUrl = match ? `https://open.spotify.com/embed/playlist/${match[1]}?utm_source=generator` : "";
            this.notification.add("Playlist am Musik-PC gestartet", { type: "success" });
        } catch (error) { this.alert(error); }
        finally { this.state.busy = false; }
        await this.refresh(false);
    }
    async savePlaylist(ev) {
        if (ev) ev.preventDefault();
        if (!this.state.playlistName.trim() || !this.state.playlistUrl.trim()) {
            this.notification.add("Name und Playlist-Link eingeben.", { type: "warning" }); return;
        }
        try {
            await this.orm.create("gl.music.playlist", [{
                name: this.state.playlistName.trim(), url: this.state.playlistUrl.trim(),
            }]);
            this.state.playlistName = ""; this.state.playlistUrl = "";
            const data = await this.orm.call("gl.music.player", "bootstrap", []);
            this.state.playlists = data.playlists;
            this.notification.add("Playlist gespeichert", { type: "success" });
        } catch (error) { this.alert(error); }
    }
    async searchPlaylists(event) {
        if (event) event.preventDefault();
        const query = this.state.searchQuery.trim();
        if (query.length < 2) {
            this.notification.add("Bitte mindestens zwei Zeichen für die Playlist-Suche eingeben.", { type: "warning" });
            return;
        }
        if (this.state.searchLoading) return;
        this.state.searchLoading = true;
        this.state.searchDone = false;
        this.state.searchedQuery = query;
        this.state.searchItems = [];
        this.state.searchNext = null;
        try {
            const result = await this.orm.call("gl.music.player", "search_playlists", [query, 0]);
            this.state.searchItems = result.items;
            this.state.searchNext = result.next_offset;
            this.state.searchDone = true;
        } catch (error) { this.alert(error); }
        finally { this.state.searchLoading = false; }
    }
    async moreSearch() {
        if (this.state.searchLoading || this.state.searchNext == null) return;
        this.state.searchLoading = true;
        const offset = this.state.searchNext;
        try {
            const result = await this.orm.call("gl.music.player", "search_playlists", [this.state.searchedQuery, offset]);
            this.state.searchItems = [...this.state.searchItems, ...result.items];
            this.state.searchNext = result.next_offset;
        } catch (error) { this.alert(error); }
        finally { this.state.searchLoading = false; }
    }
    rememberSearch(item) {
        this.state.playlistName = item.name;
        this.state.playlistUrl = item.url;
        this.notification.add("Name und Link eingetragen. Zum Merken unten 'Playlist speichern' wählen.", { type: "info" });
    }
    openTablet() {
        this.action.doAction({ type: "ir.actions.act_url", url: "/hintergrundmusik", target: "new" });
    }
    async loadOwned() {
        try {
            this.state.owned = await this.orm.call("gl.music.player", "owned_playlists", []);
            this.state.showOwned = true;
        } catch (error) { this.alert(error); }
    }
    async loadDevices() {
        this.state.showDevices = true;
        try {
            this.state.devices = await this.orm.call("gl.music.player", "available_devices", []);
        } catch (error) { this.alert(error); }
    }
    async setTarget(device) {
        if (!device || !device.id || device.restricted) return;
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            const actualName = await this.orm.call("gl.music.player", "set_target", [device.id]);
            this.state.target_name = actualName;
            this.notification.add(`Spotify-Zielgerät festgelegt: ${actualName}`, { type: "success" });
        } catch (error) { this.alert(error); }
        finally { this.state.busy = false; }
        await this.refresh(false);
        await this.loadDevices();
    }
    async startWindows() {
        try {
            await this.orm.call("gl.music.player", "request_windows_start", []);
            this.notification.add("Startsignal an Windows vorgemerkt. Wenn der Wächter läuft, öffnet er Spotify.", { type: "info" });
        } catch (error) { this.alert(error); }
    }
    async connect() {
        try {
            const action = await this.orm.call("gl.music.player", "action_spotify_connect", []);
            await this.action.doAction(action);
        } catch (error) { this.alert(error); }
    }
    openSettings() { this.action.doAction("gl_background_music.music_settings_action"); }
    openPlaylists() { this.action.doAction("gl_background_music.music_playlist_action"); }
    get repeatLabel() {
        return { off: "Wiederholen aus", context: "Playlist wiederholen", track: "Titel wiederholen" }[this.state.repeat] || "Wiederholen aus";
    }
    get timeLabel() {
        const format = (ms) => {
            const seconds = Math.floor((ms || 0) / 1000);
            return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
        };
        return `${format(this.state.progressInput)} / ${format(this.state.duration_ms)}`;
    }
}
registry.category("actions").add("gl_background_music.player", GroundliftMusic);
