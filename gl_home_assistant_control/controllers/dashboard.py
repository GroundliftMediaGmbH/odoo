# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class GlHaDashboardController(http.Controller):

    def _check_view(self):
        if not request.env.user.has_group("gl_home_assistant_control.group_ha_viewer"):
            raise AccessError(_("Keine Berechtigung für das Home-Assistant-Dashboard."))

    def _get_dashboard(self, slug=None):
        Dashboard = request.env["gl.ha.dashboard"].sudo()
        if slug:
            dashboard = Dashboard.search([("slug", "=", slug), ("active", "=", True)], limit=1)
        else:
            dashboard = Dashboard.search([("active", "=", True)], order="sequence, id", limit=1)
        return dashboard

    def _get_page(self, dashboard, page_slug=None):
        if not dashboard or not page_slug:
            return request.env["gl.ha.dashboard.page"].sudo().browse([])
        return request.env["gl.ha.dashboard.page"].sudo().search([
            ("dashboard_id", "=", dashboard.id),
            ("slug", "=", page_slug),
            ("active", "=", True),
        ], limit=1)

    def _selected_entities(self, dashboard, page=None):
        Entity = request.env["gl.ha.entity"].sudo()
        if page:
            return page.entity_ids.filtered(lambda e: e.active)
        if dashboard.entity_ids:
            return dashboard.entity_ids.filtered(lambda e: e.active)
        if dashboard.include_default_entities:
            return Entity.search([("active", "=", True), ("show_dashboard", "=", True)])
        return Entity.browse([])

    def _view_settings(self, dashboard, page=None):
        source = page or dashboard
        return {
            "name": source.name if page else dashboard.name,
            "page_slug": page.slug if page else "",
            "allow_control": bool(source.allow_control),
            "show_status": bool(source.show_status),
            "show_alerts": bool(source.show_alerts),
            "show_windows": bool(source.show_windows),
            "separate_controls_sensors": bool(source.separate_controls_sensors),
            "sensor_layout": source.sensor_layout or "compact",
            "group_mode": source.group_mode or "custom",
            "show_history_charts": bool(source.show_history_charts),
            "show_entity_ids": bool(source.show_entity_ids),
            "show_last_seen": bool(source.show_last_seen),
            "grid_columns": int(source.grid_columns or 4),
        }

    @http.route([
        "/groundlift/ha",
        "/groundlift/ha/<string:slug>",
        "/groundlift/ha/<string:slug>/<string:page_slug>",
    ], type="http", auth="user", website=True, methods=["GET"])
    def dashboard_page(self, slug=None, page_slug=None, **kwargs):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            return request.not_found()
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            return request.not_found()
        pages = dashboard.page_ids.filtered(lambda p: p.active).sorted(key=lambda p: (p.sequence, p.id))
        return request.render("gl_home_assistant_control.ha_dashboard_page", {
            "dashboard": dashboard,
            "current_page": page,
            "pages": pages,
        })

    @http.route("/groundlift/ha/data", type="jsonrpc", auth="user", methods=["POST"])
    def dashboard_data(self, slug=None, page_slug=None):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            raise UserError(_("Dashboard nicht gefunden."))
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            raise UserError(_("Dashboard-Unterseite nicht gefunden."))

        entities = self._selected_entities(dashboard, page)
        view = self._view_settings(dashboard, page)
        can_control = bool(
            view["allow_control"]
            and request.env.user.has_group("gl_home_assistant_control.group_ha_operator")
        )
        now = fields.Datetime.now()
        config = request.env["gl.ha.config"].sudo().get_config()

        alerts = request.env["gl.ha.alert"].sudo().browse([])
        if view["show_alerts"]:
            alerts = request.env["gl.ha.alert"].sudo().search(
                [("state", "=", "open")], order="severity desc, last_seen desc", limit=20
            )

        windows = request.env["gl.ha.schedule.window"].sudo().browse([])
        if view["show_windows"]:
            windows = request.env["gl.ha.schedule.window"].sudo().search([
                ("end_at", ">=", now),
                ("start_at", "<=", now + timedelta(hours=24)),
            ], order="start_at asc", limit=20)

        return {
            "dashboard": {
                "name": dashboard.name,
                "slug": dashboard.slug,
                "page_name": page.name if page else (dashboard.main_page_label or _("Übersicht")),
                "page_slug": page.slug if page else "",
                "refresh_seconds": dashboard.refresh_seconds,
                "history_hours": int(dashboard.default_history_hours),
                "can_control": can_control,
                "default_override_minutes": config.default_manual_override_minutes,
            },
            "view": view,
            "connection": {
                "last_state_sync_at": fields.Datetime.to_string(config.last_state_sync_at) if config.last_state_sync_at else None,
                "last_schedule_sync_at": fields.Datetime.to_string(config.last_schedule_sync_at) if config.last_schedule_sync_at else None,
                "last_automation_at": fields.Datetime.to_string(config.last_automation_at) if config.last_automation_at else None,
            },
            "entities": [self._entity_json(e, can_control) for e in entities],
            "alerts": [{
                "id": a.id,
                "severity": a.severity,
                "name": a.name,
                "message": a.message,
                "last_seen": fields.Datetime.to_string(a.last_seen),
            } for a in alerts],
            "windows": [{
                "source": w.source,
                "name": w.name,
                "details": w.details or "",
                "start_at": fields.Datetime.to_string(w.start_at),
                "end_at": fields.Datetime.to_string(w.end_at),
            } for w in windows],
        }

    def _entity_json(self, e, can_control):
        now = fields.Datetime.now()
        override_active = bool(e.manual_override_until and e.manual_override_until > now)
        display_role = e.dashboard_display_role()
        return {
            "id": e.id,
            "name": e.name,
            "entity_id": e.entity_id,
            "domain": e.domain,
            "room": e.room or "Allgemein",
            "dashboard_group": e.dashboard_group or "",
            "display_role": display_role,
            "device_class": e.device_class or "",
            "unit": e.unit or "",
            "state": e.state or "",
            "is_available": e.is_available,
            "has_numeric_value": e.has_numeric_value,
            "numeric_value": e.numeric_value,
            "has_control_value": e.has_control_value,
            "control_value": e.control_value,
            "history_enabled": e.history_enabled,
            "controllable": bool(e.controllable and can_control and display_role == "control"),
            "control_type": e.control_type,
            "min_value": e.min_value,
            "max_value": e.max_value,
            "has_min_value": e.has_min_value,
            "has_max_value": e.has_max_value,
            "step": e.step or 1.0,
            "override_active": override_active,
            "override_until": fields.Datetime.to_string(e.manual_override_until) if override_active else None,
            "override_value": e.manual_override_value or "",
            "last_seen_at": fields.Datetime.to_string(e.last_seen_at) if e.last_seen_at else None,
        }

    @http.route("/groundlift/ha/history", type="jsonrpc", auth="user", methods=["POST"])
    def dashboard_history(self, slug=None, page_slug=None, entity_ids=None, hours=24):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            raise UserError(_("Dashboard nicht gefunden."))
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            raise UserError(_("Dashboard-Unterseite nicht gefunden."))
        allowed_ids = set(self._selected_entities(dashboard, page).ids)
        requested_ids = [int(x) for x in (entity_ids or []) if str(x).isdigit()]
        requested_ids = [x for x in requested_ids if x in allowed_ids]
        entities = request.env["gl.ha.entity"].sudo().browse(requested_ids).exists()
        return request.env["gl.ha.history"].sudo().dashboard_series(entities, hours=hours)

    @http.route("/groundlift/ha/command", type="jsonrpc", auth="user", methods=["POST"])
    def dashboard_command(self, slug=None, page_slug=None, entity_id=None, command=None, value=None, override_minutes=None):
        self._check_view()
        dashboard = self._get_dashboard(slug)
        if not dashboard:
            raise AccessError(_("Dashboard nicht gefunden."))
        page = self._get_page(dashboard, page_slug)
        if page_slug and not page:
            raise AccessError(_("Dashboard-Unterseite nicht gefunden."))
        view = self._view_settings(dashboard, page)
        if not view["allow_control"]:
            raise AccessError(_("Steuerung ist auf dieser Dashboard-Seite deaktiviert."))
        if not request.env.user.has_group("gl_home_assistant_control.group_ha_operator"):
            raise AccessError(_("Keine Berechtigung zum Schalten."))
        entity = request.env["gl.ha.entity"].sudo().browse(int(entity_id or 0)).exists()
        if not entity:
            raise UserError(_("Entität nicht gefunden."))
        if not entity.active:
            raise AccessError(_("Diese Entität ist deaktiviert."))
        if entity.id not in set(self._selected_entities(dashboard, page).ids):
            raise AccessError(_("Diese Entität gehört nicht zu dieser Dashboard-Seite."))
        if entity.dashboard_display_role() != "control":
            raise AccessError(_("Diese Entität ist auf dem Dashboard als Sensor konfiguriert und kann hier nicht geschaltet werden."))
        entity.dashboard_command(command, value=value, override_minutes=override_minutes)
        return self._entity_json(entity, True)
