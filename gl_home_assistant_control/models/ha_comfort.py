# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlHaComfortGroup(models.Model):
    _name = "gl.ha.comfort.group"
    _description = "Home Assistant Temperatur-/Feuchtegruppe"
    _order = "sequence, name, id"

    name = fields.Char(
        string="Bezeichnung",
        required=True,
        help="Bezeichnung des Raums bzw. Messpunkts, z. B. Lager, Foyer oder Kino 1.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    config_id = fields.Many2one(
        "gl.ha.config",
        string="Home-Assistant-Einstellungen",
        required=True,
        ondelete="cascade",
        index=True,
    )
    temperature_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Temperatur",
        required=True,
        ondelete="restrict",
        domain="[('active','=',True),('has_numeric_value','=',True)]",
        help="Home-Assistant-Entität für die Raumlufttemperatur dieser Gruppe.",
    )
    humidity_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Luftfeuchtigkeit",
        required=True,
        ondelete="restrict",
        domain="[('active','=',True),('has_numeric_value','=',True)]",
        help="Home-Assistant-Entität für die relative Luftfeuchtigkeit dieser Gruppe.",
    )
    mould_warning_enabled = fields.Boolean(
        string="Schimmelgefahrmeldung",
        default=False,
        help="Wenn aktiv, erhält die lila Schimmelrisiko-Bewertung für dieses Sensorpaar Vorrang vor der normalen Behaglichkeitsfarbe.",
    )
    note = fields.Char(string="Hinweis")

    _temperature_unique = models.Constraint(
        "UNIQUE(config_id, temperature_entity_id)",
        "Eine Temperatur-Entität kann innerhalb derselben Home-Assistant-Konfiguration nur einer Temperatur-/Feuchtegruppe zugeordnet werden.",
    )
    _humidity_unique = models.Constraint(
        "UNIQUE(config_id, humidity_entity_id)",
        "Eine Luftfeuchte-Entität kann innerhalb derselben Home-Assistant-Konfiguration nur einer Temperatur-/Feuchtegruppe zugeordnet werden.",
    )

    @api.constrains("temperature_entity_id", "humidity_entity_id")
    def _check_distinct_entities(self):
        for rec in self:
            if rec.temperature_entity_id and rec.temperature_entity_id == rec.humidity_entity_id:
                raise ValidationError(_("Temperatur und Luftfeuchtigkeit müssen zwei unterschiedliche Home-Assistant-Entitäten sein."))
