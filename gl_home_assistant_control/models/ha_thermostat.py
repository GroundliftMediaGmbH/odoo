# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


THERMOSTAT_SOURCE_SELECTION = [
    ("event", "Groundlift Veranstaltung"),
    ("cinema", "Kinobetrieb"),
    ("project_event", "Projekt Theater / Veranstaltung"),
    ("project_cinema", "Projekt Kino"),
    ("project_lounge", "Projekt Lounge"),
    ("project_podcast", "Projekt Podcaststudio"),
]


class GlHaHeatingSystem(models.Model):
    _name = "gl.ha.heating.system"
    _description = "Home Assistant Heizsystem"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    pump_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Heizungspumpe",
        required=True,
        ondelete="restrict",
        domain="[('control_type','=','toggle'),('controllable','=',True),('active','=',True)]",
        help="Gemeinsame Pumpe dieses Heizsystems. Sie läuft nur, wenn mindestens eine aktive Thermostat-Zone Wärme anfordert.",
    )
    zone_ids = fields.One2many("gl.ha.thermostat.zone", "heating_system_id", string="Thermostat-Zonen")

    _pump_unique = models.Constraint(
        "UNIQUE(pump_entity_id)",
        "Eine Heizungspumpe kann nur einem Heizsystem zugeordnet werden.",
    )


