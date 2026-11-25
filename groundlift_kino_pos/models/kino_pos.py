# -*- coding: utf-8 -*-
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request


class GlKinoPosConfig(models.Model):
    _name = "gl.kino.pos.config"
    _description = "Kino POS Einstellungen"
    _rec_name = "name"

    name = fields.Char(default="Kino POS", required=True)
    reservation_stage_ids = fields.Many2many(
        "helpdesk.stage",
        "gl_kino_pos_config_reservation_stage_rel",
        "config_id",
        "stage_id",
        string="Reservierungen aus Phasen",
        help=(
            "Nur Kinoreservierungen aus diesen Helpdesk-Phasen werden auf dem Kino-POS-Dashboard angezeigt. "
            "Mehrere Phasen sind möglich. Wenn keine Phase ausgewählt ist, werden wie bisher alle noch nicht "
            "gelösten Kinoreservierungen berücksichtigt."
        ),
    )
    solved_stage_id = fields.Many2one(
        "helpdesk.stage",
        string="Ticketphase Gelöst",
        help="In diese Phase werden bearbeitete Kinoreservierungs-Tickets verschoben. Ist nichts gewählt, sucht die App automatisch nach einer Phase namens „Gelöst“ bzw. „Solved“.",
    )
    ha_dashboard_id = fields.Many2one(
        "gl.ha.dashboard",
        string="Home-Assistant-Dashboard",
        domain="[('active', '=', True)]",
        help="Dieses Dashboard wird über den Home-Assistant-Button an der Kinokasse geöffnet.",
    )
    ha_device_access_id = fields.Many2one(
        "gl.ha.device.access",
        string="Home-Assistant-Gerätezugang",
        domain="[('dashboard_id', '=', ha_dashboard_id), ('active', '=', True)]",
        help="Optional und für eine öffentliche Kinokasse empfohlen: Wählen Sie den Home-Assistant-Gerätezugang, der im selben Browser gebunden wurde. Dann öffnet der Button direkt den gerätegebundenen Home-Assistant-Zugang.",
    )
    timezone = fields.Char(
        string="Zeitzone",
        default="Europe/Berlin",
        required=True,
        help="Wird für Tageswechsel, Dienstplan und die Begrüßung verwendet.",
    )
    refresh_seconds = fields.Integer(
        string="Aktualisierung alle (Sek.)",
        default=30,
        required=True,
        help="Intervall für neue Reservierungen, Schichtwechsel und Checklistenzustand. Minimum 10 Sekunden.",
    )
    ticket_limit = fields.Integer(
        string="Maximale Reservierungen",
        default=50,
        required=True,
        help="Maximale Anzahl gleichzeitig geladener offener Kinoreservierungen.",
    )


    @api.constrains("refresh_seconds", "ticket_limit")
    def _check_numbers(self):
        for rec in self:
            if rec.refresh_seconds < 10:
                raise ValidationError(_("Das Aktualisierungsintervall muss mindestens 10 Sekunden betragen."))
            if rec.ticket_limit < 1 or rec.ticket_limit > 500:
                raise ValidationError(_("Die maximale Zahl der Reservierungen muss zwischen 1 und 500 liegen."))

    @api.constrains("reservation_stage_ids", "solved_stage_id")
    def _check_reservation_stages(self):
        for rec in self:
            if rec.solved_stage_id and rec.solved_stage_id in rec.reservation_stage_ids:
                raise ValidationError(_(
                    "Die Ticketphase „Gelöst“ darf nicht gleichzeitig als Quellphase für Reservierungen ausgewählt sein."
                ))

    @api.constrains("ha_dashboard_id", "ha_device_access_id")
    def _check_ha_access(self):
        for rec in self:
            if rec.ha_device_access_id and rec.ha_dashboard_id and rec.ha_device_access_id.dashboard_id != rec.ha_dashboard_id:
                raise ValidationError(_("Der Home-Assistant-Gerätezugang muss zum ausgewählten Dashboard gehören."))

    @api.onchange("ha_dashboard_id")
    def _onchange_ha_dashboard_id(self):
        for rec in self:
            if rec.ha_device_access_id and rec.ha_device_access_id.dashboard_id != rec.ha_dashboard_id:
                rec.ha_device_access_id = False

    @api.model
    def get_config(self):
        config = self.sudo().search([], order="id", limit=1)
        if not config:
            config = self.sudo().create({"name": "Kino POS"})
        return config

    @api.model_create_multi
    def create(self, vals_list):
        if self.sudo().search_count([]) + len(vals_list) > 1:
            raise ValidationError(_("Es kann nur einen Kino-POS-Einstellungsdatensatz geben."))
        return super().create(vals_list)

    def unlink(self):
        raise ValidationError(_("Die Kino-POS-Einstellungen können nicht gelöscht werden."))

    def get_ha_url(self):
        self.ensure_one()
        if self.ha_device_access_id and self.ha_device_access_id.active and self.ha_device_access_id.public_key_jwk:
            return self.ha_device_access_id.external_url or False
        if self.ha_dashboard_id and self.ha_dashboard_id.active:
            return "/groundlift/ha/%s" % self.ha_dashboard_id.slug
        return False

    def action_open_dashboard(self):
        """Öffnet das Kino-POS-Dashboard für den aktuell angemeldeten Odoo-Benutzer."""
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/kino-pos", "target": "new"}

    def action_open_ha_dashboard(self):
        self.ensure_one()
        url = self.get_ha_url()
        if not url:
            raise ValidationError(_("Bitte zuerst ein Home-Assistant-Dashboard konfigurieren."))
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}


