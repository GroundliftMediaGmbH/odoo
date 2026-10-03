def post_init_hook(env):
    """Initialize the dedicated HTML source from Odoo's event description.

    The field is translatable, therefore existing events are initialized once
    for every active language. From that point on, the dedicated HTML source is
    independent and is the authoritative content rendered on the event page.
    """
    events = env["event.event"].with_context(active_test=False).search([])
    if not events:
        return

    languages = env["res.lang"].search([("active", "=", True)])
    if not languages:
        languages = env["res.lang"].browse([env.lang]) if isinstance(env.lang, int) else env["res.lang"]

    # Mark all records initialized first. The source-code field itself is
    # written per language below so existing translations are preserved.
    events.write({"gl_html_description_initialized": True})

    for language in languages:
        localized_events = events.with_context(lang=language.code)
        for event in localized_events:
            event.gl_html_description_code = event.description or ""
