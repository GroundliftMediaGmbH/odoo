# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .ha_api import HomeAssistantAPI

_logger = logging.getLogger(__name__)


class GlHaConfig(models.Model):
    _name = "gl.ha.config"
    _description = "Home Assistant Einstellungen"
    _order = "id"

    name = fields.Char(default="GROUNDLIFT Home Assistant", required=True)
    active = fields.Boolean(default=True)
    base_url = fields.Char(
        string="Home Assistant URL",
        help="Von Odoo.sh erreichbare Home-Assistant-Basis-URL, vorzugsweise HTTPS.",
    )
    access_token = fields.Char(string="Long-Lived Access Token", groups="gl_home_assistant_control.group_ha_manager")
    verify_ssl = fields.Boolean(string="SSL-Zertifikat prüfen", default=True)
    extra_headers_json = fields.Text(
        string="Zusätzliche HTTP-Header (JSON)",
        groups="gl_home_assistant_control.group_ha_manager",
        help="Optional für einen vorgeschalteten sicheren Tunnel/Proxy, z. B. Service-Token-Header. JSON-Objekt mit Headername und Wert.",
    )
    request_timeout = fields.Integer(string="API-Timeout (Sek.)", default=10)
    timezone_name = fields.Char(string="Zeitzone", default="Europe/Berlin", required=True)

    state_poll_minutes = fields.Integer(string="Historienintervall (Min.)", default=5)
    history_retention_days = fields.Integer(string="Lokale Historie behalten (Tage)", default=90)
    unavailable_grace_minutes = fields.Integer(string="Warnung nach Nichterreichbarkeit (Min.)", default=3)
    default_manual_override_minutes = fields.Integer(string="Manuelle Übersteuerung (Min.)", default=120)

    schedule_horizon_days = fields.Integer(string="Zeitfenster-Vorschau (Tage)", default=14)
    event_stage_ids = fields.Many2many(
        "event.stage",
        string="Veranstaltungsphasen",
        help="Optional: Nur Veranstaltungen in diesen Odoo-Phasen für die Automatik verwenden. Leer = alle aktiven, nicht stornierten Veranstaltungen.",
    )
    cinema_default_duration_minutes = fields.Integer(string="Kino-Fallbackdauer (Min.)", default=120)
    automation_enabled = fields.Boolean(string="Automationen aktiv", default=True)

    alert_email_enabled = fields.Boolean(string="Warnungen per E-Mail", default=False)
    alert_email_to = fields.Char(string="Warn-E-Mail an")

    last_test_at = fields.Datetime(string="Letzter Verbindungstest", readonly=True)
    last_test_message = fields.Text(string="Letzte Verbindungsmeldung", readonly=True)
    last_state_sync_at = fields.Datetime(string="Letzter Statusabruf", readonly=True)
    last_schedule_sync_at = fields.Datetime(string="Letzte Zeitfenster-Aktualisierung", readonly=True)
    last_automation_at = fields.Datetime(string="Letzte Automatik-Auswertung", readonly=True)

    @api.constrains(
        "request_timeout",
        "state_poll_minutes",
        "history_retention_days",
        "unavailable_grace_minutes",
        "default_manual_override_minutes",
        "schedule_horizon_days",
        "cinema_default_duration_minutes",
    )
    def _check_positive_values(self):
        for rec in self:
            if rec.request_timeout < 1:
                raise ValidationError(_("Der API-Timeout muss mindestens 1 Sekunde betragen."))
            if rec.state_poll_minutes < 1:
                raise ValidationError(_("Das Statusintervall muss mindestens 1 Minute betragen."))
            if rec.history_retention_days < 1:
                raise ValidationError(_("Die Historie muss mindestens 1 Tag behalten werden."))
            if rec.unavailable_grace_minutes < 0 or rec.default_manual_override_minutes < 0:
                raise ValidationError(_("Zeitwerte dürfen nicht negativ sein."))
            if rec.schedule_horizon_days < 1 or rec.cinema_default_duration_minutes < 1:
                raise ValidationError(_("Zeitfenster und Kinodauer müssen größer als 0 sein."))

    @api.model
    def get_config(self):
        config = self.search([("active", "=", True)], limit=1)
        if not config:
            config = self.create({"name": "GROUNDLIFT Home Assistant"})
        return config

    def _client(self):
        self.ensure_one()
        if not self.base_url or not self.access_token:
            raise UserError(_("Bitte zuerst Home-Assistant-URL und Long-Lived Access Token eintragen."))
        extra_headers = {}
        if self.extra_headers_json:
            try:
                extra_headers = json.loads(self.extra_headers_json)
                if not isinstance(extra_headers, dict):
                    raise ValueError("JSON must be an object")
                extra_headers = {str(key): str(value) for key, value in extra_headers.items()}
            except Exception as exc:
                raise UserError(_("Zusätzliche HTTP-Header sind kein gültiges JSON-Objekt: %s") % exc) from exc
        return HomeAssistantAPI(
            self.base_url,
            self.access_token,
            verify_ssl=self.verify_ssl,
            timeout=self.request_timeout,
            extra_headers=extra_headers,
        )

    def action_test_connection(self):
        self.ensure_one()
        try:
            result = self._client().test()
            message = result.get("message") if isinstance(result, dict) else str(result)
            message = message or _("Home Assistant antwortet.")
            self.write({"last_test_at": fields.Datetime.now(), "last_test_message": message})
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {"title": _("Home Assistant"), "message": message, "type": "success", "sticky": False},
            }
        except Exception as exc:
            self.write({"last_test_at": fields.Datetime.now(), "last_test_message": str(exc)})
            raise UserError(_("Home Assistant ist nicht erreichbar: %s") % exc) from exc

    def action_sync_entities(self):
        self.ensure_one()
        self.env["gl.ha.entity"].sudo().sync_from_home_assistant(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Home Assistant"), "message": _("Entitäten und Zustände wurden aktualisiert."), "type": "success"},
        }

    def action_refresh_schedules(self):
        self.ensure_one()
        self.env["gl.ha.schedule.window"].sudo().refresh_all(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Zeitfenster"), "message": _("Event- und Kino-Zeitfenster wurden aktualisiert."), "type": "success"},
        }

    def action_run_automation(self):
        self.ensure_one()
        self.env["gl.ha.automation.rule"].sudo().evaluate_all(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Automatik"), "message": _("Automatik wurde ausgewertet."), "type": "success"},
        }

    def action_import_history_24h(self):
        self.ensure_one()
        count = self.env["gl.ha.history"].sudo().import_home_assistant_history(self, hours=24)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Historie"), "message": _("%(count)s Verlaufswerte importiert.") % {"count": count}, "type": "success"},
        }

    def action_open_dashboard(self):
        self.ensure_one()
        dashboard = self.env["gl.ha.dashboard"].search([("active", "=", True)], limit=1)
        url = "/groundlift/ha/%s" % dashboard.slug if dashboard else "/groundlift/ha"
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    @api.model
    def cron_sync_states(self):
        config = self.get_config().sudo()
        try:
            self.env["gl.ha.entity"].sudo().sync_from_home_assistant(config)
            self.env["gl.ha.alert"].sudo().resolve_system_alert("ha_connection")
        except Exception as exc:
            _logger.exception("Home Assistant state sync failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "ha_connection",
                _("Home Assistant Verbindung fehlgeschlagen: %s") % exc,
                severity="critical",
                config=config,
            )
        return True

    @api.model
    def cron_refresh_schedules(self):
        config = self.get_config().sudo()
        try:
            self.env["gl.ha.schedule.window"].sudo().refresh_all(config)
            self.env["gl.ha.alert"].sudo().resolve_system_alert("schedule_sync")
        except Exception as exc:
            _logger.exception("Home Assistant schedule refresh failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "schedule_sync",
                _("Zeitfenster konnten nicht aktualisiert werden: %s") % exc,
                severity="warning",
                config=config,
            )
        return True

    @api.model
    def cron_run_automation(self):
        config = self.get_config().sudo()
        if not config.automation_enabled:
            return True
        try:
            self.env["gl.ha.automation.rule"].sudo().evaluate_all(config)
            self.env["gl.ha.alert"].sudo().resolve_system_alert("automation")
        except Exception as exc:
            _logger.exception("Home Assistant automation failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "automation",
                _("Home-Assistant-Automatik fehlgeschlagen: %s") % exc,
                severity="critical",
                config=config,
            )
        return True

    @api.model
    def cron_cleanup_history(self):
        config = self.get_config().sudo()
        cutoff = fields.Datetime.now() - timedelta(days=config.history_retention_days)
        old = self.env["gl.ha.history"].sudo().search([("timestamp", "<", cutoff)])
        if old:
            old.unlink()
        return True
