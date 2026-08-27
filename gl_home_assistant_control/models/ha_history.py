# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from odoo import api, fields, models


class GlHaHistory(models.Model):
    _name = "gl.ha.history"
    _description = "Home Assistant Verlauf"
    _order = "timestamp desc, id desc"

    entity_id = fields.Many2one("gl.ha.entity", required=True, ondelete="cascade", index=True)
    timestamp = fields.Datetime(required=True, index=True, default=fields.Datetime.now)
    state = fields.Char()
    numeric_value = fields.Float()
    has_numeric_value = fields.Boolean()
    available = fields.Boolean(default=True)
    source = fields.Selection([("poll", "Odoo Poll"), ("ha_import", "Home Assistant Import")], default="poll", required=True)

    @api.model
    def record_entity_if_due(self, entity, config):
        last = self.search([("entity_id", "=", entity.id)], order="timestamp desc", limit=1)
        now = fields.Datetime.now()
        if last and last.timestamp and now - last.timestamp < timedelta(minutes=config.state_poll_minutes):
            return False
        return self.create({
            "entity_id": entity.id,
            "timestamp": now,
            "state": entity.state,
            "numeric_value": entity.numeric_value,
            "has_numeric_value": entity.has_numeric_value,
            "available": entity.is_available,
            "source": "poll",
        })

    @api.model
    def import_home_assistant_history(self, config, hours=24):
        entities = self.env["gl.ha.entity"].sudo().search([
            ("active", "=", True),
            ("history_enabled", "=", True),
            ("domain", "in", ["sensor", "binary_sensor", "switch", "light", "fan", "number", "input_number"]),
        ])
        if not entities:
            return 0
        start = datetime.now(timezone.utc) - timedelta(hours=hours)
        end = datetime.now(timezone.utc)
        payload = config._client().get_history(
            entities.mapped("entity_id"),
            start.isoformat(),
            end.isoformat(),
            no_attributes=True,
        )
        by_ha_id = {e.entity_id: e for e in entities}
        count = 0
        for series in payload or []:
            for item in series or []:
                ha_id = item.get("entity_id")
                entity = by_ha_id.get(ha_id)
                if not entity:
                    continue
                raw_state = str(item.get("state") or "")
                try:
                    value = float(raw_state)
                    has_numeric = True
                except (TypeError, ValueError):
                    if raw_state.casefold() in {"on", "off"}:
                        value = 1.0 if raw_state.casefold() == "on" else 0.0
                        has_numeric = True
                    else:
                        value = 0.0
                        has_numeric = False
                raw_ts = item.get("last_changed") or item.get("last_updated")
                try:
                    ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    if ts.tzinfo:
                        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    continue
                exists = self.search_count([("entity_id", "=", entity.id), ("timestamp", "=", ts)])
                if exists:
                    continue
                self.create({
                    "entity_id": entity.id,
                    "timestamp": ts,
                    "state": raw_state,
                    "numeric_value": value,
                    "has_numeric_value": has_numeric,
                    "available": raw_state.casefold() not in {"unavailable", "unknown", "none", ""},
                    "source": "ha_import",
                })
                count += 1
        return count

    @api.model
    def dashboard_series(self, entities, hours=24, max_points=320):
        since = fields.Datetime.now() - timedelta(hours=max(1, min(int(hours or 24), 24 * 31)))
        result = {}
        for entity in entities:
            rows = self.search([
                ("entity_id", "=", entity.id),
                ("timestamp", ">=", since),
                ("has_numeric_value", "=", True),
            ], order="timestamp asc", limit=10000)
            row_list = list(rows)
            if len(row_list) > max_points:
                stride = max(1, len(row_list) // max_points)
                sampled = row_list[::stride]
                if sampled[-1].id != row_list[-1].id:
                    sampled.append(row_list[-1])
                row_list = sampled
            result[str(entity.id)] = [
                {"t": fields.Datetime.to_string(row.timestamp), "v": row.numeric_value, "s": row.state or ""}
                for row in row_list
            ]
        return result
