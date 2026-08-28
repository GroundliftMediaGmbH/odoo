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

    solar_clear_before_minutes = fields.Integer(
        string="Sonnenzeit: Vorlauf bei wenig Bewölkung (Min.)",
        default=60,
        help="Wenn Sonnenauf- oder -untergang gewählt ist, wird frühestens ab diesem Abstand vor der Sonnenzeit eingeschaltet.",
    )
    solar_cloudy_before_minutes = fields.Integer(
        string="Sonnenzeit: Vorlauf bei Bewölkung (Min.)",
        default=90,
        help="Wird zusätzlich 'Wetter: Bewölkung' gewählt und der Bewölkungsgrenzwert erreicht, gilt dieser frühere Vorlauf.",
    )
    solar_cloud_threshold = fields.Float(
        string="Ab Bewölkung (%)",
        default=60.0,
        help="Ab diesem prognostizierten Bewölkungsgrad an der Sonnenzeit gilt der Bewölkungs-Vorlauf.",
    )
    has_solar_condition = fields.Boolean(compute="_compute_weather_condition_flags")
    has_cloud_condition = fields.Boolean(compute="_compute_weather_condition_flags")
    has_generic_condition = fields.Boolean(compute="_compute_weather_condition_flags")
    solar_latched_anchor = fields.Datetime(string="Sonnen-Trigger Anker", readonly=True)
    solar_latched_until = fields.Datetime(string="Sonnen-Trigger aktiv bis", readonly=True)

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
        self.env.cr.execute("""
            UPDATE gl_ha_automation_rule
               SET solar_clear_before_minutes = 60
             WHERE solar_clear_before_minutes IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_automation_rule
               SET solar_cloudy_before_minutes = 90
             WHERE solar_cloudy_before_minutes IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_automation_rule
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

    @api.constrains("condition_entity_ids", "condition_entity_id")
    def _check_solar_sensor_selection(self):
        for rec in self:
            solar = rec._weather_condition_entities().filtered(lambda e: e.weather_metric in ("sunrise", "sunset"))
            if len(solar) > 1:
                raise ValidationError(_("Bitte pro Automatikregel nur Sonnenaufgang oder Sonnenuntergang auswählen, nicht beides gleichzeitig."))

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
            rec.solar_clear_before_minutes = template.solar_clear_before_minutes
            rec.solar_cloudy_before_minutes = template.solar_cloudy_before_minutes
            rec.solar_cloud_threshold = template.solar_cloud_threshold

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

    def _weather_condition_entities(self):
        self.ensure_one()
        return self._condition_entities().filtered(lambda entity: entity.source_type == "weather")

    def _solar_condition_entities(self):
        self.ensure_one()
        return self._weather_condition_entities().filtered(
            lambda entity: entity.weather_metric in ("sunrise", "sunset")
        )

    def _solar_metric(self):
        self.ensure_one()
        solar = self._solar_condition_entities()
        return solar[:1].weather_metric if solar else False

    def _has_cloud_weather_sensor(self):
        self.ensure_one()
        return bool(self._weather_condition_entities().filtered(lambda entity: entity.weather_metric == "cloud_cover"))

    def _generic_condition_entities(self):
        """Sensoren, die mit Operator/Grenzwert ausgewertet werden.

        Sonnenauf/-untergang sind Zeitanker und keine normalen Grenzwert-Sensoren.
        Bewölkung wird bei aktivem Sonnenanker zur Wahl des Sonnen-Vorlaufs
        verwendet; ohne Sonnenanker bleibt sie ein normaler %-Messsensor.
        """
        self.ensure_one()
        solar_active = bool(self._solar_condition_entities())
        return self._condition_entities().filtered(
            lambda entity: not (
                entity.source_type == "weather"
                and (
                    entity.weather_metric in ("sunrise", "sunset")
                    or (solar_active and entity.weather_metric == "cloud_cover")
                )
            )
        )

    @api.depends("condition_entity_ids", "condition_entity_id")
    def _compute_weather_condition_flags(self):
        for rec in self:
            rec.has_solar_condition = bool(rec._solar_condition_entities())
            rec.has_cloud_condition = rec._has_cloud_weather_sensor()
            rec.has_generic_condition = bool(rec._generic_condition_entities())

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
        """Dreiwertige Auswertung für normale optionale Messsensoren.

        Sonnenzeit-Sensoren werden separat in der Zeitfensterlogik ausgewertet.
        Ist Bewölkung zusammen mit Sonnenauf/-untergang gewählt, dient sie nur
        zur Auswahl des klaren/bewölkten Sonnen-Vorlaufs.
        """
        self.ensure_one()
        sensors = self._generic_condition_entities()
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

    def _nearest_cloud_cover(self, weather_data, local_dt):
        self.ensure_one()
        cloud_map = (weather_data or {}).get("hourly_cloud_cover") or {}
        if not cloud_map:
            return None
        # Open-Meteo liefert stündliche lokale Zeitstempel. Auf die nächstgelegene
        # volle Stunde runden, damit z. B. Sonnenuntergang 20:13 die 20-Uhr-
        # Prognose nutzt.
        rounded = local_dt.replace(minute=0, second=0, microsecond=0)
        if local_dt.minute >= 30:
            rounded += timedelta(hours=1)
        key = rounded.strftime("%Y-%m-%dT%H:00")
        value = cloud_map.get(key)
        if value is not None:
            return float(value)

        # Robuster Fallback bei abweichendem Zeitformat im API-Response.
        best = None
        best_delta = None
        for time_value, cloud in cloud_map.items():
            try:
                candidate = datetime.fromisoformat(str(time_value))
                if candidate.tzinfo is None:
                    candidate = local_dt.tzinfo.localize(candidate) if hasattr(local_dt.tzinfo, "localize") else candidate.replace(tzinfo=local_dt.tzinfo)
                delta = abs((candidate - local_dt).total_seconds())
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best = float(cloud)
            except Exception:
                continue
        return best

    def _solar_trigger_for_anchor(self, anchor_start, config, weather_data=None):
        """UTC-naiven Sonnen-Trigger für den lokalen Tag des Quellbeginns liefern.

        Rückgabe: (trigger, unknown, detail)
        """
        self.ensure_one()
        metric = self._solar_metric()
        if not metric:
            return False, False, ""
        if not config.weather_enabled:
            return False, True, _("Wetter-/Sonnendaten sind in den Einstellungen deaktiviert")

        weather_data = weather_data or config.weather_snapshot(refresh_if_stale=True)
        if not weather_data:
            return False, True, _("keine Wetter-/Sonnendaten verfügbar")

        tz = self._timezone(config)
        anchor = fields.Datetime.to_datetime(anchor_start)
        aware_anchor = pytz.UTC.localize(anchor) if anchor.tzinfo is None else anchor.astimezone(pytz.UTC)
        local_date = aware_anchor.astimezone(tz).date().isoformat()
        day = (weather_data.get("days") or {}).get(local_date) or {}
        solar_value = day.get(metric)
        solar_local = config._parse_local_iso(solar_value, weather_data.get("timezone") or config.timezone_name)
        if not solar_local:
            return False, True, _("%(metric)s für %(date)s nicht verfügbar") % {
                "metric": _("Sonnenaufgang") if metric == "sunrise" else _("Sonnenuntergang"),
                "date": local_date,
            }
        solar_local = solar_local.astimezone(tz)

        cloud_cover = None
        cloudy = False
        offset = self.solar_clear_before_minutes
        if self._has_cloud_weather_sensor():
            cloud_cover = self._nearest_cloud_cover(weather_data, solar_local)
            if cloud_cover is None:
                return False, True, _("Bewölkungsprognose an der Sonnenzeit ist nicht verfügbar")
            cloudy = cloud_cover >= self.solar_cloud_threshold
            offset = self.solar_cloudy_before_minutes if cloudy else self.solar_clear_before_minutes

        trigger_local = solar_local - timedelta(minutes=offset)
        trigger_utc = trigger_local.astimezone(pytz.UTC).replace(tzinfo=None)
        metric_label = _("Sonnenaufgang") if metric == "sunrise" else _("Sonnenuntergang")
        if cloud_cover is None:
            detail = _("%(metric)s %(solar)s → %(offset)s Min. vorher (%(trigger)s)") % {
                "metric": metric_label,
                "solar": solar_local.strftime("%H:%M"),
                "offset": offset,
                "trigger": trigger_local.strftime("%H:%M"),
            }
        else:
            detail = _("%(metric)s %(solar)s · Bewölkung %(cloud).0f%% (%(kind)s) → %(offset)s Min. vorher (%(trigger)s)") % {
                "metric": metric_label,
                "solar": solar_local.strftime("%H:%M"),
                "cloud": cloud_cover,
                "kind": _("bewölkt") if cloudy else _("wenig bewölkt"),
                "offset": offset,
                "trigger": trigger_local.strftime("%H:%M"),
            }
        return trigger_utc, False, detail

    def _solar_adjusted_start(self, anchor_start, effective_start, config, weather_data=None):
        self.ensure_one()
        trigger, unknown, detail = self._solar_trigger_for_anchor(anchor_start, config, weather_data)
        if unknown:
            return effective_start, True, detail
        if trigger:
            return max(fields.Datetime.to_datetime(effective_start), trigger), False, detail
        return fields.Datetime.to_datetime(effective_start), False, detail

    def _window_result(self, now, config=None, weather_data=None, persist_solar_latch=False):
        """Zeitfenster mit optionalem Sonnenanker auswerten.

        Rückgabe: (aktiv, unbekannt, Detailtext). 'Unbekannt' wird nur gemeldet,
        wenn das normale Quell-Zeitfenster gerade aktiv wäre, aber die gewählte
        Sonnen-/Wetterinformation fehlt. Dann hält die Automatik den Ist-Zustand.
        """
        self.ensure_one()
        config = config or self.env["gl.ha.config"].sudo().get_config()
        now = fields.Datetime.to_datetime(now)

        def evaluate_period(anchor_start, effective_start, effective_end):
            anchor_start = fields.Datetime.to_datetime(anchor_start)
            effective_start = fields.Datetime.to_datetime(effective_start)
            effective_end = fields.Datetime.to_datetime(effective_end)
            if not (effective_start <= now <= effective_end):
                return False, False, ""

            # Sobald ein Sonnen-Trigger innerhalb dieses konkreten Quellfensters
            # einmal erreicht wurde, bleibt er bis zum Ende eingerastet. Dadurch
            # kann eine spätere Änderung der Bewölkungsprognose das Licht nicht
            # wieder ausschalten und anschließend erneut einschalten.
            if self._solar_metric() and self.solar_latched_anchor and self.solar_latched_until:
                latched_anchor = fields.Datetime.to_datetime(self.solar_latched_anchor)
                latched_until = fields.Datetime.to_datetime(self.solar_latched_until)
                if latched_anchor == anchor_start and now <= latched_until:
                    return True, False, _("Sonnen-Trigger bereits erreicht; bis Betriebsende eingerastet")

            adjusted_start, unknown, detail = self._solar_adjusted_start(
                anchor_start, effective_start, config, weather_data
            )
            if unknown:
                return False, True, detail
            if adjusted_start >= effective_end:
                return False, False, detail + " · " + _("Sonnen-Trigger liegt nach dem Betriebsende")
            active = adjusted_start <= now <= effective_end
            if active and persist_solar_latch and self._solar_metric():
                self.sudo().write({
                    "solar_latched_anchor": anchor_start,
                    "solar_latched_until": effective_end,
                })
                detail = (detail + " · " if detail else "") + _("Sonnen-Trigger erreicht und bis Betriebsende eingerastet")
            return active, False, detail

        if self.source == "daily":
            tz = self._timezone(config)
            aware_utc = pytz.UTC.localize(now) if now.tzinfo is None else now.astimezone(pytz.UTC)
            local_today = aware_utc.astimezone(tz).date()
            had_unknown = False
            unknown_detail = ""
            for start_day in (local_today - timedelta(days=1), local_today):
                period = self._daily_period_for_date(start_day, config)
                if not period:
                    continue
                active, unknown, detail = evaluate_period(period[0], period[0], period[1])
                if active:
                    return True, False, detail
                if unknown:
                    had_unknown = True
                    unknown_detail = detail
            return False, had_unknown, unknown_detail

        if self.source == "project":
            if not self.project_id or not self.project_start_at or not self.project_end_at:
                return False, False, ""
            if "active" in self.project_id._fields and not self.project_id.active:
                return False, False, ""
            anchor_start = fields.Datetime.to_datetime(self.project_start_at)
            effective_start = anchor_start - timedelta(minutes=self.minutes_before)
            effective_end = fields.Datetime.to_datetime(self.project_end_at) + timedelta(minutes=self.minutes_after)
            return evaluate_period(anchor_start, effective_start, effective_end)

        windows = self.env["gl.ha.schedule.window"].sudo().search([
            ("source", "=", self.source),
            ("start_at", "<=", now + timedelta(minutes=self.minutes_before)),
            ("end_at", ">=", now - timedelta(minutes=self.minutes_after)),
        ])
        had_unknown = False
        unknown_detail = ""
        for window in windows:
            anchor_start = fields.Datetime.to_datetime(window.start_at)
            effective_start = anchor_start - timedelta(minutes=self.minutes_before)
            effective_end = fields.Datetime.to_datetime(window.end_at) + timedelta(minutes=self.minutes_after)
            active, unknown, detail = evaluate_period(anchor_start, effective_start, effective_end)
            if active:
                return True, False, detail
            if unknown:
                had_unknown = True
                unknown_detail = detail
        return False, had_unknown, unknown_detail

    def _window_active(self, now, config=None, weather_data=None):
        self.ensure_one()
        active, unknown, _detail = self._window_result(now, config, weather_data)
        return active and not unknown


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

        weather_needed = any(bool(rule._weather_condition_entities()) for rule in rules)
        weather_data = config.weather_snapshot(refresh_if_stale=True) if weather_needed else {}

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
                        base_start, end_at = period
                        start_at, solar_unknown, solar_detail = rule._solar_adjusted_start(
                            base_start, base_start, config, weather_data
                        )
                        if start_at >= end_at:
                            day_cursor += timedelta(days=1)
                            continue
                        details_text = rule._daily_days_label()
                        if solar_detail:
                            details_text += " · " + solar_detail
                        if solar_unknown:
                            details_text += " · " + _("Wetterdaten derzeit nicht verfügbar")
                        add_detail(
                            rule, targets, day_cursor.isoformat(), start_at, end_at,
                            "daily", _("Zeitprogramm"), details_text,
                        )
                    day_cursor += timedelta(days=1)
                continue

            if rule.source == "project":
                if not rule.project_id or not rule.project_start_at or not rule.project_end_at:
                    continue
                if "active" in rule.project_id._fields and not rule.project_id.active:
                    continue
                anchor_start = fields.Datetime.to_datetime(rule.project_start_at)
                effective_start = anchor_start - timedelta(minutes=rule.minutes_before)
                effective_end = fields.Datetime.to_datetime(rule.project_end_at) + timedelta(minutes=rule.minutes_after)
                effective_start, solar_unknown, solar_detail = rule._solar_adjusted_start(
                    anchor_start, effective_start, config, weather_data
                )
                if effective_start >= effective_end:
                    continue
                template_detail = _("Odoo-Projekt")
                if rule.project_template_id:
                    template_detail += _(" · Vorlage: %s") % rule.project_template_id.name
                if solar_detail:
                    template_detail += " · " + solar_detail
                if solar_unknown:
                    template_detail += " · " + _("Wetterdaten derzeit nicht verfügbar")
                add_detail(
                    rule, targets, local_day(effective_start), effective_start, effective_end,
                    "project", rule.project_id.display_name or _("Projekt"), template_detail,
                )
                continue

            for window in windows_by_source.get(rule.source, []):
                anchor_start = fields.Datetime.to_datetime(window.start_at)
                effective_start = anchor_start - timedelta(minutes=rule.minutes_before)
                effective_end = fields.Datetime.to_datetime(window.end_at) + timedelta(minutes=rule.minutes_after)
                effective_start, solar_unknown, solar_detail = rule._solar_adjusted_start(
                    anchor_start, effective_start, config, weather_data
                )
                if effective_start >= effective_end:
                    continue
                source_details = window.details or ""
                if solar_detail:
                    source_details = (source_details + " · " if source_details else "") + solar_detail
                if solar_unknown:
                    source_details = (source_details + " · " if source_details else "") + _("Wetterdaten derzeit nicht verfügbar")
                add_detail(
                    rule, targets, local_day(effective_start), effective_start, effective_end,
                    window.source, window.name or "", source_details,
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

        weather_needed = any(bool(rule._weather_condition_entities()) for rule in rules)
        weather_data = config.weather_snapshot(refresh_if_stale=True) if weather_needed else {}

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
                window, window_unknown, window_detail = rule._window_result(
                    now, config, weather_data, persist_solar_latch=True
                )
                condition, condition_unknown = rule._condition_result()
                desired = window and condition
                wants_on = wants_on or desired
                # Bei fehlenden Sonnen-/Wetterdaten innerhalb eines grundsätzlich
                # aktiven Quellfensters oder bei unklarer normaler Sensorbedingung
                # wird der aktuelle Schaltzustand gehalten.
                hold_current = hold_current or bool(window_unknown or (window and condition_unknown))
                sensor_count = len(rule._condition_entities())
                generic_count = len(rule._generic_condition_entities())
                if not generic_count:
                    condition_text = _("keine zusätzliche Grenzwertbedingung") if sensor_count else _("keine Sensorbedingung")
                elif condition_unknown:
                    condition_text = _("nicht vollständig verfügbar")
                else:
                    condition_text = _("ja") if condition else _("nein")
                if window_unknown:
                    window_text = _("unbekannt")
                else:
                    window_text = _("ja") if window else _("nein")
                message = _("Zeitfenster: %(window)s / Sensorbedingung (%(count)s): %(condition)s") % {
                    "window": window_text,
                    "count": sensor_count,
                    "condition": condition_text,
                }
                if window_detail:
                    message += " · " + window_detail
                rule.write({
                    "last_evaluated_at": now,
                    "last_desired_state": "hold" if (window_unknown or (window and condition_unknown)) else ("on" if desired else "off"),
                    "last_message": message,
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
