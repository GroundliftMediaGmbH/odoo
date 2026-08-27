# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlHaProjectTemplate(models.Model):
    _name = "gl.ha.project.template"
    _description = "Home Assistant Projekt-Automatikvorlage"
    _order = "sequence, name"

    name = fields.Char(string="Vorlagenname", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    target_entity_ids = fields.Many2many(
        "gl.ha.entity",
        "gl_ha_project_template_target_entity_rel",
        "template_id",
        "entity_id",
        string="Zu schaltende Entitäten",
        required=True,
        domain="[('control_type','=','toggle'),('controllable','=',True)]",
        help="Diese Geräte werden beim Anwenden der Vorlage in die Projekt-Automatikregel übernommen.",
    )
    minutes_before = fields.Integer(
        string="Einschalten vor Projektbeginn (Min.)",
        default=60,
        help="Vorlauf, der beim Anwenden der Vorlage in die Projektregel übernommen wird.",
    )
    minutes_after = fields.Integer(
        string="Ausschalten nach Projektende (Min.)",
        default=60,
        help="Nachlauf, der beim Anwenden der Vorlage in die Projektregel übernommen wird.",
    )
    condition_entity_ids = fields.Many2many(
        "gl.ha.entity",
        "gl_ha_project_template_condition_entity_rel",
        "template_id",
        "entity_id",
        string="Optionale Messsensoren",
        domain="[('has_numeric_value','=',True)]",
        help="Optionale Sensorbedingungen werden ebenfalls in die Projektregel übernommen.",
    )
    condition_match_mode = fields.Selection([
        ("all", "Alle Sensoren müssen zutreffen"),
        ("any", "Mindestens ein Sensor muss zutreffen"),
    ], string="Verknüpfung der Sensoren", default="all", required=True)
    condition_operator = fields.Selection([
        ("lt", "kleiner als"),
        ("le", "kleiner/gleich"),
        ("gt", "größer als"),
        ("ge", "größer/gleich"),
    ], default="lt")
    condition_threshold = fields.Float(string="Grenzwert", default=50.0)
    notes = fields.Text(string="Hinweise")

    @api.constrains("minutes_before", "minutes_after")
    def _check_offsets(self):
        for rec in self:
            if rec.minutes_before < 0 or rec.minutes_after < 0:
                raise ValidationError(_("Vor- und Nachlauf dürfen nicht negativ sein."))

    @api.constrains("target_entity_ids")
    def _check_targets(self):
        for rec in self:
            if not rec.target_entity_ids:
                raise ValidationError(_("Bitte mindestens eine zu schaltende Entität auswählen."))

    def rule_values(self):
        """Werte, die beim Anwenden der Vorlage in eine Projektregel kopiert werden."""
        self.ensure_one()
        return {
            "target_entity_ids": [(6, 0, self.target_entity_ids.ids)],
            "minutes_before": self.minutes_before,
            "minutes_after": self.minutes_after,
            "condition_entity_ids": [(6, 0, self.condition_entity_ids.ids)],
            "condition_match_mode": self.condition_match_mode,
            "condition_operator": self.condition_operator,
            "condition_threshold": self.condition_threshold,
        }
