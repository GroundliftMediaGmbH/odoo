# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, time, timedelta, timezone

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


ENERGY_FACTORS_TO_KWH = {
    "wh": 0.001,
    "kwh": 1.0,
    "mwh": 1000.0,
}
POWER_FACTORS_TO_KW = {
    "w": 0.001,
    "kw": 1.0,
    "mw": 1000.0,
}
INVALID_STATES = {"", "unknown", "unavailable", "none", "nan", "inf", "-inf"}


def _normalize_unit(value):
    return str(value or "").strip().replace(" ", "").casefold()


def _parse_ha_datetime(value):
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return False


def _numeric_state(value):
    text = str(value if value is not None else "").strip()
    if text.casefold() in INVALID_STATES:
        return False
    try:
        return float(text)
    except (TypeError, ValueError):
        return False


class GlHaPowerDay(models.Model):
    _name = "gl.ha.power.day"
    _description = "Home Assistant Stromkosten je Veranstaltungstag"
    _order = "day desc, id desc"

    config_id = fields.Many2one("gl.ha.config", required=True, ondelete="cascade", index=True)
    day = fields.Date(string="Veranstaltungstag", required=True, index=True)
    window_start_at = fields.Datetime(string="Messbeginn", required=True)
    window_end_at = fields.Datetime(string="Messende", required=True)
    consumption_kwh = fields.Float(string="Verbrauch (kWh)", digits=(16, 6), readonly=True)
    price_per_kwh = fields.Float(string="Strompreis je kWh", digits=(16, 6), readonly=True)
    total_cost = fields.Float(string="Gesamtkosten", digits=(16, 6), readonly=True)
    event_count = fields.Integer(string="Veranstaltungen", readonly=True)
    cost_per_event = fields.Float(string="Kosten je Veranstaltung", digits=(16, 6), readonly=True)
    is_final = fields.Boolean(string="Abgeschlossen", readonly=True, index=True)
    meter_details_json = fields.Text(string="Zählerdetails (JSON)", readonly=True)
    last_calculated_at = fields.Datetime(string="Zuletzt berechnet", readonly=True)

    _config_day_unique = models.Constraint(
        "UNIQUE(config_id, day)",
        "Für diesen Veranstaltungstag existiert bereits eine Stromkostenberechnung.",
    )

    @api.model
    def _timezone(self, config):
        try:
            return pytz.timezone(config.timezone_name or "Europe/Berlin")
        except Exception:
            return pytz.timezone("Europe/Berlin")

    @api.model
    def _float_hour_to_time(self, value):
        value = float(value or 0.0)
        total_minutes = int(round(value * 60.0)) % (24 * 60)
        return time(hour=total_minutes // 60, minute=total_minutes % 60)

    @api.model
    def _local_aware(self, day, float_hour, tz):
        naive = datetime.combine(day, self._float_hour_to_time(float_hour))
        try:
            return tz.localize(naive, is_dst=None)
        except pytz.NonExistentTimeError:
            # Sehr selten (Sommerzeitwechsel): auf die nächste gültige Stunde schieben.
            return tz.localize(naive + timedelta(hours=1), is_dst=True)
        except pytz.AmbiguousTimeError:
            # Bei der doppelten Stunde die spätere Instanz verwenden.
            return tz.localize(naive, is_dst=False)

    @api.model
    def _odoo_naive_utc(self, aware_dt):
        return aware_dt.astimezone(timezone.utc).replace(tzinfo=None)

    @api.model
    def _window_for_day(self, config, day):
        tz = self._timezone(config)
        start_local = self._local_aware(day, config.power_day_start_hour, tz)
        end_local = self._local_aware(day + timedelta(days=1), config.power_day_end_hour, tz)
        return self._odoo_naive_utc(start_local), self._odoo_naive_utc(end_local)

    @api.model
    def _local_day_bounds_utc(self, day, config):
        tz = self._timezone(config)
        start_local = self._local_aware(day, 0.0, tz)
        end_local = self._local_aware(day + timedelta(days=1), 0.0, tz)
        return self._odoo_naive_utc(start_local), self._odoo_naive_utc(end_local)

    @api.model
    def _base_event_domain(self):
        Event = self.env["event.event"].sudo()
        domain = []
        if "active" in Event._fields:
            domain.append(("active", "=", True))
        if "kanban_state" in Event._fields:
            domain.append(("kanban_state", "!=", "cancel"))
        return domain

    @api.model
    def _events_for_day(self, config, day):
        start_utc, end_utc = self._local_day_bounds_utc(day, config)
        domain = self._base_event_domain() + [
            ("date_begin", ">=", start_utc),
            ("date_begin", "<", end_utc),
        ]
        return self.env["event.event"].sudo().search(domain, order="date_begin asc, id asc")

    @api.model
    def _event_local_day(self, event, config):
        begin = fields.Datetime.to_datetime(event.date_begin)
        if not begin:
            return False
        tz = self._timezone(config)
        return pytz.UTC.localize(begin).astimezone(tz).date()

    @api.model
    def _validated_event_field(self, config, field_name, label):
        field_name = (field_name or "").strip()
        if not field_name:
            raise ValidationError(_("Bitte das technische Feld für %s eintragen.") % label)
        Event = self.env["event.event"].sudo()
        field = Event._fields.get(field_name)
        if not field:
            raise ValidationError(
                _("Das konfigurierte Feld '%(field)s' für %(label)s existiert auf event.event nicht.")
                % {"field": field_name, "label": label}
            )
        if field.type not in {"float", "monetary", "integer"}:
            raise ValidationError(
                _("Das Feld '%(field)s' für %(label)s muss numerisch sein (Float, Monetary oder Integer). Aktueller Typ: %(type)s.")
                % {"field": field_name, "label": label, "type": field.type}
            )
        return field_name

    @api.model
    def validate_power_config(self, config):
        if not config.power_entity_ids:
            raise ValidationError(_("Bitte mindestens eine Stromverbrauchs-Entität auswählen."))
        if config.power_price_kwh <= 0:
            raise ValidationError(_("Bitte einen Strompreis größer als 0 pro kWh eintragen."))
        self._validated_event_field(config, config.power_actual_field_name, _("IST-Stromkosten"))
        self._validated_event_field(config, config.power_budget_field_name, _("SOLL-Stromkosten"))

        invalid = []
        for entity in config.power_entity_ids:
            if not entity.active:
                invalid.append(_("%(name)s (%(entity)s): Entität ist in Odoo deaktiviert") % {
                    "name": entity.name,
                    "entity": entity.entity_id,
                })
                continue
            if entity.source_type != "home_assistant" or entity.domain != "sensor":
                invalid.append(_("%(name)s (%(entity)s): kein Home-Assistant-Sensor") % {
                    "name": entity.name,
                    "entity": entity.entity_id,
                })
                continue
            unit = _normalize_unit(entity.unit)
            if unit not in ENERGY_FACTORS_TO_KWH and unit not in POWER_FACTORS_TO_KW:
                invalid.append(_("%(name)s (%(entity)s): Einheit '%(unit)s' wird nicht unterstützt") % {
                    "name": entity.name,
                    "entity": entity.entity_id,
                    "unit": entity.unit or "–",
                })
        if invalid:
            raise ValidationError(
                _("Die ausgewählten Stromzähler müssen Energie (Wh/kWh/MWh) oder Leistung (W/kW/MW) liefern:\n%s")
                % "\n".join(invalid)
            )
        return True

    @api.model
    def _history_series(self, config, start_at, end_at):
        """HA-Historie für alle ausgewählten Zähler laden.

        Wir holen vor dem Messfenster einen Puffer, damit bei kumulativen
        Energiezählern der Stand zum Messbeginn zuverlässig bestimmt werden kann.
        Für abgeschlossene Fenster wird zusätzlich ein kurzer Nachlauf geladen.
        """
        entities = config.power_entity_ids.filtered(lambda e: e.active)
        if not entities:
            return {}

        now = fields.Datetime.now()
        query_start = start_at - timedelta(hours=12)
        query_end = min(end_at + timedelta(minutes=10), now)
        start_iso = pytz.UTC.localize(query_start).isoformat()
        end_iso = pytz.UTC.localize(query_end).isoformat()
        payload = config._client().get_history(
            entities.mapped("entity_id"),
            start_iso,
            end_iso,
            no_attributes=True,
        )

        result = {entity.entity_id: [] for entity in entities}
        selected = set(result)
        for series in payload or []:
            series_entity_id = False
            for item in series or []:
                item_entity = item.get("entity_id") or series_entity_id
                if item.get("entity_id"):
                    series_entity_id = item.get("entity_id")
                if item_entity not in selected:
                    continue
                value = _numeric_state(item.get("state"))
                if value is False:
                    continue
                stamp = _parse_ha_datetime(item.get("last_updated") or item.get("last_changed"))
                if not stamp:
                    continue
                result[item_entity].append((stamp, value))

        # Die aktuelle Entität ergänzen. Das macht laufende Tagesberechnungen
        # robust, auch wenn Home Assistant den letzten Punkt noch nicht in der
        # History-Antwort zurückliefert.
        now_aware = datetime.now(timezone.utc)
        for entity in entities:
            if entity.is_available and entity.has_numeric_value:
                stamp = entity.last_updated or entity.last_seen_at or now
                if stamp:
                    stamp_dt = fields.Datetime.to_datetime(stamp)
                    stamp_aware = stamp_dt.astimezone(timezone.utc) if stamp_dt.tzinfo else pytz.UTC.localize(stamp_dt)
                else:
                    stamp_aware = now_aware
                if stamp_aware <= pytz.UTC.localize(query_end) + timedelta(minutes=1):
                    result[entity.entity_id].append((stamp_aware, float(entity.numeric_value)))

        for entity_id, points in result.items():
            # Doppelte Zeitpunkte entfernen und chronologisch sortieren.
            dedupe = {}
            for stamp, value in points:
                dedupe[stamp] = value
            result[entity_id] = sorted(dedupe.items(), key=lambda item: item[0])
        return result

    @api.model
    def _clip_points(self, points, start_at, end_at, use_after_for_end=False):
        if not points:
            return []
        start = pytz.UTC.localize(start_at)
        end = pytz.UTC.localize(end_at)
        before = [point for point in points if point[0] <= start]
        within = [point for point in points if start < point[0] <= end]
        after = [point for point in points if point[0] > end]

        clipped = []
        if before:
            clipped.append((start, before[-1][1]))
        elif within:
            # Kein verlässlicher Startstand vorhanden: ersten Wert im Fenster
            # als Basis verwenden. Damit wird nie Verbrauch erfunden.
            clipped.append(within[0])
            within = within[1:]

        clipped.extend(within)
        if clipped:
            # Für die Endgrenze verwenden wir den letzten bekannten Stand im
            # Fenster. Bei Leistungssensoren kann ein Punkt direkt nach dem Ende
            # den Endwert näherungsweise verbessern.
            if use_after_for_end and after and clipped[-1][0] < end:
                clipped.append((end, after[0][1]))
            elif clipped[-1][0] < end:
                clipped.append((end, clipped[-1][1]))
        return clipped

    @api.model
    def _energy_consumption_kwh(self, points, start_at, end_at, unit):
        clipped = self._clip_points(points, start_at, end_at, use_after_for_end=False)
        if len(clipped) < 2:
            return 0.0
        factor = ENERGY_FACTORS_TO_KWH[_normalize_unit(unit)]
        total = 0.0
        previous = clipped[0][1]
        for _stamp, value in clipped[1:]:
            delta = value - previous
            if delta >= -1e-9:
                total += max(delta, 0.0)
                previous = value
            else:
                # Typischer Tageszähler-Reset (z. B. um Mitternacht). Nur wenn
                # der neue Stand deutlich kleiner ist, wird er als Reset gewertet;
                # kleine negative Messkorrekturen werden ignoriert und verändern
                # auch die Vergleichsbasis nicht.
                if previous > 0 and value <= previous * 0.5:
                    total += max(value, 0.0)
                    previous = value
        return max(0.0, total * factor)

    @api.model
    def _power_consumption_kwh(self, points, start_at, end_at, unit):
        clipped = self._clip_points(points, start_at, end_at, use_after_for_end=True)
        if len(clipped) < 2:
            return 0.0
        factor = POWER_FACTORS_TO_KW[_normalize_unit(unit)]
        total = 0.0
        for idx in range(1, len(clipped)):
            t0, v0 = clipped[idx - 1]
            t1, v1 = clipped[idx]
            seconds = max(0.0, (t1 - t0).total_seconds())
            if seconds <= 0:
                continue
            # Trapezregel: ausreichend genau für regelmäßig gelieferte
            # Leistungswerte; Energiezähler bleiben die bevorzugte Quelle.
            avg_kw = ((max(v0, 0.0) + max(v1, 0.0)) / 2.0) * factor
            total += avg_kw * (seconds / 3600.0)
        return max(0.0, total)

    @api.model
    def _calculate_consumption(self, config, start_at, end_at):
        histories = self._history_series(config, start_at, end_at)
        total = 0.0
        details = []
        now = fields.Datetime.now()
        ongoing = end_at >= now - timedelta(minutes=max(5, int(config.power_refresh_minutes or 15)))
        for entity in config.power_entity_ids.filtered(lambda e: e.active):
            unit = _normalize_unit(entity.unit)
            points = histories.get(entity.entity_id) or []
            if ongoing and not entity.is_available:
                raise UserError(_("Der Stromzähler %(name)s (%(entity)s) ist aktuell nicht erreichbar. Der IST-Wert wird nicht mit unvollständigen Daten überschrieben.") % {
                    "name": entity.name, "entity": entity.entity_id,
                })
            if len(points) < 2:
                raise UserError(_("Für den Stromzähler %(name)s (%(entity)s) ist nicht genügend Home-Assistant-Historie vorhanden. Der IST-Wert bleibt unverändert.") % {
                    "name": entity.name, "entity": entity.entity_id,
                })
            if unit in ENERGY_FACTORS_TO_KWH:
                value = self._energy_consumption_kwh(points, start_at, end_at, entity.unit)
                mode = "energy_counter"
            elif unit in POWER_FACTORS_TO_KW:
                value = self._power_consumption_kwh(points, start_at, end_at, entity.unit)
                mode = "power_integration"
            else:
                # validate_power_config fängt dies bereits ab.
                continue
            total += value
            details.append({
                "entity_id": entity.entity_id,
                "name": entity.name,
                "unit": entity.unit,
                "mode": mode,
                "consumption_kwh": round(value, 6),
                "points": len(points),
            })
        return max(0.0, total), details

    @api.model
    def calculate_day(self, config, day, force=False):
        self.validate_power_config(config)
        events = self._events_for_day(config, day)
        if not events:
            return False

        start_at, end_at = self._window_for_day(config, day)
        now = fields.Datetime.now()
        if now < start_at:
            return False

        existing = self.sudo().search([("config_id", "=", config.id), ("day", "=", day)], limit=1)
        if existing and existing.is_final and not force:
            # Kein erneuter HA-Historienabruf. Die Verteilung wird trotzdem mit
            # dem aktuellen Eventbestand und dem aktuell konfigurierten IST-Feld
            # synchronisiert (z. B. nach Feldwechsel oder nachträglichem Event).
            event_count = len(events)
            cost_per_event = float(existing.total_cost or 0.0) / event_count if event_count else 0.0
            if existing.event_count != event_count or abs(float(existing.cost_per_event or 0.0) - cost_per_event) > 0.0005:
                existing.sudo().write({
                    "event_count": event_count,
                    "cost_per_event": cost_per_event,
                    "last_calculated_at": now,
                })
            actual_field = self._validated_event_field(config, config.power_actual_field_name, _("IST-Stromkosten"))
            events_to_write = events.filtered(
                lambda event: abs(float(event[actual_field] or 0.0) - cost_per_event) > 0.0005
            )
            if events_to_write:
                events_to_write.sudo().write({actual_field: cost_per_event})
            return existing

        effective_end = min(end_at, now)
        consumption_kwh, details = self._calculate_consumption(config, start_at, effective_end)
        total_cost = consumption_kwh * float(config.power_price_kwh or 0.0)
        event_count = len(events)
        cost_per_event = total_cost / event_count if event_count else 0.0
        is_final = now >= end_at

        vals = {
            "config_id": config.id,
            "day": day,
            "window_start_at": start_at,
            "window_end_at": end_at,
            "consumption_kwh": consumption_kwh,
            "price_per_kwh": float(config.power_price_kwh or 0.0),
            "total_cost": total_cost,
            "event_count": event_count,
            "cost_per_event": cost_per_event,
            "is_final": is_final,
            "meter_details_json": json.dumps(details, ensure_ascii=False, sort_keys=True),
            "last_calculated_at": now,
        }
        if existing:
            existing.sudo().write(vals)
            day_rec = existing
        else:
            day_rec = self.sudo().create(vals)

        actual_field = self._validated_event_field(config, config.power_actual_field_name, _("IST-Stromkosten"))
        events_to_write = events.filtered(
            lambda event: abs(float(event[actual_field] or 0.0) - cost_per_event) > 0.0005
        )
        if events_to_write:
            events_to_write.sudo().write({actual_field: cost_per_event})
        return day_rec

    @api.model
    def _recent_event_days(self, config, event_limit):
        limit = max(1, int(event_limit or 20))
        Event = self.env["event.event"].sudo()
        now = fields.Datetime.now()
        events = Event.search(
            self._base_event_domain() + [("date_begin", "<", now)],
            order="date_begin desc, id desc",
            limit=max(limit * 5, limit),
        )
        days = []
        seen = set()
        completed_events = 0
        for event in events:
            day = self._event_local_day(event, config)
            if not day:
                continue
            _start_at, end_at = self._window_for_day(config, day)
            if end_at > now:
                continue
            completed_events += 1
            if day not in seen:
                days.append(day)
                seen.add(day)
            if completed_events >= limit:
                break
        return days

    @api.model
    def backfill_recent(self, config):
        """Die Tage hinter den letzten N Veranstaltungen neu berechnen.

        Diese Aktion ist bewusst manuell: Bei der ersten Einrichtung kann so
        sofort ein belastbarer SOLL-Mittelwert aufgebaut werden, ohne dass der
        normale Cronjob bei jedem Lauf viele historische HA-Daten laden muss.
        """
        self.validate_power_config(config)
        now = fields.Datetime.now()
        calculated = 0
        for day in reversed(self._recent_event_days(config, config.power_average_event_count)):
            _start_at, end_at = self._window_for_day(config, day)
            if end_at > now:
                continue
            if self.calculate_day(config, day, force=True):
                calculated += 1
        average, sample_count = self.update_budget_average(config)
        return calculated, average, sample_count

    @api.model
    def _average_samples(self, config):
        limit = max(1, int(config.power_average_event_count or 20))
        Event = self.env["event.event"].sudo()
        now = fields.Datetime.now()
        events = Event.search(
            self._base_event_domain() + [("date_begin", "<", now)],
            order="date_begin desc, id desc",
            limit=max(limit * 5, limit),
        )
        samples = []
        cache = {}
        for event in events:
            day = self._event_local_day(event, config)
            if not day:
                continue
            day_rec = cache.get(day)
            if day_rec is None:
                day_rec = self.sudo().search([
                    ("config_id", "=", config.id),
                    ("day", "=", day),
                    ("is_final", "=", True),
                ], limit=1)
                cache[day] = day_rec or False
            if not day_rec:
                continue
            samples.append(float(day_rec.cost_per_event or 0.0))
            if len(samples) >= limit:
                break
        return samples

    @api.model
    def update_budget_average(self, config):
        budget_field = self._validated_event_field(config, config.power_budget_field_name, _("SOLL-Stromkosten"))
        samples = self._average_samples(config)
        if not samples:
            config.sudo().write({"power_current_average_cost": 0.0})
            return 0.0, 0

        average = sum(samples) / len(samples)
        config.sudo().write({"power_current_average_cost": average})

        tz = self._timezone(config)
        local_today = datetime.now(tz).date()
        start_utc, _end_utc = self._local_day_bounds_utc(local_today, config)
        future_events = self.env["event.event"].sudo().search(
            self._base_event_domain() + [("date_begin", ">=", start_utc)]
        )
        if future_events:
            events_to_write = future_events.filtered(
                lambda event: abs(float(event[budget_field] or 0.0) - average) > 0.0005
            )
            if events_to_write:
                events_to_write.sudo().write({budget_field: average})
        return average, len(samples)

    @api.model
    def run_regular_update(self, config, force=False):
        self.validate_power_config(config)
        tz = self._timezone(config)
        local_today = datetime.now(tz).date()
        now = fields.Datetime.now()
        calculated = []

        # Aktueller Tag + die letzten sieben Tage. Fertige Tage werden nur dann
        # erneut gelesen, wenn noch kein finaler Datensatz existiert. So heilt
        # sich ein vorübergehender Cron-/HA-Ausfall automatisch selbst.
        for offset in range(7, -1, -1):
            day = local_today - timedelta(days=offset)
            events = self._events_for_day(config, day)
            if not events:
                continue
            start_at, end_at = self._window_for_day(config, day)
            if start_at > now:
                continue
            existing = self.sudo().search([("config_id", "=", config.id), ("day", "=", day)], limit=1)
            was_final = bool(existing and existing.is_final)
            rec = self.calculate_day(config, day, force=force)
            if rec and (force or not existing or not was_final):
                calculated.append(rec)

        average, sample_count = self.update_budget_average(config)
        return calculated, average, sample_count
