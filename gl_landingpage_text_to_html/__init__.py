from . import models


def post_init_hook(env):
    """One-time copy of existing source texts. Never overwrite existing HTML."""
    Events = env['event.event'].sudo()
    if not Events._gl_get_plain_field_name():
        return
    last_id = 0
    while True:
        batch = Events.search([('id', '>', last_id)], order='id', limit=300)
        if not batch:
            break
        for event in batch:
            if not event.gl_landingpage_html:
                event.with_context(gl_text_to_html_skip_sync=True)._gl_fill_html_from_plain()
        last_id = batch[-1].id
