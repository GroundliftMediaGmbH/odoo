from odoo import api, fields, models


_SYNC_CONTEXT_KEY = "gl_event_html_description_skip_sync"


class EventEvent(models.Model):
    _inherit = "event.event"

    gl_html_description_code = fields.Text(
        string="Website-Beschreibung (HTML-Code)",
        translate=True,
        copy=True,
        help=(
            "HTML source for the public event description. The value is kept "
            "synchronized with Odoo's standard event description so the normal "
            "Odoo website template renders it without a custom QWeb override."
        ),
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        sync_after_create = []

        for incoming_vals in vals_list:
            vals = dict(incoming_vals)
            has_code = "gl_html_description_code" in vals
            has_description = "description" in vals

            if has_code:
                # The dedicated HTML source is authoritative when both values
                # are supplied in the same create call.
                vals["description"] = vals.get("gl_html_description_code") or ""
            elif has_description:
                vals["gl_html_description_code"] = vals.get("description") or ""

            prepared_vals_list.append(vals)
            sync_after_create.append(not has_code and not has_description)

        events = super().create(prepared_vals_list)

        # Some event creation flows can populate the standard description by
        # defaults/templates only after the create values were prepared. Copy
        # that final value into our source field once the record exists.
        for event, needs_sync in zip(events, sync_after_create):
            if needs_sync:
                event._gl_write_code_without_sync(event.description or "")
            else:
                event._gl_resync_code_from_rendered_description()

        return events

    def write(self, vals):
        if self.env.context.get(_SYNC_CONTEXT_KEY):
            return super().write(vals)

        vals = dict(vals)
        has_code = "gl_html_description_code" in vals
        has_description = "description" in vals

        if has_code:
            # HTML source wins if a caller writes both fields at once.
            vals["description"] = vals.get("gl_html_description_code") or ""
        elif has_description:
            # Keep edits made through Odoo's website editor/imports in sync too.
            vals["gl_html_description_code"] = vals.get("description") or ""

        result = super().write(vals)

        # Odoo's Html field may sanitize the value written to `description`.
        # Store that final value back in the code field so the backend always
        # shows exactly what the public website will render.
        if has_code or has_description:
            self._gl_resync_code_from_rendered_description()

        return result

    def _gl_write_code_without_sync(self, value):
        self.ensure_one()
        return super(EventEvent, self.with_context(**{_SYNC_CONTEXT_KEY: True})).write({
            "gl_html_description_code": value or "",
        })

    def _gl_resync_code_from_rendered_description(self):
        for event in self:
            rendered_value = event.description or ""
            if (event.gl_html_description_code or "") != rendered_value:
                event._gl_write_code_without_sync(rendered_value)
