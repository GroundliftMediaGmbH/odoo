/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const DEFAULT_FOLDER_ICON = "📁";
const DEFAULT_FOLDER_COLOR = "#875A7B";
const APP_MIME = "application/x-odoo-menu-id";
const FOLDER_MIME = "application/x-odoo-folder-id";
const COLOR_PRESETS = [
    "#875A7B", "#A855F7", "#6366F1", "#3B82F6", "#06B6D4",
    "#14B8A6", "#22C55E", "#84CC16", "#F59E0B", "#F97316",
    "#EF4444", "#EC4899", "#64748B", "#334155",
];

const DESKTOP_APP_XMLID = "gl_app_folders.menu_gl_app_folders_desktop";
const TOP_LEFT_HOME_SELECTORS = [
    ".o_main_navbar .o_navbar_apps_menu",
    ".o_main_navbar .o_menu_toggle",
    ".o_main_navbar .o_app_menu_toggle",
    ".o_main_navbar [title='Platzhalter']",
    ".o_main_navbar [aria-label='Platzhalter']",
    ".o_main_navbar [data-tooltip='Platzhalter']",
    "[title='Platzhalter']",
    "[aria-label='Platzhalter']",
].join(", ");

function findDesktopApp(menuService) {
    const apps = typeof menuService.getApps === "function" ? menuService.getApps() : [];
    return apps.find((app) => app.xmlid === DESKTOP_APP_XMLID || app.name === "Mein Desktop") || null;
}

function getTopLeftHomeTarget(target) {
    if (!(target instanceof Element)) {
        return null;
    }
    const element = target.closest(TOP_LEFT_HOME_SELECTORS);
    if (!element) {
        return null;
    }
    const rect = element.getBoundingClientRect();
    // Sicherheitsbegrenzung: Nur der echte linke obere Odoo-Home-/App-Button wird umgeleitet.
    if (rect.top > 88 || rect.left > 160) {
        return null;
    }
    return element;
}

registry.category("services").add("gl_app_folders.top_left_home_redirect", {
    dependencies: ["menu"],
    start(env, { menu }) {
        const onClick = async (ev) => {
            const target = getTopLeftHomeTarget(ev.target);
            if (!target) {
                return;
            }

            // In "Mein Desktop" selbst soll Odoo den Klick normal behandeln,
            // damit man zurück in die Standard-Odoo-App-Übersicht kommt.
            if (document.querySelector(".gl_app_desktop")) {
                return;
            }

            const desktopApp = findDesktopApp(menu);
            if (!desktopApp) {
                return;
            }

            ev.preventDefault();
            ev.stopPropagation();
            if (typeof ev.stopImmediatePropagation === "function") {
                ev.stopImmediatePropagation();
            }

            try {
                await menu.selectMenu(desktopApp);
            } catch (error) {
                console.error("Groundlift Desktop konnte nicht geöffnet werden.", error);
            }
        };

        document.addEventListener("click", onClick, true);
        return {
            stop() {
                document.removeEventListener("click", onClick, true);
            },
        };
    },
});


