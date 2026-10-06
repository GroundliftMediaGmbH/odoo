# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Repair the duplicate-config / duplicate-planning regression from 1.5.1.

    1.5.0 could create a new persisted config whenever the real inactive config
    was not found. 1.5.1 then correctly rebuilt planning, but did so for *all*
    those accidental configs. The result was hundreds of identical send slots.

    This migration keeps the real configuration, merges pending event queues,
    removes only unsent auto-generated planning rows/calendar entries, disables
    legacy duplicate configs, and rebuilds one clean two-month plan.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Config = env["gl.cleverreach.newsletter.config"].sudo().with_context(active_test=False)
    Job = env["gl.cleverreach.newsletter.job"].sudo()
    Queue = env["gl.cleverreach.event.queue"].sudo()

    configs = Config.search([], order="id asc")
    if not configs:
        primary = Config.with_context(gl_cr_allow_duplicate_config=True).create({})
        configs = primary
    else:
        primary = Config._canonical_config()

    duplicate_configs = configs - primary
    silent_ctx = {
        "tracking_disable": True,
        "mail_notrack": True,
        "mail_create_nosubscribe": True,
        "mail_create_nolog": True,
        "mail_notify_force_send": False,
        "no_mail_to_attendees": True,
        "dont_notify": True,
        "gl_auto_render": True,
        "gl_cr_skip_schedule_rebuild": True,
    }

    # Preserve pending announced events that may have landed on one of the
    # accidental configs before we clean their planner rows.
    for dup in duplicate_configs:
        pending = Queue.search([
            ("config_id", "=", dup.id),
            ("state", "=", "pending"),
        ], order="announced_at asc, id asc")
        for queue in pending:
            if not queue.event_id or not queue.event_id.exists():
                continue
            existing = Queue.search([
                ("config_id", "=", primary.id),
                ("event_id", "=", queue.event_id.id),
            ], limit=1)
            if not existing:
                Queue.create({
                    "config_id": primary.id,
                    "event_id": queue.event_id.id,
                    "announced_at": queue.announced_at or fields.Datetime.now(),
                    "announced_date": queue.announced_date or primary._local_today(),
                    "source_stage_id": queue.source_stage_id.id if queue.source_stage_id else False,
                    "state": "pending",
                    "note": "Aus versehentlich doppelter CleverReach-Konfiguration übernommen.",
                })

    automatic_types = ["biweekly", "weekly_this_week", "new_events"]

    # Remove the auto-generated planner rows created by 1.5.1. Sent history and
    # manually-created single-event newsletters are intentionally untouched.
    generated = Job.search([
        ("config_id", "in", configs.ids),
        ("newsletter_type", "in", automatic_types),
        ("state", "!=", "sent"),
        ("planning_key", "!=", False),
    ])
    # Also neutralise any future unsent automatic job on a non-canonical config,
    # even if it predates the planning_key field.
    duplicate_future = Job.search([
        ("config_id", "in", duplicate_configs.ids),
        ("newsletter_type", "in", automatic_types),
        ("state", "!=", "sent"),
        ("scheduled_datetime", "!=", False),
    ]) if duplicate_configs else Job.browse([])
    cleanup_jobs = generated | duplicate_future

    for job in cleanup_jobs:
        if job.calendar_event_id:
            try:
                job.calendar_event_id.sudo().with_context(**silent_ctx).unlink()
            except Exception:
                _logger.exception("Could not remove duplicate CleverReach calendar event for job %s", job.id)
    if cleanup_jobs:
        cleanup_jobs.with_context(**silent_ctx).unlink()

    # No legacy duplicate config may ever become a sender, even if someone opens
    # it through developer mode. Keep records with historical/credential data for
    # audit, but disable all automated sending on them.
    if duplicate_configs:
        duplicate_configs.with_context(**silent_ctx).write({
            "active": False,
            "biweekly_enabled": False,
            "weekly_enabled": False,
            "spontaneous_enabled": False,
        })

    # Remove obviously empty accidental configs. Configs containing credentials,
    # imported groups, or sent history are preserved but ignored by all app crons.
    for dup in duplicate_configs:
        has_credentials = bool(
            dup.client_id or dup.client_secret or dup.oauth_refresh_token or dup.access_token
        )
        has_groups = bool(dup.group_ids)
        has_sent_history = bool(Job.search_count([
            ("config_id", "=", dup.id),
            ("state", "=", "sent"),
        ]))
        if not has_credentials and not has_groups and not has_sent_history:
            try:
                dup.with_context(**silent_ctx).unlink()
            except Exception:
                _logger.exception("Could not remove empty duplicate CleverReach config %s", dup.id)

    # Reassert the requested standard schedule on the real configuration. Do not
    # change any activation switch: the safety shutdown remains exactly as set.
    today = primary._local_today()
    primary.with_context(**silent_ctx).write({
        "weekly_weekday": "1",       # Tuesday
        "weekly_send_hour": 17,
        "weekly_send_minute": 0,
        "weekly_next_due_date": primary._next_weekday_date(today, "1"),
        "biweekly_weekday": "3",     # Thursday
        "biweekly_send_hour": 18,
        "biweekly_send_minute": 0,
        "biweekly_next_due_date": primary._next_weekday_date(today, "3"),
        "spontaneous_weekday": "6",  # Sunday
        "spontaneous_interval_days": 14,
        "spontaneous_send_hour": 17,
        "spontaneous_send_minute": 0,
        "spontaneous_next_due_date": primary._next_weekday_date(today, "6"),
    })

    try:
        primary._refresh_planning_overview()
    except Exception:
        _logger.exception("Could not rebuild clean CleverReach planning during 19.0.1.5.2 migration")
