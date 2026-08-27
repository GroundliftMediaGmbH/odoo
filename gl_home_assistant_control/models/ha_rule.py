# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

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
        ("daily", "Tägliches Zeitprogramm"),
        ("project", "Odoo-Projekt (manuell)"),
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
        help="Bei Kino: Vorlauf vor der ersten Vorstellung des Tages; bei Veranstaltung/Projekt: Vorlauf vor dem jeweiligen Beginn.",
    )
    minutes_after = fields.Integer(
        string="Ausschalten nach Ende (Min.)",
        default=60,
        help="Bei Kino: Nachlauf nach der letzten Vorstellung des Tages; bei Veranstaltung/Projekt: Nachlauf nach dem jeweiligen Ende.",
    )

    # Zeitgesteuerte Automatik unabhängig von Kino/Veranstaltungen. Mehrere
    # Zeitblöcke pro Gerät werden einfach als mehrere Regeln angelegt; die
    # bestehende OR-Logik hält das Ziel an, solange mindestens eine Regel aktiv ist.
    daily_start_hour = fields.Float(
        string="Einschalten um",
        default=8.0,
        help="Lokale Uhrzeit, zu der das Zeitprogramm einschaltet.",
    )
    daily_end_hour = fields.Float(
        string="Ausschalten um",
        default=8.5,
        help="Lokale Uhrzeit, zu der das Zeitprogramm ausschaltet. Liegt sie vor der Einschaltzeit, läuft das Zeitfenster über Mitternacht.",
    )
    daily_monday = fields.Boolean(string="Mo", default=True)
    daily_tuesday = fields.Boolean(string="Di", default=True)
    daily_wednesday = fields.Boolean(string="Mi", default=True)
    daily_thursday = fields.Boolean(string="Do", default=True)
    daily_friday = fields.Boolean(string="Fr", default=True)
    daily_saturday = fields.Boolean(string="Sa", default=True)
    daily_sunday = fields.Boolean(string="So", default=True)

    # Projektbezogene Automatik: Das Odoo-Projekt dient als eindeutige Referenz.
    # Beginn und Ende werden bewusst in dieser App manuell gepflegt, damit auch
    # Projekte ohne passende Datetime-Felder (oder mit abweichender Projektlaufzeit)
    # exakt für die Gebäudesteuerung terminiert werden können.
    project_id = fields.Many2one(
        "project.project",
        string="Odoo-Projekt",
        ondelete="set null",
        index=True,
        help="Projekt, an dem diese Automatik hängt.",
    )
    project_template_id = fields.Many2one(
        "gl.ha.project.template",
        string="Projekt-Vorlage",
        ondelete="set null",
        domain="[('active','=',True)]",
        help="Die Vorlage kopiert Geräte, Vor-/Nachlauf und optionale Sensorbedingungen in diese Regel. Danach können alle Werte projektspezifisch angepasst werden.",
    )
    project_start_at = fields.Datetime(
        string="Projektbeginn",
        help="Manuell gepflegter Beginn des für die Gebäudesteuerung relevanten Projektzeitraums.",
    )
    project_end_at = fields.Datetime(
        string="Projektende",
        help="Manuell gepflegtes Ende. Bei Veranstaltungen über Mitternacht bitte das Folgedatum wählen, z. B. 13.02.2027 03:00.",
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

    @api.constrains(
        "source", "daily_start_hour", "daily_end_hour",
        "daily_monday", "daily_tuesday", "daily_wednesday",
        "daily_thursday", "daily_friday", "daily_saturday", "daily_sunday",
    )
    def _check_daily_timer(self):
        for rec in self:
            if rec.source != "daily":
                continue
            if not (0.0 <= rec.daily_start_hour < 24.0) or not (0.0 <= rec.daily_end_hour < 24.0):
                raise ValidationError(_("Ein- und Ausschaltzeit müssen zwischen 00:00 und 23:59 liegen."))
            if rec._hour_to_minutes(rec.daily_start_hour) == rec._hour_to_minutes(rec.daily_end_hour):
                raise ValidationError(_("Ein- und Ausschaltzeit dürfen beim täglichen Zeitprogramm nicht identisch sein."))
            if not any(rec._daily_weekday_flags()):
                raise ValidationError(_("Bitte mindestens einen Wochentag für das tägliche Zeitprogramm auswählen."))

    @api.constrains("target_entity_ids", "target_entity_id")
    def _check_target_entities(self):
        for rec in self:
            if not rec.target_entity_ids and not rec.target_entity_id:
                raise ValidationError(_("Bitte mindestens eine zu schaltende Entität auswählen."))

    @api.constrains("source", "project_id", "project_start_at", "project_end_at")
    def _check_project_timer(self):
        for rec in self:
            if rec.source != "project":
                continue
            if not rec.project_id:
                raise ValidationError(_("Bitte für die Projekt-Automatik ein Odoo-Projekt auswählen."))
            if not rec.project_start_at or not rec.project_end_at:
                raise ValidationError(_("Bitte Projektbeginn und Projektende vollständig eintragen."))
            if fields.Datetime.to_datetime(rec.project_end_at) <= fields.Datetime.to_datetime(rec.project_start_at):
                raise ValidationError(_("Das Projektende muss nach dem Projektbeginn liegen. Bei Ende nach Mitternacht bitte das Folgedatum auswählen."))

    @api.onchange("project_template_id")
    def _onchange_project_template_id(self):
        for rec in self:
            template = rec.project_template_id
            if not template:
                continue
            rec.target_entity_ids = template.target_entity_ids
            rec.minutes_before = template.minutes_before
            rec.minutes_after = template.minutes_after
            rec.condition_entity_ids = template.condition_entity_ids
            rec.condition_match_mode = template.condition_match_mode
            rec.condition_operator = template.condition_operator
            rec.condition_threshold = template.condition_threshold

    @api.onchange("project_id")
    def _onchange_project_id(self):
        for rec in self:
            if rec.project_id and not rec.name:
                rec.name = _("Projekt – %s") % rec.project_id.display_name

    @api.model
    def _timezone(self, config=None):
        config = config or self.env["gl.ha.config"].sudo().get_config()
        try:
            return pytz.timezone(config.timezone_name or "Europe/Berlin")
        except Exception:
            return pytz.timezone("Europe/Berlin")

    @api.model
    def _hour_to_minutes(self, value):
        # float_time speichert z. B. 08:30 als 8.5. Auf die nächste Minute
        # runden, damit die minütliche Automatik exakt und stabil arbeitet.
        return max(0, min(1439, int(round(float(value or 0.0) * 60))))

    def _daily_weekday_flags(self):
        self.ensure_one()
        return (
            self.daily_monday, self.daily_tuesday, self.daily_wednesday,
            self.daily_thursday, self.daily_friday, self.daily_saturday,
            self.daily_sunday,
        )

    def _daily_enabled_on(self, local_date):
        self.ensure_one()
        return bool(self._daily_weekday_flags()[local_date.weekday()])

    @api.model
    def _safe_localize(self, tz, value):
        try:
            return tz.localize(value, is_dst=None)
        except Exception:
            # Für seltene DST-Sonderfälle einen deterministischen Zeitpunkt
            # wählen. Normale Tageszeiten wie 08:00 sind davon nicht betroffen.
            return tz.localize(value, is_dst=False)

    def _daily_period_for_date(self, local_date, config=None):
        """UTC-naiven Start/Endzeitpunkt für einen lokalen Starttag liefern."""
        self.ensure_one()
        if self.source != "daily" or not self._daily_enabled_on(local_date):
            return None
        tz = self._timezone(config)
        start_minute = self._hour_to_minutes(self.daily_start_hour)
        end_minute = self._hour_to_minutes(self.daily_end_hour)
        start_local = self._safe_localize(
            tz, datetime.combine(local_date, time(start_minute // 60, start_minute % 60))
        )
        end_date = local_date + timedelta(days=1) if end_minute <= start_minute else local_date
        end_local = self._safe_localize(
            tz, datetime.combine(end_date, time(end_minute // 60, end_minute % 60))
        )
        return (
            start_local.astimezone(pytz.UTC).replace(tzinfo=None),
            end_local.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    def _daily_days_label(self):
        self.ensure_one()
        flags = self._daily_weekday_flags()
        if all(flags):
            return _("Täglich")
        names = [_('Mo'), _('Di'), _('Mi'), _('Do'), _('Fr'), _('Sa'), _('So')]
        return ", ".join(name for name, enabled in zip(names, flags) if enabled)

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

    def _window_active(self, now, config=None):
        self.ensure_one()
        now = fields.Datetime.to_datetime(now)
        if self.source == "daily":
            tz = self._timezone(config)
            aware_utc = pytz.UTC.localize(now) if now.tzinfo is None else now.astimezone(pytz.UTC)
            local_today = aware_utc.astimezone(tz).date()
            # Vortag mitprüfen, damit Zeitprogramme über Mitternacht (z. B.
            # 23:00–01:00) nach 00:00 weiterhin korrekt aktiv bleiben.
            for start_day in (local_today - timedelta(days=1), local_today):
                period = self._daily_period_for_date(start_day, config)
                if period and period[0] <= now <= period[1]:
                    return True
            return False

        if self.source == "project":
            if not self.project_id or not self.project_start_at or not self.project_end_at:
                return False
            if "active" in self.project_id._fields and not self.project_id.active:
                return False
            effective_start = fields.Datetime.to_datetime(self.project_start_at) - timedelta(minutes=self.minutes_before)
            effective_end = fields.Datetime.to_datetime(self.project_end_at) + timedelta(minutes=self.minutes_after)
            return effective_start <= now <= effective_end

        return bool(self.env["gl.ha.schedule.window"].sudo().search_count([
            ("source", "=", self.source),
            ("start_at", "<=", now + timedelta(minutes=self.minutes_before)),
            ("end_at", ">=", now - timedelta(minutes=self.minutes_after)),
        ]))

    @api.model
    def dashboard_plan(self, config=None, now=None, hours=24):
        """Berechnet die *effektiven* Schaltzeiten für die Dashboard-Vorschau.

        Anders als ``gl.ha.schedule.window`` zeigt diese Methode nicht nur die
        Roh-Zeitfenster von Kino/Event, sondern berücksichtigt pro Regel den
        Vor- und Nachlauf sowie tägliche Zeitprogramme und ordnet das Ergebnis
        den tatsächlich geschalteten Entitäten zu. Mehrere Regeln derselben Entität werden pro
        lokalem Kalendertag zu genau einer übersichtlichen Zeile verdichtet.
        Die einzelnen Beiträge bleiben als aufklappbare Details erhalten.
        """
        config = config or self.env["gl.ha.config"].sudo().get_config()
        now = fields.Datetime.to_datetime(now or fields.Datetime.now())
        hours = max(1, int(hours or 24))
        horizon_end = now + timedelta(hours=hours)

        rules = self.sudo().search([("active", "=", True)], order="sequence, id")
        if not rules:
            return []

        schedule_rules = rules.filtered(lambda r: r.source in ("event", "cinema"))
        max_before = max([r.minutes_before for r in schedule_rules] or [0])
        max_after = max([r.minutes_after for r in schedule_rules] or [0])
        windows = self.env["gl.ha.schedule.window"].sudo().search([
            ("start_at", "<=", horizon_end + timedelta(minutes=max_before)),
            ("end_at", ">=", now - timedelta(minutes=max_after)),
            ("source", "in", ["event", "cinema"]),
        ], order="start_at, source, name")
        windows_by_source = defaultdict(list)
        for window in windows:
            windows_by_source[window.source].append(window)

        local_tz = self._timezone(config)

        def local_day(value):
            value = fields.Datetime.to_datetime(value)
            aware = pytz.UTC.localize(value) if value.tzinfo is None else value.astimezone(pytz.UTC)
            return aware.astimezone(local_tz).date().isoformat()

        grouped = {}

        def add_detail(rule, targets, day, start_at, end_at, source, source_name, source_details):
            if end_at < now or start_at > horizon_end:
                return
            condition_count = len(rule._condition_entities())
            for target in targets:
                key = (day, target.id)
                group = grouped.setdefault(key, {
                    "date": day,
                    "target_id": target.id,
                    "target_name": target.name,
                    "details": [],
                })
                group["details"].append({
                    "source": source,
                    "source_name": source_name or "",
                    "source_details": source_details or "",
                    "rule_name": rule.name or "",
                    "start_at": start_at,
                    "end_at": end_at,
                    "condition_count": condition_count,
                })

        aware_now = pytz.UTC.localize(now) if now.tzinfo is None else now.astimezone(pytz.UTC)
        aware_horizon = pytz.UTC.localize(horizon_end) if horizon_end.tzinfo is None else horizon_end.astimezone(pytz.UTC)
        first_local_day = aware_now.astimezone(local_tz).date() - timedelta(days=1)
        last_local_day = aware_horizon.astimezone(local_tz).date()

        for rule in rules:
            targets = rule._target_entities().filtered(lambda entity: entity.active)
            if not targets:
                continue

            if rule.source == "daily":
                day_cursor = first_local_day
                while day_cursor <= last_local_day:
                    period = rule._daily_period_for_date(day_cursor, config)
                    if period:
                        start_at, end_at = period
                        add_detail(
                            rule, targets, day_cursor.isoformat(), start_at, end_at,
                            "daily", _("Zeitprogramm"), rule._daily_days_label(),
                        )
                    day_cursor += timedelta(days=1)
                continue

            if rule.source == "project":
                if not rule.project_id or not rule.project_start_at or not rule.project_end_at:
                    continue
                if "active" in rule.project_id._fields and not rule.project_id.active:
                    continue
                effective_start = fields.Datetime.to_datetime(rule.project_start_at) - timedelta(minutes=rule.minutes_before)
                effective_end = fields.Datetime.to_datetime(rule.project_end_at) + timedelta(minutes=rule.minutes_after)
                template_detail = _("Odoo-Projekt")
                if rule.project_template_id:
                    template_detail += _(" · Vorlage: %s") % rule.project_template_id.name
                add_detail(
                    rule, targets, local_day(effective_start), effective_start, effective_end,
                    "project", rule.project_id.display_name or _("Projekt"), template_detail,
                )
                continue

            for window in windows_by_source.get(rule.source, []):
                effective_start = fields.Datetime.to_datetime(window.start_at) - timedelta(minutes=rule.minutes_before)
                effective_end = fields.Datetime.to_datetime(window.end_at) + timedelta(minutes=rule.minutes_after)
                add_detail(
                    rule, targets, local_day(effective_start), effective_start, effective_end,
                    window.source, window.name or "", window.details or "",
                )

        result = []
        for group in grouped.values():
            details = sorted(group["details"], key=lambda item: (item["start_at"], item["end_at"], item["source"]))
            # Schaltphasen zusammenführen. So bleibt sichtbar, wenn innerhalb
            # eines Tages tatsächlich eine AUS-Lücke zwischen zwei Regeln liegt.
            phases = []
            for detail in details:
                start = detail["start_at"]
                end = detail["end_at"]
                if not phases or start > phases[-1][1]:
                    phases.append([start, end])
                elif end > phases[-1][1]:
                    phases[-1][1] = end

            active_now = any(start <= now <= end for start, end in phases)
            group_start = phases[0][0]
            group_end = phases[-1][1]
            result.append({
                "date": group["date"],
                "target_id": group["target_id"],
                "target_name": group["target_name"],
                "status": "active" if active_now else "planned",
                "start_at": fields.Datetime.to_string(group_start),
                "end_at": fields.Datetime.to_string(group_end),
                "phase_count": len(phases),
                "phases": [{
                    "start_at": fields.Datetime.to_string(start),
                    "end_at": fields.Datetime.to_string(end),
                } for start, end in phases],
                "details": [{
                    **{key: value for key, value in detail.items() if key not in ("start_at", "end_at")},
                    "start_at": fields.Datetime.to_string(detail["start_at"]),
                    "end_at": fields.Datetime.to_string(detail["end_at"]),
                } for detail in details],
            })

        result.sort(key=lambda item: (item["start_at"], item["target_name"].lower(), item["target_id"]))
        return result

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
                window = rule._window_active(now, config)
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