class GlHaThermostatZone(models.Model):
    _name = "gl.ha.thermostat.zone"
    _description = "Home Assistant Raumthermostat"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    heating_system_id = fields.Many2one(
        "gl.ha.heating.system",
        string="Heizsystem / gemeinsame Pumpe",
        required=True,
        ondelete="restrict",
        domain="[('active','=',True)]",
    )
    temperature_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Ist-Temperatur",
        required=True,
        ondelete="restrict",
        domain="[('active','=',True),('has_numeric_value','=',True)]",
        help="Temperatursensor des Raums.",
    )
    valve_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Heizungsventil / Thermostat-Relais",
        required=True,
        ondelete="restrict",
        domain="[('control_type','=','toggle'),('controllable','=',True),('active','=',True)]",
        help="Relais, das den Heizkreis bzw. den Thermostat des Raums öffnet und schließt.",
    )
    ventilation_entity_id = fields.Many2one(
        "gl.ha.entity",
        string="Lüftung bei Heizanforderung",
        ondelete="restrict",
        domain="[('control_type','=','toggle'),('controllable','=',True),('active','=',True)]",
        help="Optional. Bei Wärmebedarf wird die Lüftung zusätzlich eingeschaltet. Beim Ende der Heizanforderung bleibt sie an, wenn eine andere Automatik (z. B. Veranstaltung/Kino) sie weiterhin benötigt.",
    )

    base_setpoint = fields.Float(
        string="Grundtemperatur außerhalb von Zeitslots",
        default=17.0,
        required=True,
        help="Solltemperatur, wenn kein verknüpfter Veranstaltungs-, Kino- oder Projekt-Zeitslot aktiv ist.",
    )
    hysteresis = fields.Float(
        string="Temperatur-Hysterese (K)",
        default=0.5,
        required=True,
        help="Gesamte Schaltdifferenz um den Sollwert. Bei 0,5 K und Soll 22,0 °C: EIN bei <= 21,75 °C, AUS bei >= 22,25 °C.",
    )
    min_setpoint = fields.Float(string="Minimaler Sollwert", default=10.0, required=True)
    max_setpoint = fields.Float(string="Maximaler Sollwert", default=28.0, required=True)
    dashboard_step = fields.Float(string="Dashboard-Schritt (°C)", default=0.5, required=True)

    profile_ids = fields.One2many(
        "gl.ha.thermostat.profile",
        "zone_id",
        string="Solltemperaturen nach Zeitslot",
        copy=True,
    )

    manual_setpoint = fields.Float(string="Manueller Sollwert", copy=False)
    manual_override_until = fields.Datetime(string="Manuelle Temperatur bis", readonly=True, copy=False)

    heat_demand = fields.Boolean(string="Wärmeanforderung", readonly=True, copy=False)
    last_temperature = fields.Float(string="Letzte Ist-Temperatur", readonly=True, copy=False)
    last_effective_setpoint = fields.Float(string="Letzter wirksamer Sollwert", readonly=True, copy=False)
    last_setpoint_source = fields.Char(string="Sollwert-Quelle", readonly=True, copy=False)
    last_evaluated_at = fields.Datetime(string="Zuletzt ausgewertet", readonly=True, copy=False)
    last_message = fields.Char(string="Letzte Meldung", readonly=True, copy=False)

    _temperature_unique = models.Constraint(
        "UNIQUE(temperature_entity_id)",
        "Ein Temperatursensor kann nur einer Thermostat-Zone zugeordnet werden.",
    )
    _valve_unique = models.Constraint(
        "UNIQUE(valve_entity_id)",
        "Ein Heizungsventil kann nur einer Thermostat-Zone zugeordnet werden.",
    )

    @api.constrains("base_setpoint", "min_setpoint", "max_setpoint", "hysteresis", "dashboard_step")
    def _check_temperature_values(self):
        for rec in self:
            if rec.min_setpoint >= rec.max_setpoint:
                raise ValidationError(_("Der minimale Sollwert muss unter dem maximalen Sollwert liegen."))
            if not (rec.min_setpoint <= rec.base_setpoint <= rec.max_setpoint):
                raise ValidationError(_("Die Grundtemperatur muss innerhalb des erlaubten Sollwertbereichs liegen."))
            if rec.hysteresis < 0:
                raise ValidationError(_("Die Temperatur-Hysterese darf nicht negativ sein."))
            if rec.dashboard_step <= 0:
                raise ValidationError(_("Der Dashboard-Schritt muss größer als 0 sein."))

    @api.constrains("temperature_entity_id", "valve_entity_id", "ventilation_entity_id", "heating_system_id")
    def _check_distinct_entities(self):
        for rec in self:
            ids = [
                rec.temperature_entity_id.id,
                rec.valve_entity_id.id,
                rec.ventilation_entity_id.id if rec.ventilation_entity_id else False,
                rec.heating_system_id.pump_entity_id.id if rec.heating_system_id else False,
            ]
            real = [value for value in ids if value]
            if len(real) != len(set(real)):
                raise ValidationError(_("Temperatursensor, Heizungsventil, Lüftung und Heizungspumpe müssen unterschiedliche Entitäten sein."))

    def _clamp_setpoint(self, value):
        self.ensure_one()
        return min(float(self.max_setpoint), max(float(self.min_setpoint), float(value)))

    def _profile_window(self, profile, now):
        self.ensure_one()
        now = fields.Datetime.to_datetime(now)
        domain = [
            ("source", "=", profile.source),
            ("start_at", "<=", now + timedelta(minutes=max(0, profile.minutes_before))),
            ("end_at", ">=", now - timedelta(minutes=max(0, profile.minutes_after))),
        ]
        if profile.room_id:
            domain.append(("room_code", "=", profile.room_id.code))
        elif profile.source == "cinema":
            # Ohne expliziten Saal wird bewusst das etablierte, globale Kino-
            # Tagesfenster verwendet und nicht eines der zusätzlichen Saalfenster.
            domain.append(("room_code", "=", False))
        windows = self.env["gl.ha.schedule.window"].sudo().search(domain, order="start_at asc")
        for window in windows:
            start = fields.Datetime.to_datetime(window.start_at) - timedelta(minutes=max(0, profile.minutes_before))
            end = fields.Datetime.to_datetime(window.end_at) + timedelta(minutes=max(0, profile.minutes_after))
            if start <= now <= end:
                return window
        return self.env["gl.ha.schedule.window"].sudo().browse([])

    def _effective_setpoint_info(self, now=None, persist_expiry=False):
        self.ensure_one()
        now = fields.Datetime.to_datetime(now or fields.Datetime.now())
        if self.manual_override_until:
            until = fields.Datetime.to_datetime(self.manual_override_until)
            if until > now:
                return self._clamp_setpoint(self.manual_setpoint), _("Manuell"), False
            if persist_expiry:
                self.sudo().write({"manual_override_until": False})

        active_profiles = []
        for profile in self.profile_ids.filtered(lambda p: p.active):
            window = self._profile_window(profile, now)
            if window:
                active_profiles.append((profile, window))
        if active_profiles:
            # Bei Überlappungen gilt die höchste gewünschte Temperatur. Das ist
            # für parallel laufende Nutzungen deterministisch und verhindert,
            # dass ein niedrigerer Slot einen höheren Komfortbedarf aushebelt.
            profile, window = max(active_profiles, key=lambda pair: (pair[0].setpoint, pair[0].priority, -pair[0].id))
            label = profile.display_name or dict(THERMOSTAT_SOURCE_SELECTION).get(profile.source, profile.source)
            if window.name:
                label = _("%(profile)s · %(window)s") % {"profile": label, "window": window.name}
            return self._clamp_setpoint(profile.setpoint), label, window

        return self._clamp_setpoint(self.base_setpoint), _("Grundtemperatur"), False

    def dashboard_setpoint_info(self, now=None):
        self.ensure_one()
        setpoint, source, _window = self._effective_setpoint_info(now=now, persist_expiry=False)
        return setpoint, source

    def dashboard_command(self, command, value=None, override_minutes=None):
        self.ensure_one()
        config = self.env["gl.ha.config"].sudo().get_config()
        now = fields.Datetime.now()
        if command == "auto":
            self.sudo().write({"manual_override_until": False})
            return True

        current, _source, _window = self._effective_setpoint_info(now=now, persist_expiry=True)
        if command == "adjust":
            value = current + float(value or 0.0)
        elif command == "set":
            if value is None:
                raise UserError(_("Für den Thermostat ist ein Sollwert erforderlich."))
            value = float(value)
        else:
            raise UserError(_("Ungültiger Thermostat-Befehl."))

        value = self._clamp_setpoint(value)
        if override_minutes is None:
            override_minutes = config.default_manual_override_minutes
        override_minutes = max(0, int(override_minutes or 0))
        vals = {"manual_setpoint": value}
        vals["manual_override_until"] = now + timedelta(minutes=override_minutes) if override_minutes else False
        self.sudo().write(vals)
        return True

    @api.model
    def automation_intents(self, now=None):
        """Sollzustände der Raumthermostate für den zentralen OR-Automatiklauf.

        Rückgabe je Zielentität: ``wants_on`` wird mit bestehenden Automatikregeln
        ODER-verknüpft. Dadurch kann die Lüftung beim Heizen eingeschaltet werden,
        wird nach Ende des Heizbedarfs aber nicht ausgeschaltet, solange z. B. eine
        Veranstaltungs- oder Kinoregel sie weiterhin benötigt.
        """
        now = fields.Datetime.to_datetime(now or fields.Datetime.now())
        intents = defaultdict(lambda: {"wants_on": False, "hold": False, "exclusive": False, "messages": []})
        zones = self.sudo().search([], order="sequence, id")
        active_systems = set()

        for zone in zones:
            system = zone.heating_system_id
            if system:
                active_systems.add(system.id)
            demand = False
            temp = None
            setpoint, source, _window = zone._effective_setpoint_info(now=now, persist_expiry=True)
            sensor = zone.temperature_entity_id

            if not zone.active or not system or not system.active:
                message = _("Thermostat deaktiviert")
            elif not sensor or not sensor.active or not sensor.is_available or not sensor.has_numeric_value:
                message = _("Temperatursensor nicht verfügbar – Heizanforderung aus Sicherheitsgründen AUS")
            else:
                temp = float(sensor.numeric_value)
                half = max(0.0, float(zone.hysteresis or 0.0)) / 2.0
                if zone.heat_demand:
                    demand = temp < (setpoint + half)
                else:
                    demand = temp <= (setpoint - half)
                message = _("Ist %(temp).1f °C / Soll %(setpoint).1f °C · %(state)s · %(source)s") % {
                    "temp": temp,
                    "setpoint": setpoint,
                    "state": _("Wärmeanforderung") if demand else _("kein Wärmebedarf"),
                    "source": source,
                }

            vals = {
                "heat_demand": demand,
                "last_effective_setpoint": setpoint,
                "last_setpoint_source": source,
                "last_evaluated_at": now,
                "last_message": message,
            }
            if temp is not None:
                vals["last_temperature"] = temp
            zone.sudo().write(vals)

            # Das Raumventil wird ausschließlich durch diese Zone angefordert.
            if zone.valve_entity_id:
                intent = intents[zone.valve_entity_id.id]
                intent["exclusive"] = True
                intent["wants_on"] = intent["wants_on"] or demand
                intent["messages"].append(_("%(zone)s Ventil: %(state)s") % {
                    "zone": zone.name,
                    "state": _("EIN") if demand else _("AUS"),
                })

            # Lüftung: Heizbedarf ist nur eine weitere EIN-Anforderung. Andere
            # Automatikregeln bleiben im zentralen Aggregator gleichberechtigt.
            if zone.ventilation_entity_id:
                intent = intents[zone.ventilation_entity_id.id]
                intent["wants_on"] = intent["wants_on"] or demand
                intent["messages"].append(_("%(zone)s Heizen/Lüftung: %(state)s") % {
                    "zone": zone.name,
                    "state": _("EIN") if demand else _("kein Heizbedarf"),
                })

            if system and system.pump_entity_id:
                intent = intents[system.pump_entity_id.id]
                intent["exclusive"] = True
                intent["wants_on"] = intent["wants_on"] or demand
                intent["messages"].append(_("%(zone)s: %(state)s") % {
                    "zone": zone.name,
                    "state": _("Wärmeanforderung") if demand else _("kein Bedarf"),
                })

        # Heizsysteme ohne (aktive) Zone bekommen ebenfalls einen definierten
        # AUS-Wunsch, damit eine ehemals laufende gemeinsame Pumpe nicht hängen bleibt.
        for system in self.env["gl.ha.heating.system"].sudo().search([]):
            if system.pump_entity_id:
                intents[system.pump_entity_id.id]["exclusive"] = True
        return dict(intents)


