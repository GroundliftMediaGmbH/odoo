# -*- coding: utf-8 -*-
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlHaDeviceAccess(models.Model):
    _name = "gl.ha.device.access"
    _description = "Home Assistant externer Gerätezugang"
    _order = "name, id"

    name = fields.Char(string="Gerätename", required=True)
    active = fields.Boolean(default=True)
    public_id = fields.Char(
        string="Geräte-ID",
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: secrets.token_urlsafe(18),
    )

    dashboard_id = fields.Many2one(
        "gl.ha.dashboard",
        string="Dashboard",
        required=True,
        ondelete="cascade",
        index=True,
    )
    allow_main_page = fields.Boolean(string="Hauptseite erlauben", default=True)
    page_ids = fields.Many2many(
        "gl.ha.dashboard.page",
        relation="gl_ha_device_access_page_rel",
        column1="device_access_id",
        column2="page_id",
        string="Erlaubte Unterseiten",
        domain="[('dashboard_id', '=', dashboard_id)]",
    )
    allow_control = fields.Boolean(
        string="Steuerung erlauben",
        default=True,
        help="Wenn deaktiviert, ist der externe Gerätezugang unabhängig von der Dashboard-Konfiguration nur lesend.",
    )

    setup_token = fields.Char(string="Einrichtungs-Token", readonly=True, copy=False)
    setup_expires_at = fields.Datetime(string="Einrichtungslink gültig bis", readonly=True, copy=False)
    setup_url = fields.Char(string="Einrichtungslink", compute="_compute_urls")
    external_url = fields.Char(string="Geräte-Dashboard", compute="_compute_urls")

    public_key_jwk = fields.Text(string="Öffentlicher Geräteschlüssel", readonly=True, copy=False)
    key_fingerprint = fields.Char(string="Schlüssel-Fingerprint", readonly=True, copy=False)
    session_token_hash = fields.Char(string="Geräte-Cookie Hash", readonly=True, copy=False, index=True)
    registered_at = fields.Datetime(string="Gebunden seit", readonly=True, copy=False)
    last_seen_at = fields.Datetime(string="Zuletzt gesehen", readonly=True, copy=False)
    last_user_agent = fields.Char(string="Browser / Gerät", readonly=True, copy=False)
    access_state = fields.Selection(
        [
            ("waiting", "Einrichtung ausstehend"),
            ("expired", "Einrichtungslink abgelaufen"),
            ("registered", "Gerät gebunden"),
            ("disabled", "Deaktiviert"),
        ],
        string="Status",
        compute="_compute_access_state",
    )

    _public_id_unique = models.Constraint(
        "UNIQUE(public_id)",
        "Die Geräte-ID muss eindeutig sein.",
    )

    @api.depends("setup_token", "public_id")
    def _compute_urls(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        for rec in self:
            rec.external_url = "%s/groundlift/ha/device/%s" % (base_url, rec.public_id) if base_url and rec.public_id else False
            rec.setup_url = (
                "%s/groundlift/ha/device/setup/%s" % (base_url, rec.setup_token)
                if base_url and rec.setup_token
                else False
            )

    @api.depends("active", "public_key_jwk", "setup_token", "setup_expires_at")
    def _compute_access_state(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.active:
                rec.access_state = "disabled"
            elif rec.public_key_jwk:
                rec.access_state = "registered"
            elif rec.setup_token and rec.setup_expires_at and rec.setup_expires_at < now:
                rec.access_state = "expired"
            else:
                rec.access_state = "waiting"

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.setdefault("setup_token", secrets.token_urlsafe(36))
            vals.setdefault("setup_expires_at", now + timedelta(hours=24))
        return super().create(vals_list)

    @api.onchange("dashboard_id")
    def _onchange_dashboard_id(self):
        for rec in self:
            if rec.dashboard_id:
                rec.page_ids = rec.page_ids.filtered(lambda p: p.dashboard_id == rec.dashboard_id)
            else:
                rec.page_ids = [(5, 0, 0)]

    @api.constrains("dashboard_id", "page_ids", "allow_main_page")
    def _check_scope(self):
        for rec in self:
            wrong_pages = rec.page_ids.filtered(lambda p: p.dashboard_id != rec.dashboard_id)
            if wrong_pages:
                raise ValidationError(_("Alle freigegebenen Unterseiten müssen zum ausgewählten Dashboard gehören."))
            if not rec.allow_main_page and not rec.page_ids:
                raise ValidationError(_("Bitte mindestens die Hauptseite oder eine Unterseite für diesen Gerätezugang freigeben."))

    def action_regenerate_setup(self):
        self.ensure_one()
        token = secrets.token_urlsafe(36)
        self.write({
            "active": True,
            "setup_token": token,
            "setup_expires_at": fields.Datetime.now() + timedelta(hours=24),
            "public_key_jwk": False,
            "key_fingerprint": False,
            "session_token_hash": False,
            "registered_at": False,
            "last_seen_at": False,
            "last_user_agent": False,
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Neuer Einrichtungslink erstellt"),
                "message": _("Öffnen Sie den Einrichtungslink innerhalb von 24 Stunden ausschließlich auf dem gewünschten Rechner."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_revoke_binding(self):
        self.ensure_one()
        self.write({
            "setup_token": False,
            "setup_expires_at": False,
            "public_key_jwk": False,
            "key_fingerprint": False,
            "session_token_hash": False,
            "registered_at": False,
            "last_seen_at": False,
            "last_user_agent": False,
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Gerätebindung aufgehoben"),
                "message": _("Der bisherige Rechner kann nicht mehr auf das Dashboard zugreifen. Für eine neue Bindung bitte einen neuen Einrichtungslink erzeugen."),
                "type": "warning",
                "sticky": False,
            },
        }

    def action_open_external(self):
        self.ensure_one()
        if not self.public_key_jwk:
            raise ValidationError(_("Dieses Gerät ist noch nicht gebunden. Öffnen Sie zuerst den Einrichtungslink auf dem Zielrechner."))
        return {"type": "ir.actions.act_url", "url": self.external_url, "target": "new"}

    def _set_session_token(self, raw_token):
        self.ensure_one()
        self.sudo().write({
            "session_token_hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        })

    def _allowed_pages(self):
        self.ensure_one()
        return self.page_ids.filtered(lambda p: p.active and p.dashboard_id == self.dashboard_id).sorted(
            key=lambda p: (p.sequence, p.id)
        )
