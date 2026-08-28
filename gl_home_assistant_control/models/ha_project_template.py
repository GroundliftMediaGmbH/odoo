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
    solar_clear_before_minutes = fields.Integer(
        string="Sonnenzeit: Vorlauf bei wenig Bewölkung (Min.)",
        default=60,
    )
    solar_cloudy_before_minutes = fields.Integer(
        string="Sonnenzeit: Vorlauf bei Bewölkung (Min.)",
        default=90,
    )
    solar_cloud_threshold = fields.Float(string="Ab Bewölkung (%)", default=60.0)
    has_solar_condition = fields.Boolean(compute="_compute_weather_condition_flags")
    has_cloud_condition = fields.Boolean(compute="_compute_weather_condition_flags")
    has_generic_condition = fields.Boolean(compute="_compute_weather_condition_flags")
    notes = fields.Text(string="Hinweise")

    def init(self):
        super().init()
        self.env.cr.execute("""
            UPDATE gl_ha_project_template
               SET solar_clear_before_minutes = 60
             WHERE solar_clear_before_minutes IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_project_template
               SET solar_cloudy_before_minutes = 90
             WHERE solar_cloudy_before_minutes IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_project_template
               SET solar_cloud_threshold = 60.0
             WHERE solar_cloud_threshold IS NULL
        """)

    @api.constrains("minutes_before", "minutes_after")
    def _check_offsets(self):
        for rec in self:
            if rec.minutes_before < 0 or rec.minutes_after < 0:
                raise ValidationError(_("Vor- und Nachlauf dürfen nicht negativ sein."))

    @api.constrains("solar_clear_before_minutes", "solar_cloudy_before_minutes", "solar_cloud_threshold")
    def _check_solar_values(self):
        for rec in self:
            if rec.solar_clear_before_minutes < 0 or rec.solar_cloudy_before_minutes < 0:
                raise ValidationError(_("Sonnenzeit-Vorläufe dürfen nicht negativ sein."))
            if not (0.0 <= rec.solar_cloud_threshold <= 100.0):
                raise ValidationError(_("Der Bewölkungsgrenzwert muss zwischen 0 und 100 Prozent liegen."))

    @api.constrains("condition_entity_ids")
    def _check_solar_sensor_selection(self):
        for rec in self:
            solar = rec.condition_entity_ids.filtered(
                lambda entity: entity.source_type == "weather" and entity.weather_metric in ("sunrise", "sunset")
            )
            if len(solar) > 1:
                raise ValidationError(_("Bitte pro Projekt-Vorlage nur Sonnenaufgang oder Sonnenuntergang auswählen."))

    @api.depends("condition_entity_ids")
    def _compute_weather_condition_flags(self):
        for rec in self:
            weather = rec.condition_entity_ids.filtered(lambda entity: entity.source_type == "weather")
            rec.has_solar_condition = bool(weather.filtered(lambda entity: entity.weather_metric in ("sunrise", "sunset")))
            rec.has_cloud_condition = bool(weather.filtered(lambda entity: entity.weather_metric == "cloud_cover"))
            solar_active = rec.has_solar_condition
            rec.has_generic_condition = bool(rec.condition_entity_ids.filtered(
                lambda entity: not (
                    entity.source_type == "weather"
                    and (
                        entity.weather_metric in ("sunrise", "sunset")
                        or (solar_active and entity.weather_metric == "cloud_cover")
                    )
                )
            ))

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
            "solar_clear_before_minutes": self.solar_clear_before_minutes,
            "solar_cloudy_before_minutes": self.solar_cloudy_before_minutes,
            "solar_cloud_threshold": self.solar_cloud_threshold,
        }
