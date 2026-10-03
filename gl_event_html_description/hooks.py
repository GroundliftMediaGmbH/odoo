def post_init_hook(env):
    """Initialize the source-code field from existing event descriptions.

    Both fields are translatable. Existing values are copied once per active
    language so installing the module does not discard current translations.
    """
    events = env["event.event"].with_context(active_test=False).search([])
    if not events:
        return

    languages = env["res.lang"].search([("active", "=", True)])
    if not languages:
        # A normal Odoo database always has an active language, but keeping the
        # fallback makes installation safe on unusual/test databases.
        languages = env["res.lang"].search([], limit=1)

    for language in languages:
        localized_events = events.with_context(
            lang=language.code,
            gl_event_html_description_skip_sync=True,
        )
        for event in localized_events:
            event.write({
                "gl_html_description_code": event.description or "",
            })
