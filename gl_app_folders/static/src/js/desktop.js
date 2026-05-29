/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const DEFAULT_FOLDER_ICON = "📁";
const DEFAULT_FOLDER_COLOR = "#875A7B";
const APP_MIME = "application/x-odoo-menu-id";

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

    folderPreviewText(folder) {
        const apps = this.folderApps(folder).slice(0, 4).map((app) => app.name);
        if (!apps.length) {
            return _t("Leer");
        }
        return apps.join(", ");
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

    async openApp(app) {
        await this.menu.selectMenu(app);
    }

    openFolderModal(folder) {
        this.state.openFolderId = folder.id;
    }

    closeFolderModal() {
        this.state.openFolderId = null;
    }

    allowDrop(ev) {
        ev.preventDefault();
    }

    dragStartApp(ev, app) {
        this.state.draggingMenuId = Number(app.id);
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData(APP_MIME, String(app.id));
        ev.dataTransfer.setData("text/plain", String(app.id));
    }

    dragEndApp() {
        this.state.draggingMenuId = null;
    }

    getDraggedMenuId(ev) {
        const value = ev.dataTransfer.getData(APP_MIME) || ev.dataTransfer.getData("text/plain") || this.state.draggingMenuId;
        return Number(value || 0);
    }

    async dropOnFolder(ev, folder) {
        ev.preventDefault();
        ev.stopPropagation();
        const menuId = this.getDraggedMenuId(ev);
        if (!menuId) {
            return;
        }
        await this.orm.call("gl.app.folder", "desktop_add_app", [folder.id, menuId]);
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
        const targetName = targetApp.name || _t("Apps");
        const folderName = window.prompt(_t("Name für den neuen Ordner"), targetName);
        if (!folderName) {
            return;
        }
        await this.orm.call("gl.app.folder", "desktop_create_folder", [
            folderName,
            DEFAULT_FOLDER_ICON,
            DEFAULT_FOLDER_COLOR,
            [sourceMenuId, targetMenuId],
        ]);
        await this.loadData();
    }

    async createFolder() {
        const name = window.prompt(_t("Bezeichnung des neuen Ordners"), _t("Neuer Ordner"));
        if (!name) {
            return;
        }
        const icon = window.prompt(_t("Icon für den Ordner, z. B. 📁, 🎬, ⭐"), DEFAULT_FOLDER_ICON) || DEFAULT_FOLDER_ICON;
        await this.orm.call("gl.app.folder", "desktop_create_folder", [name, icon, DEFAULT_FOLDER_COLOR, []]);
        await this.loadData();
    }

    async renameFolder(folder) {
        const name = window.prompt(_t("Neue Bezeichnung"), folder.name || "");
        if (!name) {
            return;
        }
        await this.orm.call("gl.app.folder", "desktop_update_folder", [folder.id, { name }]);
        await this.loadData();
    }

    async changeFolderIcon(folder) {
        const icon = window.prompt(_t("Neues Icon, z. B. 📁, 🎬, ⭐"), folder.icon || DEFAULT_FOLDER_ICON);
        if (!icon) {
            return;
        }
        await this.orm.call("gl.app.folder", "desktop_update_folder", [folder.id, { icon }]);
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
