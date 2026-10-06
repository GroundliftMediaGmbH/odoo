# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Repair schedule anchors and rebuild the forward two-month plan.

    v19.0.1.5.0 deliberately deactivated the global configuration. Because
    Odoo's ``active`` field automatically filters inactive records, the menu then
    opened an unsaved /new form and the planner stopped refreshing that record.
    This migration keeps all activation switches exactly as they are, but resets
    the Groundlift send-plan defaults requested for production and rebuilds only
    future generated slots.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Config = env["gl.cleverreach.newsletter.config"].sudo().with_context(active_test=False)
    configs = Config.search([])

    for config in configs:
        today = config._local_today()
        schedule_vals = {
            # Diese Woche bei Groundlift: every Tuesday 17:00
            "weekly_weekday": "1",
            "weekly_send_hour": 17,
            "weekly_send_minute": 0,
            "weekly_next_due_date": config._next_weekday_date(today, "1"),
            # 2-weekly: every second Thursday 18:00
            "biweekly_weekday": "3",
            "biweekly_send_hour": 18,
            "biweekly_send_minute": 0,
            "biweekly_next_due_date": config._next_weekday_date(today, "3"),
            # Spontaneous / new events: every second Sunday 17:00
            "spontaneous_weekday": "6",
            "spontaneous_interval_days": 14,
            "spontaneous_send_hour": 17,
            "spontaneous_send_minute": 0,
            "spontaneous_next_due_date": config._next_weekday_date(today, "6"),
        }
        config.with_context(
            tracking_disable=True,
            mail_notrack=True,
            gl_cr_skip_schedule_rebuild=True,
        ).write(schedule_vals)

        # Old future planner rows can otherwise remain visible at their former
        # dates (for example December dates from the previous broken anchor).
        config._retire_future_planning_slots()
        try:
            config._refresh_planning_overview()
        except Exception:
            # Event data must not make the module upgrade fail. Opening the
            # planning overview and the daily planner cron both retry later.
            _logger.exception("Could not rebuild CleverReach planning for config %s during 19.0.1.5.1 migration", config.id)
