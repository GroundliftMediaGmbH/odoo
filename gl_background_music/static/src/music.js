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
        });
        this.timer = null;
        this.lastErrorMessage = "";
        this.lastErrorAt = 0;
        onMounted(async () => {
            await this.initialize();
            this.timer = setInterval(() => this.refresh(false), 30000);
        });
        onWillUnmount(() => {
            if (this.timer) clearInterval(this.timer);
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
        if (!this.state.connected || this.state.busy) return;
        try {
            const data = await this.orm.call("gl.music.player", "status", []);
            Object.assign(this.state, data);
            this.state.volumeInput = this.state.volume || 0;
            this.state.progressInput = this.state.progress_ms || 0;
        } catch (error) {
            if (showError) this.alert(error);
        }
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
        return `${format(this.state.progress_ms)} / ${format(this.state.duration_ms)}`;
    }
}
registry.category("actions").add("gl_background_music.player", GroundliftMusic);