export class GlAppFoldersDesktop extends Component {
    static template = "gl_app_folders.Desktop";

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.state = useState({
            folders: [],
            search: "",
            openFolderId: null,
            draggingMenuId: null,
            draggingFolderId: null,
            editorOpen: false,
            editorMode: "create",
            editorFolderId: null,
            editorName: "",
            editorColor: DEFAULT_FOLDER_COLOR,
            editorAppMenuIds: [],
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        const data = await this.orm.call("gl.app.folder", "desktop_get_data", []);
        this.state.folders = data.folders || [];
    }

    get allApps() {
        return this.menu
            .getApps()
            .filter((app) => !this.isSelfDesktopApp(app))
            .map((app) => ({ ...app, id: Number(app.id) }));
    }

    get appsById() {
        const map = new Map();
        for (const app of this.allApps) {
            map.set(Number(app.id), app);
        }
        return map;
    }

    get assignedAppIds() {
        const ids = new Set();
        for (const folder of this.state.folders) {
            for (const menuId of folder.app_menu_ids || []) {
                ids.add(Number(menuId));
            }
        }
        return ids;
    }

    get rootApps() {
        const assigned = this.assignedAppIds;
        return this.filterApps(this.allApps.filter((app) => !assigned.has(Number(app.id))));
    }

    get visibleFolders() {
        const query = this.normalizedSearch();
        if (!query) {
            return this.state.folders;
        }
        return this.state.folders.filter((folder) => {
            if ((folder.name || "").toLowerCase().includes(query)) {
                return true;
            }
            return this.folderApps(folder).some((app) => (app.name || "").toLowerCase().includes(query));
        });
    }

    get openFolder() {
        return this.state.folders.find((folder) => folder.id === this.state.openFolderId) || null;
    }

    get colorPresets() {
        return COLOR_PRESETS;
    }

    get isEditingFolder() {
        return this.state.editorMode === "edit";
    }

    hasDesktopItems() {
        return this.visibleFolders.length || this.rootApps.length;
    }

    isSelfDesktopApp(app) {
        return app.xmlid === "gl_app_folders.menu_gl_app_folders_desktop" || app.name === "Mein Desktop";
    }

    normalizedSearch() {
        return (this.state.search || "").trim().toLowerCase();
    }

    filterApps(apps) {
        const query = this.normalizedSearch();
        if (!query) {
            return apps;
        }
        return apps.filter((app) => (app.name || "").toLowerCase().includes(query));
    }

    folderApps(folder) {
        const appsById = this.appsById;
        return (folder.app_menu_ids || [])
            .map((menuId) => appsById.get(Number(menuId)))
            .filter(Boolean);
    }

    orbitApps(folder) {
        return this.folderApps(folder).slice(0, 8);
    }

    folderPreviewApps(folder) {
        return this.folderApps(folder).slice(0, 4);
    }

    folderPreviewText(folder) {
        const apps = this.folderApps(folder).slice(0, 8).map((app) => app.name);
        if (!apps.length) {
            return _t("Leer");
        }
        return apps.join(", ");
    }

    orbitItemStyle(app, index, total) {
        const radius = total <= 4 ? 88 : total <= 6 ? 96 : 104;
        const angle = -90 + (360 / Math.max(total, 1)) * index;
        const radians = (angle * Math.PI) / 180;
        const x = Math.round(Math.cos(radians) * radius);
        const y = Math.round(Math.sin(radians) * radius);
        return `${this.appIconStyle(app)} --gl-orbit-x:${x}px; --gl-orbit-y:${y}px;`;
    }

    folderStyle(folder) {
        return `--gl-folder-color: ${folder.color || DEFAULT_FOLDER_COLOR};`;
    }

    appIconStyle(app) {
        if (app.webIconData) {
            const data = String(app.webIconData);
            const src = data.startsWith("data:") ? data : `data:image/png;base64,${data}`;
            return `background-image: url("${src}");`;
        }
        const parsed = this.parseWebIcon(app);
        if (parsed.background || parsed.color) {
            return `background-color: ${parsed.background || "#875A7B"}; color: ${parsed.color || "#FFFFFF"};`;
        }
        return "";
    }

    appIconClass(app) {
        return this.parseWebIcon(app).className || "fa fa-cube";
    }

    hasAppIconImage(app) {
        return Boolean(app.webIconData);
    }

    appIconContainerClass(baseClass, app) {
        const suffix = this.hasAppIconImage(app) ? "image" : "placeholder";
        return `${baseClass} ${baseClass}--${suffix}`;
    }

    parseWebIcon(app) {
        const result = { className: "fa fa-cube", color: "#FFFFFF", background: "#875A7B" };
        if (!app.webIcon || app.webIconData) {
            return result;
        }
        const parts = String(app.webIcon).split(",").map((part) => part.trim());
        if (parts[0] && (parts[0].startsWith("fa") || parts[0].includes(" fa-"))) {
            result.className = parts[0].startsWith("fa ") ? parts[0] : `fa ${parts[0]}`;
            result.color = parts[1] || result.color;
            result.background = parts[2] || result.background;
        }
        return result;
    }

    updateSearch(ev) {
        this.state.search = ev.target.value;
    }

    updateEditorName(ev) {
        this.state.editorName = ev.target.value;
    }

    updateEditorColor(ev) {
        this.state.editorColor = ev.target.value;
    }

    chooseEditorColor(color) {
        this.state.editorColor = color;
    }

    async openApp(app) {
        await this.menu.selectMenu(app);
    }

    async openOrbitApp(ev, app) {
        ev.preventDefault();
        ev.stopPropagation();
        await this.openApp(app);
    }

    openFolderModal(folder) {
        this.state.openFolderId = folder.id;
    }

    closeFolderModal() {
        this.state.openFolderId = null;
    }

    openCreateFolderModal(appMenuIds = [], suggestedName = "") {
        this.state.editorOpen = true;
        this.state.editorMode = "create";
        this.state.editorFolderId = null;
        this.state.editorName = suggestedName || _t("Neuer Ordner");
        this.state.editorColor = DEFAULT_FOLDER_COLOR;
        this.state.editorAppMenuIds = [...appMenuIds];
    }

    openEditFolderModal(folder) {
        this.state.editorOpen = true;
        this.state.editorMode = "edit";
        this.state.editorFolderId = folder.id;
        this.state.editorName = folder.name || "";
        this.state.editorColor = folder.color || DEFAULT_FOLDER_COLOR;
        this.state.editorAppMenuIds = [];
    }

    closeEditorModal() {
        this.state.editorOpen = false;
        this.state.editorFolderId = null;
        this.state.editorName = "";
        this.state.editorColor = DEFAULT_FOLDER_COLOR;
        this.state.editorAppMenuIds = [];
    }

    allowDrop(ev) {
        ev.preventDefault();
    }

    dragStartApp(ev, app) {
        this.state.draggingMenuId = Number(app.id);
        this.state.draggingFolderId = null;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData(APP_MIME, String(app.id));
        ev.dataTransfer.setData("text/plain", String(app.id));
    }

    dragEndApp() {
        this.state.draggingMenuId = null;
    }

    dragStartFolder(ev, folder) {
        this.state.draggingFolderId = Number(folder.id);
        this.state.draggingMenuId = null;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData(FOLDER_MIME, String(folder.id));
        ev.dataTransfer.setData("text/plain", `folder:${folder.id}`);
    }

    dragEndFolder() {
        this.state.draggingFolderId = null;
    }

    getDraggedMenuId(ev) {
        const value = ev.dataTransfer.getData(APP_MIME) || this.state.draggingMenuId;
        return Number(value || 0);
    }

    getDraggedFolderId(ev) {
        const value = ev.dataTransfer.getData(FOLDER_MIME) || this.state.draggingFolderId;
        return Number(value || 0);
    }

    async dropOnFolder(ev, folder) {
        ev.preventDefault();
        ev.stopPropagation();

        const sourceFolderId = this.getDraggedFolderId(ev);
        if (sourceFolderId && sourceFolderId !== Number(folder.id)) {
            await this.resequenceFolders(sourceFolderId, Number(folder.id));
            return;
        }

        const menuId = this.getDraggedMenuId(ev);
        if (!menuId) {
            return;
        }
        await this.orm.call("gl.app.folder", "desktop_add_app", [folder.id, menuId]);
        await this.loadData();
    }

    async resequenceFolders(sourceFolderId, targetFolderId) {
        const folderIds = this.state.folders.map((folder) => Number(folder.id));
        const sourceIndex = folderIds.indexOf(Number(sourceFolderId));
        const targetIndex = folderIds.indexOf(Number(targetFolderId));
        if (sourceIndex === -1 || targetIndex === -1 || sourceIndex === targetIndex) {
            return;
        }
        folderIds.splice(sourceIndex, 1);
        const insertIndex = folderIds.indexOf(Number(targetFolderId));
        folderIds.splice(insertIndex, 0, Number(sourceFolderId));
        await this.orm.call("gl.app.folder", "desktop_resequence", [folderIds]);
        await this.loadData();
    }

    async dropOnApp(ev, targetApp) {
        ev.preventDefault();
        ev.stopPropagation();
        const sourceMenuId = this.getDraggedMenuId(ev);
        const targetMenuId = Number(targetApp.id);
        if (!sourceMenuId || sourceMenuId === targetMenuId) {
            return;
        }
        const targetName = targetApp.name || _t("Neuer Ordner");
        this.openCreateFolderModal([sourceMenuId, targetMenuId], targetName);
    }

    createFolder() {
        this.openCreateFolderModal([]);
    }

    async saveFolderEditor() {
        const name = (this.state.editorName || "").trim();
        if (!name) {
            this.notification.add(_t("Bitte gib eine Bezeichnung für den Ordner ein."), { type: "warning" });
            return;
        }
        if (this.state.editorMode === "edit") {
            await this.orm.call("gl.app.folder", "desktop_update_folder", [
                this.state.editorFolderId,
                {
                    name,
                    color: this.state.editorColor || DEFAULT_FOLDER_COLOR,
                },
            ]);
        } else {
            await this.orm.call("gl.app.folder", "desktop_create_folder", [
                name,
                DEFAULT_FOLDER_ICON,
                this.state.editorColor || DEFAULT_FOLDER_COLOR,
                this.state.editorAppMenuIds || [],
            ]);
        }
        this.closeEditorModal();
        await this.loadData();
    }

    async deleteFolder(folder) {
        const confirmed = window.confirm(
            _t("Ordner löschen? Die Apps werden dadurch nicht gelöscht, sondern erscheinen wieder auf dem Desktop.")
        );
        if (!confirmed) {
            return;
        }
        await this.orm.call("gl.app.folder", "desktop_delete_folder", [folder.id]);
        this.closeFolderModal();
        await this.loadData();
    }

    async removeAppFromFolder(ev, folder, app) {
        ev.stopPropagation();
        await this.orm.call("gl.app.folder", "desktop_remove_app", [folder.id, Number(app.id)]);
        await this.loadData();
    }

    async setAsHome() {
        await this.orm.call("gl.app.folder", "desktop_set_as_home", []);
        this.notification.add(_t("Dieser Desktop ist jetzt deine persönliche Odoo-Startseite."), {
            type: "success",
        });
    }
}

registry.category("actions").add("gl_app_folders.desktop", GlAppFoldersDesktop);
