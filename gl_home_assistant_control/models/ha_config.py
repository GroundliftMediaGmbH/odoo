# -*- coding: utf-8 -*-
import json
import logging
import re
from datetime import datetime, timedelta

import pytz
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .ha_api import HomeAssistantAPI

_logger = logging.getLogger(__name__)


class GlHaConfig(models.Model):
    _name = "gl.ha.config"
    _description = "Home Assistant Einstellungen"
    _order = "id"

    name = fields.Char(default="GROUNDLIFT Home Assistant", required=True)
    active = fields.Boolean(default=True)
    base_url = fields.Char(
        string="Home Assistant URL",
        help="Von Odoo.sh erreichbare Home-Assistant-Basis-URL, vorzugsweise HTTPS.",
    )
    access_token = fields.Char(string="Long-Lived Access Token", groups="gl_home_assistant_control.group_ha_manager")
    verify_ssl = fields.Boolean(string="SSL-Zertifikat prüfen", default=True)
    extra_headers_json = fields.Text(
        string="Zusätzliche HTTP-Header (JSON)",
        groups="gl_home_assistant_control.group_ha_manager",
        help="Optional für einen vorgeschalteten sicheren Tunnel/Proxy, z. B. Service-Token-Header. JSON-Objekt mit Headername und Wert.",
    )
    request_timeout = fields.Integer(string="API-Timeout (Sek.)", default=10)
    timezone_name = fields.Char(string="Zeitzone", default="Europe/Berlin", required=True)

    state_poll_minutes = fields.Integer(string="Historienintervall (Min.)", default=5)
    history_retention_days = fields.Integer(string="Lokale Historie behalten (Tage)", default=90)
    unavailable_grace_minutes = fields.Integer(string="Warnung nach Nichterreichbarkeit (Min.)", default=3)
    default_manual_override_minutes = fields.Integer(string="Manuelle Übersteuerung (Min.)", default=120)

    schedule_horizon_days = fields.Integer(string="Zeitfenster-Vorschau (Tage)", default=14)
    event_stage_ids = fields.Many2many(
        "event.stage",
        string="Veranstaltungsphasen",
        help="Optional: Nur Veranstaltungen in diesen Odoo-Phasen für die Automatik verwenden. Leer = alle aktiven, nicht stornierten Veranstaltungen.",
    )
    cinema_default_duration_minutes = fields.Integer(string="Kino-Fallbackdauer (Min.)", default=120)
    automation_enabled = fields.Boolean(string="Automationen aktiv", default=True)

    weather_enabled = fields.Boolean(
        string="Wetter-/Sonnendaten aktiv",
        default=True,
        help="Aktiviert die virtuellen Messsensoren für Sonnenaufgang, Sonnenuntergang und Bewölkung.",
    )
    weather_location = fields.Char(
        string="Wetter-Ort",
        default="82266 Inning am Ammersee, Deutschland",
        required=True,
        help="Ort für Sonnen- und Wetterdaten. Beim Aktualisieren wird der Ort automatisch in Koordinaten aufgelöst.",
    )
    weather_latitude = fields.Float(string="Wetter-Breitengrad", digits=(10, 6), default=48.077770, readonly=True)
    weather_longitude = fields.Float(string="Wetter-Längengrad", digits=(10, 6), default=11.151890, readonly=True)
    weather_resolved_location = fields.Char(
        string="Aufgelöster Wetter-Ort",
        default="82266 Inning am Ammersee, Deutschland",
        readonly=True,
    )
    weather_refresh_minutes = fields.Integer(string="Wetter-Aktualisierung (Min.)", default=15)
    weather_cache_json = fields.Text(string="Wetter-Cache (JSON)", readonly=True)
    last_weather_sync_at = fields.Datetime(string="Letzte Wetter-Aktualisierung", readonly=True)
    last_weather_message = fields.Text(string="Letzte Wettermeldung", readonly=True)

    # Stromkosten / Refoss-Zähler
    power_cost_enabled = fields.Boolean(
        string="Stromkosten-Ermittlung aktiv",
        default=False,
        help="Ermittelt aus ausgewählten Home-Assistant-Energie-/Leistungssensoren die Stromkosten je Veranstaltungstag.",
    )
    power_entity_ids = fields.Many2many(
        "gl.ha.entity",
        "gl_ha_config_power_entity_rel",
        "config_id",
        "entity_id",
        string="Stromzähler-Entitäten",
        domain=[("source_type", "=", "home_assistant"), ("domain", "=", "sensor"), ("active", "=", True)],
        help="Mehrere Zähler werden addiert. Unterstützt werden Wh/kWh/MWh sowie W/kW/MW (Leistung wird integriert). Energiezähler in kWh werden empfohlen.",
    )
    power_price_kwh = fields.Float(
        string="Strompreis je kWh",
        digits=(16, 6),
        default=0.0,
        help="Brutto- oder Nettopreis nach eurer Kalkulationslogik. Der Betrag wird direkt mit den gemessenen kWh multipliziert.",
    )
    power_day_start_hour = fields.Float(
        string="Messbeginn am Veranstaltungstag",
        default=7.0,
        help="Standard 07:00 Uhr am Kalendertag, an dem die Veranstaltung beginnt.",
    )
    power_day_end_hour = fields.Float(
        string="Messende am Folgetag",
        default=5.0,
        help="Standard 05:00 Uhr am Folgetag. Der Messzeitraum läuft damit standardmäßig von 07:00 bis 05:00 Uhr des Folgetags.",
    )
    power_refresh_minutes = fields.Integer(
        string="Stromkosten-Aktualisierung (Min.)",
        default=15,
        help="Wie oft laufende Veranstaltungstage neu ausgewertet werden. Der technische Cron läuft alle 5 Minuten und beachtet dieses Intervall.",
    )
    power_average_event_count = fields.Integer(
        string="SOLL-Mittelwert aus Veranstaltungen",
        default=20,
        help="Anzahl der letzten abgeschlossenen Veranstaltungen, aus deren Stromkosten der SOLL-Wert gebildet wird.",
    )
    power_actual_field_name = fields.Char(
        string="Technisches Feld für IST-Stromkosten",
        default="x_studio_event_kalk_ist_sonstige_kosten",
        help="Technischer Feldname auf event.event. Muss ein numerisches Feld (Float/Monetary/Integer) sein.",
    )
    power_budget_field_name = fields.Char(
        string="Technisches Feld für SOLL-Stromkosten",
        default="x_studio_event_kalk_soll_sonstige_kosten",
        help="Technischer Feldname auf event.event. Kann später z. B. auf x_studio_event_kalk_soll_stromkosten geändert werden.",
    )
    power_current_average_cost = fields.Float(
        string="Aktueller SOLL-Mittelwert", digits=(16, 6), readonly=True
    )
    last_power_cost_sync_at = fields.Datetime(string="Letzte Stromkosten-Aktualisierung", readonly=True)
    last_power_cost_message = fields.Text(string="Letzte Stromkostenmeldung", readonly=True)

    alert_email_enabled = fields.Boolean(string="Warnungen per E-Mail", default=False)
    alert_email_to = fields.Char(string="Warn-E-Mail an")

    last_test_at = fields.Datetime(string="Letzter Verbindungstest", readonly=True)
    last_test_message = fields.Text(string="Letzte Verbindungsmeldung", readonly=True)
    last_state_sync_at = fields.Datetime(string="Letzter Statusabruf", readonly=True)
    last_schedule_sync_at = fields.Datetime(string="Letzte Zeitfenster-Aktualisierung", readonly=True)
    last_automation_at = fields.Datetime(string="Letzte Automatik-Auswertung", readonly=True)

    @api.constrains(
        "request_timeout",
        "state_poll_minutes",
        "history_retention_days",
        "unavailable_grace_minutes",
        "default_manual_override_minutes",
        "schedule_horizon_days",
        "cinema_default_duration_minutes",
        "weather_refresh_minutes",
        "power_refresh_minutes",
        "power_average_event_count",
        "power_price_kwh",
        "power_day_start_hour",
        "power_day_end_hour",
    )
    def _check_positive_values(self):
        for rec in self:
            if rec.request_timeout < 1:
                raise ValidationError(_("Der API-Timeout muss mindestens 1 Sekunde betragen."))
            if rec.state_poll_minutes < 1:
                raise ValidationError(_("Das Statusintervall muss mindestens 1 Minute betragen."))
            if rec.history_retention_days < 1:
                raise ValidationError(_("Die Historie muss mindestens 1 Tag behalten werden."))
            if rec.unavailable_grace_minutes < 0 or rec.default_manual_override_minutes < 0:
                raise ValidationError(_("Zeitwerte dürfen nicht negativ sein."))
            if rec.schedule_horizon_days < 1 or rec.cinema_default_duration_minutes < 1:
                raise ValidationError(_("Zeitfenster und Kinodauer müssen größer als 0 sein."))
            if rec.weather_refresh_minutes < 5:
                raise ValidationError(_("Das Wetter-Aktualisierungsintervall muss mindestens 5 Minuten betragen."))
            if rec.power_refresh_minutes < 5:
                raise ValidationError(_("Das Stromkosten-Aktualisierungsintervall muss mindestens 5 Minuten betragen."))
            if rec.power_average_event_count < 1:
                raise ValidationError(_("Der SOLL-Mittelwert muss aus mindestens einer Veranstaltung gebildet werden."))
            if rec.power_price_kwh < 0:
                raise ValidationError(_("Der Strompreis darf nicht negativ sein."))
            if not (0.0 <= rec.power_day_start_hour < 24.0) or not (0.0 <= rec.power_day_end_hour < 24.0):
                raise ValidationError(_("Messbeginn und Messende müssen zwischen 00:00 und 23:59 Uhr liegen."))

    @api.constrains("power_actual_field_name", "power_budget_field_name")
    def _check_power_field_names(self):
        pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        for rec in self:
            for value, label in (
                (rec.power_actual_field_name, _("IST-Stromkosten")),
                (rec.power_budget_field_name, _("SOLL-Stromkosten")),
            ):
                if not value or not pattern.match(value.strip()):
                    raise ValidationError(_("Ungültiger technischer Feldname für %s.") % label)

    def init(self):
        """Bestandsinstallationen mit sinnvollen Wetter-Standardwerten ergänzen."""
        super().init()
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET weather_location = '82266 Inning am Ammersee, Deutschland'
             WHERE weather_location IS NULL OR weather_location = ''
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET weather_enabled = TRUE
             WHERE weather_enabled IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET weather_refresh_minutes = 15
             WHERE weather_refresh_minutes IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET weather_latitude = 48.077770,
                   weather_longitude = 11.151890,
                   weather_resolved_location = COALESCE(NULLIF(weather_resolved_location, ''), '82266 Inning am Ammersee, Deutschland')
             WHERE (weather_latitude IS NULL OR weather_latitude = 0)
               AND (weather_longitude IS NULL OR weather_longitude = 0)
               AND weather_location = '82266 Inning am Ammersee, Deutschland'
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_cost_enabled = FALSE
             WHERE power_cost_enabled IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_day_start_hour = 7.0
             WHERE power_day_start_hour IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_day_end_hour = 5.0
             WHERE power_day_end_hour IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_refresh_minutes = 15
             WHERE power_refresh_minutes IS NULL OR power_refresh_minutes < 5
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_average_event_count = 20
             WHERE power_average_event_count IS NULL OR power_average_event_count < 1
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_price_kwh = 0.0
             WHERE power_price_kwh IS NULL
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_actual_field_name = 'x_studio_event_kalk_ist_sonstige_kosten'
             WHERE power_actual_field_name IS NULL OR power_actual_field_name = ''
        """)
        self.env.cr.execute("""
            UPDATE gl_ha_config
               SET power_budget_field_name = 'x_studio_event_kalk_soll_sonstige_kosten'
             WHERE power_budget_field_name IS NULL OR power_budget_field_name = ''
        """)

    def write(self, vals):
        # Bei einem geänderten Ortsnamen erzwingen wir beim nächsten Abruf eine
        # neue Geokodierung, damit nicht versehentlich die alten Koordinaten
        # weiterverwendet werden.
        location_changed = "weather_location" in vals and "weather_resolved_location" not in vals
        if location_changed:
            vals = dict(vals)
            vals.update({
                "weather_resolved_location": False,
                "weather_latitude": 0.0,
                "weather_longitude": 0.0,
                "weather_cache_json": False,
                "last_weather_sync_at": False,
            })
        result = super().write(vals)
        if location_changed or vals.get("weather_enabled") is False:
            self.env["gl.ha.entity"].sudo().search([("source_type", "=", "weather")]).write({
                "is_available": False,
                "unavailable_since": fields.Datetime.now(),
            })
        return result

    def _weather_geocode(self):
        self.ensure_one()
        location = (self.weather_location or "").strip()
        if not location:
            raise UserError(_("Bitte einen Wetter-Ort eintragen."))

        # Open-Meteo akzeptiert Ortsnamen oder Postleitzahlen. Für Einträge wie
        # „82266 Inning am Ammersee, Deutschland“ probieren wir mehrere robuste
        # Suchvarianten und bewerten die Treffer anschließend.
        postcode_match = re.search(r"\b(\d{5})\b", location)
        postcode = postcode_match.group(1) if postcode_match else ""
        city_guess = re.sub(r"\b\d{5}\b", "", location).split(",", 1)[0].strip()
        queries = []
        for query in (location, postcode, city_guess):
            if query and query not in queries:
                queries.append(query)

        candidates = []
        last_error = None
        for query in queries:
            try:
                response = requests.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": query,
                        "count": 10,
                        "language": "de",
                        "format": "json",
                        "countryCode": "DE",
                    },
                    timeout=max(5, int(self.request_timeout or 10)),
                )
                response.raise_for_status()
                payload = response.json() or {}
                candidates.extend(payload.get("results") or [])
                if candidates:
                    break
            except Exception as exc:
                last_error = exc

        if not candidates:
            if last_error:
                raise UserError(_("Wetter-Ort konnte nicht aufgelöst werden: %s") % last_error) from last_error
            raise UserError(_("Für den Wetter-Ort wurde kein Treffer gefunden."))

        normalized_city = city_guess.casefold()
        def score(item):
            points = 0
            postcodes = {str(code) for code in (item.get("postcodes") or [])}
            if postcode and postcode in postcodes:
                points += 100
            name = str(item.get("name") or "").casefold()
            if normalized_city and (name in normalized_city or normalized_city.startswith(name) or name.startswith(normalized_city)):
                points += 30
            if str(item.get("country_code") or "").upper() == "DE":
                points += 10
            return points

        result = max(candidates, key=score)
        latitude = float(result.get("latitude"))
        longitude = float(result.get("longitude"))
        parts = [result.get("name"), result.get("admin1"), result.get("country")]
        label = ", ".join(str(part) for part in parts if part)
        self.sudo().write({
            "weather_latitude": latitude,
            "weather_longitude": longitude,
            "weather_resolved_location": self.weather_location,
            "last_weather_message": _("Ort aufgelöst: %(label)s (%(lat).5f, %(lon).5f)") % {
                "label": label or self.weather_location,
                "lat": latitude,
                "lon": longitude,
            },
        })
        return latitude, longitude

    def _weather_coordinates(self, force_geocode=False):
        self.ensure_one()
        location_changed = (self.weather_resolved_location or "") != (self.weather_location or "")
        if force_geocode or location_changed or not self.weather_latitude or not self.weather_longitude:
            return self._weather_geocode()
        return float(self.weather_latitude), float(self.weather_longitude)

    @api.model
    def _parse_local_iso(self, value, timezone_name):
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(str(value))
            if dt.tzinfo is None:
                tz = pytz.timezone(timezone_name or "Europe/Berlin")
                dt = tz.localize(dt, is_dst=None)
            return dt
        except Exception:
            return False

    def _sync_virtual_weather_entities(self, snapshot):
        self.ensure_one()
        entity_model = self.env["gl.ha.entity"].sudo()
        now = fields.Datetime.now()
        timezone_name = snapshot.get("timezone") or self.timezone_name or "Europe/Berlin"
        try:
            tz = pytz.timezone(timezone_name)
        except Exception:
            tz = pytz.timezone("Europe/Berlin")
        aware_now = pytz.UTC.localize(now).astimezone(tz)
        local_date = aware_now.date().isoformat()
        day = (snapshot.get("days") or {}).get(local_date) or {}

        values = {}
        cloud = (snapshot.get("current") or {}).get("cloud_cover")
        if cloud is not None:
            values["weather.cloud_cover"] = {
                "state": "%g" % float(cloud),
                "numeric_value": float(cloud),
                "unit": "%",
                "attributes": {"metric": "cloud_cover", "location": self.weather_location},
            }

        for metric, entity_id in (("sunrise", "weather.sunrise"), ("sunset", "weather.sunset")):
            dt = self._parse_local_iso(day.get(metric), timezone_name)
            if not dt:
                continue
            local_dt = dt.astimezone(tz)
            decimal_hour = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
            values[entity_id] = {
                "state": local_dt.strftime("%H:%M"),
                "numeric_value": decimal_hour,
                "unit": "Uhrzeit",
                "attributes": {"metric": metric, "date": local_date, "location": self.weather_location},
            }

        for entity_id in ("weather.sunrise", "weather.sunset", "weather.cloud_cover"):
            entity = entity_model.search([("entity_id", "=", entity_id)], limit=1)
            if not entity:
                continue
            metric_values = values.get(entity_id)
            if metric_values:
                entity.write({
                    "state": metric_values["state"],
                    "numeric_value": metric_values["numeric_value"],
                    "has_numeric_value": True,
                    "unit": metric_values["unit"],
                    "attributes_json": json.dumps(metric_values["attributes"], ensure_ascii=False, sort_keys=True),
                    "is_available": True,
                    "last_seen_at": now,
                    "last_updated": now,
                    "unavailable_since": False,
                })
            else:
                entity.write({
                    "is_available": False,
                    "last_updated": now,
                    "unavailable_since": entity.unavailable_since or now,
                })

    def refresh_weather_data(self, force_geocode=False):
        self.ensure_one()
        if not self.weather_enabled:
            return {}
        latitude, longitude = self._weather_coordinates(force_geocode=force_geocode)
        forecast_days = max(3, min(16, int(self.schedule_horizon_days or 14)))
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "cloud_cover",
            "hourly": "cloud_cover",
            "daily": "sunrise,sunset",
            "timezone": self.timezone_name or "Europe/Berlin",
            "forecast_days": forecast_days,
            "past_days": 1,
        }
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=max(5, int(self.request_timeout or 10)),
        )
        response.raise_for_status()
        payload = response.json() or {}

        daily = payload.get("daily") or {}
        days = {}
        for idx, date_value in enumerate(daily.get("time") or []):
            days[str(date_value)] = {
                "sunrise": (daily.get("sunrise") or [None] * (idx + 1))[idx] if idx < len(daily.get("sunrise") or []) else None,
                "sunset": (daily.get("sunset") or [None] * (idx + 1))[idx] if idx < len(daily.get("sunset") or []) else None,
            }

        hourly = payload.get("hourly") or {}
        cloud_by_hour = {}
        times = hourly.get("time") or []
        clouds = hourly.get("cloud_cover") or []
        for idx, time_value in enumerate(times):
            if idx < len(clouds) and clouds[idx] is not None:
                cloud_by_hour[str(time_value)] = float(clouds[idx])

        current = payload.get("current") or {}
        snapshot = {
            "provider": "Open-Meteo",
            "timezone": payload.get("timezone") or self.timezone_name or "Europe/Berlin",
            "latitude": float(payload.get("latitude", latitude)),
            "longitude": float(payload.get("longitude", longitude)),
            "fetched_at": fields.Datetime.to_string(fields.Datetime.now()),
            "current": {
                "time": current.get("time"),
                "cloud_cover": float(current["cloud_cover"]) if current.get("cloud_cover") is not None else None,
            },
            "days": days,
            "hourly_cloud_cover": cloud_by_hour,
        }
        now = fields.Datetime.now()
        self.sudo().write({
            "weather_cache_json": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            "last_weather_sync_at": now,
            "last_weather_message": _("Wetterdaten für %(location)s aktualisiert.") % {"location": self.weather_location},
        })
        self._sync_virtual_weather_entities(snapshot)
        return snapshot

    def weather_snapshot(self, refresh_if_stale=True):
        """Wetterdaten liefern; bei API-Ausfall einen vorhandenen Cache weiterverwenden."""
        self.ensure_one()
        snapshot = {}
        if self.weather_cache_json:
            try:
                snapshot = json.loads(self.weather_cache_json) or {}
            except Exception:
                snapshot = {}
        if not self.weather_enabled:
            return snapshot

        stale = not self.last_weather_sync_at
        if self.last_weather_sync_at:
            stale = fields.Datetime.now() - self.last_weather_sync_at >= timedelta(minutes=max(5, self.weather_refresh_minutes))
        if refresh_if_stale and stale:
            try:
                snapshot = self.refresh_weather_data()
            except Exception as exc:
                _logger.warning("Weather refresh failed; cached data will be used: %s", exc)
                self.sudo().write({"last_weather_message": _("Wetter-Aktualisierung fehlgeschlagen; Cache wird verwendet: %s") % exc})
        return snapshot

    def action_refresh_weather(self):
        self.ensure_one()
        try:
            snapshot = self.refresh_weather_data(force_geocode=True)
            today = fields.Date.context_today(self).isoformat()
            day = (snapshot.get("days") or {}).get(today) or {}
            cloud = (snapshot.get("current") or {}).get("cloud_cover")
            message = _("Wetter aktualisiert. Sonnenaufgang: %(sunrise)s · Sonnenuntergang: %(sunset)s · Bewölkung: %(cloud)s%%") % {
                "sunrise": str(day.get("sunrise") or "–")[-5:],
                "sunset": str(day.get("sunset") or "–")[-5:],
                "cloud": "–" if cloud is None else "%g" % cloud,
            }
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {"title": _("Wetter & Sonne"), "message": message, "type": "success", "sticky": False},
            }
        except Exception as exc:
            self.sudo().write({"last_weather_message": str(exc)})
            raise UserError(_("Wetterdaten konnten nicht aktualisiert werden: %s") % exc) from exc

    @api.model
    def get_config(self):
        config = self.search([("active", "=", True)], limit=1)
        if not config:
            config = self.create({"name": "GROUNDLIFT Home Assistant"})
        return config

    def _client(self):
        self.ensure_one()
        if not self.base_url or not self.access_token:
            raise UserError(_("Bitte zuerst Home-Assistant-URL und Long-Lived Access Token eintragen."))
        extra_headers = {}
        if self.extra_headers_json:
            try:
                extra_headers = json.loads(self.extra_headers_json)
                if not isinstance(extra_headers, dict):
                    raise ValueError("JSON must be an object")
                extra_headers = {str(key): str(value) for key, value in extra_headers.items()}
            except Exception as exc:
                raise UserError(_("Zusätzliche HTTP-Header sind kein gültiges JSON-Objekt: %s") % exc) from exc
        return HomeAssistantAPI(
            self.base_url,
            self.access_token,
            verify_ssl=self.verify_ssl,
            timeout=self.request_timeout,
            extra_headers=extra_headers,
        )

    def action_test_connection(self):
        self.ensure_one()
        try:
            result = self._client().test()
            message = result.get("message") if isinstance(result, dict) else str(result)
            message = message or _("Home Assistant antwortet.")
            self.write({"last_test_at": fields.Datetime.now(), "last_test_message": message})
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {"title": _("Home Assistant"), "message": message, "type": "success", "sticky": False},
            }
        except Exception as exc:
            self.write({"last_test_at": fields.Datetime.now(), "last_test_message": str(exc)})
            raise UserError(_("Home Assistant ist nicht erreichbar: %s") % exc) from exc

    def action_sync_entities(self):
        self.ensure_one()
        self.env["gl.ha.entity"].sudo().sync_from_home_assistant(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Home Assistant"), "message": _("Entitäten und Zustände wurden aktualisiert."), "type": "success"},
        }

    def action_refresh_schedules(self):
        self.ensure_one()
        self.env["gl.ha.schedule.window"].sudo().refresh_all(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Zeitfenster"), "message": _("Event- und Kino-Zeitfenster wurden aktualisiert."), "type": "success"},
        }

    def action_run_automation(self):
        self.ensure_one()
        self.env["gl.ha.automation.rule"].sudo().evaluate_all(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Automatik"), "message": _("Automatik wurde ausgewertet."), "type": "success"},
        }

    def action_import_history_24h(self):
        self.ensure_one()
        count = self.env["gl.ha.history"].sudo().import_home_assistant_history(self, hours=24)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Historie"), "message": _("%(count)s Verlaufswerte importiert.") % {"count": count}, "type": "success"},
        }

    def action_update_power_costs(self):
        self.ensure_one()
        if not self.power_cost_enabled:
            raise UserError(_("Bitte zuerst die Stromkosten-Ermittlung aktivieren."))
        try:
            calculated, average, sample_count = self.env["gl.ha.power.day"].sudo().run_regular_update(self, force=False)
            message = _(
                "Stromkosten aktualisiert: %(days)s Veranstaltungstag(e) berechnet · SOLL-Mittel %(avg).2f aus %(samples)s Veranstaltung(en)."
            ) % {"days": len(calculated), "avg": average, "samples": sample_count}
            self.sudo().write({
                "last_power_cost_sync_at": fields.Datetime.now(),
                "last_power_cost_message": message,
            })
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {"title": _("Stromkosten"), "message": message, "type": "success", "sticky": False},
            }
        except Exception as exc:
            self.sudo().write({"last_power_cost_message": str(exc)})
            raise UserError(_("Stromkosten konnten nicht aktualisiert werden: %s") % exc) from exc

    def action_backfill_power_costs(self):
        self.ensure_one()
        if not self.power_cost_enabled:
            raise UserError(_("Bitte zuerst die Stromkosten-Ermittlung aktivieren."))
        try:
            calculated, average, sample_count = self.env["gl.ha.power.day"].sudo().backfill_recent(self)
            message = _(
                "Historische Stromkosten neu berechnet: %(days)s Tag(e) · SOLL-Mittel %(avg).2f aus %(samples)s Veranstaltung(en)."
            ) % {"days": calculated, "avg": average, "samples": sample_count}
            self.sudo().write({
                "last_power_cost_sync_at": fields.Datetime.now(),
                "last_power_cost_message": message,
            })
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {"title": _("Stromkosten"), "message": message, "type": "success", "sticky": False},
            }
        except Exception as exc:
            self.sudo().write({"last_power_cost_message": str(exc)})
            raise UserError(_("Historische Stromkosten konnten nicht berechnet werden: %s") % exc) from exc

    def action_open_dashboard(self):
        self.ensure_one()
        dashboard = self.env["gl.ha.dashboard"].search([("active", "=", True)], limit=1)
        url = "/groundlift/ha/%s" % dashboard.slug if dashboard else "/groundlift/ha"
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    @api.model
    def cron_sync_states(self):
        config = self.get_config().sudo()
        try:
            self.env["gl.ha.entity"].sudo().sync_from_home_assistant(config)
            self.env["gl.ha.alert"].sudo().resolve_system_alert("ha_connection")
        except Exception as exc:
            _logger.exception("Home Assistant state sync failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "ha_connection",
                _("Home Assistant Verbindung fehlgeschlagen: %s") % exc,
                severity="critical",
                config=config,
            )
        return True

    @api.model
    def cron_refresh_schedules(self):
        config = self.get_config().sudo()
        try:
            self.env["gl.ha.schedule.window"].sudo().refresh_all(config)
            self.env["gl.ha.alert"].sudo().resolve_system_alert("schedule_sync")
        except Exception as exc:
            _logger.exception("Home Assistant schedule refresh failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "schedule_sync",
                _("Zeitfenster konnten nicht aktualisiert werden: %s") % exc,
                severity="warning",
                config=config,
            )
        return True

    @api.model
    def cron_run_automation(self):
        config = self.get_config().sudo()
        if not config.automation_enabled:
            return True
        try:
            self.env["gl.ha.automation.rule"].sudo().evaluate_all(config)
            self.env["gl.ha.alert"].sudo().resolve_system_alert("automation")
        except Exception as exc:
            _logger.exception("Home Assistant automation failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "automation",
                _("Home-Assistant-Automatik fehlgeschlagen: %s") % exc,
                severity="critical",
                config=config,
            )
        return True

    @api.model
    def cron_sync_weather(self):
        config = self.get_config().sudo()
        if not config.weather_enabled:
            return True
        try:
            config.refresh_weather_data()
            self.env["gl.ha.alert"].sudo().resolve_system_alert("weather_sync")
        except Exception as exc:
            _logger.exception("Weather sync failed")
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "weather_sync",
                _("Wetter-/Sonnendaten konnten nicht aktualisiert werden: %s") % exc,
                severity="warning",
                config=config,
            )
        return True

    @api.model
    def cron_update_power_costs(self):
        config = self.get_config().sudo()
        if not config.power_cost_enabled:
            return True
        if config.last_power_cost_sync_at:
            due_at = config.last_power_cost_sync_at + timedelta(minutes=max(5, int(config.power_refresh_minutes or 15)))
            if fields.Datetime.now() < due_at:
                return True
        try:
            calculated, average, sample_count = self.env["gl.ha.power.day"].sudo().run_regular_update(config)
            message = _(
                "Automatische Stromkosten-Aktualisierung: %(days)s Tag(e) berechnet · SOLL-Mittel %(avg).2f aus %(samples)s Veranstaltung(en)."
            ) % {"days": len(calculated), "avg": average, "samples": sample_count}
            config.sudo().write({
                "last_power_cost_sync_at": fields.Datetime.now(),
                "last_power_cost_message": message,
            })
            self.env["gl.ha.alert"].sudo().resolve_system_alert("power_cost_sync")
        except Exception as exc:
            _logger.exception("Power cost sync failed")
            config.sudo().write({
                "last_power_cost_sync_at": fields.Datetime.now(),
                "last_power_cost_message": str(exc),
            })
            self.env["gl.ha.alert"].sudo().open_system_alert(
                "power_cost_sync",
                _("Stromkosten konnten nicht aktualisiert werden: %s") % exc,
                severity="warning",
                config=config,
            )
        return True

    @api.model
    def cron_cleanup_history(self):
        config = self.get_config().sudo()
        cutoff = fields.Datetime.now() - timedelta(days=config.history_retention_days)
        old = self.env["gl.ha.history"].sudo().search([("timestamp", "<", cutoff)])
        if old:
            old.unlink()
        return True
