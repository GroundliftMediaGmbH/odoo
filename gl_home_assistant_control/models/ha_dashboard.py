# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlHaDashboard(models.Model):
    _name = "gl.ha.dashboard"
    _description = "Home Assistant Dashboard"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    slug = fields.Char(required=True, default="hauptansicht")
    entity_ids = fields.Many2many("gl.ha.entity", string="Angezeigte Entitäten")
    refresh_seconds = fields.Integer(string="Aktualisierung (Sek.)", default=15)
    default_history_hours = fields.Selection([
        ("6", "6 Stunden"),
        ("24", "24 Stunden"),
        ("168", "7 Tage"),
        ("720", "30 Tage"),
    ], default="24", required=True)
    allow_control = fields.Boolean(string="Steuerung auf dieser Seite erlauben", default=True)

    _slug_unique = models.Constraint(
        "UNIQUE(slug)",
        "Der Dashboard-Pfad muss eindeutig sein.",
    )

    @api.constrains("slug", "refresh_seconds")
    def _check_dashboard(self):
        for rec in self:
            if not re.match(r"^[a-z0-9][a-z0-9_-]*$", rec.slug or ""):
                raise ValidationError(_("Der Dashboard-Pfad darf nur Kleinbuchstaben, Zahlen, _ und - enthalten."))
            if rec.refresh_seconds < 5:
                raise ValidationError(_("Die Aktualisierung darf nicht schneller als alle 5 Sekunden erfolgen."))

    def action_open_dashboard(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/groundlift/ha/%s" % self.slug, "target": "new"}