class GlKinoPosTodoItem(models.Model):
    _name = "gl.kino.pos.todo.item"
    _description = "Kino POS Aufgabe"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string="Aufgabe", required=True)
    frequency = fields.Selection(
        [
            ("each_shift", "Jede Kinoschicht"),
            ("weekly", "1x die Woche"),
            ("twice_monthly", "2x im Monat"),
            ("monthly", "1x im Monat"),
        ],
        string="Anzeigen",
        required=True,
        default="each_shift",
    )
    note = fields.Text(string="Hinweis")

    def period_key(self, day):
        self.ensure_one()
        day = fields.Date.to_date(day)
        if self.frequency == "each_shift":
            return "shift:%s" % day.isoformat()
        if self.frequency == "weekly":
            iso = day.isocalendar()
            return "week:%04d-W%02d" % (iso.year, iso.week)
        if self.frequency == "twice_monthly":
            half = 1 if day.day <= 15 else 2
            return "half:%04d-%02d-%d" % (day.year, day.month, half)
        return "month:%04d-%02d" % (day.year, day.month)


class GlKinoPosTodoCompletion(models.Model):
    _name = "gl.kino.pos.todo.completion"
    _description = "Kino POS erledigte Aufgabe"
    _order = "completed_at desc, id desc"

    item_id = fields.Many2one("gl.kino.pos.todo.item", string="Aufgabe", required=True, ondelete="cascade", index=True)
    period_key = fields.Char(string="Zeitraum", required=True, index=True)
    shift_date = fields.Date(string="Schichtdatum", required=True, index=True)
    employee_id = fields.Many2one("hr.employee", string="Mitarbeiter:in", ondelete="set null")
    device_id = fields.Many2one("gl.kino.pos.device.access", string="Kassenrechner", ondelete="set null")
    completed_at = fields.Datetime(string="Erledigt am", default=fields.Datetime.now, required=True)

    _item_period_unique = models.Constraint(
        "UNIQUE(item_id, period_key)",
        "Diese Aufgabe wurde für den Zeitraum bereits erledigt.",
    )


class GlKinoPosDeviceAccess(models.Model):
    _name = "gl.kino.pos.device.access"
    _description = "Kino POS Gerätezugang"
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
    setup_token = fields.Char(string="Einrichtungs-Token", readonly=True, copy=False)
    setup_expires_at = fields.Datetime(string="Einrichtungslink gültig bis", readonly=True, copy=False)
    setup_url = fields.Char(string="Einrichtungslink", compute="_compute_urls")
    external_url = fields.Char(string="Kino POS Homepage", compute="_compute_urls")

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
        base_url = False
        try:
            http_request = request.httprequest
            if http_request:
                base_url = (http_request.host_url or "").rstrip("/")
        except (RuntimeError, AttributeError):
            base_url = False
        if not base_url:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        for rec in self:
            rec.external_url = "%s/kino-pos/device/%s" % (base_url, rec.public_id) if base_url and rec.public_id else False
            rec.setup_url = "%s/kino-pos/device/setup/%s" % (base_url, rec.setup_token) if base_url and rec.setup_token else False

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

    def action_regenerate_setup(self):
        self.ensure_one()
        self.write({
            "active": True,
            "setup_token": secrets.token_urlsafe(36),
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
                "message": _("Öffnen Sie den Link innerhalb von 24 Stunden ausschließlich auf dem gewünschten Kassenrechner."),
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
                "message": _("Der bisherige Rechner kann nicht mehr auf Kino POS zugreifen."),
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
