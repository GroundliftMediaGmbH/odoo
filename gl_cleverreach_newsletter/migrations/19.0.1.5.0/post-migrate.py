# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """One-time safety migration for the new fixed planning release.

    Existing installations are deliberately left in a non-sending state after
    the module update. The administrator must explicitly re-enable the global
    CleverReach switch and each desired automatic newsletter type.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Config = env["gl.cleverreach.newsletter.config"].sudo()
    configs = Config.search([])
    for config in configs:
        schedule_vals = {
            "spontaneous_weekday": config.spontaneous_weekday or "6",
            "spontaneous_interval_days": config.spontaneous_interval_days or 14,
            "spontaneous_send_hour": config.default_send_hour if config.default_send_hour not in (False, None) else 10,
            "spontaneous_send_minute": config.spontaneous_send_minute or 0,
        }
        config.with_context(tracking_disable=True, mail_notrack=True).write(schedule_vals)
        config.with_context(tracking_disable=True, mail_notrack=True).write({
            "active": False,
            "biweekly_enabled": False,
            "weekly_enabled": False,
            "spontaneous_enabled": False,
        })
    # Build the two-month overview immediately. This is safe because planning
    # never releases a CleverReach mailing, even while all send switches are off.
    for config in configs:
        try:
            config._refresh_planning_overview()
        except Exception:
            # Do not abort the module upgrade because of incomplete event data.
            # The daily planning cron and opening the planning view retry later.
            pass
