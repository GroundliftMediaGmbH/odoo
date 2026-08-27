# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class GlHaAutomationRule(models.Model):
    _name = "gl.ha.automation.rule"
    _description = "Home Assistant Automatikregel"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    source = fields.Selection([
        ("event", "Groundlift Veranstaltungen"),
        ("cinema", "Kinovorstellungen"),
    ], required=True, default="event")
    target_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Zu schaltende Entität",
        required=True,
        domain="[('control_type','=','toggle'),('controllable','=',True)]",
    )
    minutes_before = fields.Integer(string="Einschalten vor Beginn (Min.)", default=60)
    minutes_after = fields.Integer(string="Ausschalten nach Ende (Min.)", default=60)

    condition_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Optionaler Messsensor",
        domain="[('has_numeric_value','=',True)]",
    )
    condition_operator = fields.Selection([
        ("lt", "kleiner als"),
        ("le", "kleiner/gleich"),
        ("gt", "größer als"),
        ("ge", "größer/gleich"),
    ], default="lt")
    condition_threshold = fields.Float(string="Grenzwert", default=50.0)

    last_evaluated_at = fields.Datetime(readonly=True)
    last_desired_state = fields.Selection([
        ("on", "Ein"),
        ("off", "Aus"),
        ("hold", "Halten"),
        ("override", "Manuell"),
    ], readonly=True)
    last_action_at = fields.Datetime(readonly=True)
    last_message = fields.Char(readonly=True)

    @api.constrains("minutes_before", "minutes_after")
    def _check_offsets(self):
        for rec in self:
            if rec.minutes_before < 0 or rec.minutes_after < 0:
                from odoo.exceptions import ValidationError
                raise ValidationError(_("Vor- und Nachlauf dürfen nicht negativ sein."))

    def _condition_ok(self):
        self.ensure_one()
        sensor = self.condition_entity_id
        if not sensor:
            return True
        if not sensor.is_available or not sensor.has_numeric_value:
            return False
        value = sensor.numeric_value
        threshold = self.condition_threshold
        return {
            "lt": value < threshold,
            "le": value <= threshold,
            "gt": value > threshold,
            "ge": value >= threshold,
        }.get(self.condition_operator, False)

    def _window_active(self, now):
        self.ensure_one()
        return bool(self.env["gl.ha.schedule.window"].sudo().search_count([
            ("source", "=", self.source),
            ("start_at", "<=", now + timedelta(minutes=self.minutes_before)),
            ("end_at", ">=", now - timedelta(minutes=self.minutes_after)),
        ]))

    @api.model
    def evaluate_all(self, config=None):
        config = config or self.env["gl.ha.config"].get_config().sudo()
        now = fields.Datetime.now()
        rules = self.sudo().search([("active", "=", True)])
        by_target = defaultdict(list)
        for rule in rules:
            if rule.target_entity_id:
                by_target[rule.target_entity_id.id].append(rule)

        # Die Zustände werden minütlich synchronisiert. Bei deutlich älteren Daten
        # wird keine Automatikentscheidung auf Basis eines veralteten Lux-/Schaltwerts getroffen.
        if config.last_state_sync_at and now - config.last_state_sync_at > timedelta(minutes=3):
            raise RuntimeError(_("Home-Assistant-Zustände sind älter als 3 Minuten; Automatik wird aus Sicherheitsgründen ausgesetzt."))

        for target_id, target_rules in by_target.items():
            target = self.env["gl.ha.entity"].sudo().browse(target_id).exists()
            if not target:
                continue
            if target.manual_override_until and target.manual_override_until > now:
                for rule in target_rules:
                    rule.write({
                        "last_evaluated_at": now,
                        "last_desired_state": "override",
                        "last_message": _("Manuelle Übersteuerung bis %s") % target.manual_override_until,
                    })
                continue
            if target.manual_override_until and target.manual_override_until <= now:
                target.action_clear_override()

            wants_on = False
            hold_current = False
            for rule in target_rules:
                window = rule._window_active(now)
                sensor = rule.condition_entity_id
                condition_unknown = bool(sensor and (not sensor.is_available or not sensor.has_numeric_value))
                condition = False if condition_unknown else rule._condition_ok()
                desired = window and condition
                wants_on = wants_on or desired
                # Wenn ein relevantes Zeitfenster aktiv ist, aber z. B. der Lux-Sensor
                # ausfällt, wird der aktuelle Schaltzustand gehalten statt blind AUS zu schalten.
                hold_current = hold_current or bool(window and condition_unknown)
                rule.write({
                    "last_evaluated_at": now,
                    "last_desired_state": "hold" if (window and condition_unknown) else ("on" if desired else "off"),
                    "last_message": _("Zeitfenster: %(window)s / Bedingung: %(condition)s") % {
                        "window": _("ja") if window else _("nein"),
                        "condition": _("nicht verfügbar") if condition_unknown else (_("ja") if condition else _("nein")),
                    },
                })

            if not target.is_available:
                continue
            current_on = target._current_on()
            desired_on = True if wants_on else (current_on if hold_current else False)
            if desired_on != current_on:
                try:
                    target._apply_home_assistant("on" if desired_on else "off")
                    for rule in target_rules:
                        rule.write({"last_action_at": fields.Datetime.now()})
                    self.env["gl.ha.alert"].sudo().resolve_system_alert("automation_target:%s" % target.entity_id)
                except Exception as exc:
                    _logger.exception("Automation command failed for %s", target.entity_id)
                    self.env["gl.ha.alert"].sudo().open_system_alert(
                        "automation_target:%s" % target.entity_id,
                        _("Automatik konnte %(entity)s nicht schalten: %(error)s") % {"entity": target.name, "error": exc},
                        severity="critical",
                        entity=target,
                        config=config,
                    )
        config.sudo().write({"last_automation_at": now})
        return True
