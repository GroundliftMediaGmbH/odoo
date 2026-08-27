# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timezone, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

SUPPORTED_DOMAINS = {
    "sensor", "binary_sensor", "switch", "light", "climate", "fan", "number", "input_number", "input_boolean"
}
CONTROL_DOMAINS = {"switch", "light", "climate", "fan", "number", "input_number", "input_boolean"}
UNAVAILABLE_STATES = {"unavailable", "unknown", "none", ""}


def _float_or_false(value):
    if value in (None, False, "", "unknown", "unavailable"):
        return False
    try:
        return float(value)
    except (TypeError, ValueError):
        return False


def _ha_datetime(value):
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return False


class GlHaEntity(models.Model):
    _name = "gl.ha.entity"
    _description = "Home Assistant Entität"
    _order = "room, name, entity_id"

    name = fields.Char(required=True)
    ha_name = fields.Char(string="Home Assistant Name", readonly=True)
    entity_id = fields.Char(string="Home Assistant Entity ID", required=True, index=True)
    domain = fields.Char(index=True, readonly=True)
    room = fields.Char(string="Raum/Gruppe")
    dashboard_group = fields.Char(
        string="Dashboard-Gruppe",
        help="Optionale frei definierbare Anzeigegruppe. Bleibt das Feld leer, kann das Dashboard stattdessen den Home-Assistant-Raum verwenden.",
    )
    device_class = fields.Char(readonly=True)
    unit = fields.Char(string="Einheit", readonly=True)

    active = fields.Boolean(default=True)
    show_dashboard = fields.Boolean(string="Im Dashboard anzeigen", default=True)
    dashboard_role = fields.Selection([
        ("auto", "Automatisch"),
        ("control", "Aktives Element / Steuerung"),
        ("sensor", "Sensor / Messwert"),
    ], string="Darstellung im Dashboard", default="auto", required=True,
       help="Legt fest, ob die Entität in getrennten Dashboard-Bereichen als Steuerung oder Sensor erscheint. 'Automatisch' verwendet die Steuerbarkeit der Entität.")
    controllable = fields.Boolean(string="Steuerbar", default=False)
    history_enabled = fields.Boolean(string="Verlauf aufzeichnen", default=True)
    alert_enabled = fields.Boolean(string="Bei Ausfall warnen", default=True)

    control_type = fields.Selection([
        ("none", "Nur Anzeige"),
        ("toggle", "Ein/Aus"),
        ("temperature", "Thermostat-Temperatur"),
        ("number", "Zahlenregler"),
    ], default="none", required=True)
    min_value = fields.Float(string="Minimum")
    max_value = fields.Float(string="Maximum")
    has_min_value = fields.Boolean(readonly=True)
    has_max_value = fields.Boolean(readonly=True)
    step = fields.Float(string="Schrittweite", default=1.0)

    state = fields.Char(string="Zustand", readonly=True)
    numeric_value = fields.Float(string="Messwert", readonly=True)
    has_numeric_value = fields.Boolean(readonly=True)
    control_value = fields.Float(string="Sollwert", readonly=True)
    has_control_value = fields.Boolean(readonly=True)
    attributes_json = fields.Text(string="Attribute JSON", readonly=True)
    is_available = fields.Boolean(string="Erreichbar", default=False, readonly=True, index=True)
    last_changed = fields.Datetime(readonly=True)
    last_updated = fields.Datetime(readonly=True)
    last_seen_at = fields.Datetime(readonly=True)
    unavailable_since = fields.Datetime(readonly=True)

    manual_override_until = fields.Datetime(string="Manuell übersteuert bis", readonly=True)
    manual_override_value = fields.Char(string="Manueller Wert", readonly=True)

    _entity_id_unique = models.Constraint(
        "UNIQUE(entity_id)",
        "Die Home-Assistant Entity ID muss eindeutig sein.",
    )

    def init(self):
        # Bestehende Entitäten aus älteren Versionen werden automatisch
        # nach ihrer technischen Steuerbarkeit einsortiert, solange keine
        # manuelle Dashboard-Rolle gesetzt wurde.
        self.env.cr.execute(
            "UPDATE gl_ha_entity SET dashboard_role = 'auto' WHERE dashboard_role IS NULL"
        )

    @api.constrains("step")
    def _check_step(self):
        for rec in self:
            if rec.step <= 0:
                raise ValidationError(_("Die Schrittweite muss größer als 0 sein."))

    @api.model
    def _default_control_type(self, domain):
        if domain in {"switch", "light", "fan", "input_boolean"}:
            return "toggle"
        if domain == "climate":
            return "temperature"
        if domain in {"number", "input_number"}:
            return "number"
        return "none"

    @api.model
    def _state_values(self, item):
        entity_id = item.get("entity_id") or ""
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
        state = str(item.get("state") or "")
        attrs = item.get("attributes") or {}
        available = state.casefold() not in UNAVAILABLE_STATES
        numeric = _float_or_false(state)
        control_value = False

        if domain == "climate":
            numeric = _float_or_false(attrs.get("current_temperature"))
            control_value = _float_or_false(attrs.get("temperature"))
        elif domain in {"number", "input_number"}:
            control_value = numeric
        elif state.casefold() in {"on", "off"}:
            numeric = 1.0 if state.casefold() == "on" else 0.0

        min_value = _float_or_false(attrs.get("min_temp") if domain == "climate" else attrs.get("min"))
        max_value = _float_or_false(attrs.get("max_temp") if domain == "climate" else attrs.get("max"))
        step = _float_or_false(attrs.get("target_temp_step") if domain == "climate" else attrs.get("step"))
        if domain == "climate" and not step:
            step = 0.5
        if not step:
            step = 1.0

        return {
            "ha_name": attrs.get("friendly_name") or entity_id,
            "domain": domain,
            "device_class": attrs.get("device_class") or False,
            "unit": attrs.get("unit_of_measurement") or attrs.get("temperature_unit") or False,
            "state": state,
            "numeric_value": numeric or 0.0,
            "has_numeric_value": numeric is not False,
            "control_value": control_value or 0.0,
            "has_control_value": control_value is not False,
            "attributes_json": json.dumps(attrs, ensure_ascii=False, sort_keys=True, default=str),
            "is_available": available,
            "last_changed": _ha_datetime(item.get("last_changed")),
            "last_updated": _ha_datetime(item.get("last_updated")),
            "last_seen_at": fields.Datetime.now(),
            "min_value": min_value or 0.0,
            "max_value": max_value or 0.0,
            "has_min_value": min_value is not False,
            "has_max_value": max_value is not False,
            "step": step,
        }

    @api.model
    def sync_from_home_assistant(self, config=None):
        config = config or self.env["gl.ha.config"].get_config().sudo()
        states = config._client().get_states()
        if not isinstance(states, list):
            raise UserError(_("Home Assistant lieferte keine gültige Zustandsliste."))

        now = fields.Datetime.now()
        seen_ids = set()
        existing = {rec.entity_id: rec for rec in self.sudo().search([])}

        for item in states:
            entity_id = item.get("entity_id")
            if not entity_id or "." not in entity_id:
                continue
            domain = entity_id.split(".", 1)[0]
            if domain not in SUPPORTED_DOMAINS:
                continue
            seen_ids.add(entity_id)
            vals = self._state_values(item)
            rec = existing.get(entity_id)
            domain = vals["domain"]
            if rec:
                if vals["is_available"]:
                    vals["unavailable_since"] = False
                elif rec.is_available or not rec.unavailable_since:
                    vals["unavailable_since"] = now
                rec.sudo().write(vals)
            else:
                supported = domain in SUPPORTED_DOMAINS
                attrs = item.get("attributes") or {}
                vals.update({
                    "name": vals.get("ha_name") or entity_id,
                    "entity_id": entity_id,
                    "room": attrs.get("area_name") or attrs.get("area") or attrs.get("room") or False,
                    "active": supported,
                    "show_dashboard": supported,
                    "controllable": domain in CONTROL_DOMAINS,
                    "history_enabled": supported,
                    "alert_enabled": supported,
                    "control_type": self._default_control_type(domain),
                    "unavailable_since": False if vals["is_available"] else now,
                })
                rec = self.sudo().create(vals)
                existing[entity_id] = rec

            if rec.history_enabled and vals["is_available"]:
                self.env["gl.ha.history"].sudo().record_entity_if_due(rec, config)

        for entity_id, rec in existing.items():
            if not rec.active or entity_id in seen_ids:
                continue
            vals = {"is_available": False}
            if not rec.unavailable_since:
                vals["unavailable_since"] = now
            rec.sudo().write(vals)

        self._evaluate_availability_alerts(config)
        config.sudo().write({"last_state_sync_at": now})
        return True

    @api.model
    def _evaluate_availability_alerts(self, config):
        now = fields.Datetime.now()
        grace = timedelta(minutes=config.unavailable_grace_minutes)
        for rec in self.sudo().search([("active", "=", True), ("alert_enabled", "=", True)]):
            key = "entity_unavailable:%s" % rec.entity_id
            if rec.is_available:
                self.env["gl.ha.alert"].sudo().resolve_system_alert(key)
                continue
            since = rec.unavailable_since or rec.last_seen_at or now
            if now - since >= grace:
                self.env["gl.ha.alert"].sudo().open_system_alert(
                    key,
                    _("%(name)s (%(entity)s) ist in Home Assistant nicht erreichbar.") % {"name": rec.name, "entity": rec.entity_id},
                    severity="warning",
                    entity=rec,
                    config=config,
                )

    def dashboard_display_role(self):
        self.ensure_one()
        if self.dashboard_role in {"control", "sensor"}:
            return self.dashboard_role
        if self.controllable and self.control_type != "none":
            return "control"
        return "sensor"

    def action_clear_override(self):
        self.write({"manual_override_until": False, "manual_override_value": False})
        return True

    def _current_on(self):
        self.ensure_one()
        return (self.state or "").casefold() in {"on", "heat", "heating", "cool", "cooling", "auto"}

    def _apply_home_assistant(self, command, value=None):
        self.ensure_one()
        config = self.env["gl.ha.config"].get_config().sudo()
        if not self.controllable or self.control_type == "none":
            raise UserError(_("Diese Entität ist nicht zur Steuerung freigegeben."))
        if not self.is_available:
            raise UserError(_("Diese Entität ist derzeit nicht erreichbar."))

        client = config._client()
        data = {"entity_id": self.entity_id}
        if self.control_type == "toggle":
            if command not in {"on", "off"}:
                raise UserError(_("Ungültiger Schaltbefehl."))
            client.call_service(self.domain, "turn_on" if command == "on" else "turn_off", data)
        elif self.control_type == "temperature":
            if command != "set" or value is None:
                raise UserError(_("Für einen Thermostat ist ein Sollwert erforderlich."))
            value = float(value)
            if self.has_min_value and value < self.min_value:
                raise UserError(_("Der Sollwert liegt unter dem erlaubten Minimum."))
            if self.has_max_value and value > self.max_value:
                raise UserError(_("Der Sollwert liegt über dem erlaubten Maximum."))
            data["temperature"] = value
            client.call_service("climate", "set_temperature", data)
        elif self.control_type == "number":
            if command != "set" or value is None:
                raise UserError(_("Für den Regler ist ein Wert erforderlich."))
            value = float(value)
            if self.has_min_value and value < self.min_value:
                raise UserError(_("Der Wert liegt unter dem erlaubten Minimum."))
            if self.has_max_value and value > self.max_value:
                raise UserError(_("Der Wert liegt über dem erlaubten Maximum."))
            data["value"] = value
            client.call_service(self.domain, "set_value", data)
        else:
            raise UserError(_("Für diesen Entitätstyp ist keine Steuerung definiert."))

        try:
            item = client.get_state(self.entity_id)
            if isinstance(item, dict):
                self.sudo().write(self._state_values(item))
        except Exception:
            _logger.info("State refresh after service failed for %s", self.entity_id, exc_info=True)
        return True

    def dashboard_command(self, command, value=None, override_minutes=None):
        self.ensure_one()
        if command == "auto":
            self.action_clear_override()
            return True

        self._apply_home_assistant(command, value=value)
        config = self.env["gl.ha.config"].get_config().sudo()
        if override_minutes is None:
            override_minutes = config.default_manual_override_minutes
        override_minutes = max(0, int(override_minutes or 0))
        if override_minutes:
            manual_value = str(value) if command == "set" else command
            self.sudo().write({
                "manual_override_until": fields.Datetime.now() + timedelta(minutes=override_minutes),
                "manual_override_value": manual_value,
            })
        return True