class GlHaThermostatProfile(models.Model):
    _name = "gl.ha.thermostat.profile"
    _description = "Thermostat Solltemperatur nach Zeitquelle"
    _order = "priority desc, id"

    zone_id = fields.Many2one("gl.ha.thermostat.zone", required=True, ondelete="cascade", index=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(default=10)
    name = fields.Char(string="Bezeichnung")
    source = fields.Selection(THERMOSTAT_SOURCE_SELECTION, string="Zeitquelle", required=True, default="event")
    room_id = fields.Many2one(
        "gl.ha.project.room",
        string="Raum / Kinosaal",
        domain="[('active','=',True)]",
        help="Optionaler Raumfilter. Für Kino 1/Kino 2 kann damit nur der jeweilige Saal berücksichtigt werden. Leer bedeutet die gesamte Quelle.",
    )
    setpoint = fields.Float(string="Solltemperatur", default=22.0, required=True)
    minutes_before = fields.Integer(string="Vorlauf (Min.)", default=0)
    minutes_after = fields.Integer(string="Nachlauf (Min.)", default=0)

    @api.depends("name", "source", "room_id", "setpoint")
    def _compute_display_name(self):
        labels = dict(THERMOSTAT_SOURCE_SELECTION)
        for rec in self:
            if rec.name:
                rec.display_name = rec.name
            else:
                label = labels.get(rec.source, rec.source or _("Zeitslot"))
                if rec.room_id:
                    label += " · " + rec.room_id.name
                rec.display_name = _("%(source)s → %(temp).1f °C") % {"source": label, "temp": rec.setpoint}

    @api.constrains("setpoint", "minutes_before", "minutes_after", "zone_id")
    def _check_profile(self):
        for rec in self:
            if rec.minutes_before < 0 or rec.minutes_after < 0:
                raise ValidationError(_("Vor- und Nachlauf dürfen nicht negativ sein."))
            if rec.zone_id and not (rec.zone_id.min_setpoint <= rec.setpoint <= rec.zone_id.max_setpoint):
                raise ValidationError(_("Die Solltemperatur des Zeitslots liegt außerhalb des erlaubten Bereichs der Thermostat-Zone."))
