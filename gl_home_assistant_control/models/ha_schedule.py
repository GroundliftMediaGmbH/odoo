# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime, timedelta, timezone

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class GlHaScheduleWindow(models.Model):
    _name = "gl.ha.schedule.window"
    _description = "Home Assistant Automatik-Zeitfenster"
    _order = "start_at, source, name"

    name = fields.Char(required=True)
    source = fields.Selection([("event", "Groundlift Veranstaltung"), ("cinema", "Kino")], required=True, index=True)
    source_ref = fields.Char(index=True)
    start_at = fields.Datetime(required=True, index=True)
    end_at = fields.Datetime(required=True, index=True)
    details = fields.Char()

    _source_ref_time_unique = models.Constraint(
        "UNIQUE(source, source_ref, start_at)",
        "Dieses Zeitfenster existiert bereits.",
    )

    @api.model
    def refresh_all(self, config=None):
        config = config or self.env["gl.ha.config"].get_config().sudo()
        self._refresh_events(config)
        self._refresh_cinema(config)
        # Alte Cache-Fenster dienen nicht als Historie und werden begrenzt gehalten.
        self.search([("end_at", "<", fields.Datetime.now() - timedelta(days=7))]).unlink()
        config.sudo().write({"last_schedule_sync_at": fields.Datetime.now()})
        return True

    @api.model
    def _replace_source(self, source, vals_list, cutoff_start, cutoff_end):
        old = self.search([
            ("source", "=", source),
            ("start_at", "<=", cutoff_end),
            ("end_at", ">=", cutoff_start),
        ])
        if old:
            old.unlink()
        if vals_list:
            self.create(vals_list)

    @api.model
    def _refresh_events(self, config):
        now = fields.Datetime.now()
        start = now - timedelta(days=2)
        end = now + timedelta(days=config.schedule_horizon_days)
        Event = self.env["event.event"].sudo()
        domain = [("date_begin", "<=", end), ("date_end", ">=", start)]
        if "active" in Event._fields:
            domain.append(("active", "=", True))
        if "kanban_state" in Event._fields:
            domain.append(("kanban_state", "!=", "cancel"))
        if config.event_stage_ids and "stage_id" in Event._fields:
            domain.append(("stage_id", "in", config.event_stage_ids.ids))
        events = Event.search(domain)
        vals_list = []
        for event in events:
            # Odoo 19 kann Event-Slots verwenden. Dann wird pro Slot ein eigenes
            # Zeitfenster erzeugt, damit Pausen zwischen Slots nicht unnötig Licht aktivieren.
            slots = event.event_slot_ids if "event_slot_ids" in Event._fields and getattr(event, "is_multi_slots", False) else False
            if slots:
                for slot in slots:
                    begin = fields.Datetime.to_datetime(slot.start_datetime)
                    finish = fields.Datetime.to_datetime(slot.end_datetime or slot.start_datetime)
                    if not begin or not finish:
                        continue
                    vals_list.append({
                        "name": event.name or _("Veranstaltung"),
                        "source": "event",
                        "source_ref": "%s:slot:%s" % (event.id, slot.id),
                        "start_at": begin,
                        "end_at": finish,
                        "details": _("Odoo Veranstaltung · Slot"),
                    })
                continue

            begin = fields.Datetime.to_datetime(event.date_begin)
            finish = fields.Datetime.to_datetime(event.date_end or event.date_begin)
            if not begin or not finish:
                continue
            vals_list.append({
                "name": event.name or _("Veranstaltung"),
                "source": "event",
                "source_ref": str(event.id),
                "start_at": begin,
                "end_at": finish,
                "details": _("Odoo Veranstaltung"),
            })
        self._replace_source("event", vals_list, start, end)

    @api.model
    def _parse_duration_minutes(self, raw, fallback):
        if not raw:
            return fallback
        text = str(raw).strip()
        clock = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", text)
        if clock:
            value = int(clock.group(1)) * 60 + int(clock.group(2))
            return value if 1 <= value <= 600 else fallback
        match = re.search(r"(\d+)", text)
        if not match:
            return fallback
        value = int(match.group(1))
        return value if 1 <= value <= 600 else fallback

    @api.model
    def _aware_to_odoo(self, dt):
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @api.model
    def _refresh_cinema(self, config):
        KinoConfig = self.env["gl.kino.newsletter.config"].sudo()
        Issue = self.env["gl.kino.newsletter.issue"].sudo()
        kino_config = KinoConfig.get_config()
        tz = pytz.timezone(kino_config.timezone_name or config.timezone_name or "Europe/Berlin")
        local_today = datetime.now(tz).date()
        week_start, week_end = Issue._get_week_range(local_today, kino_config)

        ranges = [(week_start, week_end)]
        next_start = week_end + timedelta(days=1)
        next_end = next_start + timedelta(days=6)
        if next_start <= local_today + timedelta(days=config.schedule_horizon_days):
            ranges.append((next_start, next_end))

        shows = []
        for start_date, end_date in ranges:
            issue = Issue.new({
                "name": "HA Kino Cache",
                "config_id": kino_config.id,
                "week_start": start_date,
                "week_end": end_date,
            })
            shows.extend(issue._fetch_cinetixx_shows())

        vals_list = []
        dedupe = set()
        for show in shows:
            raw_start = show.get("start")
            if not raw_start:
                continue
            start_dt = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
            raw_end = show.get("end")
            if raw_end:
                end_dt = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
            else:
                minutes = self._parse_duration_minutes(show.get("duration"), config.cinema_default_duration_minutes)
                end_dt = start_dt + timedelta(minutes=minutes)
            start_odoo = self._aware_to_odoo(start_dt)
            end_odoo = self._aware_to_odoo(end_dt)
            ref = show.get("show_id") or "%s|%s|%s" % (show.get("film") or "Film", show.get("kino") or "", raw_start)
            dedupe_key = (ref, start_odoo)
            if dedupe_key in dedupe:
                continue
            dedupe.add(dedupe_key)
            vals_list.append({
                "name": show.get("film") or _("Kinovorstellung"),
                "source": "cinema",
                "source_ref": str(ref),
                "start_at": start_odoo,
                "end_at": end_odoo,
                "details": show.get("kino") or _("Kino"),
            })

        now = fields.Datetime.now()
        cutoff_start = now - timedelta(days=2)
        cutoff_end = now + timedelta(days=config.schedule_horizon_days + 7)
        self._replace_source("cinema", vals_list, cutoff_start, cutoff_end)
