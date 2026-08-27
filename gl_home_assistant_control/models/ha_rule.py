# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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

    # Neue Mehrfachauswahl. Die beiden alten Many2one-Felder bleiben bewusst im
    # Modell, damit bestehende Installationen ohne Datenverlust aktualisiert
    # werden können. init() übernimmt vorhandene Werte automatisch in die M2M-
    # Felder. Die Legacy-Felder sind in der Oberfläche nicht mehr sichtbar.
    target_entity_ids = fields.Many2many(
        "gl.ha.entity",
        "gl_ha_rule_target_entity_rel",
        "rule_id",
        "entity_id",
        string="Zu schaltende Entitäten",
        required=True,
        domain="[('control_type','=','toggle'),('controllable','=',True)]",
        help="Alle hier ausgewählten Entitäten werden durch dieselbe Automatikregel geschaltet.",
    )
    target_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Zu schaltende Entität (Alt)",
        domain="[('control_type','=','toggle'),('controllable','=',True)]",
        help="Kompatibilitätsfeld für Regeln aus älteren Modulversionen.",
    )

    minutes_before = fields.Integer(
        string="Einschalten vor Beginn (Min.)",
        default=60,
        help="Bei Kino: Vorlauf vor der ersten Vorstellung des jeweiligen Tages.",
    )
    minutes_after = fields.Integer(
        string="Ausschalten nach Ende (Min.)",
        default=60,
        help="Bei Kino: Nachlauf nach dem Ende der letzten Vorstellung des jeweiligen Tages.",
    )

    condition_entity_ids = fields.Many2many(
        "gl.ha.entity",
        "gl_ha_rule_condition_entity_rel",
        "rule_id",
        "entity_id",
        string="Optionale Messsensoren",
        domain="[('has_numeric_value','=',True)]",
        help="Mehrere Messsensoren können gemeinsam als Bedingung verwendet werden.",
    )
    condition_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Optionaler Messsensor (Alt)",
        domain="[('has_numeric_value','=',True)]",
        help="Kompatibilitätsfeld für Regeln aus älteren Modulversionen.",
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

    last_evaluated_at = fields.Datetime(readonly=True)
    last_desired_state = fields.Selection([
        ("on", "Ein"),
        ("off", "Aus"),
        ("hold", "Halten"),
        ("override", "Manuell"),
    ], readonly=True)
    last_action_at = fields.Datetime(readonly=True)
    last_message = fields.Char(readonly=True)

    def init(self):
        """Übernimmt bestehende Einzel-Auswahlen beim Modulupdate in M2M.

        Damit kann eine vorhandene v1.1.0-Installation direkt aktualisiert
        werden. Bereits konfigurierte Regeln bleiben vollständig erhalten.
        """
        super().init()
        self.env.cr.execute("""
            INSERT INTO gl_ha_rule_target_entity_rel (rule_id, entity_id)
            SELECT r.id, r.target_entity_id
              FROM gl_ha_automation_rule r
             WHERE r.target_entity_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        self.env.cr.execute("""
            INSERT INTO gl_ha_rule_condition_entity_rel (rule_id, entity_id)
            SELECT r.id, r.condition_entity_id
              FROM gl_ha_automation_rule r
             WHERE r.condition_entity_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)

    @api.constrains("minutes_before", "minutes_after")
    def _check_offsets(self):
        for rec in self:
            if rec.minutes_before < 0 or rec.minutes_after < 0:
                raise ValidationError(_("Vor- und Nachlauf dürfen nicht negativ sein."))

    @api.constrains("target_entity_ids", "target_entity_id")
    def _check_target_entities(self):
        for rec in self:
            if not rec.target_entity_ids and not rec.target_entity_id:
                raise ValidationError(_("Bitte mindestens eine zu schaltende Entität auswählen."))

    def _target_entities(self):
        """Liefert neue M2M-Ziele plus ggf. noch vorhandenes Legacy-Ziel."""
        self.ensure_one()
        entities = self.target_entity_ids
        if self.target_entity_id:
            entities |= self.target_entity_id
        return entities

    def _condition_entities(self):
        """Liefert neue M2M-Sensoren plus ggf. noch vorhandenen Legacy-Sensor."""
        self.ensure_one()
        entities = self.condition_entity_ids
        if self.condition_entity_id:
            entities |= self.condition_entity_id
        return entities

    def _compare_sensor(self, sensor):
        self.ensure_one()
        value = sensor.numeric_value
        threshold = self.condition_threshold
        return {
            "lt": value < threshold,
            "le": value <= threshold,
            "gt": value > threshold,
            "ge": value >= threshold,
        }.get(self.condition_operator, False)

    def _condition_result(self):
        """Dreiwertige Auswertung für mehrere optionale Sensoren.

        Rückgabe: (condition_ok, condition_unknown)

        - ALL: Ein bekannter False-Wert entscheidet sofort False. Sind sonst nur
          True + unbekannte Sensoren vorhanden, wird der Zustand als unbekannt
          behandelt und die aktuelle Schaltstellung gehalten.
        - ANY: Ein bekannter True-Wert entscheidet sofort True. Sind sonst nur
          False + unbekannte Sensoren vorhanden, wird ebenfalls gehalten.
        """
        self.ensure_one()
        sensors = self._condition_entities()
        if not sensors:
            return True, False

        results = []
        for sensor in sensors:
            if not sensor.is_available or not sensor.has_numeric_value:
                results.append(None)
            else:
                results.append(self._compare_sensor(sensor))

        if self.condition_match_mode == "any":
            if True in results:
                return True, False
            if None in results:
                return False, True
            return False, False

        # Standard: alle Bedingungen müssen zutreffen.
        if False in results:
            return False, False
        if None in results:
            return False, True
        return True, False

    def _condition_ok(self):
        """Kompatibilitätshelfer für evtl. externe Aufrufer."""
        self.ensure_one()
        ok, unknown = self._condition_result()
        return ok and not unknown

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
            for target in rule._target_entities():
                by_target[target.id].append(rule)

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
                        "last_message": _("Manuelle Übersteuerung von %(target)s bis %(until)s") % {
                            "target": target.name,
                            "until": target.manual_override_until,
                        },
                    })
                continue
            if target.manual_override_until and target.manual_override_until <= now:
                target.action_clear_override()

            wants_on = False
            hold_current = False
            for rule in target_rules:
                window = rule._window_active(now)
                condition, condition_unknown = rule._condition_result()
                desired = window and condition
                wants_on = wants_on or desired
                # Wenn ein relevantes Zeitfenster aktiv ist, aber eine noch nicht
                # entscheidbare Sensorbedingung vorliegt, wird der aktuelle
                # Schaltzustand gehalten statt blind AUS zu schalten.
                hold_current = hold_current or bool(window and condition_unknown)
                sensor_count = len(rule._condition_entities())
                if not sensor_count:
                    condition_text = _("keine Sensorbedingung")
                elif condition_unknown:
                    condition_text = _("nicht vollständig verfügbar")
                else:
                    condition_text = _("ja") if condition else _("nein")
                rule.write({
                    "last_evaluated_at": now,
                    "last_desired_state": "hold" if (window and condition_unknown) else ("on" if desired else "off"),
                    "last_message": _("Zeitfenster: %(window)s / Sensorbedingung (%(count)s): %(condition)s") % {
                        "window": _("ja") if window else _("nein"),
                        "count": sensor_count,
                        "condition": condition_text,
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
