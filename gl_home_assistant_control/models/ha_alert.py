# -*- coding: utf-8 -*-
from odoo import _, fields, models, tools


class GlHaAlert(models.Model):
    _name = "gl.ha.alert"
    _description = "Home Assistant Warnung"
    _inherit = ["mail.thread"]
    _order = "state, severity desc, last_seen desc"

    name = fields.Char(required=True, tracking=True)
    key = fields.Char(required=True, index=True)
    entity_id = fields.Many2one("gl.ha.entity", ondelete="cascade", index=True)
    severity = fields.Selection([
        ("info", "Info"),
        ("warning", "Warnung"),
        ("critical", "Kritisch"),
    ], default="warning", required=True, tracking=True)
    state = fields.Selection([("open", "Offen"), ("resolved", "Erledigt")], default="open", required=True, index=True, tracking=True)
    message = fields.Text(required=True)
    first_seen = fields.Datetime(default=fields.Datetime.now, required=True)
    last_seen = fields.Datetime(default=fields.Datetime.now, required=True)
    resolved_at = fields.Datetime()
    occurrence_count = fields.Integer(default=1)

    _key_state_unique = models.Constraint(
        "UNIQUE(key, state)",
        "Pro Warnschlüssel darf es nur einen Datensatz je Status geben.",
    )

    def _send_alert_email(self, config):
        self.ensure_one()
        if not config or not config.alert_email_enabled or not config.alert_email_to:
            return
        body = "<p><strong>%s</strong></p><p>%s</p>" % (tools.html_escape(self.name or ""), tools.html_escape(self.message or ""))
        self.env["mail.mail"].sudo().create({
            "subject": "GROUNDLIFT Home Assistant: %s" % self.name,
            "email_to": config.alert_email_to,
            "body_html": body,
        }).send()

    def open_system_alert(self, key, message, severity="warning", entity=None, config=None):
        alert = self.search([("key", "=", key), ("state", "=", "open")], limit=1)
        now = fields.Datetime.now()
        if alert:
            alert.write({
                "message": message,
                "severity": severity,
                "last_seen": now,
                "occurrence_count": alert.occurrence_count + 1,
            })
            return alert
        # Avoid unique conflict with an old resolved row by reusing it.
        old = self.search([("key", "=", key), ("state", "=", "resolved")], order="id desc", limit=1)
        vals = {
            "name": entity.name if entity else _("Systemwarnung"),
            "key": key,
            "entity_id": entity.id if entity else False,
            "severity": severity,
            "state": "open",
            "message": message,
            "first_seen": now,
            "last_seen": now,
            "resolved_at": False,
            "occurrence_count": 1,
        }
        if old:
            old.write(vals)
            alert = old
        else:
            alert = self.create(vals)
        alert._send_alert_email(config)
        return alert

    def resolve_system_alert(self, key):
        alerts = self.search([("key", "=", key), ("state", "=", "open")])
        if alerts:
            alerts.write({"state": "resolved", "resolved_at": fields.Datetime.now()})
        return True

    def action_resolve(self):
        self.write({"state": "resolved", "resolved_at": fields.Datetime.now()})
        return True
