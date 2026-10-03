from markupsafe import Markup

from odoo import api, fields, models


class EventEvent(models.Model):
    _inherit = "event.event"

    gl_html_description_code = fields.Text(
        string="Website-Beschreibung (HTML)",
        translate=True,
        copy=True,
        help=(
            "HTML source rendered on the public event page instead of Odoo's "
            "standard event description."
        ),
    )
    gl_html_description_initialized = fields.Boolean(
        string="HTML-Beschreibung initialisiert",
        default=False,
        copy=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)

        # A newly-created event receives the HTML source that Odoo has already
        # produced for its standard description (including template/onchange
        # content). If the caller explicitly supplied our field, keep it.
        for event, vals in zip(events, vals_list):
            if "gl_html_description_code" in vals:
                if not event.gl_html_description_initialized:
                    event.gl_html_description_initialized = True
                continue

            event.write({
                "gl_html_description_code": event.description or "",
                "gl_html_description_initialized": True,
            })

        return events

    def write(self, vals):
        # Explicitly editing the HTML source makes it authoritative, including
        # when the user intentionally saves an empty value.
        if "gl_html_description_code" in vals and "gl_html_description_initialized" not in vals:
            vals = dict(vals, gl_html_description_initialized=True)
        return super().write(vals)

    def _gl_get_public_description_html(self):
        """Return trusted HTML for the website event description.

        Before initialization (e.g. while installing/upgrading), gracefully
        fall back to Odoo's native description. Once initialized, even an empty
        HTML source is intentional and must remain empty.
        """
        self.ensure_one()
        source = (
            self.gl_html_description_code
            if self.gl_html_description_initialized
            else (self.description or "")
        )
        return Markup(source or "")
