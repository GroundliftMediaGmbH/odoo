# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Synchronize existing events once after module installation."""
    events = env["event.event"].sudo().search([])
    events._gl_sync_event_cover_from_image()
